use std::{
    cell::Cell,
    sync::{Arc, Condvar, Mutex, atomic},
};

use crossbeam_deque::{Injector, Steal, Stealer, Worker};
use crossbeam_utils::sync::{Parker, Unparker};
use pyo3::{Py, Python};

use crate::handles::BoxedHandle;
use crate::runtime::Runtime;

thread_local! {
    pub(crate) static LOCAL_WORKER: Cell<*const Worker<BoxedHandle>> = const { Cell::new(std::ptr::null()) };
}

pub(crate) struct WorkSchedule {
    stealers: Vec<Stealer<BoxedHandle>>,
    pub unparkers: Vec<Unparker>,
    idle_flags: Vec<atomic::AtomicBool>,
    idle_count: atomic::AtomicUsize,
    speculation: atomic::AtomicUsize,
}

impl WorkSchedule {
    pub fn new(
        stealers: Vec<Stealer<BoxedHandle>>,
        unparkers: Vec<Unparker>,
        idle_flags: Vec<atomic::AtomicBool>,
    ) -> Self {
        Self {
            stealers,
            unparkers,
            idle_flags,
            idle_count: atomic::AtomicUsize::new(0),
            speculation: atomic::AtomicUsize::new(0),
        }
    }

    #[inline(always)]
    fn set_idle(&self, idx: usize) {
        self.idle_flags[idx].store(true, atomic::Ordering::Release);
        self.idle_count.fetch_add(1, atomic::Ordering::AcqRel);
    }

    #[inline(always)]
    fn clear_idle(&self, idx: usize) -> bool {
        if self.idle_flags[idx]
            .compare_exchange(true, false, atomic::Ordering::AcqRel, atomic::Ordering::Relaxed)
            .is_ok()
        {
            self.idle_count.fetch_sub(1, atomic::Ordering::AcqRel);
            return true;
        }
        false
    }

    //: wake one parked worker to scan for work, with throttling.
    //  atomic order preservation is guaranteed by crossbeam-deque
    //  publish being SeqCst RMW.
    pub fn unpark_one(&self) {
        if self.idle_count.load(atomic::Ordering::Acquire) == 0 {
            return;
        }
        if self
            .speculation
            .compare_exchange(0, 1, atomic::Ordering::AcqRel, atomic::Ordering::Relaxed)
            .is_err()
        {
            return;
        }
        self.wake_idle();
    }

    //: "forcefully" a parked worker regardless of "speculation" state.
    pub fn unpark(&self) {
        if self.idle_count.load(atomic::Ordering::Acquire) == 0 {
            return;
        }
        self.speculation.fetch_add(1, atomic::Ordering::AcqRel);
        self.wake_idle();
    }

    #[inline(always)]
    fn wake_idle(&self) {
        for (i, flag) in self.idle_flags.iter().enumerate() {
            if flag
                .compare_exchange(true, false, atomic::Ordering::AcqRel, atomic::Ordering::Relaxed)
                .is_ok()
            {
                self.idle_count.fetch_sub(1, atomic::Ordering::AcqRel);
                self.unparkers[i].unpark();
                return;
            }
        }
        self.speculation.fetch_sub(1, atomic::Ordering::AcqRel);
    }
}

pub struct WorkerState {
    pub read_buf: Box<[u8]>,
}

pub(crate) fn find_work(
    worker: &Worker<BoxedHandle>,
    injector: &Injector<BoxedHandle>,
    stealers: &[Stealer<BoxedHandle>],
    idx: usize,
) -> Option<BoxedHandle> {
    if let Some(handle) = worker.pop() {
        return Some(handle);
    }

    loop {
        match injector.steal() {
            Steal::Success(handle) => return Some(handle),
            Steal::Retry => {}
            Steal::Empty => break,
        }
    }
    for (i, stealer) in stealers.iter().enumerate() {
        if i == idx {
            continue;
        }
        loop {
            match stealer.steal() {
                Steal::Success(handle) => return Some(handle),
                Steal::Retry => {}
                Steal::Empty => break,
            }
        }
    }
    None
}

#[inline]
pub(crate) fn work_loop(
    scheduler: Arc<WorkSchedule>,
    runtime: Py<Runtime>,
    idx: usize,
    worker: Worker<BoxedHandle>,
    mut parker: Parker,
    cond: Arc<(Mutex<usize>, Condvar)>,
) {
    LOCAL_WORKER.with(|c| c.set(&raw const worker));
    let mut state = WorkerState {
        read_buf: vec![0; 262_144].into_boxed_slice(),
    };

    Python::attach(|py| {
        let rself = runtime.get();
        let mut is_speculating = false;

        loop {
            if let Some(handle) = find_work(&worker, &rself.work_injector, &scheduler.stealers, idx) {
                if is_speculating {
                    is_speculating = false;
                    if scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel) == 1 {
                        scheduler.unpark_one();
                    }
                }
                handle.run(py, &runtime, &mut state);
                continue;
            }
            if rself.work_stopping.load(atomic::Ordering::Acquire) {
                if is_speculating {
                    scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel);
                }
                break;
            }

            //: nothing to run: advertise as idle and re-scan
            scheduler.set_idle(idx);
            if let Some(handle) = find_work(&worker, &rself.work_injector, &scheduler.stealers, idx) {
                if !scheduler.clear_idle(idx) {
                    //: a producer claimed our idle flag while we were scanning:
                    //  absorb the speculation token here
                    scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel);
                }
                if is_speculating {
                    is_speculating = false;
                    if scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel) == 1 {
                        scheduler.unpark_one();
                    }
                }
                handle.run(py, &runtime, &mut state);
                continue;
            }
            if rself.work_stopping.load(atomic::Ordering::Acquire) {
                scheduler.clear_idle(idx);
                if is_speculating {
                    scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel);
                }
                break;
            }

            //: stop speculating and park, unless a final scan find work
            if is_speculating {
                is_speculating = false;
                scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel);
                //: calls into `unpark_one` elide wakes while our search is active.
                //  A handle pushed during our last scan would be stranded, thus
                //  we need to re-scan after we released the token and actually park.
                if let Some(handle) = find_work(&worker, &rself.work_injector, &scheduler.stealers, idx) {
                    if !scheduler.clear_idle(idx) {
                        //: as before, absorb the speculation token if the flag was claimed
                        scheduler.speculation.fetch_sub(1, atomic::Ordering::AcqRel);
                    }
                    handle.run(py, &runtime, &mut state);
                    continue;
                }
            }
            parker = py.detach(move || {
                parker.park();
                parker
            });

            //: if we cleared our own idle flag, no producer claimed
            //  us this cycle: the park returned on a stale token left over from
            //  a cycle where we found work without parking, and thus there's no
            //  speculation involved.
            let claimed = !scheduler.clear_idle(idx);
            if rself.work_stopping.load(atomic::Ordering::Acquire) {
                break;
            }
            is_speculating = claimed;
        }

        LOCAL_WORKER.with(|c| c.set(std::ptr::null()));
        drop(runtime);
    });

    let (lock, cvar) = &*cond;
    let mut pending = lock.lock().unwrap();
    *pending -= 1;
    cvar.notify_one();
}
