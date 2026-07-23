import os

from ._streams import _Stream
from ._sync import Lock
from ._tonio import Fd as _Fd
from ._types import Coro


class Fd(_Fd):
    @property
    def closed(self) -> bool:
        return self.fd == -1

    def close(self) -> None:
        if self.closed:
            return
        fd = self.fd
        self._io_close()
        self._drop()
        os.close(fd)

    def __del__(self) -> None:
        self.close()


class FdStream(_Stream):
    def __init__(self, fd: int):
        self._fd = Fd(fd)
        self._lock_r = Lock()
        self._lock_w = Lock()

    def fileno(self) -> int:
        return self._fd.fd

    def send_all(self, data: bytes | bytearray | memoryview) -> Coro[None]:
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
                                yield waiter
                                continue

                            try:
                                sent += os.write(fd, remaining)
                            except BlockingIOError, InterruptedError:
                                self._fd._io_clear_w()
                                continue
                            except BaseException as exc:
                                raise exc
                            else:
                                break

    def receive_some(self, max_bytes: int | None = None) -> Coro[bytes]:
        max_bytes = max_bytes or 65536
        if self._fd.closed:
            raise RuntimeError('file closed')

        fd = self.fileno()
        with self._lock_r.or_raise():
            while True:
                if (waiter := self._fd._io_arm_r()) is not None:
                    yield waiter
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

    def _wait_readable(self) -> Coro[None]:
        if (waiter := self._fd._io_arm_r()) is not None:
            yield waiter

    def _wait_writable(self) -> Coro[None]:
        if (waiter := self._fd._io_arm_w()) is not None:
            yield waiter

    def close(self):
        self._fd.close()
