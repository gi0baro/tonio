use std::{
    cell::Cell,
    collections::BinaryHeap,
    io::Read,
    os::fd::FromRawFd,
    sync::{Arc, Condvar, Mutex, atomic},
    thread,
    time::{Duration, Instant},
};

use crossbeam_deque::{Injector, Worker};
use crossbeam_utils::sync::Parker;
use mio::{Interest, Poll, Token, Waker, event};
use pyo3::prelude::*;

use crate::{
    blocking::BlockingRunnerPool,
    handles::BoxedHandle,
    io::{
        TOKEN_SIGNALS, TOKEN_WAKER,
        schedule::{ScheduledIO, readiness_from_event},
        source::Source,
    },
    // py::copy_context,
    time::Timer,
    work::{LOCAL_WORKER, WorkSchedule, work_loop},
};

pub struct RuntimeState {
    buf: Box<[u8]>,
    io: Poll,
    sig_sock: (socket2::Socket, socket2::Socket),
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub struct Runtime {
    io_registrations: papaya::HashMap<usize, Arc<ScheduledIO>>,
    io_registry: arc_swap::ArcSwapOption<mio::Registry>,
    io_pending_release: Mutex<Vec<Arc<ScheduledIO>>>,
    io_needs_release: atomic::AtomicBool,
    waker: arc_swap::ArcSwapOption<Waker>,
    handles_sched: Mutex<BinaryHeap<Timer>>,
    blocking_pool: BlockingRunnerPool,
    //: `Injector` need to be Boxed as it exceeds the alignment CPython's object allocator gives a pyclass
    pub work_injector: Box<Injector<BoxedHandle>>,
    work_schedule: arc_swap::ArcSwapOption<WorkSchedule>,
    pub work_stopping: atomic::AtomicBool,
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
        //: release deregistered entries
        //  NOTE: This is the only place `Arc`s are dropped, and it runs strictly between poll batches:
        //        any token still in flight from the previous batch stayed valid through its dispatch,
        //        the kernel deregistration happened before the entry was parked,
        //        so no future batch can carry its token
        if self.io_needs_release.swap(false, atomic::Ordering::AcqRel) {
            self.io_pending_release.lock().unwrap().clear();
        }

        //: get proper poll timeout
        let mut sched_time: Option<u64> = None;
        {
            let guard_sched = self.handles_sched.lock().unwrap();
            if let Some(timer) = guard_sched.peek() {
                let tick = Instant::now().duration_since(self.epoch).as_micros();
                sched_time = Some(if timer.when > tick {
                    (timer.when - tick) as u64
                } else {
                    0
                });
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
            match event.token().0 {
                TOKEN_WAKER => {}
                TOKEN_SIGNALS => self.handle_io_signals(py, state),
                token => {
                    //: get the handler from the token and compute our readiness word from the event
                    //  NOTE: the token is the exposed address of the Arc, kept alive at least until the release point
                    //        at the top of the loop cycle. Only the poll cycle can free deregistrations,
                    //        thus safety is guaranteed here.
                    let io = unsafe { &*std::ptr::with_exposed_provenance::<ScheduledIO>(token) };
                    let ready = readiness_from_event(event);
                    io.set_readiness(ready);
                    //: wake and schedule work
                    let (reader, writer) = io.wake(ready);
                    if let Some(ev) = reader {
                        self.add_io_handle(Box::new(ev));
                    }
                    if let Some(ev) = writer {
                        self.add_io_handle(Box::new(ev));
                    }
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
                        self.defer_handle(Box::new(guard_sched.pop().unwrap()));
                    }
                }
            }
        }

        poll_result
    }

    pub(crate) fn io_register(&self, fd: i32) -> anyhow::Result<Arc<ScheduledIO>> {
        let registry = self.io_registry.load_full().expect("runtime is not running");
        let io = Arc::new(ScheduledIO::new(fd));
        let token = Arc::as_ptr(&io).expose_provenance();
        self.io_registrations.pin().insert(token, io.clone());
        let mut source = Source::FD(fd);
        if let Err(err) = registry.register(&mut source, Token(token), Interest::READABLE | Interest::WRITABLE) {
            self.io_registrations.pin().remove(&token);
            return Err(err.into());
        }
        Ok(io)
    }

    pub(crate) fn io_deregister(&self, io: &Arc<ScheduledIO>) {
        let token = Arc::as_ptr(io).expose_provenance();
        let regs = self.io_registrations.pin();
        if let Some(io) = regs.remove(&token) {
            if let Some(registry) = self.io_registry.load().as_ref() {
                let mut source = Source::FD(io.fd);
                _ = registry.deregister(&mut source);
            }
            //: shutdown any leftofer work
            let (reader, writer) = io.shutdown();
            if let Some(ev) = reader {
                self.add_io_handle(Box::new(ev));
            }
            if let Some(ev) = writer {
                self.add_io_handle(Box::new(ev));
            }
            //: add to the release queue
            self.io_pending_release.lock().unwrap().push(io.clone());
            self.io_needs_release.store(true, atomic::Ordering::Release);
        }
    }

    fn stop_threads(&self, cond: Arc<(Mutex<usize>, Condvar)>) {
        self.work_stopping.store(true, atomic::Ordering::Release);
        if let Some(sched) = self.work_schedule.load_full() {
            for unparker in &sched.unparkers {
                unparker.unpark();
            }
        }
        let (lock, cvar) = &*cond;
        let _guard = cvar.wait_while(lock.lock().unwrap(), |pending| *pending > 0);
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
    fn handle_io_signals(&self, py: Python, state: &mut RuntimeState) {
        let sock = &mut state.sig_sock.0;
        let read = self.read_from_sock(sock, &mut state.buf);
        if read > 0 && self.sig_listening.load(atomic::Ordering::Relaxed) {
            for sig in &state.buf[..read] {
                if let Some(event) = self.sig_handlers.pin().get(sig) {
                    self.sig_loop_handled.store(true, atomic::Ordering::Relaxed);
                    self.add_io_handle(Box::new(event.clone_ref(py)));
                }
            }
        }
    }

    fn init_sig_socket(
        &self,
        py: Python,
        registry: &mio::Registry,
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

        let mut source = Source::FD(fdr.try_into()?);

        registry.register(&mut source, Token(TOKEN_SIGNALS), Interest::READABLE)?;

        Ok(socks)
    }

    fn drop_sig_socket(&self, py: Python, state: &mut RuntimeState) -> anyhow::Result<()> {
        let fd: usize = self
            .ssock_r
            .load()
            .call_method0(py, pyo3::intern!(py, "fileno"))?
            .extract(py)?;
        #[allow(clippy::cast_possible_wrap)]
        let mut source = Source::FD(fd as i32);
        state.io.registry().deregister(&mut source)?;

        Ok(())
    }

    fn cleanup_io(&self, state: &mut RuntimeState) {
        let regs = self.io_registrations.pin();
        for (_, io) in &regs {
            let mut source = Source::FD(io.fd);
            _ = state.io.registry().deregister(&mut source);
            _ = io.shutdown();
        }
        regs.clear();
        self.io_needs_release.store(false, atomic::Ordering::Release);
        self.io_pending_release.lock().unwrap().clear();
    }

    fn teardown(&self, py: Python, state: &mut RuntimeState, threads_cvar: Arc<(Mutex<usize>, Condvar)>) {
        _ = self.drop_sig_socket(py, state);
        self.cleanup_io(state);
        self.stop_threads(threads_cvar);
        self.work_schedule.swap(None);
        self.waker.swap(None);
        self.io_registry.swap(None);
    }

    #[inline(always)]
    fn wake(&self) {
        _ = self.waker.load().as_ref().map(|v| v.wake());
    }

    pub fn add_handle(&self, handle: BoxedHandle) {
        let local = LOCAL_WORKER.with(Cell::get);
        if local.is_null() {
            self.work_injector.push(handle);
        } else {
            unsafe { (*local).push(handle) };
        }
        self.maybe_unpark_workers();
    }

    #[inline]
    pub fn add_io_handle(&self, handle: BoxedHandle) {
        self.work_injector.push(handle);
        if let Some(sched) = self.work_schedule.load().as_ref() {
            sched.unpark();
        }
    }

    pub fn defer_handle(&self, handle: BoxedHandle) {
        self.work_injector.push(handle);
        self.maybe_unpark_workers();
    }

    #[inline(always)]
    fn maybe_unpark_workers(&self) {
        if let Some(sched) = self.work_schedule.load().as_ref() {
            sched.unpark_one();
        }
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
        let mut sig_set = std::collections::HashSet::with_capacity(signals.len());
        for sig in signals {
            sig_set.insert(sig);
        }

        Self {
            io_registrations: papaya::HashMap::with_capacity(128),
            io_registry: None.into(),
            io_pending_release: Mutex::new(Vec::new()),
            io_needs_release: atomic::AtomicBool::new(false),
            waker: None.into(),
            handles_sched: Mutex::new(BinaryHeap::with_capacity(32)),
            blocking_pool: BlockingRunnerPool::new(threads_blocking, threads_blocking_timeout),
            work_injector: Box::new(Injector::new()),
            work_schedule: None.into(),
            work_stopping: atomic::AtomicBool::new(false),
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
        let poll = Poll::new()?;
        let waker = Waker::new(poll.registry(), Token(TOKEN_WAKER))?;
        let sig_sock = rself.init_sig_socket(py, poll.registry())?;
        let registry = poll.registry().try_clone()?;
        let mut events = event::Events::with_capacity(128);
        let mut state = RuntimeState {
            buf: vec![0; 4096].into_boxed_slice(),
            io: poll,
            sig_sock,
        };

        rself.io_registry.swap(Some(Arc::new(registry)));
        rself.waker.swap(Some(Arc::new(waker)));

        let n = rself.threads_cb;
        let mut workers = Vec::with_capacity(n);
        let mut parkers = Vec::with_capacity(n);
        let mut stealers = Vec::with_capacity(n);
        let mut unparkers = Vec::with_capacity(n);
        let mut idle_flags = Vec::with_capacity(n);
        for _ in 0..n {
            let worker = Worker::new_lifo();
            stealers.push(worker.stealer());
            workers.push(worker);
            let parker = Parker::new();
            unparkers.push(parker.unparker().clone());
            parkers.push(parker);
            idle_flags.push(atomic::AtomicBool::new(false));
        }
        let schedule = Arc::new(WorkSchedule::new(stealers, unparkers, idle_flags));
        rself.work_stopping.store(false, atomic::Ordering::Release);
        rself.work_schedule.swap(Some(schedule.clone()));

        let threads_cb_cvar = Arc::new((Mutex::new(n), Condvar::new()));
        for (idx, (worker, parker)) in workers.into_iter().zip(parkers).enumerate() {
            let runtime = pyself.clone_ref(py);
            let schedule = schedule.clone();
            let cvar = threads_cb_cvar.clone();
            thread::spawn(move || work_loop(schedule, runtime, idx, worker, parker, cvar));
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
                rself.teardown(py, &mut state, threads_cb_cvar);
                return Err(err.into());
            }
        }

        rself.teardown(py, &mut state, threads_cb_cvar);
        // rself.stopping.store(false, atomic::Ordering::Release);
        Ok(())
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<Runtime>()?;

    Ok(())
}
