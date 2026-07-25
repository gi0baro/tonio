use std::{
    os::fd::{AsRawFd, FromRawFd, IntoRawFd, OwnedFd},
    sync::{Arc, Mutex},
};

use mio::Interest;
use pyo3::{exceptions::PyOSError, prelude::*};

use crate::{events::Waiter, io::schedule::ScheduledIO};

#[cfg(target_os = "linux")]
fn exit_fd(pid: i32) -> std::io::Result<OwnedFd> {
    let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid as libc::pid_t, 0 as libc::c_uint) };
    if fd < 0 {
        return Err(std::io::Error::last_os_error());
    }

    Ok(unsafe { OwnedFd::from_raw_fd(fd as i32) })
}

#[cfg(any(
    target_vendor = "apple",
    target_os = "freebsd",
    target_os = "netbsd",
    target_os = "openbsd",
    target_os = "dragonfly"
))]
fn exit_fd(pid: i32) -> std::io::Result<OwnedFd> {
    let kq = unsafe { libc::kqueue() };
    if kq < 0 {
        return Err(std::io::Error::last_os_error());
    }
    let kq = unsafe { OwnedFd::from_raw_fd(kq) };

    if unsafe { libc::fcntl(kq.as_raw_fd(), libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
        return Err(std::io::Error::last_os_error());
    }

    #[cfg(target_vendor = "apple")]
    let event = libc::kevent {
        ident: pid as libc::uintptr_t,
        filter: libc::EVFILT_PROC,
        flags: libc::EV_ADD | libc::EV_ONESHOT,
        fflags: libc::NOTE_EXIT,
        data: 0,
        udata: std::ptr::null_mut(),
    };
    #[cfg(not(target_vendor = "apple"))]
    let event = libc::kevent {
        ident: pid as libc::uintptr_t,
        filter: libc::EVFILT_PROC,
        flags: libc::EV_ADD | libc::EV_ONESHOT,
        fflags: libc::NOTE_EXIT,
        ..unsafe { std::mem::zeroed() }
    };

    let rv = unsafe {
        libc::kevent(
            kq.as_raw_fd(),
            &raw const event,
            1,
            std::ptr::null_mut(),
            0,
            std::ptr::null(),
        )
    };
    if rv < 0 {
        return Err(std::io::Error::last_os_error());
    }

    Ok(kq)
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub(crate) struct ProcFd {
    io: Arc<ScheduledIO>,
    inner: Mutex<Option<OwnedFd>>,
}

#[pymethods]
impl ProcFd {
    #[new]
    fn new(py: Python, pid: i32) -> PyResult<Self> {
        let inner = exit_fd(pid).map_err(|err| {
            err.raw_os_error().map_or_else(
                || PyOSError::new_err(err.to_string()),
                |errno| PyOSError::new_err((errno, err.to_string())),
            )
        })?;
        let runtime = crate::get_runtime(py)?;
        let io = runtime.get().io_register(inner.as_raw_fd(), Interest::READABLE)?;

        Ok(Self {
            io,
            inner: Mutex::new(Some(inner)),
        })
    }

    #[getter(fd)]
    fn _get_fd(&self) -> i32 {
        self.inner.lock().unwrap().as_ref().map_or(-1, AsRawFd::as_raw_fd)
    }

    fn _drop(&self) {
        if let Some(inner) = self.inner.lock().unwrap().take() {
            _ = inner.into_raw_fd();
        }
    }

    #[pyo3(signature = (timeout=None))]
    fn _io_arm_r(&self, py: Python, timeout: Option<usize>) -> PyResult<Option<Py<Waiter>>> {
        self.io.arm_r(py, timeout)
    }

    fn _io_close(&self, py: Python) {
        if let Ok(runtime) = crate::get_runtime(py) {
            runtime.get().io_deregister(&self.io);
        }
    }
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<ProcFd>()?;

    Ok(())
}
