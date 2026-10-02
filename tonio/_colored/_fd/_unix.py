import os

from ..._fd._unix import FdStream as _FdStream
from ...exceptions import ResourceBroken


class FdStream(_FdStream):
    async def send_all(self, data: bytes | bytearray | memoryview):
        if self._fd.closed:
            raise RuntimeError('file closed')

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
                                with self._lock_io:
                                    sent += os.write(self._fd.fd, remaining)
                            except InterruptedError:
                                pass
                            except BlockingIOError:
                                self._fd._io_clear_w()
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

        with self._lock_r.or_raise():
            while True:
                if (waiter := self._fd._io_arm_r()) is not None:
                    await waiter
                    continue

                try:
                    with self._lock_io:
                        data = os.read(self._fd.fd, max_bytes)
                except InterruptedError:
                    pass
                except BlockingIOError:
                    self._fd._io_clear_r()
                except BaseException as exc:
                    raise exc
                else:
                    break

        return data
