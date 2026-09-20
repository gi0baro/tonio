from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Final

from .._fd._unix import ProcFd, open_proc_fd
from .._streams import _Stream
from .._sync import Lock
from .._types import Coro


if TYPE_CHECKING:
    import signal
    from collections.abc import Sequence

    from . import StrOrBytesPath


class Process:
    universal_newlines: Final = False
    encoding: Final = None
    errors: Final = None

    def __init__(
        self,
        popen: subprocess.Popen[bytes],
        stdin: _Stream | None,
        stdout: _Stream | None,
        stderr: _Stream | None,
    ) -> None:
        self._proc = popen
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

        self.stdio: tuple[_Stream, _Stream] | None = None
        if self.stdin is not None and self.stdout is not None:
            self.stdio = (self.stdin, self.stdout)

        self._wait_lock: Lock = Lock()

        self._pidfd: ProcFd | None = open_proc_fd(self._proc.pid)
        self.args: StrOrBytesPath | Sequence[StrOrBytesPath] = self._proc.args
        self.pid: int = self._proc.pid

    def __repr__(self) -> str:
        returncode = self.returncode
        if returncode is None:
            status = f'running with PID {self.pid}'
        else:
            if returncode < 0:
                status = f'exited with signal {-returncode}'
            else:
                status = f'exited with status {returncode}'
        return f'<tonio.Process {self.args!r}: {status}>'

    @property
    def returncode(self) -> int | None:
        result = self._proc.poll()
        if result is not None:
            self._close_pidfd()
        return result

    def _close_pidfd(self) -> None:
        if (pidfd := self._pidfd) is not None:
            pidfd.close()
            self._pidfd = None

    def wait(self) -> Coro[int]:
        with (yield self._wait_lock()):
            if self.poll() is None:
                if (pidfd := self._pidfd) is not None:
                    if (waiter := pidfd._io_arm_r()) is not None:
                        yield waiter
                else:
                    #: pidfd should never be None. but, apparently, on kqueue
                    #  there's a race condition where it says the process
                    #  doesn't exist before `waitpid` says it hasn't exited yet.
                    #  we do a runtime suspension to "mitigate" the next blocking wait.
                    yield
                self._proc.wait()
                self._close_pidfd()

        return self._proc.returncode

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, sig: signal.Signals | int) -> None:
        self._proc.send_signal(sig)

    def terminate(self) -> None:
        self._proc.terminate()

    def kill(self) -> None:
        self._proc.kill()
