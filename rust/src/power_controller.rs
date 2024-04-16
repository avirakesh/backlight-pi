use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::JoinHandle,
    time::Duration,
};

use rppal::gpio::{Gpio, Level, Trigger};

/**
 * Monitors the power_pin for HIGH and LOW values, updates power_on,
 * and unparks thread_handles when the value of power_on changes.
 */
pub(crate) fn monitor_power(
    power_pin: u8,
    power_on: Arc<AtomicBool>,
    thread_handles: Vec<JoinHandle<()>>,
) {
    // Set up the GPIO Pin as input
    let mut input_pin = Gpio::new()
        .unwrap()
        .get(power_pin as u8)
        .unwrap()
        .into_input();
    // Set an interrupt for both HIGH and LOW.
    // LOW = Power OFF
    // HIGH = POWER ON
    input_pin.set_interrupt(Trigger::Both).unwrap();

    // Read the initial value so the various threads can start out in
    // a consistent state.
    let read = input_pin.read();
    power_on.store(
        match read {
            Level::Low => false,
            Level::High => true,
        },
        Ordering::Relaxed,
    );

    // unpark all threads just in case they need to come up.
    for handle in &thread_handles {
        handle.thread().unpark();
    }

    loop {
        // Poll with 10s timeout to prevent the thread for being de-prioritized
        // too much. Not sure if this actually helps :/
        let poll_result = input_pin.poll_interrupt(false, Option::Some(Duration::from_secs(10)));
        if poll_result.is_err() {
            panic!("Failed to poll for interrupt.");
        }

        let level_opt = poll_result.unwrap();
        if level_opt.is_none() {
            // no value means the poll timed out.
            continue;
        }

        let power = match level_opt.unwrap() {
            Level::Low => false,
            Level::High => true,
        };
        power_on.store(power, Ordering::Relaxed);
        for handle in &thread_handles {
            handle.thread().unpark();
        }
    }
}
