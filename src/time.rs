use pyo3::prelude::*;
use std::cmp::Ordering;
use std::sync::Arc;

use crate::events::Suspension;
use crate::handles::Handle;

pub struct Timer {
    pub(crate) when: u128,
    pub(crate) target: Arc<Suspension>,
}

// impl Timer {
//     fn new(target: SuspensionData, when: u128) -> Self {
//         Self {
//             when,
//             target,
//             cancelled: Arc::new(false.into()),
//         }
//     }
// }

impl PartialEq for Timer {
    fn eq(&self, _other: &Self) -> bool {
        false
    }
}

impl Eq for Timer {}

impl PartialOrd for Timer {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Timer {
    fn cmp(&self, other: &Self) -> Ordering {
        if self.when < other.when {
            return Ordering::Greater;
        }
        if self.when > other.when {
            return Ordering::Less;
        }
        Ordering::Equal
    }
}

impl Handle for Timer {
    fn run(
        &self,
        py: Python,
        runtime: Py<crate::runtime::Runtime>,
        _state: &mut crate::runtime::RuntimeCBHandlerState,
    ) {
        self.target.resume(py, runtime.get(), py.None(), 0);
    }
}
