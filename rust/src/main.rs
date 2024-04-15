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
    // println!("{:?}", device_preference);
    // println!("");
    let sample_windows = SampleWindows::read(&device_preference.resolution);
    // println!("{:?}", sample_points);
    // println!("");
    let led_info = LedInfo::read();
    let power_pin = led_info.power_pin as u8;
    // println!("{:?}", led_info);

    // run_camera_encode_loop(device_preference, sample_points);
    // test_leds(led_info);

    let power_on = Arc::new(AtomicBool::new(true));
    // let test = Mutex::new(Arc::new(false));

    let camera_controller =
        start_camera_controller(power_on.clone(), device_preference, sample_windows);

    let led_thread_handle = start_led_controller(
        power_on.clone(),
        camera_controller.sample_points_queue.clone(),
        led_info,
    );

    let thread_handles = vec![camera_controller.thread_handle, led_thread_handle];
    monitor_power(power_pin, power_on, thread_handles); // never returns
}
