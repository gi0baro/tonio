import contextlib
import errno
import signal
import threading

from ._tonio import CancelledError, get_runtime


class _SignalReceiver:
    __slots__ = ['_sigs', '_chr', '_chw', '_inner']

    def __init__(self, sigs):
        self._sigs = sigs

    def _init_channel(self):
        raise NotImplementedError

    def _register_coros(self, runtime):
        raise NotImplementedError

    def __enter__(self):
        self._chw, self._chr = self._init_channel()
        self._register_coros(get_runtime())
        return self

    def __exit__(self, exc_type, exc, tb):
        runtime = get_runtime()
        for sig in self._sigs:
            runtime._sig_rem(sig)
        with contextlib.suppress(CancelledError):
            self._inner.throw(CancelledError)

    def __iter__(self):
        return self

    def __aiter__(self):
        return self


def _noop(*args, **kwargs):
    return


def _is_main_thread():
    return threading.main_thread().ident == threading.current_thread().ident


def _check_sig(sig):
    if not isinstance(sig, int):
        raise TypeError(f'sig must be an int, not {sig!r}')

    if sig not in signal.valid_signals():
        raise ValueError(f'invalid signal number {sig}')


def _set_sig_wfd(fd):
    if fd >= 0:
        return signal.set_wakeup_fd(fd, warn_on_full_buffer=False)
    return signal.set_wakeup_fd(fd)


def _sig_add(sig):
    if not _is_main_thread():
        raise ValueError('Signals can only be handled from the main thread')

    _check_sig(sig)
    try:
        # register a dummy signal handler so Python will write the signal no in the wakeup fd
        signal.signal(sig, _noop)
        # set SA_RESTART to limit EINTR occurrences
        signal.siginterrupt(sig, False)
    except OSError as exc:
        if exc.errno == errno.EINVAL:
            raise RuntimeError(f'signum {sig} cannot be caught')
        raise


def _sig_rem(sig):
    if not _is_main_thread():
        raise ValueError('Signals can only be handled from the main thread')

    if sig == signal.SIGINT:
        handler = signal.default_int_handler
    else:
        handler = signal.SIG_DFL

    try:
        signal.signal(sig, handler)
    except OSError as exc:
        if exc.errno == errno.EINVAL:
            raise RuntimeError(f'signum {sig} cannot be caught')
        raise


def _signal_receiver(cls, *signals):
    for sig in signals:
        _check_sig(sig)
    return cls(signals)
