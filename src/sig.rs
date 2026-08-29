pub(crate) struct SigMaskGuard(libc::sigset_t);

impl SigMaskGuard {
    pub(crate) fn block_sigchld() -> Self {
        unsafe {
            let mut set: libc::sigset_t = std::mem::zeroed();
            let mut old: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&raw mut set);
            libc::sigaddset(&raw mut set, libc::SIGCHLD);
            libc::pthread_sigmask(libc::SIG_BLOCK, &raw const set, &raw mut old);
            Self(old)
        }
    }
}

impl Drop for SigMaskGuard {
    fn drop(&mut self) {
        unsafe { libc::pthread_sigmask(libc::SIG_SETMASK, &raw const self.0, std::ptr::null_mut()) };
    }
}
