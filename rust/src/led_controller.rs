use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{self, park, JoinHandle},
    time::Duration,
};

use palette::{rgb::Rgb, Hsv, IntoColor, MixAssign};
use queues::IsQueue;
use rs_ws281x::{ChannelBuilder, Controller, ControllerBuilder};

use crate::{
    common::{SampledColors, SampledColorsQueue},
    user_config::{LedInfo, Side},
};

/**
 * Entry point for start LED controller thread. Returns the thread's handle
 * which must be unparked when power turns "on".
 */
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

/**
 * Does what it says on the tin. Fetches filled sampled color buffers and
 * updates the LED with the sampled colors.
 */
fn _main_led_thread_loop(
    power_on: Arc<AtomicBool>,
    sample_points: Arc<SampledColorsQueue>,
    led_info: LedInfo,
) {
    loop {
        while !power_on.load(Ordering::Relaxed) {
            // Efficiently wait for power to be turned on.
            park();
        }

        // Setup the LED Controller object.
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

        // Kick off the sample fetching and rendering loop.
        _get_samples_and_draw(
            power_on.clone(),
            sample_points.clone(),
            &mut led_controller,
            &led_info,
        );

        // Above function only returns on power off. Set all LEDs to "off"
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
    // Track the current values of the LEDs
    let mut current_colors = SampledColors {
        top: vec![Hsv::from([0.0, 0.0, 0.0]); led_info.led_idxs.get(&Side::TOP).unwrap().len()],
        bottom: vec![
            Hsv::from([0.0, 0.0, 0.0]);
            led_info.led_idxs.get(&Side::BOTTOM).unwrap().len()
        ],
        left: vec![Hsv::from([0.0, 0.0, 0.0]); led_info.led_idxs.get(&Side::LEFT).unwrap().len()],
        right: vec![Hsv::from([0.0, 0.0, 0.0]); led_info.led_idxs.get(&Side::RIGHT).unwrap().len()],
    };

    // Tracks the colors we're trying to get to
    let mut target_colors = current_colors.clone();

    // Number of iterations to try and get to target colors
    let mut iter_num: u32 = 1;
    const MAX_ITERS: u32 = 31;

    // let mut start = std::time::Instant::now();
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

            // Do not wait if we might still be transitioning to the target color
            if iter_num < MAX_ITERS {
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

        // Either power is off, or we're transitioning to target color.
        // Either way render the target colors.
        // If power is off, the loop will break after the render.
        if filled_opt.is_none() {
            iter_num += 1;
            _display_colors(
                led_controller,
                led_info,
                &mut current_colors,
                &target_colors,
                iter_num,
                MAX_ITERS
            );
            continue;
        }

        // Make a copy of the filled sampled colors buffer.
        let filled_colors = filled_opt.unwrap();
        target_colors = *filled_colors.clone();

        {
            // Return the consumed colors to camera_controller
            let mut empty_q = sampled_colors.empty_queue.lock().unwrap();
            empty_q.add(filled_colors).unwrap();
        }
        sampled_colors.empty_cv.notify_all();

        // New target_colors found. Reset num_iters, and display the colors
        iter_num = 1;
        _display_colors(
            led_controller,
            led_info,
            &mut current_colors,
            &target_colors,
            iter_num,
            MAX_ITERS
        );

        // num_frames += 1;
        // if num_frames % 10 == 0 {
        //     let curr_time = std::time::Instant::now();
        //     println!(
        //         "# Frames: {}; Time: {}; Framerate: {}",
        //         num_frames,
        //         (curr_time - start).as_secs_f64(),
        //         num_frames as f64 / (curr_time - start).as_secs_f64(),
        //     );
        //     if num_frames >= 100 {
        //         num_frames = 0;
        //         start = std::time::Instant::now();
        //     }
        // }
    }
}

/**
 * Set LED Colors. It interpolates colors between current_colors and
 * target_colors for each LED. The new colors of the LED are set in
 * current_colors.
 *
 * Must be called repeatedly with the same current and
 * target colors to transition to colors fully.
 */
fn _display_colors(
    led_controller: &mut Controller,
    led_info: &LedInfo,
    current_colors: &mut SampledColors,
    target_colors: &SampledColors,
    iter_num: u32,
    target_iter_num: u32
) {
    let target_iter_num: f32 = target_iter_num as f32;
    let iter_num: f32 = iter_num as f32;
    // We want to linearly transition in TRANSITION_ITER_TARGET iterations
    if iter_num <= 0.0 || iter_num as f32 > target_iter_num {
        return;
    }

    // Absolute normalized point of current_color. This is normalized between
    // target_colors and some theoretical starting color (which would have been)
    // the value of current_colors at iter_num = 1
    let prev_norm_step: f32 = (iter_num - 1.0) / target_iter_num;
    // Absolute normalized point where the next color should be. This is
    // normalized between some unknown starting color and the target color.
    let curr_norm_step: f32 = iter_num / target_iter_num;

    // Factor by which current color in this step. This is simply the curr_norm_step
    // normalized between prev_norm_step and 1.
    let interpolation_factor = (curr_norm_step - prev_norm_step) / (1.0 - prev_norm_step);

    let leds = led_controller.leds_mut(0);

    for ((led_idx, current_color), target_color) in led_info
        .led_idxs
        .get(&Side::TOP)
        .unwrap()
        .iter()
        .zip(current_colors.top.iter_mut())
        .zip(target_colors.top.iter())
    {
        // Calculate an interpolated value in HSV space.
        current_color.mix_assign(*target_color, interpolation_factor);
        // Slightly weird transformation of interpolated color to RGB colorspace
        let rgb: Rgb = (*current_color).into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        // Update the LED with the interpolated color
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }

    for ((led_idx, current_color), target_color) in led_info
        .led_idxs
        .get(&Side::BOTTOM)
        .unwrap()
        .iter()
        .zip(current_colors.bottom.iter_mut())
        .zip(target_colors.bottom.iter())
    {
        // Calculate an interpolated value in HSV space.
        current_color.mix_assign(*target_color, interpolation_factor);
        // Slightly weird transformation of interpolated color to RGB colorspace
        let rgb: Rgb = (*current_color).into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        // Update the LED with the interpolated color
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }

    for ((led_idx, current_color), target_color) in led_info
        .led_idxs
        .get(&Side::LEFT)
        .unwrap()
        .iter()
        .zip(current_colors.left.iter_mut())
        .zip(target_colors.left.iter())
    {
        // Calculate an interpolated value in HSV space.
        current_color.mix_assign(*target_color, interpolation_factor);
        // Slightly weird transformation of interpolated color to RGB colorspace
        let rgb: Rgb = (*current_color).into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        // Update the LED with the interpolated color
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }

    for ((led_idx, current_color), target_color) in led_info
        .led_idxs
        .get(&Side::RIGHT)
        .unwrap()
        .iter()
        .zip(current_colors.right.iter_mut())
        .zip(target_colors.right.iter())
    {
        // Calculate an interpolated value in HSV space.
        current_color.mix_assign(*target_color, interpolation_factor);
        // Slightly weird transformation of interpolated color to RGB colorspace
        let rgb: Rgb = (*current_color).into_color();
        let rgb_u8 = rgb.into_format::<u8>();
        // Update the LED with the interpolated color
        leds[*led_idx] = [rgb_u8.blue, rgb_u8.green, rgb_u8.red, 0];
    }

    led_controller.render().unwrap();
}
