use std::sync::{Condvar, Mutex};

use palette::Hsv;
use queues::Queue;

#[derive(Debug, Clone)]
pub(crate) struct SampledColors {
    pub(crate) top: Vec<Hsv>,
    pub(crate) bottom: Vec<Hsv>,
    pub(crate) left: Vec<Hsv>,
    pub(crate) right: Vec<Hsv>,
}

#[derive(Debug)]
pub(crate) struct SampledColorsQueue {
    pub(crate) filled_queue: Mutex<Queue<Box<SampledColors>>>,
    pub(crate) filled_cv: Condvar,
    pub(crate) empty_queue: Mutex<Queue<Box<SampledColors>>>,
    pub(crate) empty_cv: Condvar,
}
