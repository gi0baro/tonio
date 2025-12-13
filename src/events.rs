use pyo3::{IntoPyObjectExt, prelude::*, types::PyList};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex, atomic},
};

use crate::{
    handles::{BoxedHandle, Handle, PyAsyncGenHandle, PyGenHandle, PyGenThrower},
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
        // println!("event notify {:?}", guard.len());
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
        // println!("event got waker");
        if self.flag.load(atomic::Ordering::Acquire) {
            // println!("direct wake call");
            waker.wake(py);
            return;
        }
        let mut guard = self.watchers.lock().unwrap();
        guard.push_back(waker);
        // println!("event stored waker");
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
        // println!("event set called");
        if self
            .flag
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            self.notify(py);
        }
    }

    fn clear(&self) {
        if self
            .flag
            .compare_exchange(true, false, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            self.unnotify();
        }
    }

    fn is_set(&self) -> bool {
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

// #[repr(u8)]
// enum WaiterState {
//     Inited = 0,
//     Registered = 1,
//     Notified = 2,
//     Done = 3,
// }

// TO HANDLE TIMEOUTS: we need timers to capture waker. Once the timer gets called,
// it should call the waker, that should call the `skip` method of suspend.
// => Waker should probably be wrapped in Arc
#[pyclass(frozen, module = "tonio._tonio")]
pub(crate) struct Waiter {
    // state: atomic::AtomicU8,
    registered: atomic::AtomicBool,
    // TODO: support multiple events
    // event: Py<Event>,
    events: Vec<Py<Event>>,
    // TODO: actually handle timeout and relative abort
    timeout: Option<usize>,
}

impl Waiter {
    fn from_event(py: Python, event: Py<Event>, timeout: Option<usize>) -> Py<Self> {
        let slf = Self {
            registered: false.into(),
            events: vec![event],
            // state: (WaiterState::Inited as u8).into(),
            timeout,
        };
        Py::new(py, slf).unwrap()
    }

    fn build_sentinel(&self, py: Python) -> Option<Sentinel> {
        match self.events.len() {
            1 => None,
            v => Some(Sentinel::new(py, v)),
        }
    }

    fn register(&self, py: Python, runtime: Py<Runtime>, suspension: Arc<Suspension>) {
        for (idx, event) in self.events.iter().enumerate() {
            let waker = Waker {
                runtime: runtime.clone_ref(py),
                target: suspension.clone(),
                idx,
            };
            if let Some(timeout) = self.timeout {
                // create timer
                let when = runtime.get()._get_clock() + (timeout as u128);
                let timer = Timer {
                    when,
                    target: (suspension.clone(), idx),
                };
                runtime.get().add_timer(timer);
            }
            event.get().add_waker(py, waker);
        }
    }

    // THIS SHOULD BE CALLED ONLY BY LOOP, CREATE AN INSTANCE OF A NEW OBJ
    pub(crate) fn register_pygen(pyself: Py<Self>, py: Python, runtime: Py<Runtime>, parent: &PyGenHandle) {
        // println!("waiter registered");
        // self.event.get().add_waiter(waiter);
        // CREATE WAKER:
        //  - if timeout, it's also a timer
        //  - event needs to track reference and call the wakers
        //  HOW DO WE KEEP LOOP REF IN WAKER?
        let rself = pyself.get();
        // if rself
        //     .state
        //     .compare_exchange(
        //         WaiterState::Inited as u8,
        //         WaiterState::Registered as u8,
        //         atomic::Ordering::Release,
        //         atomic::Ordering::Relaxed,
        //     )
        //     .is_ok()
        // {
        if rself
            .registered
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            // let waiter = Waiter { stack: parent.stack.as_ref().map(|v| v.clone_ref(py)), parent: parent.coro.clone_ref(py) };
            // let waker = Waker { runtime, waiter };
            let sentinel = rself.build_sentinel(py);
            let suspension = Suspension::from_pygen(py, parent, sentinel);
            rself.register(py, runtime, suspension);
        } else {
            panic!()
        }
    }

    pub(crate) fn register_pyasyncgen(pyself: Py<Self>, py: Python, runtime: Py<Runtime>, parent: &PyAsyncGenHandle) {
        let rself = pyself.get();
        // if rself
        //     .state
        //     .compare_exchange(
        //         WaiterState::Inited as u8,
        //         WaiterState::Registered as u8,
        //         atomic::Ordering::Release,
        //         atomic::Ordering::Relaxed,
        //     )
        //     .is_ok()
        // {
        if rself
            .registered
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            let sentinel = rself.build_sentinel(py);
            let suspension = Suspension::from_pyasyncgen(py, parent, sentinel);
            rself.register(py, runtime, suspension);
        } else {
            panic!()
        }
    }

    // fn unregister(&self) {}
}

#[pymethods]
impl Waiter {
    #[new]
    #[pyo3(signature = (*events))]
    fn new(events: Vec<Py<Event>>) -> Self {
        Self {
            registered: false.into(),
            events,
            // state: (WaiterState::Inited as u8).into(),
            timeout: None,
        }
    }

    fn __await__(pyself: Py<Self>) -> Py<Self> {
        pyself
    }

    fn __next__(pyself: Py<Self>) -> Option<Py<Self>> {
        // match pyself.get().state.load(atomic::Ordering::Acquire) {
        //     0 => Some(pyself),
        //     _ => None,
        // }
        match pyself.get().registered.load(atomic::Ordering::Acquire) {
            false => Some(pyself),
            true => None,
        }
    }
}

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

enum SuspensionTarget {
    PyGen(Py<PyAny>),
    PyAsyncGen(Py<PyAny>),
}

// impl SuspensionTarget {
//     fn clone_ref(&self, py: Python) -> Py<PyAny> {
//         match self {
//             Self::PyGen(v) => v.clone_ref(py),
//             Self::PyAsyncGen(v) => v.clone_ref(py),
//         }
//     }
// }

pub(crate) struct Suspension {
    parent: Option<SuspensionData>,
    target: SuspensionTarget,
    consumed: atomic::AtomicBool,
    sentinel: Option<Sentinel>,
}

impl Suspension {
    pub(crate) fn from_pygen(py: Python, coro_handle: &PyGenHandle, sentinel: Option<Sentinel>) -> Arc<Self> {
        Self {
            parent: coro_handle.parent.clone(),
            target: SuspensionTarget::PyGen(coro_handle.coro.clone_ref(py)),
            consumed: false.into(),
            sentinel,
        }
        .into()
    }

    pub(crate) fn from_pyasyncgen(py: Python, handle: &PyAsyncGenHandle, sentinel: Option<Sentinel>) -> Arc<Self> {
        Self {
            parent: handle.parent.clone(),
            target: SuspensionTarget::PyAsyncGen(handle.coro.clone_ref(py)),
            consumed: false.into(),
            sentinel,
        }
        .into()
    }

    fn to_handle(&self, py: Python, value: Py<PyAny>) -> BoxedHandle {
        match &self.target {
            SuspensionTarget::PyGen(target) => {
                // println!("suspension resume {:?}", target.bind(py));
                let handle = PyGenHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::PyAsyncGen(target) => {
                let handle = PyAsyncGenHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
        }
    }

    fn to_throw_handle(&self, py: Python, err: PyErr) -> BoxedHandle {
        let value = err.into_value(py).as_any().clone_ref(py);
        match &self.target {
            SuspensionTarget::PyGen(target) => {
                // println!("suspension throw {:?}", target.bind(py));
                let handle = PyGenThrower {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::PyAsyncGen(_) => panic!(),
        }
    }

    fn suspend(&self) {
        if let Some(sentinel) = &self.sentinel {
            sentinel.increment();
        }
    }

    pub fn resume(&self, py: Python, runtime: &Runtime, value: Py<PyAny>, order: usize) {
        // println!("suspension resume call {:?}", value.bind(py));
        if let Some(sentinel) = &self.sentinel {
            if let Some(composed_value) = sentinel.decrement(py, (order, value)) {
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
