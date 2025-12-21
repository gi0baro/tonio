import contextlib

from ._tonio import CancelledError, Scope as _Scope, get_runtime
from ._types import Coro


class Scope(_Scope):
    def spawn(self, coro: Coro):
        def inner(waiter):
            yield waiter
            yield coro

        def wrapper(event, waiter):
            try:
                yield inner(waiter)
            except CancelledError as exc:
                with contextlib.suppress(CancelledError):
                    waiter.throw(exc)
                raise coro.throw(exc)
            finally:
                event.set()

        if wrapped_coro := self._track_pygen(wrapper):
            get_runtime()._spawn_pygen(wrapped_coro)

    def __enter__(self):
        if not self._consume():
            raise RuntimeError('Cannot enter the same scope multiple times.')
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        return

    def __call__(self):
        waiter, coros = self._stack()
        for coro in coros:
            with contextlib.suppress(CancelledError):
                coro.throw(CancelledError)
        yield waiter


def scope():
    return Scope()
