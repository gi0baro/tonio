from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from ..._streams import _Stream
from ..._subprocess._win import Process as _Process
from .._ctl import spawn_blocking
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

        self.args: StrOrBytesPath | Sequence[StrOrBytesPath] = self._proc.args
        self.pid: int = self._proc.pid

    async def wait(self) -> int:
        async with self._wait_lock:
            if self.poll() is None:
                await spawn_blocking(self._proc.wait)

        return self._proc.returncode
