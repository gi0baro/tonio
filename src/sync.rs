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
    event: Py<Event>,
}

#[pymethods]
impl Barrier {
    #[new]
    fn new(py: Python, value: usize) -> Self {
        Self {
            value,
            count: 0.into(),
            event: Py::new(py, Event::new()).unwrap(),
        }
    }

    fn ack(&self, py: Python) -> usize {
        let count = self.count.fetch_add(1, atomic::Ordering::Release);
        if (count + 1) >= self.value {
            self.event.get().set(py);
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
    buf: atomic::AtomicUsize,
    closed: atomic::AtomicBool,
    stream: Mutex<VecDeque<Py<PyAny>>>,
    consumers: Mutex<VecDeque<Py<Event>>>,
    senders: Mutex<VecDeque<Py<Event>>>,
}

enum ChannelRecvResult {
    Message(Py<PyAny>),
    Waiter(Py<Event>),
    Empty,
}

impl Channel {
    fn send_or_hold(&self, py: Python, message: Py<PyAny>) -> Option<Py<Event>> {
        if self.buf.fetch_add(1, atomic::Ordering::Release) >= self.size {
            // println!("CHANNEL OVERFLOW");
            let event = Py::new(py, Event::new()).unwrap();
            let mut waiters = self.senders.lock().unwrap();
            waiters.push_back(event.clone_ref(py));
            return Some(event);
        }
        self.send(py, message);
        None
    }

    fn send(&self, py: Python, message: Py<PyAny>) {
        {
            let mut stream = self.stream.lock().unwrap();
            stream.push_back(message);
            // println!("CHANNEL SEND LEN {}", stream.len());
        }
        if let Some(event) = {
            let mut consumers = self.consumers.lock().unwrap();
            // println!("CHANNEL CONSUMERS {:?}", consumers.len());
            consumers.pop_front()
        } {
            // println!("CHANNEL CONSUMER WAKE");
            event.get().set(py);
        }
    }

    fn receive(&self, py: Python) -> ChannelRecvResult {
        if let Some(message) = {
            let mut stream = self.stream.lock().unwrap();
            // println!("CHANNEL RECV LEN {}", stream.len());
            stream.pop_front()
        } {
            self.buf.fetch_sub(1, atomic::Ordering::Release);
            if let Some(event) = {
                let mut senders = self.senders.lock().unwrap();
                // println!("CHANNEL SENDERS {}", senders.len());
                senders.pop_front()
            } {
                // println!("CHANNEL SENDER WAKE");
                event.get().set(py);
            }
            return ChannelRecvResult::Message(message);
        }
        if self.closed.load(atomic::Ordering::Acquire) {
            return ChannelRecvResult::Empty;
        }
        let event = Py::new(py, Event::new()).unwrap();
        let mut registry = self.consumers.lock().unwrap();
        registry.push_back(event.clone_ref(py));
        ChannelRecvResult::Waiter(event)
    }
}

struct UnboundedChannel {
    stream: Mutex<VecDeque<Py<PyAny>>>,
    consumers: Mutex<VecDeque<Py<Event>>>,
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
                buf: 0.into(),
                closed: false.into(),
                stream: Mutex::new(VecDeque::new()),
                consumers: Mutex::new(VecDeque::new()),
                senders: Mutex::new(VecDeque::new()),
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
                stream: Mutex::new(VecDeque::new()),
                consumers: Mutex::new(VecDeque::new()),
            }),
        }
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct ChannelSender {
    channel: Arc<Channel>,
}

#[pymethods]
impl ChannelSender {
    #[new]
    fn new(channel: Py<PyChannel>) -> Self {
        Self {
            channel: channel.get().inner.clone(),
        }
    }

    fn close(&self, py: Python) {
        // println!("CLOSE BEGIN");
        self.channel.closed.store(true, atomic::Ordering::Release);
        // println!("CLOSE BOOL");
        let mut consumers = self.channel.consumers.lock().unwrap();
        // println!("CLOSE CONS {}", consumers.len());
        while let Some(event) = consumers.pop_front() {
            event.get().set(py);
        }
        // println!("CLOSE DONE");
    }

    fn _send_or_wait(&self, py: Python, message: Py<PyAny>) -> Option<Py<Event>> {
        self.channel.send_or_hold(py, message)
    }

    fn _send(&self, py: Python, message: Py<PyAny>) {
        self.channel.send(py, message);
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct ChannelReceiver {
    channel: Arc<Channel>,
}

#[pymethods]
impl ChannelReceiver {
    #[new]
    fn new(channel: Py<PyChannel>) -> Self {
        Self {
            channel: channel.get().inner.clone(),
        }
    }

    fn _receive(&self, py: Python) -> PyResult<(Option<Py<PyAny>>, Option<Py<Event>>)> {
        match self.channel.receive(py) {
            ChannelRecvResult::Message(message) => Ok((Some(message), None)),
            ChannelRecvResult::Waiter(event) => Ok((None, Some(event))),
            ChannelRecvResult::Empty => Err(pyo3::exceptions::PyBrokenPipeError::new_err("channel closed")),
        }
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct UnboundedChannelSender {
    channel: Arc<UnboundedChannel>,
}

#[pymethods]
impl UnboundedChannelSender {
    #[new]
    fn new(channel: Py<PyUnboundedChannel>) -> Self {
        Self {
            channel: channel.get().inner.clone(),
        }
    }

    fn send(&self, py: Python, message: Py<PyAny>) {
        {
            let mut stream = self.channel.stream.lock().unwrap();
            stream.push_back(message);
        }
        let mut consumers = self.channel.consumers.lock().unwrap();
        if let Some(event) = consumers.pop_front() {
            event.get().set(py);
        }
    }
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
struct UnboundedChannelReceiver {
    channel: Arc<UnboundedChannel>,
}

#[pymethods]
impl UnboundedChannelReceiver {
    #[new]
    fn new(channel: Py<PyUnboundedChannel>) -> Self {
        Self {
            channel: channel.get().inner.clone(),
        }
    }

    fn _receive(&self, py: Python) -> (Option<Py<PyAny>>, Option<Py<Event>>) {
        if let Some(message) = {
            let mut stream = self.channel.stream.lock().unwrap();
            stream.pop_front()
        } {
            return (Some(message), None);
        }
        let event = Py::new(py, Event::new()).unwrap();
        let mut registry = self.channel.consumers.lock().unwrap();
        registry.push_back(event.clone_ref(py));
        (None, Some(event))
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
