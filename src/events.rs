use arc_swap::ArcSwapOption;
use pyo3::{IntoPyObjectExt, prelude::*, types::PyList};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex, atomic},
};

use crate::{
    handles::{self, BoxedHandle, Handle},
    runtime::Runtime,
    time::Timer,
};

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub(crate) struct Event {
    flag: atomic::AtomicBool,
    watchers: Mutex<VecDeque<Waker>>,
}

impl Event {
    fn notify(&self, py: Python) {
        let mut guard = self.watchers.lock().unwrap();
        while let Some(waker) = guard.pop_front() {
            waker.wake(py);
        }
    }

    fn unnotify(&self) {
        let guard = self.watchers.lock().unwrap();
        for waker in guard.iter() {
            waker.hold();
        }
    }

    fn add_waker(&self, py: Python, waker: Waker) {
        let mut guard = self.watchers.lock().unwrap();
        if self.flag.load(atomic::Ordering::Acquire) {
            waker.wake(py);
            return;
        }
        guard.push_back(waker);
    }
}

#[pymethods]
impl Event {
    #[new]
    pub(crate) fn new() -> Self {
        Self {
            flag: false.into(),
            watchers: Mutex::new(VecDeque::new()),
        }
    }

    pub(crate) fn set(&self, py: Python) {
        if self
            .flag
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            self.notify(py);
        }
    }

    pub(crate) fn clear(&self) {
        if self
            .flag
            .compare_exchange(true, false, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            self.unnotify();
        }
    }

    pub(crate) fn is_set(&self) -> bool {
        self.flag.load(atomic::Ordering::Acquire)
    }

    // TODO: timeout resolution should be micros!
    fn waiter(pyself: Py<Self>, py: Python, timeout: Option<usize>) -> Py<Waiter> {
        Waiter::from_event(py, pyself, timeout)
    }
}

impl Handle for Py<Event> {
    fn run(&self, py: Python, _runtime: Py<Runtime>, _state: &mut crate::runtime::RuntimeCBHandlerState) {
        self.get().set(py);
    }
}

#[pyclass(frozen, module = "tonio._tonio")]
pub(crate) struct Waiter {
    registered: atomic::AtomicBool,
    cancelled: ArcSwapOption<atomic::AtomicBool>,
    events: Vec<Py<Event>>,
    timeout: Option<usize>,
}

impl Waiter {
    fn from_event(py: Python, event: Py<Event>, timeout: Option<usize>) -> Py<Self> {
        let slf = Self {
            registered: false.into(),
            // cancelled: Mutex::new(None),
            cancelled: None.into(),
            events: vec![event],
            timeout,
        };
        Py::new(py, slf).unwrap()
    }

    pub fn new_for_suspension() -> Self {
        Self {
            registered: false.into(),
            cancelled: Some(Arc::new(false.into())).into(),
            events: vec![],
            timeout: None,
        }
    }

    fn build_sentinel(&self, py: Python) -> Option<Sentinel> {
        match self.events.len() {
            0..1 => None,
            v => Some(Sentinel::new(py, v)),
        }
    }

    fn register(&self, py: Python, runtime: Py<Runtime>, suspension: Arc<Suspension>) {
        if self.events.is_empty() {
            suspension.resume(py, runtime.get(), py.None(), 0);
            return;
        }
        self.cancelled.swap(Some(suspension.cancelled.clone()));
        for (idx, event) in self.events.iter().enumerate() {
            let waker = Waker {
                runtime: runtime.clone_ref(py),
                target: suspension.clone(),
                idx,
            };
            event.get().add_waker(py, waker);
        }
        if let Some(timeout) = self.timeout {
            let when = runtime.get()._get_clock() + (timeout as u128);
            let timer = Timer {
                when,
                target: suspension.clone(),
            };
            runtime.get().add_timer(timer);
        }
    }

    pub(crate) fn register_pygen(
        pyself: Py<Self>,
        py: Python,
        runtime: Py<Runtime>,
        target: SuspensionTarget,
        parent: Option<SuspensionData>,
    ) {
        let rself = pyself.get();
        if rself
            .registered
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            let sentinel = rself.build_sentinel(py);
            let suspension = Suspension::from_pygen(target, parent, sentinel, rself.cancelled.load_full());
            rself.register(py, runtime, suspension);
        } else {
            panic!("Waiter already registered")
        }
    }

    // fn unregister(&self) {}
}

#[pymethods]
impl Waiter {
    #[new]
    #[pyo3(signature = (*events))]
    pub fn new(events: Vec<Py<Event>>) -> Self {
        Self {
            registered: false.into(),
            cancelled: None.into(),
            events,
            timeout: None,
        }
    }

    fn __await__(pyself: Py<Self>) -> Py<Self> {
        // println!("Waiter AWAIT {pyself:?}");
        pyself
    }

    fn __next__(pyself: Py<Self>) -> Option<Py<Self>> {
        match pyself.get().registered.load(atomic::Ordering::Acquire) {
            false => Some(pyself),
            true => None,
        }
    }

    fn send(&self, value: Py<PyAny>) -> PyResult<Py<PyAny>> {
        Err(pyo3::exceptions::PyStopIteration::new_err(value))
    }

    fn throw(&self, value: Bound<PyAny>) -> PyResult<()> {
        let py = value.py();
        let err = PyErr::from_value(value);
        if err.is_instance_of::<crate::errors::CancelledError>(py)
            && let Some(cancelled) = self.cancelled.load().as_ref()
        {
            // println!("waiter cancelled");
            cancelled.store(true, atomic::Ordering::Release);
        }
        Err(err)
    }
}

#[derive(Debug)]
#[pyclass(frozen, module = "tonio._tonio")]
pub(crate) struct ResultHolder {
    size: usize,
    // counter: atomic::AtomicUsize,
    data: Mutex<Vec<Py<PyAny>>>,
}

#[pymethods]
impl ResultHolder {
    #[new]
    #[pyo3(signature = (size = 1))]
    pub fn new(py: Python, size: usize) -> Self {
        let mut data = Vec::with_capacity(size);
        for _ in 0..size {
            data.push(py.None());
        }
        Self {
            size,
            // counter: 0.into(),
            data: Mutex::new(data),
        }
    }

    #[pyo3(signature = (value, index = None))]
    pub fn store(&self, value: Py<PyAny>, index: Option<usize>) {
        let index = index.unwrap_or(0);
        let mut guard = self.data.lock().unwrap();
        // *(&mut guard[..][index]) = value;
        guard[..][index] = value;
        // self.counter.fetch_add(1, atomic::Ordering::Release);
    }

    fn fetch(&self, py: Python) -> Py<PyAny> {
        let guard = self.data.lock().unwrap();
        match self.size {
            1 => guard.first().unwrap().clone_ref(py),
            _ => PyList::new(py, &guard[..]).unwrap().into_py_any(py).unwrap(),
        }
    }

    // fn consumed(&self) -> bool {
    //     self.counter.load(atomic::Ordering::Acquire) >= self.size
    // }
}

pub struct Waker {
    runtime: Py<Runtime>,
    target: Arc<Suspension>,
    idx: usize,
}

impl Waker {
    // fn clone(&self, py: Python) -> Self {
    //     Self {
    //         runtime: self.runtime.clone_ref(py),
    //         target: self.target.clone(),
    //         idx: self.idx,
    //     }
    // }

    pub fn wake(&self, py: Python) {
        // println!("waker called {:?}", self.idx);
        self.target.resume(py, self.runtime.get(), py.None(), self.idx);
    }

    fn hold(&self) {
        self.target.suspend();
    }

    // pub fn abort(&self, py: Python) {
    //     self.target.skip(py, self.runtime.get());
    // }
}

pub(crate) type SuspensionData = (Arc<Suspension>, usize);

#[derive(Debug)]
pub(crate) enum SuspensionTarget {
    Gen(Py<PyAny>),
    GenCtx((Py<PyAny>, Py<PyAny>)),
    AsyncGen(Py<PyAny>),
    AsyncGenCtx((Py<PyAny>, Py<PyAny>)),
}

#[derive(Debug)]
pub(crate) struct Suspension {
    parent: Option<SuspensionData>,
    target: SuspensionTarget,
    consumed: atomic::AtomicBool,
    cancelled: Arc<atomic::AtomicBool>,
    sentinel: Option<Sentinel>,
}

impl Suspension {
    pub(crate) fn from_pygen(
        target: SuspensionTarget,
        parent: Option<SuspensionData>,
        sentinel: Option<Sentinel>,
        cancelled: Option<Arc<atomic::AtomicBool>>,
    ) -> Arc<Self> {
        let cancelled = if let Some(v) = cancelled {
            v
        } else {
            parent
                .as_ref()
                .map_or_else(|| Arc::new(false.into()), |v| v.0.cancelled.clone())
        };
        Self {
            parent,
            target,
            consumed: false.into(),
            cancelled,
            sentinel,
        }
        .into()
    }

    fn to_handle(&self, py: Python, value: Py<PyAny>) -> BoxedHandle {
        match &self.target {
            SuspensionTarget::Gen(target) => {
                let handle = handles::PyGenHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::AsyncGen(target) => {
                let handle = handles::PyAsyncGenHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::GenCtx((target, ctx)) => {
                let handle = handles::PyGenCtxHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::AsyncGenCtx((target, ctx)) => {
                let handle = handles::PyAsyncGenCtxHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
        }
    }

    fn to_throw_handle(&self, py: Python, err: PyErr) -> BoxedHandle {
        let value = err.into_value(py).as_any().clone_ref(py);
        match &self.target {
            SuspensionTarget::Gen(target) => {
                let handle = handles::PyGenThrower {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::AsyncGen(target) => {
                let handle = handles::PyGenThrower {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::GenCtx((target, ctx)) => {
                let handle = handles::PyGenCtxThrower {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::AsyncGenCtx((target, ctx)) => {
                let handle = handles::PyGenCtxThrower {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
        }
    }

    fn suspend(&self) {
        if let Some(sentinel) = &self.sentinel {
            sentinel.increment();
        }
    }

    pub fn resume(&self, py: Python, runtime: &Runtime, value: Py<PyAny>, order: usize) {
        if self.cancelled.load(atomic::Ordering::Acquire) {
            // println!("suspension resume aborted");
            return;
        }
        if let Some(sentinel) = &self.sentinel {
            if let Some(composed_value) = sentinel.decrement(py, (order, value)) {
                // println!("suspension resume call SENTINEL {:?}", composed_value.bind(py));
                runtime.add_handle(self.to_handle(py, composed_value));
            }
            return;
        }
        if self
            .consumed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            runtime.add_handle(self.to_handle(py, value));
        }
    }

    pub fn error(&self, py: Python, runtime: &Runtime, value: PyErr) {
        if let Some(sentinel) = &self.sentinel {
            if sentinel.consume() {
                runtime.add_handle(self.to_throw_handle(py, value));
            }
            return;
        }
        if self
            .consumed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            runtime.add_handle(self.to_throw_handle(py, value));
        }
    }

    // for timeouts
    // fn skip(&self, py: Python, runtime: &Runtime) {
    //     // TODO: add some state checks to avoid `resume` being called after this?
    //     if self.consumed.compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed).is_ok() {
    //         runtime.add_handle(self.to_handle(py, py.None()));
    //     }
    // }
}

#[derive(Debug)]
pub(crate) struct Sentinel {
    counter: atomic::AtomicUsize,
    // results: Mutex<Vec<Py<PyAny>>>,
    res: ResultHolder,
}

impl Sentinel {
    fn new(py: Python, len: usize) -> Self {
        // let mut res = Vec::with_capacity(len);
        // for _ in 0..len {
        //     res.push(py.None());
        // }
        Self {
            counter: len.into(),
            res: ResultHolder::new(py, len),
        }
    }

    fn increment(&self) {
        self.counter.fetch_add(1, atomic::Ordering::Release);
    }

    fn decrement(&self, py: Python, result: (usize, Py<PyAny>)) -> Option<Py<PyAny>> {
        let prev = self.counter.fetch_sub(1, atomic::Ordering::Release);
        if prev == 0 {
            self.counter.fetch_add(1, atomic::Ordering::Release);
            return None;
        }
        if prev >= 1 {
            self.res.store(result.1, Some(result.0));
        }
        if prev == 1 {
            return Some(self.res.fetch(py));
        }
        None
    }

    fn consume(&self) -> bool {
        match self.counter.load(atomic::Ordering::Acquire) {
            0 => false,
            _ => {
                self.counter.store(0, atomic::Ordering::Release);
                true
            }
        }
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Event>()?;
    module.add_class::<Waiter>()?;
    module.add_class::<ResultHolder>()?;

    Ok(())
}
