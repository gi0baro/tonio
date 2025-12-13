use pyo3::prelude::*;
use std::cmp::Ordering;

use crate::events::SuspensionData;
use crate::handles::Handle;

pub struct Timer {
    pub(crate) when: u128,
    pub(crate) target: SuspensionData,
}

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
        self.target.0.resume(py, runtime.get(), py.None(), self.target.1);
    }
}
