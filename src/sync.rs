use pyo3::prelude::*;
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex, atomic},
};

use crate::events::Event;

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct Lock {
    state: atomic::AtomicBool,
    waiters: Mutex<VecDeque<Py<Event>>>,
}

#[pymethods]
impl Lock {
    #[new]
    fn new() -> Self {
        Self {
            state: false.into(),
            waiters: Mutex::new(VecDeque::new()),
        }
    }

    fn acquire(&self, py: Python) -> Option<Py<Event>> {
        if self
            .state
            .compare_exchange(false, true, atomic::Ordering::Acquire, atomic::Ordering::Relaxed)
            .is_err()
        {
            let mut events = self.waiters.lock().unwrap();
            let event = Py::new(py, Event::new()).unwrap();
            events.push_back(event.clone_ref(py));
            return Some(event);
        }
        None
    }

    fn try_acquire(&self) -> PyResult<()> {
        if self
            .state
            .compare_exchange(false, true, atomic::Ordering::Acquire, atomic::Ordering::Relaxed)
            .is_err()
        {
            return Err(crate::errors::WouldBlock::new_err("Cannot acquire lock"));
        }
        Ok(())
    }

    fn release(&self, py: Python) {
        let mut events = self.waiters.lock().unwrap();
        if let Some(event) = events.pop_front() {
            event.get().set(py);
            return;
        }
        self.state.store(false, atomic::Ordering::Release);
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct Semaphore {
    state: Mutex<(usize, VecDeque<Py<Event>>)>,
}

#[pymethods]
impl Semaphore {
    #[new]
    fn new(value: usize) -> Self {
        Self {
            state: Mutex::new((value, VecDeque::new())),
        }
    }

    fn acquire(&self, py: Python) -> Option<Py<Event>> {
        let mut state = self.state.lock().unwrap();
        #[allow(clippy::cast_possible_wrap)]
        let value = state.0 as i32 - state.1.len() as i32;
        // println!("ACQ VAL {:?}", value);
        if value <= 0 {
            let event = Py::new(py, Event::new()).unwrap();
            state.1.push_back(event.clone_ref(py));
            return Some(event);
        }
        state.0 -= 1;
        None
    }

    fn try_acquire(&self) -> PyResult<()> {
        let mut state = self.state.lock().unwrap();
        #[allow(clippy::cast_possible_wrap)]
        let value = state.0 as i32 - state.1.len() as i32;
        if value <= 0 {
            return Err(crate::errors::WouldBlock::new_err("Cannot acquire semaphore"));
        }
        state.0 -= 1;
        Ok(())
    }

    fn release(&self, py: Python) {
        let mut state = self.state.lock().unwrap();
        if let Some(event) = state.1.pop_front() {
            event.get().set(py);
            return;
        }
        state.0 += 1;
    }

    fn tokens(&self) -> usize {
        let state = self.state.lock().unwrap();
        state.0
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct Barrier {
    value: usize,
    count: atomic::AtomicUsize,
    #[pyo3(get)]
    _event: Py<Event>,
}

#[pymethods]
impl Barrier {
    #[new]
    fn new(py: Python, value: usize) -> Self {
        Self {
            value,
            count: 0.into(),
            _event: Py::new(py, Event::new()).unwrap(),
        }
    }

    fn ack(&self, py: Python) -> usize {
        let count = self.count.fetch_add(1, atomic::Ordering::AcqRel);
        if (count + 1) >= self.value {
            self._event.get().set(py);
        }
        count
    }

    fn value(&self) -> usize {
        self.count.load(atomic::Ordering::Relaxed)
    }
}

#[pyclass(frozen, module = "tonio._tonio")]
struct LockCtx {
    lock: Py<Lock>,
    consumed: atomic::AtomicBool,
}

#[pymethods]
impl LockCtx {
    #[new]
    fn new(lock: Py<Lock>) -> Self {
        Self {
            lock,
            consumed: false.into(),
        }
    }

    fn __enter__(&self) -> PyResult<()> {
        if self
            .consumed
            .compare_exchange(false, true, atomic::Ordering::Relaxed, atomic::Ordering::Relaxed)
            .is_err()
        {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Cannot acquire the same lock ctx multiple times.",
            ));
        }
        Ok(())
    }

    fn __exit__(&self, py: Python, _exc_type: Bound<PyAny>, _exc_value: Bound<PyAny>, _exc_tb: Bound<PyAny>) {
        let lock = self.lock.get();
        lock.release(py);
    }
}

#[pyclass(frozen, module = "tonio._tonio")]
struct SemaphoreCtx {
    semaphore: Py<Semaphore>,
    consumed: atomic::AtomicBool,
}

#[pymethods]
impl SemaphoreCtx {
    #[new]
    fn new(semaphore: Py<Semaphore>) -> Self {
        Self {
            semaphore,
            consumed: false.into(),
        }
    }

    fn __enter__(&self) -> PyResult<()> {
        if self
            .consumed
            .compare_exchange(false, true, atomic::Ordering::Relaxed, atomic::Ordering::Relaxed)
            .is_err()
        {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Cannot acquire the same semaphore ctx multiple times.",
            ));
        }
        Ok(())
    }

    fn __exit__(&self, py: Python, _exc_type: Bound<PyAny>, _exc_value: Bound<PyAny>, _exc_tb: Bound<PyAny>) {
        let semaphore = self.semaphore.get();
        semaphore.release(py);
    }
}

struct ChannelState {
    queue: VecDeque<(Py<PyAny>, Option<Py<Event>>)>,
    waiters: VecDeque<Py<Event>>,
}

struct Channel {
    size: usize,
    len: atomic::AtomicUsize,
    state: Mutex<ChannelState>,
    tx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    rx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    closed: atomic::AtomicBool,
}

impl Channel {
    fn tx_add(&self) -> usize {
        let idx = self.tx.0.fetch_add(1, atomic::Ordering::Relaxed);
        let tx = self.tx.1.pin();
        tx.insert(idx);
        idx
    }

    fn rx_add(&self) -> usize {
        let idx = self.rx.0.fetch_add(1, atomic::Ordering::Relaxed);
        let rx = self.rx.1.pin();
        rx.insert(idx);
        idx
    }

    fn tx_rem(&self, py: Python, idx: usize) {
        let tx = self.tx.1.pin();
        tx.remove(&idx);
        if tx.is_empty() {
            self.close(py);
        }
    }

    fn rx_rem(&self, py: Python, idx: usize) {
        let rx = self.rx.1.pin();
        rx.remove(&idx);
        if rx.is_empty() {
            self.close(py);
        }
    }

    fn close(&self, py: Python) {
        if self
            .closed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            let mut waiters = {
                let mut state = self.state.lock().unwrap();
                std::mem::take(&mut state.waiters)
            };
            for event in waiters.drain(..) {
                event.get().set(py);
            }
        }
    }

    fn push(&self, py: Python, message: Py<PyAny>) -> Option<Py<Event>> {
        let len = self.len.fetch_add(1, atomic::Ordering::Relaxed);
        //: over capacity: sender parks on an event set once its message gets pulled
        let want_pull = (len >= self.size).then(|| Py::new(py, Event::new()).unwrap());
        let want_push = {
            let mut state = self.state.lock().unwrap();
            state
                .queue
                .push_back((message, want_pull.as_ref().map(|event| event.clone_ref(py))));
            state.waiters.pop_front()
        };
        if let Some(event) = want_push {
            event.get().set(py);
        }
        want_pull
    }

    fn pull(&self, py: Python) -> (Option<Py<Event>>, Option<Py<PyAny>>) {
        macro_rules! try_pull {
            ($state:ident) => {
                if let Some((message, want_pull)) = $state.queue.pop_front() {
                    drop($state);
                    self.len.fetch_sub(1, atomic::Ordering::Relaxed);
                    if let Some(event) = want_pull {
                        event.get().set(py);
                    }
                    return (None, Some(message));
                }
                if self.closed.load(atomic::Ordering::Acquire) {
                    return (None, None);
                }
            };
        }

        //: fast path — message available or channel closed, no event allocation
        {
            let mut state = self.state.lock().unwrap();
            try_pull!(state);
        }
        //: miss path — allocate the event with no lock held, then recheck before parking
        let want_push = Py::new(py, Event::new()).unwrap();
        let mut state = self.state.lock().unwrap();
        try_pull!(state);
        state.waiters.push_back(want_push.clone_ref(py));
        drop(state);
        (Some(want_push), None)
    }
}

struct UnboundedChannelState {
    queue: VecDeque<Py<PyAny>>,
    waiters: VecDeque<Py<Event>>,
}

struct UnboundedChannel {
    state: Mutex<UnboundedChannelState>,
    tx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    rx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    closed: atomic::AtomicBool,
}

impl UnboundedChannel {
    fn tx_add(&self) -> usize {
        let idx = self.tx.0.fetch_add(1, atomic::Ordering::Relaxed);
        let tx = self.tx.1.pin();
        tx.insert(idx);
        idx
    }

    fn rx_add(&self) -> usize {
        let idx = self.rx.0.fetch_add(1, atomic::Ordering::Relaxed);
        let rx = self.rx.1.pin();
        rx.insert(idx);
        idx
    }

    fn tx_rem(&self, py: Python, idx: usize) {
        let tx = self.tx.1.pin();
        tx.remove(&idx);
        if tx.is_empty() {
            self.close(py);
        }
    }

    fn rx_rem(&self, py: Python, idx: usize) {
        let rx = self.rx.1.pin();
        rx.remove(&idx);
        if rx.is_empty() {
            self.close(py);
        }
    }

    fn push(&self, py: Python, message: Py<PyAny>) {
        let want_push = {
            let mut state = self.state.lock().unwrap();
            state.queue.push_back(message);
            state.waiters.pop_front()
        };
        if let Some(event) = want_push {
            event.get().set(py);
        }
    }

    fn pull(&self, py: Python) -> (Option<Py<Event>>, Option<Py<PyAny>>) {
        macro_rules! try_pull {
            ($state:ident) => {
                if let Some(message) = $state.queue.pop_front() {
                    return (None, Some(message));
                }
                if self.closed.load(atomic::Ordering::Acquire) {
                    return (None, None);
                }
            };
        }

        //: fast path — message available or channel closed, no event allocation
        {
            let mut state = self.state.lock().unwrap();
            try_pull!(state);
        }
        //: miss path — allocate the event with no lock held, then recheck before parking
        let want_push = Py::new(py, Event::new()).unwrap();
        let mut state = self.state.lock().unwrap();
        try_pull!(state);
        state.waiters.push_back(want_push.clone_ref(py));
        drop(state);
        (Some(want_push), None)
    }

    fn close(&self, py: Python) {
        if self
            .closed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            let mut waiters = {
                let mut state = self.state.lock().unwrap();
                std::mem::take(&mut state.waiters)
            };
            for event in waiters.drain(..) {
                event.get().set(py);
            }
        }
    }
}

#[pyclass(frozen, module = "tonio._tonio", name = "Channel")]
struct PyChannel {
    inner: Arc<Channel>,
}

#[pymethods]
impl PyChannel {
    #[new]
    fn new(size: usize) -> Self {
        Self {
            inner: Arc::new(Channel {
                size,
                len: 0.into(),
                state: Mutex::new(ChannelState {
                    queue: VecDeque::new(),
                    waiters: VecDeque::new(),
                }),
                tx: (0.into(), papaya::HashSet::new()),
                rx: (0.into(), papaya::HashSet::new()),
                closed: false.into(),
            }),
        }
    }
}

#[pyclass(frozen, module = "tonio._tonio", name = "UnboundedChannel")]
struct PyUnboundedChannel {
    inner: Arc<UnboundedChannel>,
}

#[pymethods]
impl PyUnboundedChannel {
    #[new]
    fn new() -> Self {
        Self {
            inner: Arc::new(UnboundedChannel {
                state: Mutex::new(UnboundedChannelState {
                    queue: VecDeque::new(),
                    waiters: VecDeque::new(),
                }),
                tx: (0.into(), papaya::HashSet::new()),
                rx: (0.into(), papaya::HashSet::new()),
                closed: false.into(),
            }),
        }
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct ChannelSender {
    channel: Arc<Channel>,
    id: usize,
}

#[pymethods]
impl ChannelSender {
    #[new]
    fn new(channel: Py<PyChannel>) -> Self {
        let inner = &channel.get().inner;
        let id = inner.tx_add();
        Self {
            channel: inner.clone(),
            id,
        }
    }

    // TODO: clone

    fn close(&self, py: Python) {
        self.channel.close(py);
    }

    fn _send(&self, py: Python, message: Py<PyAny>) -> PyResult<Option<Py<Event>>> {
        if self.channel.closed.load(atomic::Ordering::Acquire) {
            return Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed"));
        }
        Ok(self.channel.push(py, message))
    }
}

impl Drop for ChannelSender {
    fn drop(&mut self) {
        Python::attach(|py| self.channel.tx_rem(py, self.id));
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct ChannelReceiver {
    channel: Arc<Channel>,
    id: usize,
}

#[pymethods]
impl ChannelReceiver {
    #[new]
    fn new(channel: Py<PyChannel>) -> Self {
        let inner = &channel.get().inner;
        let id = inner.rx_add();
        Self {
            channel: channel.get().inner.clone(),
            id,
        }
    }

    // TODO: clone

    fn _receive(&self, py: Python) -> PyResult<(Option<Py<Event>>, bool, Option<Py<PyAny>>)> {
        match self.channel.pull(py) {
            (event @ Some(_), None) => Ok((event, true, None)),
            (None, message @ Some(_)) => Ok((None, false, message)),
            _ => Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed")),
        }
    }
}

impl Drop for ChannelReceiver {
    fn drop(&mut self) {
        Python::attach(|py| self.channel.rx_rem(py, self.id));
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct UnboundedChannelSender {
    channel: Arc<UnboundedChannel>,
    id: usize,
}

#[pymethods]
impl UnboundedChannelSender {
    #[new]
    fn new(channel: Py<PyUnboundedChannel>) -> Self {
        let inner = &channel.get().inner;
        let id = inner.tx_add();
        Self {
            channel: inner.clone(),
            id,
        }
    }

    // TODO: clone

    fn send(&self, py: Python, message: Py<PyAny>) -> PyResult<()> {
        if self.channel.closed.load(atomic::Ordering::Acquire) {
            return Err(pyo3::exceptions::PyBrokenPipeError::new_err("Channel closed"));
        }
        self.channel.push(py, message);
        Ok(())
    }

    fn close(&self, py: Python) {
        self.channel.close(py);
    }
}

impl Drop for UnboundedChannelSender {
    fn drop(&mut self) {
        Python::attach(|py| self.channel.tx_rem(py, self.id));
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct UnboundedChannelReceiver {
    channel: Arc<UnboundedChannel>,
    id: usize,
}

#[pymethods]
impl UnboundedChannelReceiver {
    #[new]
    fn new(channel: Py<PyUnboundedChannel>) -> Self {
        let inner = &channel.get().inner;
        let id = inner.rx_add();
        Self {
            channel: inner.clone(),
            id,
        }
    }

    // TODO: clone

    fn _receive(&self, py: Python) -> PyResult<(Option<Py<Event>>, bool, Option<Py<PyAny>>)> {
        match self.channel.pull(py) {
            (event @ Some(_), None) => Ok((event, true, None)),
            (None, message @ Some(_)) => Ok((None, false, message)),
            _ => Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed")),
        }
    }
}

impl Drop for UnboundedChannelReceiver {
    fn drop(&mut self) {
        Python::attach(|py| self.channel.rx_rem(py, self.id));
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Lock>()?;
    module.add_class::<Semaphore>()?;
    module.add_class::<Barrier>()?;
    module.add_class::<LockCtx>()?;
    module.add_class::<SemaphoreCtx>()?;
    module.add_class::<PyChannel>()?;
    module.add_class::<ChannelSender>()?;
    module.add_class::<ChannelReceiver>()?;
    module.add_class::<PyUnboundedChannel>()?;
    module.add_class::<UnboundedChannelSender>()?;
    module.add_class::<UnboundedChannelReceiver>()?;

    Ok(())
}
