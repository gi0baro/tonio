mod py;
pub(crate) mod schedule;

#[cfg(unix)]
pub(crate) type RawFd = std::os::fd::RawFd;
#[cfg(windows)]
pub(crate) type RawFd = std::os::windows::io::RawSocket;

// NOTE: I/O tokens are the exposed addresses of the `Arc<T>` entries, where T
//       is 128-byte aligned, so no address can collide with these
pub(crate) const TOKEN_WAKER: usize = 0;
pub(crate) const TOKEN_SIGNALS: usize = 1;

pub(crate) use py::init_pymodule;
