import os

from ..._fd._win import FdStream as _FdStream
from ...exceptions import ResourceBroken
from .._ctl import spawn_blocking


class FdStream(_FdStream):
    async def send_all(self, data: bytes | bytearray | memoryview):
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
                            sent += await spawn_blocking(os.write, fd, remaining)
                        except BrokenPipeError as exc:
                            raise ResourceBroken from exc

    async def receive_some(self, max_bytes: int | None = None) -> bytes:
        max_bytes = max_bytes or 65536
        if self._fd == -1:
            raise RuntimeError('file closed')

        fd = self._fd
        with self._lock_r.or_raise():
            data = await spawn_blocking(os.read, fd, max_bytes)

        return data
