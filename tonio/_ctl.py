import contextlib
from typing import Callable, ParamSpec, TypeVar

from ._events import Event, Waiter
from ._tonio import CancelledError, ResultHolder, get_runtime
from ._types import Coro


_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


def spawn(*coros: Coro):
    events = []
    res = ResultHolder(len(coros))
    errs = []

    def wrapper(idx, coro, event):
        try:
            ret = yield coro
            res.store(ret, idx)
        except Exception as exc:
            errs.append(exc)
        finally:
            event.set()

    for idx, coro in enumerate(coros):
        event = Event()
        events.append(event)
        get_runtime()._spawn_pygen(wrapper(idx, coro, event))

    waiter = Waiter(*events)

    def join():
        yield waiter
        if errs:
            raise ExceptionGroup('SpawnExceptionGroup', errs)
        return res.fetch()

    return join()


def spawn_blocking(fn: Callable[_Params, _Return], /, *args: _Params.args, **kwargs: _Params.kwargs) -> Coro[_Return]:
    ctl, event, res = get_runtime()._spawn_blocking(fn, *args, **kwargs)
    with contextlib.suppress(CancelledError):
        yield event.waiter(None)
    err, val = res.fetch()
    if err is None:
        ctl.abort()
        yield event.waiter(None)
        err, val = res.fetch()
    if err is True:
        raise val
    return val
