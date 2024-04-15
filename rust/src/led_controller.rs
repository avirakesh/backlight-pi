use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{self, park, JoinHandle},
    time::Duration,
};

use palette::{rgb::Rgb, IntoColor};
use queues::IsQueue;
use rs_ws281x::{ChannelBuilder, Controller, ControllerBuilder};

use crate::{
    common::{SampledColors, SampledColorsQueue},
    user_config::{LedInfo, Side},
};

pub(crate) fn start_led_controller(
    power_on: Arc<AtomicBool>,
    sample_points: Arc<SampledColorsQueue>,
    led_info: LedInfo,
) -> JoinHandle<()> {
    thread::spawn(move || {
        println!("Starting LED Controller Thread...");
        _main_led_thread_loop(power_on, sample_points, led_info);
    })
}

fn _main_led_thread_loop(
    power_on: Arc<AtomicBool>,
    sample_points: Arc<SampledColorsQueue>,
    led_info: LedInfo,
) {
    loop {
        while !power_on.load(Ordering::Relaxed) {
            park();
        }

        let mut led_controller = ControllerBuilder::new()
            .dma(10)
            .channel(
                0,
                ChannelBuilder::new()
                    .pin(led_info.control_pin)
                    .count(led_info.num_leds())
                    .brightness(255 / 2) // 50% brightness
                    .strip_type(rs_ws281x::StripType::Ws2812)
                    .build(),
            )
            .build()
            .unwrap();

        _get_samples_and_draw(
            power_on.clone(),
            sample_points.clone(),
            &mut led_controller,
            &led_info,
        );

        // Above function only returns on power off. See all LEDs to "off"
        let leds = led_controller.leds_mut(0);
        for led in leds {
            *led = [0, 0, 0, 0];
        }
        led_controller.render().unwrap();
    }
}

fn _get_samples_and_draw(
    power_on: Arc<AtomicBool>,
    sampled_colors: Arc<SampledColorsQueue>,
    led_controller: &mut Controller,
    led_info: &LedInfo,
) {
    // let mut start = Instant::now();
    // let mut num_frames: u64 = 0;
    while power_on.load(Ordering::Relaxed) {
        // Grab filled sampled points
        let mut filled_opt: Option<Box<SampledColors>> = Option::None;
        while power_on.load(Ordering::Relaxed) {
            let mut filled_q = sampled_colors.filled_queue.lock().unwrap();
            let filled_res = filled_q.remove();
            if filled_res.is_ok() {
                filled_opt = Some(filled_res.unwrap());
                break;
            }

            let mut wait_timeout = sampled_colors
                .filled_cv
                .wait_timeout(filled_q, Duration::from_millis(30))
                .unwrap();

            let filled_res = wait_timeout.0.remove();
            if filled_res.is_ok() {
                filled_opt = Some(filled_res.unwrap());
                break;
            }
        }

        if filled_opt.is_none() {
            // power off
            break;
        }
        let filled_colors = filled_opt.unwrap();
        _display_colors(led_controller, led_info, &filled_colors);

        {
            // Return the consumed colors
            let mut empty_q = sampled_colors.empty_queue.lock().unwrap();
            empty_q.add(filled_colors).unwrap();
        }
        sampled_colors.empty_cv.notify_all();
        // num_frames += 1;
        // if num_frames % 10 == 0 {
        //     let curr_time = Instant::now();
        //     println!(
        //         "# Frames: {}; Time: {}; Framerate: {}",
        //         num_frames,
        //         (curr_time - start).as_secs_f64(),
        //         num_frames as f64 / (curr_time - start).as_secs_f64(),
        //     );
        //     if num_frames >= 100 {
        //         num_frames = 0;
        //         start = Instant::now();
        //     }
        // }
    }
}

fn _display_colors(
    led_controller: &mut Controller,
    led_info: &LedInfo,
    colors: &Box<SampledColors>,
) {
    let leds = led_controller.leds_mut(0);

    for (led_idx, hsv) in led_info
        .led_idxs
        .get(&Side::TOP)
        .unwrap()
        .iter()
        .zip(colors.top.iter())
    {
        let temp_hsv = *hsv;
        let rgb: Rgb = temp_hsv.into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }

    for (led_idx, hsv) in led_info
        .led_idxs
        .get(&Side::BOTTOM)
        .unwrap()
        .iter()
        .zip(colors.bottom.iter())
    {
        let temp_hsv = *hsv;
        let rgb: Rgb = temp_hsv.into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }
    for (led_idx, hsv) in led_info
        .led_idxs
        .get(&Side::LEFT)
        .unwrap()
        .iter()
        .zip(colors.left.iter())
    {
        let temp_hsv = *hsv;
        let rgb: Rgb = temp_hsv.into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }
    for (led_idx, hsv) in led_info
        .led_idxs
        .get(&Side::RIGHT)
        .unwrap()
        .iter()
        .zip(colors.right.iter())
    {
        let temp_hsv = *hsv;
        let rgb: Rgb = temp_hsv.into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }

    led_controller.render().unwrap();
}
