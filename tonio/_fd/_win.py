import os

from .._ctl import spawn_blocking
from .._streams import _Stream
from .._sync import Lock
from .._types import Coro
from ..exceptions import ResourceBroken


#: since Windows sucks, and readiness notifications exist only on sockets,
#  we fall-back to calling std blocking methods through the blocking pool.
class FdStream(_Stream):
    def __init__(self, fd: int):
        self._fd = fd
        self._lock_r = Lock()
        self._lock_w = Lock()

    def fileno(self) -> int:
        return self._fd

    def send_all(self, data: bytes | bytearray | memoryview) -> Coro[None]:
        if self._fd == -1:
            raise RuntimeError('file closed')

        fd = self._fd
        with self._lock_w.or_raise():
            with memoryview(data) as data:
                if not data:
                    return

                sent = 0
                while sent < len(data):
                    with data[sent:] as remaining:
                        try:
                            sent += yield spawn_blocking(os.write, fd, remaining)
                        except BrokenPipeError as exc:
                            raise ResourceBroken from exc

    def receive_some(self, max_bytes: int | None = None) -> Coro[bytes]:
        max_bytes = max_bytes or 65536
        if self._fd == -1:
            raise RuntimeError('file closed')

        fd = self._fd
        with self._lock_r.or_raise():
            data = yield spawn_blocking(os.read, fd, max_bytes)

        return data

    def close(self):
        if self._fd == -1:
            return
        fd, self._fd = self._fd, -1
        os.close(fd)

    def __del__(self) -> None:
        self.close()
