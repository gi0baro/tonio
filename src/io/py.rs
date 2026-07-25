use std::sync::Arc;

use mio::Interest;
use pyo3::prelude::*;

use super::schedule::ScheduledIO;
use crate::events::Waiter;

//: raw-fd registration handle for consumers that perform their own I/O
#[pyclass(frozen, subclass, name = "ScheduledIO", module = "tonio._tonio")]
struct PyScheduledIO {
    io: Arc<ScheduledIO>,
}

#[pymethods]
impl PyScheduledIO {
    #[new]
    fn new(py: Python, fd: i32) -> PyResult<Self> {
        let runtime = crate::get_runtime(py)?;
        let io = runtime.get().io_register(fd, Interest::READABLE | Interest::WRITABLE)?;
        Ok(Self { io })
    }

    #[pyo3(signature = (timeout=None))]
    fn _arm_r(&self, py: Python, timeout: Option<usize>) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_r(py, timeout)
    }

    #[pyo3(signature = (timeout=None))]
    fn _arm_w(&self, py: Python, timeout: Option<usize>) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_w(py, timeout)
    }

    fn consume_r(&self) -> bool {
        self.io.consume_r()
    }

    fn consume_w(&self) -> bool {
        self.io.consume_w()
    }

    fn close(&self, py: Python) {
        if let Ok(runtime) = crate::get_runtime(py) {
            runtime.get().io_deregister(&self.io);
        }
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<PyScheduledIO>()?;

    Ok(())
}
