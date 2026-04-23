from .._tonio import CancelledError, PyAsyncGenScope as _Scope, get_runtime
from ._ctl import yield_now


class Scope(_Scope):
    def spawn(self, coro):
        async def inner(waiter):
            await waiter
            await coro

        async def wrapper(event, waiter):
            try:
                await inner(waiter)
            except CancelledError:
                pass
            except BaseException as exc:
                raise exc
            finally:
                event.set()

        if wrapped_coro := self._track(wrapper):
            get_runtime()._spawn_pyasyncgen(wrapped_coro)

    async def __aenter__(self):
        if not self._incr(0):
            raise RuntimeError('Cannot enter the same scope multiple times.')
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        self._incr(1)
        await yield_now()
        waiter = self._exit()
        await waiter


def scope():
    return Scope()
