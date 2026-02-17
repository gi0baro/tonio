import contextlib
from typing import Any, Awaitable, Callable, Iterable, ParamSpec, TypeVar

from .._tonio import CancelledError, ResultHolder, get_runtime
from ._events import Event, Waiter


_T = TypeVar('_T')
_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


class AsyncSpawnJoin:
    __slots__ = ['_waiter', '_res', '_errs']

    def __init__(self, waiter, res, errs):
        self._waiter = waiter
        self._res = res
        self._errs = errs

    def __await__(self):
        return self._wait().__await__()

    async def _wait(self):
        await self._waiter
        if self._errs:
            raise ExceptionGroup('SpawnExceptionGroup', self._errs)
        return self._res.fetch()


def spawn(*coros) -> Awaitable[Any]:
    events = []
    res = ResultHolder(len(coros))
    errs = []

    async def wrapper(idx, coro, event):
        try:
            ret = await coro
            res.store(ret, idx)
        except Exception as exc:
            errs.append(exc)
        finally:
            event.set()

    for idx, coro in enumerate(coros):
        event = Event()
        events.append(event)
        get_runtime()._spawn_pyasyncgen(wrapper(idx, coro, event))

    waiter = Waiter(*events)
    return AsyncSpawnJoin(waiter, res, errs)


async def spawn_blocking(fn: Callable[_Params, _Return], /, *args: _Params.args, **kwargs: _Params.kwargs) -> _Return:
    ctl, event, res = get_runtime()._spawn_blocking(fn, *args, **kwargs)
    with contextlib.suppress(CancelledError):
        await event.waiter(None)
    err, val = res.fetch()
    if err is None:
        ctl.abort()
        await event.waiter(None)
        err, val = res.fetch()
    if err is True:
        raise val
    return val


def map(fn: Callable[[_T], _Return], /, xs: Iterable[_T]) -> Awaitable[list[_Return]]:
    return spawn(*[fn(x) for x in xs])


def map_blocking(fn: Callable[[_T], _Return], /, xs: Iterable[_T]) -> Awaitable[list[_Return]]:
    return spawn(*[spawn_blocking(fn, x) for x in xs])


async def yield_now():
    event = Event()
    event.set()
    await event.waiter(None)
