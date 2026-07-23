use std::{
    os::fd::{AsRawFd, FromRawFd, IntoRawFd, OwnedFd},
    sync::{Arc, Mutex},
};

use pyo3::prelude::*;

use crate::{events::Waiter, io::schedule::ScheduledIO};

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub(crate) struct Fd {
    io: Arc<ScheduledIO>,
    inner: Mutex<Option<OwnedFd>>,
    blocking: bool,
}

#[pymethods]
impl Fd {
    #[new]
    fn new(py: Python, fd: i32) -> PyResult<Self> {
        let blocking = crate::py::os_get_blocking(py, fd)?;
        crate::py::os_set_blocking(py, fd, false)?;

        let inner = unsafe { OwnedFd::from_raw_fd(fd) };
        let runtime = crate::get_runtime(py)?;
        #[allow(clippy::cast_possible_wrap)]
        let io = runtime.get().io_register(fd)?;

        Ok(Self {
            io,
            inner: Mutex::new(Some(inner)),
            blocking,
        })
    }

    #[getter(fd)]
    fn _get_fd(&self) -> i32 {
        self.inner.lock().unwrap().as_ref().map_or(-1, AsRawFd::as_raw_fd)
    }

    fn _drop(&self, py: Python) {
        if let Some(inner) = self.inner.lock().unwrap().take() {
            let fd = inner.into_raw_fd();
            _ = crate::py::os_set_blocking(py, fd, self.blocking);
        }
    }

    #[pyo3(signature = (timeout=None))]
    fn _io_arm_r(&self, py: Python, timeout: Option<usize>) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_r(py, timeout)
    }

    #[pyo3(signature = (timeout=None))]
    fn _io_arm_w(&self, py: Python, timeout: Option<usize>) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_w(py, timeout)
    }

    fn _io_clear_r(&self) {
        self.io.clear_r();
    }

    fn _io_clear_w(&self) {
        self.io.clear_w();
    }

    fn _io_close(&self, py: Python) {
        if let Ok(runtime) = crate::get_runtime(py) {
            runtime.get().io_deregister(&self.io);
        }
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Fd>()?;

    Ok(())
}
