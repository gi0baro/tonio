from __future__ import annotations

import asyncio
from collections import deque

from ._events import Event


class _ImmediateWaiter:
    """Resolves synchronously and starts the task immediately.

    Task cancellation occur on first await of the spawned coroutine.
    Mirrors the Rust Waiter::new_for_suspension().
    """

    def __await__(self):
        return iter(())

    def abort(self):
        pass

    def unwind(self):
        pass


class _ScopeBase:
    __slots__ = [
        '_entered',
        '_exited',
        '_task_count',
        '_done_event',
        '_task_done_events',
        '_cancelled',
        '_asyncio_tasks',
    ]

    def __init__(self):
        self._entered = False
        self._exited = False
        self._task_count = 0
        self._done_event = Event()
        self._task_done_events: deque = deque()
        self._cancelled = False
        self._asyncio_tasks: deque[asyncio.Task] = deque()

    def _incr(self, val: int) -> bool:
        if val == 0:
            # Trying to __enter__
            if self._entered:
                return False
            self._entered = True
            return True
        else:
            # Trying to __exit__
            # No more spawn()s will be honored
            self._exited = True
            return True

    def _track(self, wrapper_fn):
        """Register a task wrapper and return the started coroutine."""
        if self._exited:
            return None
        self._task_count += 1
        scope = self

        class _TaskDoneEvent(Event):
            def __init__(self):
                super().__init__()
                self._counted = False

            def set(self):
                super().set()
                if not self._counted:
                    self._counted = True
                    scope._task_count -= 1
                    if scope._task_count <= 0:
                        scope._done_event.set()

        done_event = _TaskDoneEvent()
        self._task_done_events.append(done_event)
        return wrapper_fn(done_event, _ImmediateWaiter())

    def _exit(self):
        """Return a waiter that resolves when all tracked tasks finish."""
        if self._cancelled:
            # Mirror Rust: mark unfinished tasks done so the scope can exit.
            # The asyncio tasks themselves are cancelled via Scope.cancel().
            for ev in self._task_done_events:
                if not ev._counted:
                    ev.set()
        if self._task_count <= 0:
            self._done_event.set()
        return self._done_event.waiter(None)

    def _register_task(self, task: asyncio.Task) -> None:
        """Track the asyncio tasks spawned allowing cancel() to hit it."""
        self._asyncio_tasks.append(task)
        if self._cancelled:
            # Scope canceled even before starting.
            # Make sure the tasks will be canceled on next loop run.
            asyncio.get_running_loop().call_soon(task.cancel)

    def cancel(self) -> bool:
        if self._cancelled:
            return False
        self._cancelled = True
        for task in self._asyncio_tasks:
            if not task.done():
                task.cancel()
        return True


class PyGenScope(_ScopeBase):
    pass


class PyAsyncGenScope(_ScopeBase):
    pass
