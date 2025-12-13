use crossbeam_channel as channel;
use pyo3::prelude::*;
use std::{
    sync::{Arc, atomic},
    thread, time,
};

use crate::events::{Event, ResultHolder};

pub(crate) struct BlockingTask {
    event: Py<Event>,
    result: Py<ResultHolder>,
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
    ) -> (Self, Py<Event>, Py<ResultHolder>) {
        let event = Py::new(py, Event::new()).unwrap();
        let rh = Py::new(py, ResultHolder::new(py, 1)).unwrap();
        let task = Self {
            event: event.clone_ref(py),
            result: rh.clone_ref(py),
            target,
            args,
            kwargs,
        };
        (task, event, rh)
    }

    fn run(self, py: Python) {
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
                self.result.get().store(v.unbind(), None);
            }
            Err(err) => {
                // TODO: handle possible cancellation, need to raise
                self.result.get().store(err.value(py).as_any().clone().unbind(), None);
            }
        }

        self.event.get().set(py);
    }
}

pub(crate) struct BlockingRunnerPool {
    birth: time::Instant,
    queue: channel::Sender<BlockingTask>,
    tq: channel::Receiver<BlockingTask>,
    threads: Arc<atomic::AtomicUsize>,
    tmax: usize,
    idle_timeout: time::Duration,
    spawning: atomic::AtomicBool,
    spawn_tick: atomic::AtomicU64,
}

impl BlockingRunnerPool {
    pub fn new(max_threads: usize, idle_timeout: u64) -> Self {
        let (qtx, qrx) = channel::unbounded();
        Self {
            queue: qtx,
            tq: qrx.clone(),
            threads: Arc::new(1.into()),
            tmax: max_threads,
            birth: time::Instant::now(),
            spawning: false.into(),
            spawn_tick: 0.into(),
            idle_timeout: time::Duration::from_secs(idle_timeout),
        }
    }

    #[inline(always)]
    fn spawn_thread(&self) {
        let tick = self.birth.elapsed().as_micros() as u64;
        if tick - self.spawn_tick.load(atomic::Ordering::Relaxed) < 350 {
            return;
        }
        if self
            .spawning
            .compare_exchange(false, true, atomic::Ordering::Relaxed, atomic::Ordering::Relaxed)
            .is_err()
        {
            return;
        }

        let queue = self.tq.clone();
        let tcount = self.threads.clone();
        let timeout = self.idle_timeout;
        thread::spawn(move || {
            tcount.fetch_add(1, atomic::Ordering::Release);
            blocking_worker(queue, timeout);
            tcount.fetch_sub(1, atomic::Ordering::Release);
        });

        self.spawn_tick
            .store(self.birth.elapsed().as_micros() as u64, atomic::Ordering::Relaxed);
        self.spawning.store(false, atomic::Ordering::Relaxed);
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
