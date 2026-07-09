from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import ctypes
import inspect
import sys
import threading
import time as _stdlib_time
from types import CoroutineType
from typing import Any

from ._events import Event, Result
from .exceptions import CancelledError, RuntimeNotInitializedError


_current_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    if _current_runtime is None:
        raise RuntimeNotInitializedError('no runtime is active')
    return _current_runtime


def set_runtime(rt: Runtime | None):
    global _current_runtime
    _current_runtime = rt


# Set up the ctypes binding for PyThreadState_SetAsyncExc once at module level.
_PyThreadState_SetAsyncExc = ctypes.pythonapi.PyThreadState_SetAsyncExc
_PyThreadState_SetAsyncExc.argtypes = [ctypes.c_ulong, ctypes.py_object]
_PyThreadState_SetAsyncExc.restype = ctypes.c_int


def _async_raise(tid: int, exc_type: type[BaseException]) -> None:
    """Best-effort injection of `exc_type` into the thread identified by `tid`.

    Mirrors the native backend's `BlockingTaskCtl::abort()` which calls
    `PyThreadState_SetAsyncExc` through the PyO3 FFI. This works as good
    as the native backend does ;)
    """
    ret = _PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), exc_type)
    if ret != 1:
        # Error codes:
        # -1 = succeeded
        # 0 = thread not found
        # >1 = unexpected state
        # Clean up and continue.
        if ret > 1:
            _PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)


if sys.platform == 'win32':
    import select as _select

    _LOOP_FACTORY = asyncio.SelectorEventLoop

    # Windows needs proper filedescriptor checks
    def _check_fd_socket(fd: int, loop: asyncio.AbstractEventLoop) -> None:
        """Raise a clear error if `fd` is not a socket on Windows.

        `asyncio.SelectorEventLoop` relies on `select()`, which raises strange
        ValueError or OSError on unix stuff like pipes, files, console handles.

        Instead of letting this blow-up later,
        check early and with a sane error message.
        """
        try:
            _select.select([fd], [], [], 0)
        except (ValueError, OSError) as exc:
            raise RuntimeError(
                f'asyncio backend only supports TCP socket FDs on Windows; FD {fd} is not a socket ({exc})'
            ) from exc
else:
    _LOOP_FACTORY = asyncio.new_event_loop

    def _check_fd_socket(fd: int, loop: asyncio.AbstractEventLoop) -> None:
        """Noop on platforms non-Windows

        Unix & macOS platforms can handle a broad sort of file descriptors.
        There is no need to check them upfront
        """
        return


async def _consume_pygen(gen) -> Any:
    """Run a tonio pygen generator-based coroutine inside asyncio.

    Bubbles up tonio generators yielded stuff up to a real result
    """
    try:
        yielded = gen.send(None)
    except StopIteration as e:
        return e.value

    while True:
        try:
            if asyncio.iscoroutine(yielded) or inspect.isawaitable(yielded):
                result = await yielded
            elif inspect.isgenerator(yielded):
                result = await _consume_pygen(yielded)
            else:
                await asyncio.sleep(0)
                result = None
        except BaseException as exc:
            try:
                yielded = gen.throw(exc)
            except StopIteration as e:
                return e.value
        else:
            try:
                yielded = gen.send(result)
            except StopIteration as e:
                return e.value


class BlockingTaskCtl:
    __slots__ = ['_task', '_thread_id']

    def __init__(self, task: asyncio.Task | None):
        self._task = task
        self._thread_id: int | None = None

    def _set_tid(self, tid: int) -> None:
        """Store the native thread ID (called from the executor thread)."""
        self._thread_id = tid

    def abort(self):
        # Best-effort: inject CancelledError into the blocking thread, just
        # like the native backend does via PyThreadState_SetAsyncExc.
        if self._thread_id is not None:
            _async_raise(self._thread_id, CancelledError)
        # Cancel the asyncio wrapper task so the caller is unblocked quickly.
        if self._task is not None:
            self._task.cancel()


class Runtime:
    """asyncio-based runtime, mainly for Windows support

    Provides the same low-level interface as the native `_tonio.Runtime`
    so `tonio._runtime.Runtime` can subclass this instead of the Rust version.
    """

    def __init__(
        self,
        threads: int,
        threads_blocking: int,
        threads_blocking_timeout: int,
        context: bool,
        signals: list[int],
    ):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=threads_blocking)
        self._stopping = False
        self._ssock_r = None
        self._ssock_w = None
        self._sig_listening = False
        self._sigset = signals
        self._sig_wfd = -1
        self._epoch = _stdlib_time.monotonic()
        self._loop: asyncio.AbstractEventLoop = None
        self._pending: list[CoroutineType] = []

    @property
    def _clock(self) -> int:
        return round((_stdlib_time.monotonic() - self._epoch) * 1_000_000)

    def _spawn_pyasyncgen(self, coro) -> asyncio.Task | None:
        # coro could be also a generator
        if inspect.isgenerator(coro):
            coro = _consume_pygen(coro)
        if self._loop is None:
            # Queue the coro so _run() can handle it when loop gets available.
            self._pending.append(coro)
            return None
        try:
            return asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            # Called from a non-async thread, maybe a block_on from a ThreadPoolExecutor
            asyncio.run_coroutine_threadsafe(coro, self._loop)
            return None

    def _spawn_pygen(self, gen) -> asyncio.Task | None:
        coro = _consume_pygen(gen)
        if self._loop is None:
            # Queue the coro so _run() can handle it when loop gets available.
            self._pending.append(coro)
            return None
        try:
            return asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
            return None

    def _spawn_blocking(self, fn, *args, **kwargs) -> tuple[BlockingTaskCtl, Event, Result]:
        event = Event()
        result = Result(size=2)

        # Capture the caller's context to run fn inside an executor
        ctx = contextvars.copy_context()

        # Allows the thread ID to be stored via _set_tid()
        ctl = BlockingTaskCtl(task=None)

        async def _run():
            loop = asyncio.get_running_loop()
            try:
                # Store the thread ID before running the payload.
                # so abort() may work across threads
                def _wrapper():
                    ctl._set_tid(threading.get_ident())
                    return ctx.run(fn, *args, **kwargs)

                val = await loop.run_in_executor(self._executor, _wrapper)
                result.store(False, 0)
                result.store(val, 1)
            except Exception as e:
                result.store(True, 0)
                result.store(e, 1)
            finally:
                event.set()

        try:
            task = asyncio.get_running_loop().create_task(_run())
            ctl._task = task
        except RuntimeError:
            # Called from a non-async thread, like block_on in a ThreadPoolExecutor
            # Lets ctl._task = None as there is no asyncio task to cancel
            loop = self._loop
            if loop is not None:
                asyncio.run_coroutine_threadsafe(_run(), loop)

        return ctl, event, result

    def _io_event_r(self, fd: int) -> Event:
        from ._events import _IOEvent

        loop = asyncio.get_running_loop()
        _check_fd_socket(fd, loop)  # Needed guard on Windows
        event = _IOEvent(fd, loop.remove_reader)

        def _teardown_guard():
            loop.remove_reader(fd)
            event.set()

        loop.add_reader(fd, _teardown_guard)
        return event

    def _io_event_w(self, fd: int) -> Event:
        from ._events import _IOEvent

        loop = asyncio.get_running_loop()
        _check_fd_socket(fd, loop)  # Needed guard on Windows
        event = _IOEvent(fd, loop.remove_writer)

        def _teardown_guard():
            loop.remove_writer(fd)
            event.set()

        loop.add_writer(fd, _teardown_guard)
        return event

    def _sig_add(self, sig: int) -> Event:
        raise NotImplementedError('No signal handling availble on asyncio backend (yet)')

    def _sig_rem(self, sig: int) -> bool:
        return False

    def _disarm_loop(self):
        self._loop.close()
        asyncio.set_event_loop(None)
        self._loop = None

    def _run(self):
        """Run the event loop until `stop()` is called

        As subclasses may override stop() to set self._stopping,
        it should trigger asyncio' `loop.stop()` via a checking callback
        """
        loop = _LOOP_FACTORY()
        asyncio.set_event_loop(loop)
        self._loop = loop
        set_runtime(self)
        try:
            # Handle coros queued before the event loop got available
            for coro in self._pending:
                loop.create_task(coro)
            self._pending.clear()

            def _check_stop():
                if self._stopping:
                    loop.stop()
                else:
                    loop.call_soon(_check_stop)

            # Keep checking for the stop condition between other coro runs
            loop.call_soon(_check_stop)
            loop.run_forever()
        finally:
            set_runtime(None)
            self._disarm_loop()

    def _shutdown(self):
        self._stopping = True
        self._executor.shutdown(wait=False)
        if self._loop is not None:
            self._loop.stop()

    def __del__(self):
        # Shuts down self._executor:
        self._shutdown()
