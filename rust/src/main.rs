mod camera_controller;
mod common;
mod led_controller;
mod power_controller;
mod user_config;

use std::sync::{atomic::AtomicBool, Arc};

use crate::{
    camera_controller::start_camera_controller,
    led_controller::start_led_controller,
    power_controller::monitor_power,
    user_config::{DevicePreference, LedInfo, SampleWindows},
};

fn main() {
    let device_preference = DevicePreference::read();
    let sample_windows = SampleWindows::read(&device_preference.resolution);
    let led_info = LedInfo::read();
    let power_pin = led_info.power_pin as u8;

    // AtomicBool to serve as a sentinel for the power value. Various threads
    // will only run if this value is set to true.
    let power_on = Arc::new(AtomicBool::new(true));

    // Start the camera controller threads.
    let camera_controller =
        start_camera_controller(power_on.clone(), device_preference, sample_windows);

    // Start the LED controller threads.
    let led_thread_handle = start_led_controller(
        power_on.clone(),
        camera_controller.sample_points_queue.clone(),
        led_info,
    );

    // Infinitely poll the GPIO pin for the power value.
    let thread_handles = vec![camera_controller.thread_handle, led_thread_handle];
    monitor_power(power_pin, power_on, thread_handles); // never returns
}
