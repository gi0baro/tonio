from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from .._events import Event, Waiter
from .._tonio import ResultHolder, get_runtime


_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


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

    async def join():
        await waiter
        if errs:
            raise ExceptionGroup('SpawnExceptionGroup', errs)
        return res.fetch()

    return join()


async def spawn_blocking(fn: Callable[_Params, _Return], /, *args: _Params.args, **kwargs: _Params.kwargs) -> _Return:
    event, res = get_runtime()._spawn_blocking(fn, *args, **kwargs)
    await event.waiter(None)
    return res.fetch()


async def yield_now():
    event = Event()
    event.set()
    await event.waiter(None)
