use crossbeam_channel as channel;
use pyo3::{PyTypeInfo, prelude::*};
use std::{
    sync::{Arc, atomic},
    thread, time,
};

use crate::errors::CancelledError;
use crate::events::{Event, ResultHolder};

#[derive(Clone, Copy)]
#[repr(u8)]
enum TaskState {
    Queued,
    Running,
    Cancelled,
    Done,
}

struct BlockingTaskState(atomic::AtomicU8);

impl BlockingTaskState {
    #[inline(always)]
    const fn new(state: TaskState) -> Self {
        Self(atomic::AtomicU8::new(state as u8))
    }

    #[inline(always)]
    fn is(&self, state: TaskState) -> bool {
        self.0.load(atomic::Ordering::Acquire) == state as u8
    }

    #[inline(always)]
    fn store(&self, state: TaskState) {
        self.0.store(state as u8, atomic::Ordering::Release);
    }

    #[inline]
    fn transition(&self, from: TaskState, to: TaskState) -> bool {
        self.0
            .compare_exchange(
                from as u8,
                to as u8,
                atomic::Ordering::AcqRel,
                atomic::Ordering::Acquire,
            )
            .is_ok()
    }
}

#[pyclass(frozen, module = "tonio._tonio")]
pub(crate) struct BlockingTaskCtl {
    state: BlockingTaskState,
    tid: atomic::AtomicUsize,
    event: Py<Event>,
    result: Py<ResultHolder>,
}

impl BlockingTaskCtl {
    #[inline(always)]
    fn store_ok(&self, py: Python, value: Py<PyAny>) {
        let result = self.result.get();
        result.store(pyo3::types::PyBool::new(py, false).as_any().clone().unbind(), Some(0));
        result.store(value, Some(1));
    }

    #[inline(always)]
    fn store_err(&self, py: Python, err: &PyErr) {
        let result = self.result.get();
        result.store(pyo3::types::PyBool::new(py, true).as_any().clone().unbind(), Some(0));
        result.store(err.value(py).as_any().clone().unbind(), Some(1));
    }

    #[inline(always)]
    fn notify(&self, py: Python) {
        self.event.get().set(py);
    }

    #[inline(always)]
    fn begin(&self, py: Python) -> bool {
        //: published before the transition so anything observing `Running` sees a usable tid
        self.tid.store(
            crate::py::thread_ident(py).unwrap().try_into().unwrap(),
            atomic::Ordering::Release,
        );
        if self.state.transition(TaskState::Queued, TaskState::Running) {
            return true;
        }
        self.tid.store(0, atomic::Ordering::Release);
        false
    }

    #[inline(always)]
    fn finish(&self) {
        self.tid.store(0, atomic::Ordering::Release);
        self.state.store(TaskState::Done);
    }
}

#[pymethods]
impl BlockingTaskCtl {
    fn abort(&self, py: Python) {
        if self.state.transition(TaskState::Queued, TaskState::Cancelled) {
            self.store_err(py, &crate::errors::abort());
            self.notify(py);
            return;
        }

        if self.state.is(TaskState::Running) {
            let tid = self.tid.load(atomic::Ordering::Acquire);
            if tid > 0 {
                let err = CancelledError::type_object(py);
                unsafe {
                    pyo3::ffi::PyThreadState_SetAsyncExc(tid.cast_signed().try_into().unwrap(), err.as_ptr());
                }
            }
        }
    }
}

pub(crate) struct BlockingTask {
    ctl: Py<BlockingTaskCtl>,
    target: Py<PyAny>,
    args: Py<PyAny>,
    kwargs: Option<Py<PyAny>>,
    ctx: Option<Py<PyAny>>,
}

impl BlockingTask {
    pub fn new(
        py: Python,
        target: Py<PyAny>,
        args: Py<PyAny>,
        kwargs: Option<Py<PyAny>>,
        ctx: Option<Py<PyAny>>,
    ) -> (Self, Py<BlockingTaskCtl>, Py<Event>, Py<ResultHolder>) {
        let event = Py::new(py, Event::new()).unwrap();
        let rh = Py::new(py, ResultHolder::new(py, 2)).unwrap();
        let ctl = Py::new(
            py,
            BlockingTaskCtl {
                state: BlockingTaskState::new(TaskState::Queued),
                tid: 0.into(),
                event: event.clone_ref(py),
                result: rh.clone_ref(py),
            },
        )
        .unwrap();
        let task = Self {
            ctl: ctl.clone_ref(py),
            target,
            args,
            kwargs,
            ctx,
        };
        (task, ctl, event, rh)
    }

    fn run(self, py: Python) {
        if !self.ctl.get().begin(py) {
            return;
        }

        let res = unsafe {
            let ctx = self.ctx.as_ref().map(Py::as_ptr);
            let callable = self.target.into_ptr();
            let args = self.args.into_ptr();
            if let Some(ctx) = ctx {
                pyo3::ffi::PyContext_Enter(ctx);
            }
            let ret = match self.kwargs {
                Some(kw) => pyo3::ffi::PyObject_Call(callable, args, kw.into_ptr()),
                None => pyo3::ffi::PyObject_CallObject(callable, args),
            };
            if let Some(ctx) = ctx {
                pyo3::ffi::PyContext_Exit(ctx);
            }
            Bound::from_owned_ptr_or_err(py, ret)
        };

        let ctl = self.ctl.get();
        match res {
            Ok(v) => ctl.store_ok(py, v.unbind()),
            Err(err) => ctl.store_err(py, &err),
        }
        ctl.finish();
        ctl.notify(py);
    }
}

pub(crate) struct BlockingRunnerPool {
    queue: channel::Sender<BlockingTask>,
    tq: channel::Receiver<BlockingTask>,
    threads: Arc<atomic::AtomicUsize>,
    tmax: usize,
    idle_timeout: time::Duration,
    load: Arc<atomic::AtomicIsize>,
}

impl BlockingRunnerPool {
    pub fn new(max_threads: usize, idle_timeout: u64) -> Self {
        let (qtx, qrx) = channel::unbounded();
        Self {
            queue: qtx,
            tq: qrx.clone(),
            threads: Arc::new(0.into()),
            tmax: max_threads,
            idle_timeout: time::Duration::from_secs(idle_timeout),
            load: Arc::new(0.into()),
        }
    }

    #[inline(always)]
    fn spawn_thread(&self) {
        if self.threads.fetch_add(1, atomic::Ordering::Relaxed) >= self.tmax {
            self.threads.fetch_sub(1, atomic::Ordering::Relaxed);
            return;
        }

        let queue = self.tq.clone();
        let timeout = self.idle_timeout;
        let load = self.load.clone();
        let tcount = self.threads.clone();
        thread::spawn(move || blocking_worker(queue, timeout, load, tcount));
    }

    #[inline]
    pub fn run(&self, task: BlockingTask) -> Result<(), channel::SendError<BlockingTask>> {
        self.queue.send(task)?;
        let threads = self.threads.load(atomic::Ordering::SeqCst);
        if self.load.fetch_add(1, atomic::Ordering::Relaxed) >= 0 && threads < self.tmax {
            self.spawn_thread();
        }
        Ok(())
    }
}

fn blocking_worker(
    queue: channel::Receiver<BlockingTask>,
    timeout: time::Duration,
    load: Arc<atomic::AtomicIsize>,
    tcount: Arc<atomic::AtomicUsize>,
) {
    Python::attach(|py| {
        let tid = crate::py::thread_ident(py).unwrap();

        while let Ok(task) = py.detach(|| {
            load.fetch_sub(1, atomic::Ordering::Relaxed);
            let mut res = queue.recv_timeout(timeout);
            load.fetch_add(1, atomic::Ordering::Relaxed);
            if res.is_err() {
                tcount.fetch_sub(1, atomic::Ordering::SeqCst);
                if let Ok(task) = queue.try_recv() {
                    tcount.fetch_add(1, atomic::Ordering::SeqCst);
                    res = Ok(task);
                }
            }
            res
        }) {
            task.run(py);

            //: always cleanup threadstate async exc
            unsafe {
                pyo3::ffi::PyThreadState_SetAsyncExc(tid.try_into().unwrap(), std::ptr::null_mut());
            }
        }
    });
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<BlockingTaskCtl>()?;

    Ok(())
}
