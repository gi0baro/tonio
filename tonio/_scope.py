import contextlib
import inspect

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
                while True:
                    if inspect.getgeneratorstate(coro) in [inspect.GEN_CREATED, inspect.GEN_RUNNING]:
                        yield
                        continue
                    raise coro.throw(exc)
            finally:
                event.set()

        if wrapped_coro := self._track_pygen(wrapper):
            get_runtime()._spawn_pygen(wrapped_coro)

    def __enter__(self):
        if not self._incr(0):
            raise RuntimeError('Cannot enter the same scope multiple times.')
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self._incr(1)
        return

    def __call__(self):
        yield
        waiter, coros = self._stack()

        while True:
            pending = []
            for coro in coros:
                if inspect.getgeneratorstate(coro) == inspect.GEN_RUNNING:
                    pending.append(coro)
                    continue
                with contextlib.suppress(CancelledError):
                    coro.throw(CancelledError)

            if not pending:
                break
            coros = list(pending)

        yield waiter


def scope():
    return Scope()
