import contextlib
import inspect

from .._tonio import CancelledError, Scope as _Scope, get_runtime
from ._ctl import yield_now


class Scope(_Scope):
    def spawn(self, coro):
        async def wrapper(event):
            try:
                await coro
            finally:
                event.set()

        if wrapped_coro := self._track_pyasyncgen(wrapper):
            get_runtime()._spawn_pyasyncgen(wrapped_coro)

    async def __aenter__(self):
        if not self._incr(0):
            raise RuntimeError('Cannot enter the same scope multiple times.')
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        self._incr(1)
        await yield_now()
        waiter, coros = self._stack()

        while True:
            pending = []
            for coro in coros:
                cstate = inspect.getcoroutinestate(coro)
                if cstate in [inspect.CORO_CREATED, inspect.CORO_RUNNING]:
                    pending.append(coro)
                    continue
                if cstate == inspect.CORO_CLOSED:
                    continue
                with contextlib.suppress(CancelledError):
                    coro.throw(CancelledError)

            if not pending:
                break
            coros = list(pending)

        await waiter


def scope():
    return Scope()
