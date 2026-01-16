use crossbeam_channel as channel;
use pyo3::{PyTypeInfo, prelude::*};
use std::{
    sync::{Arc, atomic},
    thread, time,
};

use crate::errors::CancelledError;
use crate::events::{Event, ResultHolder};

#[pyclass(frozen, module = "tonio._tonio")]
pub(crate) struct BlockingTaskCtl {
    tid: atomic::AtomicU64,
}

#[pymethods]
impl BlockingTaskCtl {
    fn abort(&self, py: Python) {
        let tid = self.tid.load(atomic::Ordering::Acquire);
        if tid > 0 {
            let err = CancelledError::type_object(py);
            unsafe {
                pyo3::ffi::PyThreadState_SetAsyncExc(tid.cast_signed(), err.as_ptr());
            }
        }
    }
}

pub(crate) struct BlockingTask {
    event: Py<Event>,
    result: Py<ResultHolder>,
    ctl: Py<BlockingTaskCtl>,
    target: Py<PyAny>,
    args: Py<PyAny>,
    kwargs: Option<Py<PyAny>>,
}

impl BlockingTask {
    pub fn new(
        py: Python,
        target: Py<PyAny>,
        args: Py<PyAny>,
        kwargs: Option<Py<PyAny>>,
    ) -> (Self, Py<BlockingTaskCtl>, Py<Event>, Py<ResultHolder>) {
        let event = Py::new(py, Event::new()).unwrap();
        let rh = Py::new(py, ResultHolder::new(py, 2)).unwrap();
        let ctl = Py::new(py, BlockingTaskCtl { tid: 0.into() }).unwrap();
        let task = Self {
            event: event.clone_ref(py),
            result: rh.clone_ref(py),
            ctl: ctl.clone_ref(py),
            target,
            args,
            kwargs,
        };
        (task, ctl, event, rh)
    }

    fn run(self, py: Python) {
        self.ctl
            .get()
            .tid
            .store(crate::py::thread_ident(py).unwrap(), atomic::Ordering::Release);

        match unsafe {
            let callable = self.target.into_ptr();
            let args = self.args.into_ptr();
            let ret = match self.kwargs {
                Some(kw) => pyo3::ffi::PyObject_Call(callable, args, kw.into_ptr()),
                None => pyo3::ffi::PyObject_CallObject(callable, args),
            };
            Bound::from_owned_ptr_or_err(py, ret)
        } {
            Ok(v) => {
                let result = self.result.get();
                result.store(pyo3::types::PyBool::new(py, false).as_any().clone().unbind(), Some(0));
                result.store(v.unbind(), Some(1));
            }
            Err(err) => {
                let result = self.result.get();
                result.store(pyo3::types::PyBool::new(py, true).as_any().clone().unbind(), Some(0));
                result.store(err.value(py).as_any().clone().unbind(), Some(1));
            }
        }

        self.event.get().set(py);
    }
}

pub(crate) struct BlockingRunnerPool {
    queue: channel::Sender<BlockingTask>,
    tq: channel::Receiver<BlockingTask>,
    threads: Arc<atomic::AtomicUsize>,
    tmax: usize,
    idle_timeout: time::Duration,
    spawning: atomic::AtomicBool,
}

impl BlockingRunnerPool {
    pub fn new(max_threads: usize, idle_timeout: u64) -> Self {
        let (qtx, qrx) = channel::unbounded();
        Self {
            queue: qtx,
            tq: qrx.clone(),
            threads: Arc::new(1.into()),
            tmax: max_threads,
            spawning: false.into(),
            idle_timeout: time::Duration::from_secs(idle_timeout),
        }
    }

    #[inline(always)]
    fn spawn_thread(&self) {
        if self
            .spawning
            .compare_exchange(false, true, atomic::Ordering::Release, atomic::Ordering::Relaxed)
            .is_err()
        {
            return;
        }

        self.threads.fetch_add(1, atomic::Ordering::Release);

        let queue = self.tq.clone();
        let tcount = self.threads.clone();
        let timeout = self.idle_timeout;
        thread::spawn(move || {
            blocking_worker(queue, timeout);
            tcount.fetch_sub(1, atomic::Ordering::Release);
        });

        self.spawning.store(false, atomic::Ordering::Release);
    }

    #[inline]
    pub fn run(&self, task: BlockingTask) -> Result<(), channel::SendError<BlockingTask>> {
        self.queue.send(task)?;
        if !self.queue.is_empty() && self.threads.load(atomic::Ordering::Acquire) < self.tmax {
            self.spawn_thread();
        }
        Ok(())
    }
}

fn blocking_worker(queue: channel::Receiver<BlockingTask>, timeout: time::Duration) {
    Python::attach(|py| {
        while let Ok(task) = py.detach(|| queue.recv_timeout(timeout)) {
            task.run(py);
        }
    });
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<BlockingTaskCtl>()?;

    Ok(())
}
