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
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_err()
        {
            let mut events = self.waiters.lock().unwrap();
            let event = Py::new(py, Event::new()).unwrap();
            events.push_back(event.clone_ref(py));
            return Some(event);
        }
        None
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

    fn release(&self, py: Python) {
        let mut state = self.state.lock().unwrap();
        if let Some(event) = state.1.pop_front() {
            event.get().set(py);
            return;
        }
        state.0 += 1;
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
        let count = self.count.fetch_add(1, atomic::Ordering::Release);
        if (count + 1) >= self.value {
            self._event.get().set(py);
        }
        count
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
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
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
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
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

struct Channel {
    size: usize,
    len: atomic::AtomicUsize,
    tx_queue: Mutex<VecDeque<(Py<PyAny>, Py<Event>)>>,
    rx_queue: Mutex<VecDeque<Py<Event>>>,
    tx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    rx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    closed: atomic::AtomicBool,
}

impl Channel {
    fn tx_add(&self) -> usize {
        let idx = self.tx.0.fetch_add(1, atomic::Ordering::Release);
        let tx = self.tx.1.pin();
        tx.insert(idx);
        idx
    }

    fn rx_add(&self) -> usize {
        let idx = self.rx.0.fetch_add(1, atomic::Ordering::Release);
        let rx = self.rx.1.pin();
        rx.insert(idx);
        idx
    }

    fn tx_rem(&self, idx: usize) {
        let tx = self.tx.1.pin();
        tx.remove(&idx);
        if tx.is_empty() {
            self.close();
        }
    }

    fn rx_rem(&self, idx: usize) {
        let rx = self.rx.1.pin();
        rx.remove(&idx);
        if rx.is_empty() {
            self.close();
        }
    }

    fn close(&self) {
        if self
            .closed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
        {
            Python::attach(|py| {
                let mut rx = self.rx_queue.lock().unwrap();
                while let Some(event) = rx.pop_front() {
                    event.get().set(py);
                }
            });
        }
    }

    fn push(&self, py: Python, message: Py<PyAny>) -> Py<Event> {
        let want_pull = Py::new(py, Event::new()).unwrap();
        let len = self.len.fetch_add(1, atomic::Ordering::SeqCst);
        if len < self.size {
            want_pull.get().set(py);
        }
        {
            let mut tx = self.tx_queue.lock().unwrap();
            tx.push_back((message, want_pull.clone_ref(py)));
        }
        if let Some(want_push) = {
            let mut rx = self.rx_queue.lock().unwrap();
            rx.pop_front()
        } {
            want_push.get().set(py);
        }
        want_pull
    }

    fn pull(&self, py: Python) -> (Py<Event>, Option<Py<PyAny>>) {
        let want_push = Py::new(py, Event::new()).unwrap();
        if let Some((message, want_pull)) = {
            match self.tx_queue.try_lock() {
                Ok(mut tx) => tx.pop_front(),
                _ => None,
            }
        } {
            self.len.fetch_sub(1, atomic::Ordering::SeqCst);
            want_push.get().set(py);
            want_pull.get().set(py);
            return (want_push, Some(message));
        }
        if self.closed.load(atomic::Ordering::SeqCst) {
            want_push.get().set(py);
        } else {
            let mut rx = self.rx_queue.lock().unwrap();
            rx.push_back(want_push.clone_ref(py));
        }
        (want_push, None)
    }
}

struct UnboundedChannel {
    tx_queue: Mutex<VecDeque<Py<PyAny>>>,
    rx_queue: Mutex<VecDeque<Py<Event>>>,
    tx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    rx: (atomic::AtomicUsize, papaya::HashSet<usize>),
    closed: atomic::AtomicBool,
}

impl UnboundedChannel {
    fn tx_add(&self) -> usize {
        let idx = self.tx.0.fetch_add(1, atomic::Ordering::Release);
        let tx = self.tx.1.pin();
        tx.insert(idx);
        idx
    }

    fn rx_add(&self) -> usize {
        let idx = self.rx.0.fetch_add(1, atomic::Ordering::Release);
        let rx = self.rx.1.pin();
        rx.insert(idx);
        idx
    }

    fn tx_rem(&self, idx: usize) {
        let tx = self.tx.1.pin();
        tx.remove(&idx);
        if tx.is_empty() {
            self.close(None);
        }
    }

    fn rx_rem(&self, idx: usize) {
        let rx = self.rx.1.pin();
        rx.remove(&idx);
        if rx.is_empty() {
            self.close(None);
        }
    }

    fn push(&self, py: Python, message: Py<PyAny>) {
        {
            let mut tx = self.tx_queue.lock().unwrap();
            tx.push_back(message);
        }
        if let Some(event) = {
            let mut rx = self.rx_queue.lock().unwrap();
            rx.pop_front()
        } {
            event.get().set(py);
        }
    }

    fn pull(&self, py: Python) -> (Py<Event>, Option<Py<PyAny>>, bool) {
        let mut closed = false;
        let want_push = Py::new(py, Event::new()).unwrap();
        //: lock `rx_queue` so we have only 1 receiver at time in the following section
        let mut rx = self.rx_queue.lock().unwrap();
        if let Some(message) = match self.tx_queue.try_lock() {
            //: if the `tx_queue` lock acq fails, senders are writing
            Ok(mut data) => data.pop_front(),
            _ => None,
        } {
            return (want_push, Some(message), closed);
        }
        if self.closed.load(atomic::Ordering::SeqCst) {
            want_push.get().set(py);
            closed = true;
        } else {
            rx.push_back(want_push.clone_ref(py));
        }
        (want_push, None, closed)
    }

    fn close(&self, py: Option<Python>) {
        // TODO: change to always acquire python interpreter instead of arg?
        if self
            .closed
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_ok()
            && let Some(py) = py
        {
            let mut rx = self.rx_queue.lock().unwrap();
            while let Some(event) = rx.pop_front() {
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
                tx_queue: Mutex::new(VecDeque::new()),
                rx_queue: Mutex::new(VecDeque::new()),
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
                tx_queue: Mutex::new(VecDeque::new()),
                rx_queue: Mutex::new(VecDeque::new()),
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

    fn close(&self) {
        self.channel.close();
    }

    fn _send(&self, py: Python, message: Py<PyAny>) -> PyResult<Py<Event>> {
        if self.channel.closed.load(atomic::Ordering::SeqCst) {
            return Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed"));
        }
        Ok(self.channel.push(py, message))
    }
}

impl Drop for ChannelSender {
    fn drop(&mut self) {
        self.channel.tx_rem(self.id);
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

    fn _receive(&self, py: Python) -> PyResult<(Py<Event>, bool, Option<Py<PyAny>>)> {
        if self.channel.closed.load(atomic::Ordering::SeqCst) {
            return Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed"));
        }
        let (event, message) = self.channel.pull(py);
        Ok((event, message.is_none(), message))
    }
}

impl Drop for ChannelReceiver {
    fn drop(&mut self) {
        self.channel.rx_rem(self.id);
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
        if self.channel.closed.load(atomic::Ordering::SeqCst) {
            return Err(pyo3::exceptions::PyBrokenPipeError::new_err("Channel closed"));
        }
        self.channel.push(py, message);
        Ok(())
    }

    fn close(&self, py: Python) {
        self.channel.close(Some(py));
    }
}

impl Drop for UnboundedChannelSender {
    fn drop(&mut self) {
        self.channel.tx_rem(self.id);
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

    fn _receive(&self, py: Python) -> PyResult<(Py<Event>, bool, Option<Py<PyAny>>)> {
        let (event, message, closed) = self.channel.pull(py);
        if closed {
            return Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed"));
        }
        Ok((event, message.is_none(), message))
    }
}

impl Drop for UnboundedChannelReceiver {
    fn drop(&mut self) {
        self.channel.rx_rem(self.id);
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
