use std::{
    collections::HashMap,
    f32::consts::{E, PI},
    fs::read_to_string,
    path::Path,
};

use json::JsonValue;

pub(crate) const KERNEL_SIZE: usize = 5;

const CONFIG_PATH: &str = "./config";
const DEVICE_PREFS_FILE: &str = "v4l2_device.txt";
const RESOLUTION_FILE: &str = "resolution.txt";
const LED_FILE: &str = "led.json";
const SAMPLE_POINTS_FILE: &str = "sample_points.json";

#[derive(Debug)]
pub(crate) struct DevicePreference {
    pub(crate) device_path: String,
    pub(crate) resolution: (usize, usize), // (width, height)
}

#[derive(Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Clone, Copy)]
pub(crate) enum Side {
    TOP,
    LEFT,
    BOTTOM,
    RIGHT,
}

#[derive(Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(crate) struct LedSideInfo {
    pub(crate) is_orientation_natural: bool,
    pub(crate) count: usize,
}

#[derive(Debug)]
pub(crate) struct SampleWindows {
    /**
     * Each field is a vector of rectangles where the each rectangle is encoded as
     * as pair of coordinates:
     * ((top_left_x, top_left_y), (bottom_right_x, bottom_right_y)) all inclusive
     */
    pub(crate) top: Vec<((usize, usize), (usize, usize))>,
    pub(crate) left: Vec<((usize, usize), (usize, usize))>,
    pub(crate) bottom: Vec<((usize, usize), (usize, usize))>,
    pub(crate) right: Vec<((usize, usize), (usize, usize))>,
    /**
     * Gaussian Kernel for blurring
     */
    pub(crate) kernel: [[f32; KERNEL_SIZE]; KERNEL_SIZE],
}

#[derive(Debug)]
pub(crate) struct LedInfo {
    pub(crate) control_pin: i32,
    pub(crate) power_pin: i32,
    pub(crate) led_idxs: HashMap<Side, Vec<usize>>,
}

///////////////////
// Implementations
///////////////////
impl DevicePreference {
    pub(crate) fn read() -> Self {
        let device_path = Path::new(CONFIG_PATH).join(DEVICE_PREFS_FILE);
        let device_txt = read_to_string(&device_path)
            .expect(format!("Could not read {}", device_path.to_str().unwrap()).as_str());

        let resolution_path = Path::new(CONFIG_PATH).join(RESOLUTION_FILE);
        let resolution_txt = read_to_string(&resolution_path)
            .expect(format!("Could not open file {}", resolution_path.to_str().unwrap()).as_str());
        let resolution_split = resolution_txt.split_whitespace();
        let resolution_parts: Vec<&str> = resolution_split.collect();
        if resolution_parts.len() != 2 {
            panic!(
                "Resolution Text could not be parsed. Resolution:\n{}",
                resolution_txt
            );
        }

        return Self {
            device_path: String::from(device_txt.trim()),
            resolution: (
                resolution_parts[0].trim().parse().unwrap(),
                resolution_parts[1].trim().parse().unwrap(),
            ),
        };
    }
}

impl SampleWindows {
    pub(crate) fn read(image_size: &(usize, usize)) -> Self {
        let sample_points_path = Path::new(CONFIG_PATH).join(SAMPLE_POINTS_FILE);
        let sample_points_raw = read_to_string(&sample_points_path).expect(
            format!(
                "Could not read file {}",
                sample_points_path.to_str().unwrap()
            )
            .as_str(),
        );

        let sample_points_json = json::parse(sample_points_raw.as_str()).expect(
            format!(
                "Could not parse {} as json.",
                sample_points_path.to_str().unwrap()
            )
            .as_str(),
        );

        let top_json = &sample_points_json["top"];
        let top = SampleWindows::_parse_window_from_json(top_json, image_size);
        // println!("Top: {:?}", top);

        let bottom_json = &sample_points_json["bottom"];
        let bottom = SampleWindows::_parse_window_from_json(bottom_json, image_size);
        // println!("Bottom: {:?}", bottom);

        let left_json = &sample_points_json["left"];
        let left = SampleWindows::_parse_window_from_json(left_json, image_size);
        // println!("Left: {:?}", left);

        let right_json = &sample_points_json["right"];
        let right = SampleWindows::_parse_window_from_json(right_json, image_size);
        // println!("Right: {:?}", right);

        Self {
            top: top,
            left: left,
            bottom: bottom,
            right: right,
            kernel: SampleWindows::_generate_gaussian_kernel(),
        }
    }

    fn _parse_window_from_json(
        json_value: &JsonValue,
        image_size: &(usize, usize),
    ) -> Vec<((usize, usize), (usize, usize))> {
        let mut ret: Vec<((usize, usize), (usize, usize))> = Vec::new();

        for val in json_value.members() {
            let coords_raw: Vec<&JsonValue> = val.members().collect();
            let point_x = coords_raw[0].as_i32().unwrap();
            let point_y = coords_raw[1].as_i32().unwrap();

            let radius = KERNEL_SIZE as i32 / 2;

            // Cast to i32 so we can have negative values
            let mut window_top_left_x = point_x - radius;
            let mut window_top_left_y = point_y - radius;

            let mut window_bottom_right_x = point_x + radius;
            let mut window_bottom_right_y = point_y + radius;

            // Note we're assuming that the Kernel can fit entirely
            // into the image. If not, good luck!
            if window_top_left_x < 0 {
                window_top_left_x = 0;
                window_bottom_right_x = KERNEL_SIZE as i32;
            } else if window_bottom_right_x > image_size.0 as i32 {
                window_top_left_x = (image_size.0 - KERNEL_SIZE) as i32;
                window_bottom_right_x = image_size.0 as i32;
            }

            if window_top_left_y < 0 {
                window_top_left_y = 0;
                window_bottom_right_y = KERNEL_SIZE as i32;
            } else if window_bottom_right_y > image_size.1 as i32 {
                window_top_left_y = (image_size.1 - KERNEL_SIZE) as i32;
                window_bottom_right_y = image_size.1 as i32;
            }

            let window = (
                (window_top_left_x as usize, window_top_left_y as usize),
                (
                    window_bottom_right_x as usize,
                    window_bottom_right_y as usize,
                ),
            );

            ret.push(window);
        }
        ret
    }

    fn _generate_gaussian_kernel() -> [[f32; KERNEL_SIZE]; KERNEL_SIZE] {
        const SIGMA: f32 = 1.0;
        let radius = KERNEL_SIZE as i32 / 2;

        let mut ret = [[0 as f32; KERNEL_SIZE]; KERNEL_SIZE];

        for i in (-radius)..(radius + 1) {
            for j in (-radius)..(radius + 1) {
                let exponent = -(((i as f32).powi(2) + (j as f32).powi(2)) / (2.0 * SIGMA.powi(2)));
                let val = (1.0 / (2.0 * PI * SIGMA.powi(2))) * E.powf(exponent);
                ret[(i + radius) as usize][(j + radius) as usize] = val;
            }
        }

        // Normalize the kernel so the convolution stays within bounds.
        let mut sum = 0.0;
        for i in ret {
            for j in i {
                sum += j;
            }
        }

        for row in ret.iter_mut() {
            for val in row.iter_mut() {
                *val = *val / sum;
            }
        }

        ret
    }
}

impl Side {
    fn as_str(&self) -> &str {
        match self {
            Side::TOP => "top",
            Side::LEFT => "left",
            Side::BOTTOM => "bottom",
            Side::RIGHT => "right",
        }
    }

    fn from_str(side: &str) -> Self {
        match side {
            "top" => Self::TOP,
            "bottom" => Self::BOTTOM,
            "left" => Self::LEFT,
            "right" => Self::RIGHT,
            _ => panic!("Invalid String for Side '{}'", side),
        }
    }
}

impl LedSideInfo {
    fn from(led_json: &JsonValue, side: Side) -> Self {
        let count = led_json["counts"][side.as_str()].as_usize().unwrap();
        let is_orientation_natural = led_json["orientation"][side.as_str()].as_bool().unwrap();
        Self {
            is_orientation_natural,
            count,
        }
    }
}

impl LedInfo {
    pub(crate) fn read() -> Self {
        let led_path = Path::new(CONFIG_PATH).join(LED_FILE);
        let led_raw = read_to_string(&led_path)
            .expect(format!("Could not read file {}", led_path.to_str().unwrap()).as_str());

        let led_json = json::parse(&led_raw)
            .expect(format!("Could not parse {} as JSON", led_path.to_str().unwrap()).as_str());
        // println!("{:?}", led_json);

        let mut order: Vec<Side> = Vec::new();
        let order_json = &led_json["order"];
        for side in order_json.members() {
            order.push(Side::from_str(side.as_str().unwrap()));
        }

        let mut side_info: HashMap<Side, LedSideInfo> = HashMap::new();
        side_info.insert(Side::TOP, LedSideInfo::from(&led_json, Side::TOP));
        side_info.insert(Side::LEFT, LedSideInfo::from(&led_json, Side::LEFT));
        side_info.insert(Side::BOTTOM, LedSideInfo::from(&led_json, Side::BOTTOM));
        side_info.insert(Side::RIGHT, LedSideInfo::from(&led_json, Side::RIGHT));

        let mut num_leds_seen: usize = 0;
        let mut led_idxs: HashMap<Side, Vec<usize>> = HashMap::new();
        for side in &order {
            let info = side_info.get(side).unwrap();
            let mut idxs: Vec<usize> = Vec::new();
            for i in num_leds_seen..num_leds_seen + info.count {
                idxs.push(i);
            }

            if !info.is_orientation_natural {
                idxs.reverse();
            }

            led_idxs.insert(side.to_owned(), idxs);
            num_leds_seen += info.count;
        }

        Self {
            control_pin: led_json["pin"].as_i32().unwrap(),
            power_pin: led_json["power_pin"].as_i32().unwrap(),
            led_idxs: led_idxs,
        }
    }

    pub(crate) fn num_leds(&self) -> i32 {
        let mut total_count: usize = 0;
        for (_, idxs) in &self.led_idxs {
            total_count += idxs.len();
        }
        total_count as i32
    }
}
