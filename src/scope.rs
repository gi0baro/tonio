use pyo3::prelude::*;
use std::sync::{Mutex, atomic};

use crate::events::{Event, Waiter};

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct PyGenScope {
    stack: Mutex<Vec<(Py<Waiter>, Py<Event>)>>,
    waiter: Mutex<Option<Py<Waiter>>>,
    consumed: atomic::AtomicU8,
    cancelled: atomic::AtomicBool,
}

#[pymethods]
impl PyGenScope {
    #[new]
    fn new() -> Self {
        Self {
            stack: Mutex::new(Vec::new()),
            waiter: Mutex::new(None),
            consumed: 0.into(),
            cancelled: false.into(),
        }
    }

    fn _incr(&self, from: u8) -> bool {
        self.consumed
            .compare_exchange(from, from + 1, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
    }

    fn _track(&self, pygen: Bound<PyAny>) -> PyResult<Py<PyAny>> {
        if self.consumed.load(atomic::Ordering::Acquire) > 1 {
            return Ok(pygen.py().None());
        }
        let py = pygen.py();
        let event = Py::new(py, Event::new()).unwrap();
        let waiter = Py::new(py, Waiter::new_for_suspension()).unwrap();
        let coro = pygen.call1((event.clone_ref(py), waiter.clone_ref(py)))?.unbind();
        let mut guard = self.stack.lock().unwrap();
        guard.push((waiter, event));
        Ok(coro)
    }

    fn _exit(&self, py: Python) -> PyResult<Py<Waiter>> {
        let mut guard = self.waiter.lock().unwrap();
        if guard.is_some() {
            return Err(pyo3::exceptions::PyRuntimeError::new_err("Scope already consumed"));
        }
        let stack = {
            let mut stack = self.stack.lock().unwrap();
            std::mem::take(&mut *stack)
        };
        let mut events = Vec::with_capacity(stack.len());
        let cancelled = self.cancelled.load(atomic::Ordering::Acquire);
        for (waiter, event) in stack {
            let revent = event.get();
            if cancelled && !revent.is_set() {
                revent.set(py);
                waiter.get().abort_pygen(py);
            }
            events.push(event);
        }
        let waiter = Py::new(py, Waiter::new(events)).unwrap();
        *guard = Some(waiter.clone_ref(py));
        Ok(waiter)
    }

    fn cancel(&self) -> bool {
        self.cancelled
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct PyAsyncGenScope {
    stack: Mutex<Vec<(Py<Waiter>, Py<Event>)>>,
    waiter: Mutex<Option<Py<Waiter>>>,
    consumed: atomic::AtomicU8,
    cancelled: atomic::AtomicBool,
}

#[pymethods]
impl PyAsyncGenScope {
    #[new]
    fn new() -> Self {
        Self {
            stack: Mutex::new(Vec::new()),
            waiter: Mutex::new(None),
            consumed: 0.into(),
            cancelled: false.into(),
        }
    }

    fn _incr(&self, from: u8) -> bool {
        self.consumed
            .compare_exchange(from, from + 1, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
    }

    fn _track(&self, pygen: Bound<PyAny>) -> PyResult<Py<PyAny>> {
        if self.consumed.load(atomic::Ordering::Acquire) > 1 {
            return Ok(pygen.py().None());
        }
        let py = pygen.py();
        let event = Py::new(py, Event::new()).unwrap();
        let waiter = Py::new(py, Waiter::new_for_suspension()).unwrap();
        let coro = pygen.call1((event.clone_ref(py), waiter.clone_ref(py)))?.unbind();
        let mut guard = self.stack.lock().unwrap();
        guard.push((waiter, event));
        Ok(coro)
    }

    fn _exit(&self, py: Python) -> PyResult<Py<Waiter>> {
        let mut guard = self.waiter.lock().unwrap();
        if guard.is_some() {
            return Err(pyo3::exceptions::PyRuntimeError::new_err("Scope already consumed"));
        }
        let stack = {
            let mut stack = self.stack.lock().unwrap();
            std::mem::take(&mut *stack)
        };
        let mut events = Vec::with_capacity(stack.len());
        let cancelled = self.cancelled.load(atomic::Ordering::Acquire);
        for (waiter, event) in stack {
            let revent = event.get();
            if cancelled && !revent.is_set() {
                revent.set(py);
                waiter.get().abort_pyasyncgen(py);
            }
            events.push(event);
        }
        let waiter = Py::new(py, Waiter::new(events)).unwrap();
        *guard = Some(waiter.clone_ref(py));
        Ok(waiter)
    }

    fn cancel(&self) -> bool {
        self.cancelled
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<PyGenScope>()?;
    module.add_class::<PyAsyncGenScope>()?;

    Ok(())
}
