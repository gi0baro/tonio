use pyo3::{IntoPyObjectExt, prelude::*, types::PyList};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex, atomic},
};

use crate::{
    errors::abort,
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
    #[inline]
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

    #[inline]
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
    #[inline]
    fn run(&self, py: Python, _runtime: Py<Runtime>, _state: &mut crate::runtime::RuntimeCBHandlerState) {
        self.get().set(py);
    }
}

// TODO: split into gen-asyngen classes (needs two different `waiter` build methods in `Event`)
#[pyclass(frozen, module = "tonio._tonio")]
pub(crate) struct Waiter {
    registered: atomic::AtomicBool,
    aborted: Arc<atomic::AtomicBool>,
    events: Vec<Py<Event>>,
    timeout: Option<usize>,
    checkpoint_gen: arc_swap::ArcSwapOption<PyGenSuspension>,
    checkpoint_asyncgen: arc_swap::ArcSwapOption<PyAsyncGenSuspension>,
}

impl Waiter {
    fn from_event(py: Python, event: Py<Event>, timeout: Option<usize>) -> Py<Self> {
        let slf = Self {
            registered: false.into(),
            aborted: Arc::new(false.into()),
            events: vec![event],
            timeout,
            checkpoint_gen: None.into(),
            checkpoint_asyncgen: None.into(),
        };
        Py::new(py, slf).unwrap()
    }

    pub fn new_for_suspension() -> Self {
        Self {
            registered: false.into(),
            aborted: Arc::new(false.into()),
            events: vec![],
            timeout: None,
            checkpoint_gen: None.into(),
            checkpoint_asyncgen: None.into(),
        }
    }

    fn build_sentinel(&self, py: Python) -> Option<Sentinel> {
        match self.events.len() {
            0..=1 => None,
            v => Some(Sentinel::new(py, v)),
        }
    }

    fn register(&self, py: Python, runtime: Py<Runtime>, suspension: Suspension) {
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
        parent: Option<PyGenSuspensionData>,
    ) {
        let rself = pyself.get();
        if rself
            .registered
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            if rself.events.is_empty() {
                let suspension = if let Some(parent_data) = parent {
                    if parent_data.0.checkpoint.is_none() {
                        // if parent_data.0.sentinel.is_some() {
                        //     panic!("Cannot register a checkpoint waiter with a parent sentinel");
                        // }
                        PyGenSuspension::from_checkpoint(py, target, parent_data, Arc::new(pyself.clone_ref(py)))
                    } else {
                        let checkpoint = parent_data.0.checkpoint.clone();
                        rself
                            .checkpoint_gen
                            .swap(checkpoint.as_ref().unwrap().get().checkpoint_gen.load_full());
                        PyGenSuspension::from_gen(target, Some(parent_data), None, checkpoint)
                    }
                } else {
                    panic!("Cannot register a checkpoint waiter without a parent");
                };
                if rself.aborted.load(atomic::Ordering::Acquire) {
                    suspension.error(py, runtime.get(), abort());
                    return;
                }
                // println!("CHECKPOINT WAITER {:?}", suspension.target);
                suspension.resume(py, runtime.get(), py.None(), 0);
                return;
            }

            let sentinel = rself.build_sentinel(py);
            let suspension: Arc<PyGenSuspension> = match parent {
                Some(parent_data) => {
                    let checkpoint = parent_data.0.checkpoint.clone();
                    PyGenSuspension::from_gen(target, Some(parent_data), sentinel, checkpoint).into()
                }
                None => PyGenSuspension::from_gen(target, None, sentinel, None).into(),
            };
            if let Some(checkpoint) = &suspension.checkpoint {
                checkpoint.get().checkpoint_gen.swap(Some(suspension.clone()));
            }
            // println!("WAITER REGISTERED {:?}", suspension.target);
            rself.register(py, runtime, Suspension::Gen(suspension));
        } else {
            panic!("Waiter already registered")
        }
    }

    pub(crate) fn register_pyasyncgen(
        pyself: Py<Self>,
        py: Python,
        runtime: Py<Runtime>,
        target: SuspensionTarget,
        checkpoint: Option<Arc<Py<Self>>>,
    ) {
        let rself = pyself.get();
        if rself
            .registered
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            let sentinel = rself.build_sentinel(py);
            if rself.events.is_empty() {
                let suspension = Arc::new(PyAsyncGenSuspension::from_gen(
                    target,
                    sentinel,
                    rself.aborted.clone(),
                    Some(Arc::new(pyself.clone_ref(py))),
                ));
                rself.checkpoint_asyncgen.swap(Some(suspension.clone()));
                if rself.aborted.load(atomic::Ordering::Acquire) {
                    suspension.error(py, runtime.get(), abort());
                    return;
                }
                suspension.resume(py, runtime.get(), py.None(), 0);
                return;
            }
            let suspension = match checkpoint {
                Some(checkpoint) => {
                    let rcheckpoint = checkpoint.get();
                    let suspension = Arc::new(PyAsyncGenSuspension::from_gen(
                        target,
                        sentinel,
                        rcheckpoint.aborted.clone(),
                        Some(checkpoint.clone()),
                    ));
                    rcheckpoint.checkpoint_asyncgen.swap(Some(suspension.clone()));
                    suspension
                }
                _ => PyAsyncGenSuspension::from_gen(target, sentinel, Arc::new(false.into()), None).into(),
            };
            rself.register(py, runtime, Suspension::AsyncGen(suspension));
        } else {
            panic!("Waiter already registered")
        }
    }

    pub(crate) fn abort_pygen(&self, py: Python) {
        if self
            .aborted
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
            && let Some(checkpoint) = self.checkpoint_gen.load().as_ref()
        {
            checkpoint.error(py, crate::get_runtime(py).unwrap().get(), abort());
        }
    }

    pub(crate) fn abort_pyasyncgen(&self, py: Python) {
        if self
            .aborted
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
            && let Some(checkpoint) = self.checkpoint_asyncgen.load().as_ref()
        {
            // println!("ABORT ASYNCG {:?}", checkpoint.target);
            checkpoint.error(py, crate::get_runtime(py).unwrap().get(), abort());
        }
    }
}

#[pymethods]
impl Waiter {
    #[new]
    #[pyo3(signature = (*events))]
    pub fn new(events: Vec<Py<Event>>) -> Self {
        Self {
            registered: false.into(),
            aborted: Arc::new(false.into()),
            events,
            timeout: None,
            checkpoint_gen: None.into(),
            checkpoint_asyncgen: None.into(),
        }
    }

    #[staticmethod]
    fn checkpoint() -> Self {
        Self::new_for_suspension()
    }

    fn abort(&self, py: Python) {
        self.abort_pyasyncgen(py);
    }

    fn unwind(&self, py: Python) {
        self.abort_pygen(py);
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

    pub(crate) fn throw(&self, value: Bound<PyAny>) -> PyResult<()> {
        let err = PyErr::from_value(value);
        // println!("WAITER THROW {:?}", err);
        Err(err)
    }
}

#[derive(Debug)]
#[pyclass(frozen, module = "tonio._tonio", name = "Result")]
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
    target: Suspension,
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

#[derive(Clone)]
pub(crate) enum Suspension {
    Gen(Arc<PyGenSuspension>),
    AsyncGen(Arc<PyAsyncGenSuspension>),
}

impl Suspension {
    pub(crate) fn resume(&self, py: Python, runtime: &Runtime, value: Py<PyAny>, order: usize) {
        match self {
            Self::Gen(inner) => inner.resume(py, runtime, value, order),
            Self::AsyncGen(inner) => inner.resume(py, runtime, value, order),
        }
    }

    fn suspend(&self) {
        match self {
            Self::Gen(inner) => inner.suspend(),
            Self::AsyncGen(inner) => inner.suspend(),
        }
    }
}

pub(crate) type PyGenSuspensionData = (Arc<PyGenSuspension>, usize);

#[derive(Debug)]
pub(crate) enum SuspensionTarget {
    Gen(Py<PyAny>),
    GenCtx((Py<PyAny>, Py<PyAny>)),
    AsyncGen(Py<PyAny>),
    AsyncGenCtx((Py<PyAny>, Py<PyAny>)),
}

#[derive(Debug)]
pub(crate) struct PyGenSuspension {
    parent: Option<PyGenSuspensionData>,
    pub target: SuspensionTarget,
    consumed: atomic::AtomicBool,
    is_checkpoint: bool,
    sentinel: Option<Sentinel>,
    checkpoint: Option<Arc<Py<Waiter>>>,
}

impl PyGenSuspension {
    pub(crate) fn from_gen(
        target: SuspensionTarget,
        parent: Option<PyGenSuspensionData>,
        sentinel: Option<Sentinel>,
        checkpoint: Option<Arc<Py<Waiter>>>,
    ) -> Self {
        Self {
            parent,
            target,
            consumed: false.into(),
            is_checkpoint: false,
            sentinel,
            checkpoint,
        }
    }

    pub(crate) fn from_handle(target: SuspensionTarget, parent: Option<PyGenSuspensionData>) -> Self {
        let checkpoint = match &parent {
            Some(parent_data) => {
                if parent_data.0.is_checkpoint {
                    parent_data
                        .0
                        .checkpoint
                        .as_ref()
                        .unwrap()
                        .get()
                        .checkpoint_gen
                        .swap(Some(parent_data.0.clone()));
                }
                parent_data.0.checkpoint.clone()
            }
            None => None,
        };

        Self {
            parent,
            target,
            consumed: false.into(),
            is_checkpoint: false,
            sentinel: None,
            checkpoint,
        }
    }

    fn from_checkpoint(
        py: Python,
        target: SuspensionTarget,
        parent: PyGenSuspensionData,
        checkpoint: Arc<Py<Waiter>>,
    ) -> Self {
        let (parent_susp, parent_idx) = parent;
        let new_parent = Self {
            target: match &parent_susp.target {
                SuspensionTarget::Gen(inner) => SuspensionTarget::Gen(inner.clone_ref(py)),
                SuspensionTarget::GenCtx(inner) => {
                    SuspensionTarget::GenCtx((inner.0.clone_ref(py), inner.1.clone_ref(py)))
                }
                _ => unreachable!(),
            },
            parent: parent_susp.parent.clone(),
            consumed: false.into(),
            is_checkpoint: true,
            sentinel: None,
            checkpoint: Some(checkpoint),
        };
        Self {
            parent: Some((Arc::new(new_parent), parent_idx)),
            target,
            consumed: false.into(),
            is_checkpoint: false,
            sentinel: None,
            checkpoint: None,
        }
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
            SuspensionTarget::GenCtx((target, ctx)) => {
                let handle = handles::PyGenCtxHandle {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            _ => unreachable!(),
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
            SuspensionTarget::GenCtx((target, ctx)) => {
                let handle = handles::PyGenCtxThrower {
                    parent: self.parent.clone(),
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            _ => unreachable!(),
        }
    }

    fn suspend(&self) {
        if let Some(sentinel) = &self.sentinel {
            sentinel.increment();
        }
    }

    pub fn resume(&self, py: Python, runtime: &Runtime, value: Py<PyAny>, order: usize) {
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
        // println!("GENSUSP ERR {:?} {:?}", self.target, self.consumed);
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
pub(crate) struct PyAsyncGenSuspension {
    pub target: SuspensionTarget,
    consumed: atomic::AtomicBool,
    sentinel: Option<Sentinel>,
    aborted: Arc<atomic::AtomicBool>,
    checkpoint: Option<Arc<Py<Waiter>>>,
}

impl PyAsyncGenSuspension {
    pub(crate) fn from_gen(
        target: SuspensionTarget,
        sentinel: Option<Sentinel>,
        aborted: Arc<atomic::AtomicBool>,
        checkpoint: Option<Arc<Py<Waiter>>>,
    ) -> Self {
        Self {
            target,
            consumed: false.into(),
            sentinel,
            aborted,
            checkpoint,
        }
    }

    fn to_handle(&self, py: Python, value: Py<PyAny>) -> BoxedHandle {
        match &self.target {
            SuspensionTarget::AsyncGen(target) => {
                let handle = handles::PyAsyncGenHandle {
                    coro: target.clone_ref(py),
                    value,
                    checkpoint: self.checkpoint.clone(),
                };
                Box::new(handle)
            }
            SuspensionTarget::AsyncGenCtx((target, ctx)) => {
                let handle = handles::PyAsyncGenCtxHandle {
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                    checkpoint: self.checkpoint.clone(),
                };
                Box::new(handle)
            }
            _ => unreachable!(),
        }
    }

    fn to_throw_handle(&self, py: Python, err: PyErr) -> BoxedHandle {
        let value = err.into_value(py).as_any().clone_ref(py);
        match &self.target {
            SuspensionTarget::AsyncGen(target) => {
                let handle = handles::PyAsyncGenThrower {
                    coro: target.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            SuspensionTarget::AsyncGenCtx((target, ctx)) => {
                let handle = handles::PyAsyncGenCtxThrower {
                    coro: target.clone_ref(py),
                    ctx: ctx.clone_ref(py),
                    value,
                };
                Box::new(handle)
            }
            _ => unreachable!(),
        }
    }

    fn suspend(&self) {
        if let Some(sentinel) = &self.sentinel {
            sentinel.increment();
        }
    }

    pub fn resume(&self, py: Python, runtime: &Runtime, value: Py<PyAny>, order: usize) {
        if self.aborted.load(atomic::Ordering::Acquire) {
            return;
        }
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
        // println!("AGENSUSP ERR {:?} {:?}", self.target, self.consumed);
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
