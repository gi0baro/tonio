import contextlib

from .._tonio import CancelledError, Scope as _Scope, get_runtime


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
        if not self._consume():
            raise RuntimeError('Cannot enter the same scope multiple times.')
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        waiter, coros = self._stack()
        for coro in coros:
            with contextlib.suppress(CancelledError):
                coro.throw(CancelledError)
        await waiter
        return


def scope():
    return Scope()
