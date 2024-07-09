use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Condvar, Mutex,
    },
    thread,
    time::Duration,
};

use palette::{Hsv, IntoColor, Srgb};
use queues::{IsQueue, Queue};
use rscam::{
    Camera, Config, Frame, CID_AUTO_WHITE_BALANCE, CID_BRIGHTNESS, CID_CONTRAST,
    CID_EXPOSURE_ABSOLUTE, CID_EXPOSURE_AUTO, CID_GAIN, CID_GAMMA, CID_HUE, CID_SATURATION,
    CID_SHARPNESS, CID_WHITE_BALANCE_TEMPERATURE, FIELD_NONE,
};
use turbojpeg::{Decompressor, Image, PixelFormat};

use crate::{
    common::{SampledColors, SampledColorsQueue},
    user_config::{DevicePreference, SampleWindows, KERNEL_SIZE},
};

pub(crate) struct CameraController {
    /**
     * Handle to be unparked when power is turned on.
     * This allows the thread to sleep while power is "off".
     */
    pub(crate) thread_handle: thread::JoinHandle<()>,
    /**
     * Blocking queue that will contain the sampled colors from the frames
     */
    pub(crate) sample_points_queue: Arc<SampledColorsQueue>,
}

/**
 * Simple blocking queue structure to transfer frames from V4L2 camera to the
 * sampler thread.
 * We don't need a queue for empty Frames because Frames going out of scope
 * returns the V4L2 buffer implicitly.
 */
struct V4L2FrameQueue {
    filled_queue: Mutex<Queue<Arc<Frame>>>,
    filled_cv: Condvar,
}

/**
 * Entry point for starting the camera threads.
 */
pub(crate) fn start_camera_controller(
    power_on: Arc<AtomicBool>,
    device: DevicePreference,
    sample_windows: SampleWindows,
) -> CameraController {
    let points_queue = Arc::new(SampledColorsQueue {
        filled_queue: Mutex::new(Queue::new()),
        filled_cv: Condvar::new(),
        empty_queue: Mutex::new(Queue::new()),
        empty_cv: Condvar::new(),
    });

    let device_arc = Arc::new(device);

    let thread_points_queue = points_queue.clone();
    let thread_handle = thread::spawn(move || {
        println!("Starting Camera Threads...");
        _main_camera_controller_loop(power_on, device_arc, sample_windows, thread_points_queue);
    });

    CameraController {
        thread_handle,
        sample_points_queue: points_queue,
    }
}

//////////////////////////// Image Sampler Thread Start ////////////////////////////
/**
 * Does what it says on the tin. Starts another thread to fetch frames from
 * V4L2 camera, and  uses the calling thread to decode V4L2 frames and sample
 * colors from the decoded frames.
 */
fn _main_camera_controller_loop(
    power_on: Arc<AtomicBool>,
    device: Arc<DevicePreference>,
    sample_windows: SampleWindows,
    sampled_colors_queue: Arc<SampledColorsQueue>,
) {
    loop {
        while !power_on.load(Ordering::Relaxed) {
            // power_controller will unpark the thread when power is turned on.
            thread::park_timeout(Duration::from_secs(10));
        }

        let v4l2_queue = Arc::new(V4L2FrameQueue {
            filled_queue: Mutex::new(Queue::new()),
            filled_cv: Condvar::new(),
        });

        let power_on_clone = power_on.clone();
        let v4l2_queue_clone = v4l2_queue.clone();
        let device_clone = device.clone();

        // Thread to get image from the V4L2 camera, and pump them to this
        // thread to be decoded and sampled.
        // Two threads are needed because RPi Zero cannot decode
        // JPEGs at 30fps, and we don't want stale camera frames.
        let v4l2_thread = thread::spawn(move || {
            // println!("Starting V4L2 Thread...");
            _pump_v4l2_frames_from_camera(power_on_clone, device_clone, v4l2_queue_clone);
        });

        _decode_and_pump_sampled_colors(
            power_on.clone(),
            device.clone(),
            &sample_windows,
            v4l2_queue,
            sampled_colors_queue.clone(),
        );

        // Previous function only returns if power_pin was set to off.
        // Wait for v4l2 thread to join
        v4l2_thread.join().unwrap();
    }
}

/**
 * Loop to get frames from v4l2_thread, decode the frame, pick out colors from
 * specific windows, and send the sampled colors to led_controller
 */
fn _decode_and_pump_sampled_colors(
    power_on: Arc<AtomicBool>,
    device: Arc<DevicePreference>,
    sample_windows: &SampleWindows,
    v4l2_queue: Arc<V4L2FrameQueue>,
    sampled_colors_queue: Arc<SampledColorsQueue>,
) {
    {
        // Set up the empty sampled color buffers.
        // led_controller only ever grabs one buffer; the other two are kept to
        // ensure that stale buffers can be recycled in case led_controller
        // takes too long.
        let mut empty_queue = sampled_colors_queue.empty_queue.lock().unwrap();
        for _ in 0..3 {
            let sampled_colors = Box::new(SampledColors {
                top: vec![Hsv::from([0.0, 0.0, 0.0]); sample_windows.top.len()],
                bottom: vec![Hsv::from([0.0, 0.0, 0.0]); sample_windows.bottom.len()],
                left: vec![Hsv::from([0.0, 0.0, 0.0]); sample_windows.left.len()],
                right: vec![Hsv::from([0.0, 0.0, 0.0]); sample_windows.right.len()],
            });
            empty_queue.add(sampled_colors).unwrap();
        }
    } // empty queue mutex scope

    let mut decompressor = Decompressor::new().expect("Could not create JPEG decompressor.");
    // Pre-allocate a buffer to hold decoded rgb buffer.
    let buffer_length_bytes = device.resolution.0 * device.resolution.1 * PixelFormat::RGB.size();
    let mut rgb_buffer = Image {
        pixels: vec![0 as u8; buffer_length_bytes],
        width: device.resolution.0,
        pitch: device.resolution.0 * PixelFormat::RGB.size(),
        height: device.resolution.1,
        format: PixelFormat::RGB,
    };

    // Main decode and pump loop
    while power_on.load(Ordering::Relaxed) {
        // Fetch an empty sampled colors buffer to fill.
        let mut empty_points_opt: Option<Box<SampledColors>> = Option::None;
        while power_on.load(Ordering::Relaxed) {
            let mut empty_points_q = sampled_colors_queue.empty_queue.lock().unwrap();
            let empty_points_res = empty_points_q.remove();

            if empty_points_res.is_ok() {
                empty_points_opt = Option::Some(empty_points_res.unwrap());
                break;
            }
            let mut wait_timeout = sampled_colors_queue
                .empty_cv
                .wait_timeout(empty_points_q, Duration::from_millis(30))
                .unwrap();

            let empty_points_res = wait_timeout.0.remove();
            if empty_points_res.is_ok() {
                empty_points_opt = Option::Some(empty_points_res.unwrap());
                break;
            }
        }

        if empty_points_opt.is_none() {
            // power off
            break;
        }
        let mut empty_points = empty_points_opt.unwrap();

        // Fetch a filled v4l2 frame.
        let mut filled_frame_opt: Option<Arc<Frame>> = Option::None;
        while power_on.load(Ordering::Relaxed) {
            let mut filled_frame_q = v4l2_queue.filled_queue.lock().unwrap();
            let filled_frame_res = filled_frame_q.remove();
            if filled_frame_res.is_ok() {
                filled_frame_opt = Option::Some(filled_frame_res.unwrap());
                break;
            }

            let mut wait_timeout = v4l2_queue
                .filled_cv
                .wait_timeout(filled_frame_q, Duration::from_millis(30))
                .unwrap();

            let filled_frame_res = wait_timeout.0.remove();
            if filled_frame_res.is_ok() {
                filled_frame_opt = Option::Some(filled_frame_res.unwrap());
                break;
            }
        }

        if filled_frame_opt.is_none() {
            // Power off
            break;
        }

        let filled_frame = filled_frame_opt.unwrap();
        // Decode v4l2 frame to RGB
        let temp_rgb = Image {
            pixels: &mut rgb_buffer.pixels[..],
            width: rgb_buffer.width,
            pitch: rgb_buffer.pitch,
            height: rgb_buffer.height,
            format: rgb_buffer.format,
        };
        let decode_res = _decode_v4l2_frame_to_rgb(&filled_frame, &mut decompressor, temp_rgb);
        if decode_res.is_err() {
            // Camera occasionally sends a malformed jpeg. Log and drop.
            println!("Failed to decode image: {}", decode_res.unwrap_err());
            continue;
        }

        // Sample points from the frame and put them in the empty buffer
        _sample_frames(&rgb_buffer, sample_windows, &mut empty_points);

        // One last check before sending the sampled points off!
        if !power_on.load(Ordering::Relaxed) {
            break;
        }

        let mut removed_points_opt: Option<Box<SampledColors>> = Option::None;
        {
            let mut filled_samples_q = sampled_colors_queue.filled_queue.lock().unwrap();
            // Remove any existing sampled color buffer from the queue to give led_controller
            // the most up-to-date sample
            let removed_points_res = filled_samples_q.remove();
            if !removed_points_res.is_err() {
                removed_points_opt = Option::Some(removed_points_res.unwrap());
            }
            // Queue up the latest samples
            filled_samples_q.add(empty_points).unwrap();
        }
        sampled_colors_queue.filled_cv.notify_all();

        if removed_points_opt.is_some() {
            // Re-add to empty queue
            let mut empty_samples_q = sampled_colors_queue.empty_queue.lock().unwrap();
            empty_samples_q.add(removed_points_opt.unwrap()).unwrap();
            // No need to notify, this is the one thread that waits on empty queue
        }
    } // main decode loop
}

/**
 * Decodes a MJPEG frame from V4L2 camera to RGB buffer
 */
fn _decode_v4l2_frame_to_rgb(
    mjpg: &Frame,
    decompressor: &mut Decompressor,
    output_image: Image<&mut [u8]>,
) -> Result<(), String> {
    let decompress = decompressor.decompress(&mjpg[..], output_image);
    if decompress.is_err() {
        return Err(format!("Decompression Failed: {}", decompress.unwrap_err()).to_string());
    }

    let _ = decompress.unwrap();
    Ok(())
}

/**
 * Sample specific windows from the image.
 */
fn _sample_frames(
    image: &Image<Vec<u8>>,
    sample_windows: &SampleWindows,
    output_points: &mut SampledColors,
) {
    for (i, bounds) in sample_windows.top.iter().enumerate() {
        let val = &mut output_points.top[i];
        _calculate_value_for_bounds(image, bounds, sample_windows.kernel, val);
    }

    for (i, bounds) in sample_windows.bottom.iter().enumerate() {
        let val = &mut output_points.bottom[i];
        _calculate_value_for_bounds(image, bounds, sample_windows.kernel, val);
    }

    for (i, bounds) in sample_windows.left.iter().enumerate() {
        let val = &mut output_points.left[i];
        _calculate_value_for_bounds(image, bounds, sample_windows.kernel, val);
    }

    for (i, bounds) in sample_windows.right.iter().enumerate() {
        let val = &mut output_points.right[i];
        _calculate_value_for_bounds(image, bounds, sample_windows.kernel, val);
    }
}

/**
 * Calculate convolution of one point on the image with the given kernel.
 * Assume bounds to be of the size as the convolution kernel.
 */
fn _calculate_value_for_bounds(
    image: &Image<Vec<u8>>,
    bounds: &((usize, usize), (usize, usize)),
    kernel: [[f32; KERNEL_SIZE]; KERNEL_SIZE],
    output: &mut Hsv,
) {
    let pixels = &image.pixels;
    let stride = image.pitch;

    let mut r: f32 = 0.0;
    let mut g: f32 = 0.0;
    let mut b: f32 = 0.0;

    for x in 0..KERNEL_SIZE {
        for y in 0..KERNEL_SIZE {
            let img_coords = (bounds.0 .0 + x, bounds.0 .1 + y);

            let r_idx = _coords_to_idx(&img_coords, stride);
            let g_idx = r_idx + 1;
            let b_idx = r_idx + 2;

            let kernel_val = kernel[y][x];
            r += kernel_val * pixels[r_idx] as f32;
            g += kernel_val * pixels[g_idx] as f32;
            b += kernel_val * pixels[b_idx] as f32;
        }
    }

    let rgb: Srgb<u8> = Srgb::from([r as u8, g as u8, b as u8]);
    let rgb: Srgb = rgb.into_format();
    // Convert color to HSV for easy interpolation.
    *output = rgb.into_color();
}

/**
 * Utility function to convert the conventional (x, y) coordinates to an index in the flat buffer.
 */
fn _coords_to_idx((x, y): &(usize, usize), stride: usize) -> usize {
    let row_idx = y * stride;
    let col_idx = x * PixelFormat::RGB.size();
    row_idx + col_idx
}
//////////////////////////// Image Sampler Thread End ////////////////////////////

//////////////////////////// V4L2 Thread Start ////////////////////////////
/**
 * Main thread loop that opens the V4L2 device, configures it, and pumps frame
 * to the sampler thread.
 */
fn _pump_v4l2_frames_from_camera(
    power_on: Arc<AtomicBool>,
    device: Arc<DevicePreference>,
    v4l2_queue: Arc<V4L2FrameQueue>,
) {
    let mut camera = Camera::new(&device.device_path)
        .expect(format!("Could not open camera {}", device.device_path).as_str());

    _set_v4l2_camera_controls(&mut camera);

    let config = Config {
        interval: (1, 30), // 30fps hardcoded. This may or may not be reasonable for the camera
        resolution: (device.resolution.0 as u32, device.resolution.1 as u32),
        format: b"MJPG",
        field: FIELD_NONE,
        nbuffers: 4,
    };

    camera.start(&config).unwrap();

    // let start = Instant::now();
    // let mut num_frames: u64 = 0;
    while power_on.load(Ordering::Relaxed) {
        let frame = Arc::new(camera.capture().unwrap());
        // println!("Frame fetched.");
        // num_frames += 1;
        {
            let mut filled_v4l2_q = v4l2_queue.filled_queue.lock().unwrap();

            // silently drop any existing frame in filled_v4l2_q. This ensures that there can
            // be at most one queues up frame to be decoded.
            let removed_frame = filled_v4l2_q.remove();
            if removed_frame.is_ok() {
                // println!("Removed an already existing frame.");
            } else {
                // println!("No frame in queue.");
            }
            let _ = filled_v4l2_q.add(frame).unwrap();
        }
        v4l2_queue.filled_cv.notify_all(); // Wake up any thread that
                                           // might be waiting on a new frame.

        // if num_frames % 100 == 0 {
        //     let curr_time = Instant::now();
        //     println!(
        //         "# Frames: {}; Time: {}; Framerate: {}; Length: {}",
        //         num_frames,
        //         (curr_time - start).as_secs_f64(),
        //         num_frames as f64 / (curr_time - start).as_secs_f64(),
        //         frame.len()
        //     );
        // }
    }

    {
        // Power off. Empty queue and exit.
        let mut filled_v4l2_q = v4l2_queue.filled_queue.lock().unwrap();
        loop {
            let remove = filled_v4l2_q.remove();
            if remove.is_err() {
                // Removed all frames.
                break;
            }
            // silently drop the frame (by going out of scope)
        }
    }

    camera.stop().unwrap();
}

/**
 * Simple utility function to set V4L2 controls of the given Camera.
 * These values were determined by trial and error, your results might vary.
 */
fn _set_v4l2_camera_controls(camera: &mut Camera) {
    camera.set_control(CID_BRIGHTNESS, &64).unwrap();
    camera.set_control(CID_CONTRAST, &80).unwrap();
    camera.set_control(CID_SATURATION, &150).unwrap();
    camera.set_control(CID_HUE, &0).unwrap();
    camera.set_control(CID_GAMMA, &100).unwrap();
    camera.set_control(CID_GAIN, &32).unwrap();
    camera.set_control(CID_SHARPNESS, &10).unwrap();

    // Disable auto whitebalance and set whitepoint manually
    // This is needed to prevent the camera from auto whitebalancing,
    // potentially messing the colors.
    camera.set_control(CID_AUTO_WHITE_BALANCE, &0).unwrap();
    camera
        .set_control(CID_WHITE_BALANCE_TEMPERATURE, &4100)
        .unwrap();

    // Disable auto exposure and set an exposure value
    // This is needed to prevent the camera from auto blowing out dark scenes
    // or dimming dark ones.
    camera.set_control(CID_EXPOSURE_AUTO, &1).unwrap();
    camera.set_control(CID_EXPOSURE_ABSOLUTE, &300).unwrap();
}
//////////////////////////// V4L2 Thread End ////////////////////////////
