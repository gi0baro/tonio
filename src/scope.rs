use pyo3::prelude::*;
use std::sync::{Mutex, atomic};

use crate::events::{Event, Waiter};

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct Scope {
    stack: Mutex<Vec<(Py<PyAny>, Py<Event>)>>,
    waiter: Mutex<Option<Py<Waiter>>>,
    consumed: atomic::AtomicBool,
    cancelled: atomic::AtomicBool,
}

#[pymethods]
impl Scope {
    #[new]
    fn new() -> Self {
        Self {
            stack: Mutex::new(Vec::new()),
            waiter: Mutex::new(None),
            consumed: false.into(),
            cancelled: false.into(),
        }
    }

    fn _consume(&self) -> bool {
        self.consumed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
    }

    fn _track_pygen(&self, pygen: Bound<PyAny>) -> PyResult<Py<PyAny>> {
        if self.cancelled.load(atomic::Ordering::Acquire) {
            return Ok(pygen.py().None());
        }
        let py = pygen.py();
        let event = Py::new(py, Event::new()).unwrap();
        let waiter = Waiter::new_for_suspension();
        let coro = pygen.call1((event.clone_ref(py), waiter))?.unbind();
        let mut guard = self.stack.lock().unwrap();
        guard.push((coro.clone_ref(py), event));
        Ok(coro)
    }

    fn _track_pyasyncgen(&self, pygen: Bound<PyAny>) -> PyResult<Py<PyAny>> {
        if self.cancelled.load(atomic::Ordering::Acquire) {
            return Ok(pygen.py().None());
        }
        let py = pygen.py();
        let event = Py::new(py, Event::new()).unwrap();
        let coro = pygen.call1((event.clone_ref(py),))?.unbind();
        let mut guard = self.stack.lock().unwrap();
        guard.push((coro.clone_ref(py), event));
        Ok(coro)
    }

    fn _stack(&self, py: Python) -> PyResult<(Py<Waiter>, Vec<Py<PyAny>>)> {
        let mut guard = self.waiter.lock().unwrap();
        if guard.is_some() {
            return Err(pyo3::exceptions::PyRuntimeError::new_err("Scope already consumed"));
        }
        let mut stack = self.stack.lock().unwrap();
        let stack = std::mem::take(&mut *stack);
        let mut coros = Vec::with_capacity(stack.len());
        let mut events = Vec::with_capacity(stack.len());
        let cancelled = self.cancelled.load(atomic::Ordering::Acquire);
        for (coro, event) in stack {
            let revent = event.get();
            if cancelled && !revent.is_set() {
                revent.set(py);
                coros.push(coro);
            }
            events.push(event);
        }
        let waiter = Py::new(py, Waiter::new(events)).unwrap();
        *guard = Some(waiter.clone_ref(py));
        Ok((waiter, coros))
    }

    fn cancel(&self) -> bool {
        self.cancelled
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Scope>()?;

    Ok(())
}
