use std::{
    collections::{BinaryHeap, VecDeque},
    // io::Read,
    // mem,
    // os::fd::FromRawFd,
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

enum IOHandle {
    Py(PyHandleData),
    Signals,
}

enum PyHandle {
    Persisted(Py<crate::events::Event>),
    Once(Py<crate::events::Event>),
}

impl PyHandle {
    fn clone_ref(&self, py: Python) -> Self {
        match self {
            Self::Persisted(inner) => Self::Persisted(inner.clone_ref(py)),
            Self::Once(inner) => Self::Once(inner.clone_ref(py)),
        }
    }

    fn consume(&self, py: Python) -> (Py<crate::events::Event>, bool) {
        match self {
            Self::Persisted(inner) => (inner.clone_ref(py), false),
            Self::Once(inner) => (inner.clone_ref(py), true),
        }
    }
}

struct PyHandleData {
    interest: Interest,
    reader: Option<PyHandle>,
    writer: Option<PyHandle>,
}

enum IOHandleChange {
    Register((Source, Token, Interest)),
    Reregister((Source, Token, Interest)),
    Deregister(Source),
}

pub struct RuntimeState {
    // buf: Box<[u8]>,
    events: event::Events,
    // pub read_buf: Box<[u8]>,
    // tick_last: u128,
}

pub struct RuntimeCBHandlerState {
    pub read_buf: Box<[u8]>,
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub struct Runtime {
    // idle: atomic::AtomicBool,
    io: Mutex<Poll>,
    waker: Arc<Waker>,
    handles_io: papaya::HashMap<Token, IOHandle>,
    handles_io_changes: Mutex<VecDeque<IOHandleChange>>,
    handles_sched: Mutex<BinaryHeap<Timer>>,
    blocking_pool: BlockingRunnerPool,
    channel_handle_send: channel::Sender<BoxedHandle>,
    channel_handle_recv: channel::Receiver<BoxedHandle>,
    channel_sig_send: channel::Sender<()>,
    channel_sig_recv: channel::Receiver<()>,
    epoch: Instant,
    // ssock: RwLock<Option<(socket2::Socket, socket2::Socket)>>,
    closed: atomic::AtomicBool,
    // sig_handlers: papaya::HashMap<u8, ()>,
    sig_listening: atomic::AtomicBool,
    sig_loop_handled: atomic::AtomicBool,
    // sig_wfd: RwLock<Py<PyAny>>,
    stopping: atomic::AtomicBool,
    // ssock_r: RwLock<Py<PyAny>>,
    // ssock_w: RwLock<Py<PyAny>>,
    threads_cb: usize,
    use_pyctx: bool,
}

impl Runtime {
    #[inline]
    fn poll(&self, py: Python, state: &mut RuntimeState) -> std::result::Result<(), std::io::Error> {
        //: update registry
        {
            let io = self.io.lock().unwrap();
            let mut guard_io = self.handles_io_changes.lock().unwrap();
            while let Some(op) = guard_io.pop_front() {
                _ = match op {
                    IOHandleChange::Register(mut data) => io.registry().register(&mut data.0, data.1, data.2),
                    IOHandleChange::Reregister(mut data) => io.registry().reregister(&mut data.0, data.1, data.2),
                    IOHandleChange::Deregister(mut data) => io.registry().deregister(&mut data),
                };
            }
        }

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
            // self.idle.store(true, atomic::Ordering::Release);
            py.detach(|| {
                let mut io = self.io.lock().unwrap();
                let res = io.poll(&mut state.events, sched_time.map(Duration::from_micros));
                // self.idle.store(false, atomic::Ordering::Release);
                if let Err(ref err) = res
                    && err.kind() == std::io::ErrorKind::Interrupted
                {
                    // if we got an interrupt, we retry ready events (as we might need to process signals)
                    let _ = io.poll(&mut state.events, Some(Duration::from_millis(0)));
                }
                res
            })
        };

        //: handle events + cleanup
        let io_handles = self.handles_io.pin();
        let mut deregs = Vec::new();
        for event in &state.events {
            if let Some(io_handle) = io_handles.get(&event.token()) {
                match io_handle {
                    IOHandle::Py(handle) => self.handle_io_py(py, event, handle, &mut deregs),
                    IOHandle::Signals => panic!(),
                }
            }
        }
        drop(io_handles);
        for (fd, interest) in deregs {
            match interest {
                Interest::READABLE => self._reader_rem(py, fd),
                Interest::WRITABLE => self._writer_rem(py, fd),
                _ => unreachable!(),
            };
        }

        //: timers
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

        poll_result
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

    // #[inline(always)]
    // fn read_from_sock(&self, socket: &mut socket2::Socket, buf: &mut [u8]) -> usize {
    //     let mut len = 0;
    //     loop {
    //         match socket.read(&mut buf[len..]) {
    //             Ok(readn) if readn > 0 => len += readn,
    //             Err(err) if err.kind() == std::io::ErrorKind::Interrupted => {}
    //             _ => break,
    //         }
    //     }
    //     len
    // }

    #[inline]
    fn handle_io_py(
        &self,
        py: Python,
        event: &event::Event,
        handle: &PyHandleData,
        deregs: &mut Vec<(usize, Interest)>,
    ) {
        if let Some(reader) = &handle.reader
            && event.is_readable()
        {
            let (handle, consumed) = reader.consume(py);
            _ = self.channel_handle_send.send(Box::new(handle));
            if consumed {
                deregs.push((event.token().0, Interest::READABLE));
            }
        }
        if let Some(writer) = &handle.writer
            && event.is_writable()
        {
            let (handle, consumed) = writer.consume(py);
            _ = self.channel_handle_send.send(Box::new(handle));
            if consumed {
                deregs.push((event.token().0, Interest::WRITABLE));
            }
        }
    }

    // #[inline]
    // fn handle_io_signals(&self, py: Python, buf: &mut [u8]) {
    //     let mut sock_guard = self.ssock.write().unwrap();
    //     if let Some((socket, _)) = sock_guard.as_mut() {
    //         let read = self.read_from_sock(socket, buf);
    //         if read > 0 && self.sig_listening.load(atomic::Ordering::Relaxed) {
    //             for sig in &buf[..read] {
    //                 // self.sig_handle(py, *sig);
    //             }
    //         }
    //     }
    // }

    // #[inline]
    // fn sig_handle(&self, py: Python, sig: u8) {
    //     if let Some(handle) = self.sig_handlers.pin().get(&sig) {
    //         self.sig_loop_handled.store(true, atomic::Ordering::Relaxed);

    //         if handle.cancelled() {
    //             self._sig_rem(sig);
    //         } else {
    //             _ = self.channel_handle_send.send(Box::new(handle.clone_ref(py)));
    //         }
    //     }
    // }

    #[inline(always)]
    fn wake(&self) {
        // if self.idle.load(atomic::Ordering::Acquire) {
        //     // println!("WAKE UP");
        //     _ = self.waker.wake();
        // }
        _ = self.waker.wake();
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
        _py: Python,
        threads: usize,
        threads_blocking: usize,
        threads_blocking_timeout: u64,
        context: bool,
    ) -> PyResult<Self> {
        let poll = Poll::new()?;
        let waker = Waker::new(poll.registry(), Token(0))?;
        let (channel_handle_send, channel_handle_recv) = channel::unbounded();
        let (channel_sig_send, channel_sig_recv) = channel::bounded(threads);

        Ok(Self {
            // idle: atomic::AtomicBool::new(false),
            io: Mutex::new(poll),
            waker: Arc::new(waker),
            handles_io: papaya::HashMap::with_capacity(128),
            handles_io_changes: Mutex::new(VecDeque::with_capacity(16)),
            handles_sched: Mutex::new(BinaryHeap::with_capacity(32)),
            blocking_pool: BlockingRunnerPool::new(threads_blocking, threads_blocking_timeout),
            channel_handle_send,
            channel_handle_recv,
            channel_sig_send,
            channel_sig_recv,
            epoch: Instant::now(),
            // ssock: RwLock::new(None),
            closed: atomic::AtomicBool::new(false),
            // sig_handlers: papaya::HashMap::with_capacity(32),
            sig_listening: atomic::AtomicBool::new(false),
            sig_loop_handled: atomic::AtomicBool::new(false),
            // sig_wfd: RwLock::new(py.None()),
            stopping: atomic::AtomicBool::new(false),
            // ssock_r: RwLock::new(py.None()),
            // ssock_w: RwLock::new(py.None()),
            threads_cb: threads,
            use_pyctx: context,
        })
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

    // #[getter(_sig_wfd)]
    // fn _get_sig_wfd(&self, py: Python) -> Py<PyAny> {
    //     self.sig_wfd.read().unwrap().clone_ref(py)
    // }

    // #[setter(_sig_wfd)]
    // fn _set_sig_wfd(&self, val: Py<PyAny>) {
    //     let mut guard = self.sig_wfd.write().unwrap();
    //     *guard = val;
    // }

    // #[getter(_ssock_r)]
    // fn _get_ssock_r(&self, py: Python) -> Py<PyAny> {
    //     self.ssock_r.read().unwrap().clone_ref(py)
    // }

    // #[setter(_ssock_r)]
    // fn _set_ssock_r(&self, val: Py<PyAny>) {
    //     let mut guard = self.ssock_r.write().unwrap();
    //     *guard = val;
    // }

    // #[getter(_ssock_w)]
    // fn _get_ssock_w(&self, py: Python) -> Py<PyAny> {
    //     self.ssock_w.read().unwrap().clone_ref(py)
    // }

    // #[setter(_ssock_w)]
    // fn _set_ssock_w(&self, val: Py<PyAny>) {
    //     let mut guard = self.ssock_w.write().unwrap();
    //     *guard = val;
    // }

    // fn _ssock_set(&self, fd_r: usize, fd_w: usize) -> PyResult<()> {
    //     {
    //         let mut guard = self.ssock.write().unwrap();
    //         *guard = Some(unsafe {
    //             (
    //                 #[allow(clippy::cast_possible_wrap)]
    //                 socket2::Socket::from_raw_fd(fd_r as i32),
    //                 #[allow(clippy::cast_possible_wrap)]
    //                 socket2::Socket::from_raw_fd(fd_w as i32),
    //             )
    //         });
    //     }

    //     let token = Token(fd_r);
    //     let mut source = Source::FD(fd_r.try_into()?);
    //     let interest = Interest::READABLE;

    //     {
    //         let guard_poll = self.io.lock().unwrap();
    //         guard_poll.registry().register(&mut source, token, interest)?;
    //     }
    //     self.handles_io.pin().insert(token, IOHandle::Signals);

    //     Ok(())
    // }

    // fn _ssock_del(&self, fd_r: usize) -> PyResult<()> {
    //     let token = Token(fd_r);
    //     if let Some(IOHandle::Signals) = self.handles_io.pin().remove(&token) {
    //         #[allow(clippy::cast_possible_wrap)]
    //         let mut source = Source::FD(fd_r as i32);
    //         let guard_poll = self.io.lock().unwrap();
    //         guard_poll.registry().deregister(&mut source)?;
    //     }
    //     self.ssock.write().unwrap().take();

    //     Ok(())
    // }

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
    ) -> PyResult<(Py<crate::events::Event>, Py<crate::events::ResultHolder>)> {
        let (task, event, rh) = crate::blocking::BlockingTask::new(py, f, args, kwargs);
        self.blocking_pool
            .run(task)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        Ok((event, rh))
    }

    #[pyo3(signature = (fd, persisted = true))]
    fn _reader_add(&self, py: Python, fd: usize, persisted: bool) -> Py<crate::events::Event> {
        // println!("Runtime.reader_add {}", fd);
        let token = Token(fd);
        let event = Py::new(py, crate::events::Event::new()).unwrap();

        self.handles_io.pin().update_or_insert_with(
            token,
            |io_handle| {
                if let IOHandle::Py(data) = io_handle {
                    #[allow(clippy::cast_possible_wrap)]
                    let source = Source::FD(fd as i32);
                    let interest = data.interest | Interest::READABLE;
                    let reader = match persisted {
                        true => PyHandle::Persisted(event.clone_ref(py)),
                        false => PyHandle::Once(event.clone_ref(py)),
                    };
                    let mut guard_io = self.handles_io_changes.lock().unwrap();
                    guard_io.push_back(IOHandleChange::Reregister((source, token, data.interest)));
                    return IOHandle::Py(PyHandleData {
                        interest,
                        reader: Some(reader),
                        writer: Some(data.writer.as_ref().unwrap().clone_ref(py)),
                    });
                }
                unreachable!()
            },
            || {
                #[allow(clippy::cast_possible_wrap)]
                let source = Source::FD(fd as i32);
                let interest = Interest::READABLE;
                let reader = match persisted {
                    true => PyHandle::Persisted(event.clone_ref(py)),
                    false => PyHandle::Once(event.clone_ref(py)),
                };
                let mut guard_io = self.handles_io_changes.lock().unwrap();
                guard_io.push_back(IOHandleChange::Register((source, token, interest)));
                IOHandle::Py(PyHandleData {
                    interest,
                    reader: Some(reader),
                    writer: None,
                })
            },
        );
        self.wake();
        event
        // println!("Runtime.reader_add {} done", fd);
    }

    fn _reader_rem(&self, py: Python, fd: usize) -> bool {
        // println!("Runtime.reader_rem {}", fd);
        let token = Token(fd);

        let ret = match self.handles_io.pin().remove_if(&token, |_, io_handle| {
            if let IOHandle::Py(data) = io_handle {
                return data.interest == Interest::READABLE;
            }
            false
        }) {
            Ok(None) => false,
            Ok(_) => {
                #[allow(clippy::cast_possible_wrap)]
                let source = Source::FD(fd as i32);
                let mut guard_io = self.handles_io_changes.lock().unwrap();
                guard_io.push_back(IOHandleChange::Deregister(source));
                true
            }
            _ => {
                self.handles_io.pin().update(token, |io_handle| {
                    if let IOHandle::Py(data) = io_handle {
                        #[allow(clippy::cast_possible_wrap)]
                        let source = Source::FD(fd as i32);
                        let interest = Interest::WRITABLE;
                        let mut guard_io = self.handles_io_changes.lock().unwrap();
                        guard_io.push_back(IOHandleChange::Reregister((source, token, interest)));
                        return IOHandle::Py(PyHandleData {
                            interest,
                            reader: None,
                            writer: Some(data.writer.as_ref().unwrap().clone_ref(py)),
                        });
                    }
                    unreachable!()
                });
                true
            }
        };
        self.wake();
        // println!("Runtime.reader_rem {} done", fd);
        ret
    }

    #[pyo3(signature = (fd, persisted = true))]
    fn _writer_add(&self, py: Python, fd: usize, persisted: bool) -> Py<crate::events::Event> {
        // println!("Runtime.writer_add {}", fd);
        let token = Token(fd);
        let event = Py::new(py, crate::events::Event::new()).unwrap();

        self.handles_io.pin().update_or_insert_with(
            token,
            |io_handle| {
                if let IOHandle::Py(data) = io_handle {
                    #[allow(clippy::cast_possible_wrap)]
                    let source = Source::FD(fd as i32);
                    let interest = data.interest | Interest::WRITABLE;
                    let writer = match persisted {
                        true => PyHandle::Persisted(event.clone_ref(py)),
                        false => PyHandle::Once(event.clone_ref(py)),
                    };
                    let mut guard_io = self.handles_io_changes.lock().unwrap();
                    guard_io.push_back(IOHandleChange::Reregister((source, token, data.interest)));
                    return IOHandle::Py(PyHandleData {
                        interest,
                        reader: Some(data.reader.as_ref().unwrap().clone_ref(py)),
                        writer: Some(writer),
                    });
                }
                unreachable!()
            },
            || {
                #[allow(clippy::cast_possible_wrap)]
                let source = Source::FD(fd as i32);
                let interest = Interest::WRITABLE;
                let writer = match persisted {
                    true => PyHandle::Persisted(event.clone_ref(py)),
                    false => PyHandle::Once(event.clone_ref(py)),
                };
                let mut guard_io = self.handles_io_changes.lock().unwrap();
                guard_io.push_back(IOHandleChange::Register((source, token, interest)));
                IOHandle::Py(PyHandleData {
                    interest,
                    reader: None,
                    writer: Some(writer),
                })
            },
        );
        self.wake();
        event
        // println!("Runtime.writer_add {} done", fd);
    }

    fn _writer_rem(&self, py: Python, fd: usize) -> bool {
        // println!("Runtime.writer_rem {}", fd);
        let token = Token(fd);

        let ret = match self.handles_io.pin().remove_if(&token, |_, io_handle| {
            if let IOHandle::Py(data) = io_handle {
                return data.interest == Interest::WRITABLE;
            }
            false
        }) {
            Ok(None) => false,
            Ok(_) => {
                #[allow(clippy::cast_possible_wrap)]
                let source = Source::FD(fd as i32);
                let mut guard_io = self.handles_io_changes.lock().unwrap();
                guard_io.push_back(IOHandleChange::Deregister(source));
                true
            }
            _ => {
                self.handles_io.pin().update(token, |io_handle| {
                    if let IOHandle::Py(data) = io_handle {
                        let interest = Interest::READABLE;
                        #[allow(clippy::cast_possible_wrap)]
                        let source = Source::FD(fd as i32);
                        let mut guard_io = self.handles_io_changes.lock().unwrap();
                        guard_io.push_back(IOHandleChange::Reregister((source, token, interest)));
                        return IOHandle::Py(PyHandleData {
                            interest,
                            reader: Some(data.reader.as_ref().unwrap().clone_ref(py)),
                            writer: None,
                        });
                    }
                    unreachable!()
                });
                true
            }
        };
        self.wake();
        // println!("Runtime.writer_rem {} done", fd);
        ret
    }

    // fn _sig_add(&self, py: Python, sig: u8, callback: Py<PyAny>, args: Py<PyAny>, context: Py<PyAny>) {
    //     // let handle = Py::new(py, CBHandle::new(callback, args, context)).unwrap();
    //     // self.sig_handlers.pin().insert(sig, handle);
    // }

    // fn _sig_rem(&self, sig: u8) -> bool {
    //     self.sig_handlers.pin().remove(&sig).is_some()
    // }

    // fn _sig_clear(&self) {
    //     self.sig_handlers.pin().clear();
    // }

    fn _run(pyself: Py<Self>, py: Python) -> PyResult<()> {
        let rself = pyself.get();
        let mut state = RuntimeState {
            // buf: vec![0; 4096].into_boxed_slice(),
            events: event::Events::with_capacity(128),
        };

        let threads_cb_cvar = Arc::new((Mutex::new(rself.threads_cb), Condvar::new()));
        for _ in 0..rself.threads_cb {
            let runtime = pyself.clone_ref(py);
            let chan_handle = rself.channel_handle_recv.clone();
            let chan_sig = rself.channel_sig_recv.clone();
            let cvar = threads_cb_cvar.clone();
            thread::spawn(|| Runtime::handle_cb_loop(runtime, chan_handle, chan_sig, cvar));
        }

        loop {
            if rself.stopping.load(atomic::Ordering::Acquire) {
                break;
            }
            if let Err(err) = rself.poll(py, &mut state) {
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

        rself.stop_threads(threads_cb_cvar);
        // rself.stopping.store(false, atomic::Ordering::Release);
        Ok(())
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Runtime>()?;

    Ok(())
}
