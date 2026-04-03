use std::{
    collections::{BinaryHeap, HashMap, VecDeque},
    io::Read,
    os::fd::FromRawFd,
    sync::{Arc, Condvar, Mutex, atomic},
    thread,
    time::{Duration, Instant},
};

// use anyhow::Result;
use crossbeam_channel as channel;
use mio::{Interest, Poll, Token, Waker, event};
use pyo3::prelude::*;

use crate::{
    blocking::BlockingRunnerPool,
    handles::BoxedHandle,
    io::Source,
    // py::copy_context,
    time::Timer,
};

type IOPyOp = (Token, Interest, Py<crate::events::Event>);

enum IOHandle {
    Py(PyHandleData),
    Signals,
}

struct PyHandleData {
    interest: Interest,
    reader: Option<Py<crate::events::Event>>,
    writer: Option<Py<crate::events::Event>>,
}

pub struct RuntimeState {
    buf: Box<[u8]>,
    io: Poll,
    handles: HashMap<Token, IOHandle>,
    sig_sock: (socket2::Socket, socket2::Socket),
}

pub struct RuntimeCBHandlerState {
    pub read_buf: Box<[u8]>,
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub struct Runtime {
    io_ops: Mutex<VecDeque<IOPyOp>>,
    waker: arc_swap::ArcSwapOption<Waker>,
    handles_sched: Mutex<BinaryHeap<Timer>>,
    blocking_pool: BlockingRunnerPool,
    channel_handle_send: channel::Sender<BoxedHandle>,
    channel_handle_recv: channel::Receiver<BoxedHandle>,
    channel_sig_send: channel::Sender<()>,
    channel_sig_recv: channel::Receiver<()>,
    epoch: Instant,
    closed: atomic::AtomicBool,
    sig_set: std::collections::HashSet<u8>,
    sig_wfd: arc_swap::ArcSwap<Py<PyAny>>,
    sig_handlers: papaya::HashMap<u8, Py<crate::events::Event>>,
    sig_listening: atomic::AtomicBool,
    sig_loop_handled: atomic::AtomicBool,
    // sig_wfd: RwLock<Py<PyAny>>,
    stopping: atomic::AtomicBool,
    ssock_r: arc_swap::ArcSwap<Py<PyAny>>,
    ssock_w: arc_swap::ArcSwap<Py<PyAny>>,
    threads_cb: usize,
    use_pyctx: bool,
}

impl Runtime {
    #[inline(always)]
    fn poll(
        &self,
        py: Python,
        state: &mut RuntimeState,
        events: &mut event::Events,
    ) -> std::result::Result<(), std::io::Error> {
        //: get proper poll timeout
        let mut sched_time: Option<u64> = None;
        {
            let guard_sched = self.handles_sched.lock().unwrap();
            if let Some(timer) = guard_sched.peek() {
                let tick = Instant::now().duration_since(self.epoch).as_micros();
                if timer.when > tick {
                    let dt = (timer.when - tick) as u64;
                    sched_time = Some(dt);
                }
            }
        }

        let poll_result = {
            py.detach(|| {
                let res = state.io.poll(events, sched_time.map(Duration::from_micros));
                if let Err(ref err) = res
                    && err.kind() == std::io::ErrorKind::Interrupted
                {
                    // if we got an interrupt, we retry ready events (as we might need to process signals)
                    let _ = state.io.poll(events, Some(Duration::from_millis(0)));
                }
                res
            })
        };

        //: handle events
        for event in events.iter() {
            if let Some(io_handle) = state.handles.remove(&event.token()) {
                match io_handle {
                    IOHandle::Py(handle) => self.handle_io_py(py, event, handle, state.io.registry()),
                    IOHandle::Signals => self.handle_io_signals(py, event, state),
                }
            }
        }

        //: handle timers
        {
            let mut guard_sched = self.handles_sched.lock().unwrap();
            if let Some(timer) = guard_sched.peek() {
                let tick = Instant::now().duration_since(self.epoch).as_micros();
                if timer.when <= tick {
                    while let Some(timer) = guard_sched.peek() {
                        if timer.when > tick {
                            break;
                        }
                        _ = self.channel_handle_send.send(Box::new(guard_sched.pop().unwrap()));
                    }
                }
            }
        }

        //: update registry from ops
        {
            let io_ops = self.io_ops.lock().unwrap();
            Self::registry_update(state, io_ops);
        }

        poll_result
    }

    #[inline(always)]
    fn registry_clean_from_token(registry: &mio::Registry, token: Token, interest: Option<Interest>) {
        let mut source = Source::FD(token.0.try_into().unwrap());
        _ = match interest {
            Some(interest) => registry.reregister(&mut source, token, interest),
            None => registry.deregister(&mut source),
        };
    }

    #[inline(always)]
    fn registry_update(state: &mut RuntimeState, mut ops: std::sync::MutexGuard<VecDeque<IOPyOp>>) {
        while let Some((token, interest, event)) = ops.pop_front() {
            if let Some(io_handle) = state.handles.get_mut(&token) {
                let IOHandle::Py(data) = io_handle else { unreachable!() };
                data.interest |= interest;
                match interest {
                    Interest::READABLE => data.reader = Some(event),
                    Interest::WRITABLE => data.writer = Some(event),
                    _ => unreachable!(),
                }
                let mut source = Source::FD(token.0.try_into().unwrap());
                _ = state.io.registry().reregister(&mut source, token, data.interest);
            } else {
                let io_handle = match interest {
                    Interest::READABLE => IOHandle::Py(PyHandleData {
                        interest,
                        reader: Some(event),
                        writer: None,
                    }),
                    Interest::WRITABLE => IOHandle::Py(PyHandleData {
                        interest,
                        reader: None,
                        writer: Some(event),
                    }),
                    _ => unreachable!(),
                };
                state.handles.insert(token, io_handle);
                let mut source = Source::FD(token.0.try_into().unwrap());
                _ = state.io.registry().register(&mut source, token, interest);
            }
        }
    }

    #[inline]
    fn handle_cb_loop(
        runtime: Py<Runtime>,
        handles: channel::Receiver<BoxedHandle>,
        sig: channel::Receiver<()>,
        cond: Arc<(Mutex<usize>, Condvar)>,
    ) {
        // println!("cb handle loop start");
        let mut state = RuntimeCBHandlerState {
            read_buf: vec![0; 262_144].into_boxed_slice(),
        };
        Python::attach(|py| {
            loop {
                if let Some(handle) = py.detach(|| {
                    channel::select_biased! {
                        recv(handles) -> msg => msg.ok(),
                        recv(sig) -> _ => None
                    }
                }) {
                    // println!("running handle");
                    handle.run(py, runtime.clone_ref(py), &mut state);
                    continue;
                }
                drop(runtime);
                break;
            }
        });

        // println!("cb handle loop stopping");
        let (lock, cvar) = &*cond;
        let mut pending = lock.lock().unwrap();
        *pending -= 1;
        cvar.notify_one();
        // println!("cb handle loop stopped");
    }

    fn stop_threads(&self, cond: Arc<(Mutex<usize>, Condvar)>) {
        // println!("terminating threads");
        for _ in 0..self.threads_cb {
            _ = self.channel_sig_send.send(());
        }
        let (lock, cvar) = &*cond;
        let _guard = cvar.wait_while(lock.lock().unwrap(), |pending| *pending > 0);
        // println!("all threads terminated");
    }

    #[inline(always)]
    fn read_from_sock(&self, socket: &mut socket2::Socket, buf: &mut [u8]) -> usize {
        let mut len = 0;
        loop {
            match socket.read(&mut buf[len..]) {
                Ok(readn) if readn > 0 => len += readn,
                Err(err) if err.kind() == std::io::ErrorKind::Interrupted => {}
                _ => break,
            }
        }
        len
    }

    #[inline(always)]
    fn new_interest_from_py_r(prev: &PyHandleData) -> Option<Interest> {
        if prev.interest == Interest::READABLE {
            return None;
        }
        Some(Interest::WRITABLE)
    }

    #[inline(always)]
    fn new_interest_from_py_w(prev: &PyHandleData) -> Option<Interest> {
        if prev.interest == Interest::WRITABLE {
            return None;
        }
        Some(Interest::READABLE)
    }

    #[inline(always)]
    fn handle_io_py(&self, py: Python, event: &event::Event, handle: PyHandleData, registry: &mio::Registry) {
        if let Some(reader) = &handle.reader
            && (event.is_readable() || event.is_read_closed())
        {
            Self::registry_clean_from_token(registry, event.token(), Self::new_interest_from_py_r(&handle));
            _ = self.channel_handle_send.send(Box::new(reader.clone_ref(py)));
        }
        if let Some(writer) = &handle.writer
            && (event.is_writable() || event.is_write_closed())
        {
            Self::registry_clean_from_token(registry, event.token(), Self::new_interest_from_py_w(&handle));
            _ = self.channel_handle_send.send(Box::new(writer.clone_ref(py)));
        }
    }

    #[inline(always)]
    fn handle_io_signals(&self, py: Python, event: &event::Event, state: &mut RuntimeState) {
        let sock = &mut state.sig_sock.0;
        let read = self.read_from_sock(sock, &mut state.buf);
        if read > 0 && self.sig_listening.load(atomic::Ordering::Relaxed) {
            for sig in &state.buf[..read] {
                if let Some(event) = self.sig_handlers.pin().get(sig) {
                    self.sig_loop_handled.store(true, atomic::Ordering::Relaxed);
                    _ = self.channel_handle_send.send(Box::new(event.clone_ref(py)));
                }
            }
        }
        state.handles.insert(event.token(), IOHandle::Signals);
    }

    fn init_sig_socket(
        &self,
        py: Python,
        registry: &mio::Registry,
        handles: &mut HashMap<Token, IOHandle>,
    ) -> anyhow::Result<(socket2::Socket, socket2::Socket)> {
        let fdr: usize = self
            .ssock_r
            .load()
            .call_method0(py, pyo3::intern!(py, "fileno"))?
            .extract(py)?;
        let fdw: usize = self
            .ssock_w
            .load()
            .call_method0(py, pyo3::intern!(py, "fileno"))?
            .extract(py)?;
        let socks = unsafe {
            (
                #[allow(clippy::cast_possible_wrap)]
                socket2::Socket::from_raw_fd(fdr as i32),
                #[allow(clippy::cast_possible_wrap)]
                socket2::Socket::from_raw_fd(fdw as i32),
            )
        };

        let token = Token(fdr);
        let mut source = Source::FD(fdr.try_into()?);
        let interest = Interest::READABLE;

        handles.insert(token, IOHandle::Signals);
        registry.register(&mut source, token, interest)?;

        Ok(socks)
    }

    fn drop_sig_socket(&self, py: Python, mut state: RuntimeState) -> anyhow::Result<()> {
        let fd: usize = self
            .ssock_r
            .load()
            .call_method0(py, pyo3::intern!(py, "fileno"))?
            .extract(py)?;
        let token = Token(fd);
        if let Some(IOHandle::Signals) = state.handles.remove(&token) {
            #[allow(clippy::cast_possible_wrap)]
            let mut source = Source::FD(fd as i32);
            state.io.registry().deregister(&mut source)?;
        }

        Ok(())
    }

    #[inline(always)]
    fn wake(&self) {
        _ = self.waker.load().as_ref().map(|v| v.wake());
    }

    pub fn add_handle(&self, handle: BoxedHandle) {
        _ = self.channel_handle_send.send(handle);
    }

    pub fn add_timer(&self, timer: Timer) {
        {
            let mut guard = self.handles_sched.lock().unwrap();
            guard.push(timer);
        }
        self.wake();
    }
}

#[pymethods]
impl Runtime {
    #[new]
    pub(crate) fn new(
        py: Python,
        threads: usize,
        threads_blocking: usize,
        threads_blocking_timeout: u64,
        context: bool,
        signals: Vec<u8>,
    ) -> Self {
        let (channel_handle_send, channel_handle_recv) = channel::unbounded();
        let (channel_sig_send, channel_sig_recv) = channel::bounded(threads);

        let mut sig_set = std::collections::HashSet::with_capacity(signals.len());
        for sig in signals {
            sig_set.insert(sig);
        }

        Self {
            io_ops: Mutex::new(VecDeque::with_capacity(16)),
            waker: None.into(),
            handles_sched: Mutex::new(BinaryHeap::with_capacity(32)),
            blocking_pool: BlockingRunnerPool::new(threads_blocking, threads_blocking_timeout),
            channel_handle_send,
            channel_handle_recv,
            channel_sig_send,
            channel_sig_recv,
            epoch: Instant::now(),
            // ssock: RwLock::new(None),
            closed: atomic::AtomicBool::new(false),
            sig_set,
            sig_wfd: arc_swap::ArcSwap::new(py.None().into()),
            sig_handlers: papaya::HashMap::with_capacity(32),
            sig_listening: atomic::AtomicBool::new(false),
            sig_loop_handled: atomic::AtomicBool::new(false),
            // sig_wfd: RwLock::new(py.None()),
            stopping: atomic::AtomicBool::new(false),
            ssock_r: arc_swap::ArcSwap::new(py.None().into()),
            ssock_w: arc_swap::ArcSwap::new(py.None().into()),
            threads_cb: threads,
            use_pyctx: context,
        }
    }

    #[getter(_clock)]
    pub(crate) fn _get_clock(&self) -> u128 {
        Instant::now().duration_since(self.epoch).as_micros()
    }

    #[getter(_closed)]
    fn _get_closed(&self) -> bool {
        self.closed.load(atomic::Ordering::Acquire)
    }

    #[setter(_closed)]
    fn _set_closed(&self, val: bool) {
        self.closed.store(val, atomic::Ordering::Release);
    }

    #[getter(_stopping)]
    fn _get_stopping(&self) -> bool {
        self.stopping.load(atomic::Ordering::Acquire)
    }

    #[setter(_stopping)]
    fn _set_stopping(&self, val: bool) {
        // println!("SET STOP");
        self.stopping.store(val, atomic::Ordering::Release);
        self.wake();
    }

    #[getter(_sig_listening)]
    fn _get_sig_listening(&self) -> bool {
        self.sig_listening.load(atomic::Ordering::Relaxed)
    }

    #[setter(_sig_listening)]
    fn _set_sig_listening(&self, val: bool) {
        self.sig_listening.store(val, atomic::Ordering::Relaxed);
    }

    #[getter(_sig_wfd)]
    fn _get_sig_wfd(&self, py: Python) -> Py<PyAny> {
        self.sig_wfd.load().clone_ref(py)
    }

    #[setter(_sig_wfd)]
    fn _set_sig_wfd(&self, val: Py<PyAny>) {
        self.sig_wfd.swap(val.into());
    }

    #[getter(_sigset)]
    fn _get_sigset(&self) -> Vec<&u8> {
        self.sig_set.iter().collect()
    }

    #[getter(_ssock_r)]
    fn _get_ssock_r(&self, py: Python) -> Py<PyAny> {
        self.ssock_r.load().clone_ref(py)
    }

    #[setter(_ssock_r)]
    fn _set_ssock_r(&self, val: Py<PyAny>) {
        self.ssock_r.swap(val.into());
    }

    #[getter(_ssock_w)]
    fn _get_ssock_w(&self, py: Python) -> Py<PyAny> {
        self.ssock_w.load().clone_ref(py)
    }

    #[setter(_ssock_w)]
    fn _set_ssock_w(&self, val: Py<PyAny>) {
        self.ssock_w.swap(val.into());
    }

    fn _spawn_pygen(&self, py: Python, coro: Py<PyAny>) {
        if self.use_pyctx {
            let ctx = unsafe {
                let ret = pyo3::ffi::PyContext_CopyCurrent();
                Bound::from_owned_ptr(py, ret).unbind()
            };
            self.add_handle(Box::new(crate::handles::PyGenCtxHandle::new(py, coro, ctx)));
            return;
        }
        self.add_handle(Box::new(crate::handles::PyGenHandle::new(py, coro)));
    }

    fn _spawn_pyasyncgen(&self, py: Python, coro: Py<PyAny>) {
        if self.use_pyctx {
            let ctx = unsafe {
                let ret = pyo3::ffi::PyContext_CopyCurrent();
                Bound::from_owned_ptr(py, ret).unbind()
            };
            self.add_handle(Box::new(crate::handles::PyAsyncGenCtxHandle::new(py, coro, ctx)));
            return;
        }
        self.add_handle(Box::new(crate::handles::PyAsyncGenHandle::new(py, coro)));
    }

    #[pyo3(signature = (f, *args, **kwargs))]
    fn _spawn_blocking(
        &self,
        py: Python,
        f: Py<PyAny>,
        args: Py<PyAny>,
        kwargs: Option<Py<PyAny>>,
    ) -> PyResult<(
        Py<crate::blocking::BlockingTaskCtl>,
        Py<crate::events::Event>,
        Py<crate::events::ResultHolder>,
    )> {
        let ctx = match self.use_pyctx {
            true => unsafe {
                let ret = pyo3::ffi::PyContext_CopyCurrent();
                let bound = Bound::from_owned_ptr(py, ret).unbind();
                Some(bound)
            },
            false => None,
        };
        let (task, ctl, event, rh) = crate::blocking::BlockingTask::new(py, f, args, kwargs, ctx);
        self.blocking_pool
            .run(task)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok((ctl, event, rh))
    }

    #[pyo3(signature = (fd))]
    fn _io_event_r(&self, py: Python, fd: usize) -> PyResult<Py<crate::events::Event>> {
        let token = Token(fd);
        let event = Py::new(py, crate::events::Event::new())?;
        {
            let mut ops = self.io_ops.lock().unwrap();
            ops.push_back((token, Interest::READABLE, event.clone_ref(py)));
        }

        self.wake();
        Ok(event)
    }

    #[pyo3(signature = (fd))]
    fn _io_event_w(&self, py: Python, fd: usize) -> PyResult<Py<crate::events::Event>> {
        let token = Token(fd);
        let event = Py::new(py, crate::events::Event::new())?;
        {
            let mut ops = self.io_ops.lock().unwrap();
            ops.push_back((token, Interest::WRITABLE, event.clone_ref(py)));
        }

        self.wake();
        Ok(event)
    }

    fn _sig_add(&self, py: Python, sig: u8) -> PyResult<Py<crate::events::Event>> {
        let event = Py::new(py, crate::events::Event::new())?;
        self.sig_handlers.pin().insert(sig, event.clone_ref(py));
        Ok(event)
    }

    fn _sig_rem(&self, sig: u8) -> bool {
        self.sig_handlers.pin().remove(&sig).is_some()
    }

    fn _run(pyself: Py<Self>, py: Python) -> PyResult<()> {
        let rself = pyself.get();
        let mut handles = HashMap::with_capacity(128);
        let poll = Poll::new()?;
        let waker = Waker::new(poll.registry(), Token(0))?;
        let sig_sock = rself.init_sig_socket(py, poll.registry(), &mut handles)?;
        let mut events = event::Events::with_capacity(128);
        let mut state = RuntimeState {
            buf: vec![0; 4096].into_boxed_slice(),
            io: poll,
            handles,
            sig_sock,
        };

        rself.waker.swap(Some(Arc::new(waker)));

        let threads_cb_cvar = Arc::new((Mutex::new(rself.threads_cb), Condvar::new()));
        for _ in 0..rself.threads_cb {
            let runtime = pyself.clone_ref(py);
            let chan_handle = rself.channel_handle_recv.clone();
            let chan_sig = rself.channel_sig_recv.clone();
            let cvar = threads_cb_cvar.clone();
            thread::spawn(|| Self::handle_cb_loop(runtime, chan_handle, chan_sig, cvar));
        }

        loop {
            if rself.stopping.load(atomic::Ordering::Acquire) {
                break;
            }
            if let Err(err) = rself.poll(py, &mut state, &mut events) {
                if err.kind() == std::io::ErrorKind::Interrupted {
                    if rself.sig_loop_handled.swap(false, atomic::Ordering::Relaxed) {
                        continue;
                    }
                    break;
                }
                rself.stop_threads(threads_cb_cvar);
                return Err(err.into());
            }
        }

        _ = rself.drop_sig_socket(py, state);
        rself.stop_threads(threads_cb_cvar);
        rself.waker.swap(None);
        // rself.stopping.store(false, atomic::Ordering::Release);
        Ok(())
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Runtime>()?;

    Ok(())
}
