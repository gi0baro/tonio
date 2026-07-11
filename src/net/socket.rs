use std::sync::{Arc, atomic};

use pyo3::prelude::*;

use crate::{events::Waiter, io::schedule::ScheduledIO};

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub(crate) struct Socket {
    io: Arc<ScheduledIO>,
    #[pyo3(get)]
    _sock: Py<PyAny>,
    _eof: atomic::AtomicBool,
}

#[pymethods]
impl Socket {
    #[new]
    fn new(py: Python, stdlib_sock: Py<PyAny>) -> PyResult<Self> {
        let fd: usize = stdlib_sock.call_method0(py, pyo3::intern!(py, "fileno"))?.extract(py)?;
        stdlib_sock.call_method1(py, pyo3::intern!(py, "setblocking"), (false,))?;

        let runtime = crate::get_runtime(py)?;
        #[allow(clippy::cast_possible_wrap)]
        let io = runtime.get().io_register(fd as i32)?;

        Ok(Self {
            _sock: stdlib_sock,
            _eof: false.into(),
            io,
        })
    }

    fn _eof_get(&self) -> bool {
        self._eof.load(atomic::Ordering::Acquire)
    }

    fn _eof_set(&self) {
        self._eof.store(true, atomic::Ordering::Release);
    }

    fn _io_arm_r(&self, py: Python) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_r(py)
    }

    fn _io_arm_w(&self, py: Python) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_w(py)
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
