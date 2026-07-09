from __future__ import annotations

import asyncio

from .exceptions import CancelledError


class _Waiter:
    __slots__ = ['_asyncio_events', '_timeout']

    def __init__(self, events: list[asyncio.Event], timeout_us: int | None):
        if not events:
            raise RuntimeError('No event provided')

        self._asyncio_events = events
        self._timeout = timeout_us / 1_000_000 if timeout_us else timeout_us

    def __await__(self):
        return self._wait().__await__()

    async def _wait(self):
        if all(ev.is_set() for ev in self._asyncio_events):
            # yield explicitly, otherwise `yield_now() (set() + waiter)`
            # will not yield like the native Waiter.
            await asyncio.sleep(0)
            return

        if len(self._asyncio_events) == 1:
            coro = self._asyncio_events[0].wait()
        else:
            # resolves only if every event fires
            coro = asyncio.gather(*(ev.wait() for ev in self._asyncio_events))

        if self._timeout is None:
            await coro
        else:
            try:
                await asyncio.wait_for(coro, timeout=self._timeout)
            except asyncio.TimeoutError:
                pass

    def abort(self):
        pass

    def unwind(self):
        pass


class _CheckpointWaiter:
    """Waiter.checkpoint() used for coroutine cancellation.

    When awaited, checks for `_aborted` flag and throws `CancelledError`
    """

    __slots__ = ['_aborted', '_fut', '_handle', '_task']

    def __init__(self):
        self._aborted: bool = False
        self._fut: asyncio.Future | None = None
        self._handle: asyncio.Handle | None = None
        self._task: asyncio.Task | None = None

    def __await__(self):
        if self._aborted:
            raise CancelledError()
        self._task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        self._fut = fut = loop.create_future()
        # Resolved in the next loops to allow the current execution to continue
        self._handle = loop.call_soon(lambda: None if fut.done() else fut.set_result(None))
        try:
            # fut can be already canceled
            return fut.__await__()
        except asyncio.CancelledError as err:
            raise CancelledError() from err

    def abort(self):
        """Mark as aborted and cancel the future if the await has started.

        Mirrors the native `unwind()` behaviour.
        """
        self._aborted = True
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
        if self._fut is not None and not self._fut.done():
            self._fut.cancel()
        elif self._task is not None and not self._task.done():
            self._task.cancel()

    def unwind(self):
        """Cancel the containing task regardless of its state

        Uses `self._task` as it may be different than the current task
        """
        self.abort()
        if self._task is not None and not self._task.done():
            self._task.cancel()


class Waiter(_Waiter):
    def __init__(self, *events: Event):
        super().__init__([e._asyncio_event for e in events], timeout_us=None)

    @staticmethod
    def checkpoint() -> _CheckpointWaiter:
        return _CheckpointWaiter()


class Event:
    """Mimics the Rust-based Event class"""

    __slots__ = ['_asyncio_event', '_loop']

    def __init__(self):
        self._asyncio_event = asyncio.Event()
        # Stores the loop, allowing other threads to call `set()`
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            # There is no current loop. This is fine.
            self._loop = None

    def set(self):
        if self.is_set():
            return
        # Only defer the real flag set when called from a foreign thread.
        # Otherwise set it synchoronolusly.
        # Kinda mimics the AtomicBool of the native counterpart.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._asyncio_event.set)
                return
        self._asyncio_event.set()

    def clear(self):
        self._asyncio_event.clear()

    def is_set(self) -> bool:
        return self._asyncio_event.is_set()

    def waiter(self, timeout_us: int | None) -> _Waiter:
        return _Waiter([self._asyncio_event], timeout_us)


class _IOWaiter(_Waiter):
    """Like _Waiter but calls remove_fn(fd) on cancellation

    Avoids WinError 10038: Socket op on non-socket.
    """

    __slots__ = ['_fd', '_remove_fn']

    def __init__(self, events: list[asyncio.Event], timeout_us: int | None, fd: int, remove_fn: callable):
        super().__init__(events, timeout_us)
        self._fd = fd
        self._remove_fn = remove_fn

    async def _wait(self):
        try:
            await super()._wait()
        except BaseException:
            try:
                self._remove_fn(self._fd)
            except Exception:
                pass
            raise


class _IOEvent(Event):
    """Event backed by add_reader/add_writer

    cleans up on cancellation.
    """

    __slots__ = ['_fd', '_remove_fn']

    def __init__(self, fd: int, remove_fn: callable):
        super().__init__()
        self._fd = fd
        self._remove_fn = remove_fn

    def waiter(self, timeout_us: int | None) -> _IOWaiter:
        return _IOWaiter([self._asyncio_event], timeout_us, self._fd, self._remove_fn)


class Result:
    """Store values across coroutines"""

    __slots__ = ['_values']

    def __init__(self, size: int = 1):
        assert size >= 1, 'Improper use of Result size'
        self._values: list = [None] * size

    def store(self, value, index: int | None = None):
        self._values[0 if index is None else index] = value

    def fetch(self):
        if len(self._values) <= 1:
            return self._values[0]
        return list(self._values)
