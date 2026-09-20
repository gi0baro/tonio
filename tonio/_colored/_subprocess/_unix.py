from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from ..._fd._unix import ProcFd, open_proc_fd
from ..._streams import _Stream
from ..._subprocess._unix import Process as _Process
from .. import yield_now
from .._sync import Lock


if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..._subprocess import StrOrBytesPath


class Process(_Process):
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

    async def wait(self) -> int:
        async with self._wait_lock:
            if self.poll() is None:
                if (pidfd := self._pidfd) is not None:
                    if (waiter := pidfd._io_arm_r()) is not None:
                        await waiter
                else:
                    #: pidfd should never be None. but, apparently, on kqueue
                    #  there's a race condition where it says the process
                    #  doesn't exist before `waitpid` says it hasn't exited yet.
                    #  we do a runtime suspension to "mitigate" the next blocking wait.
                    await yield_now()
                self._proc.wait()
                self._close_pidfd()

        return self._proc.returncode
