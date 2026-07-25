import os

from .._fd import FdStream as _FdStream
from ..exceptions import ResourceBroken


class FdStream(_FdStream):
    async def send_all(self, data: bytes | bytearray | memoryview):
        if self._fd.closed:
            raise RuntimeError('file closed')

        fd = self.fileno()
        with self._lock_w.or_raise():
            with memoryview(data) as data:
                if not data:
                    return

                sent = 0
                while sent < len(data):
                    with data[sent:] as remaining:
                        while True:
                            if (waiter := self._fd._io_arm_w()) is not None:
                                await waiter
                                continue

                            try:
                                sent += os.write(fd, remaining)
                            except BlockingIOError, InterruptedError:
                                self._fd._io_clear_w()
                                continue
                            except BrokenPipeError as exc:
                                raise ResourceBroken from exc
                            except BaseException as exc:
                                raise exc
                            else:
                                break

    async def receive_some(self, max_bytes: int | None = None) -> bytes:
        max_bytes = max_bytes or 65536
        if self._fd.closed:
            raise RuntimeError('file closed')

        fd = self.fileno()
        with self._lock_r.or_raise():
            while True:
                if (waiter := self._fd._io_arm_r()) is not None:
                    await waiter
                    continue

                try:
                    data = os.read(fd, max_bytes)
                except BlockingIOError, InterruptedError:
                    self._fd._io_clear_r()
                    continue
                except BaseException as exc:
                    raise exc
                else:
                    break

        return data
