import contextlib
import threading
from typing import Any, Awaitable, Callable, Iterable, ParamSpec, TypeVar

from .._tonio import CancelledError, Result, get_runtime
from ._events import Event
from ._scope import Scope
from ._sync import Barrier


_T = TypeVar('_T')
_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


class _SpawnJoinCollect:
    __slots__ = ['_barrier', '_res', '_errs']

    def __init__(self, barrier, res, errs):
        self._barrier = barrier
        self._res = res
        self._errs = errs

    def __await__(self):
        return self._wait().__await__()

    async def _wait(self):
        await self._barrier.wait()
        if self._errs:
            raise ExceptionGroup('SpawnExceptionGroup', self._errs)
        return self._res.fetch()


class _SpawnJoin:
    __slots__ = ['_barrier', '_errs']

    def __init__(self, barrier, errs):
        self._barrier = barrier
        self._errs = errs

    def __await__(self):
        return self._wait().__await__()

    async def _wait(self):
        await self._barrier.wait()
        if self._errs:
            raise ExceptionGroup('SpawnExceptionGroup', self._errs)


class _Spawn:
    __slots__ = []

    @staticmethod
    def __call__(*coros) -> Awaitable[Any]:
        barrier = Barrier(len(coros) + 1)
        res = Result(len(coros))
        errs = []

        async def wrapper(idx, coro, barrier):
            try:
                ret = await coro
                res.store(ret, idx)
            except Exception as exc:
                errs.append(exc)
            finally:
                barrier.ack()

        for idx, coro in enumerate(coros):
            get_runtime()._spawn_pyasyncgen(wrapper(idx, coro, barrier))

        return _SpawnJoinCollect(barrier, res, errs)

    @staticmethod
    def without_results(*coros) -> Awaitable[None]:
        barrier = Barrier(len(coros) + 1)
        errs = []

        async def wrapper(coro, barrier):
            try:
                await coro
            except Exception as exc:
                errs.append(exc)
            finally:
                barrier.ack()

        for coro in coros:
            get_runtime()._spawn_pyasyncgen(wrapper(coro, barrier))

        return _SpawnJoin(barrier, errs)

    @staticmethod
    def without_tracking(*coros):
        for coro in coros:
            get_runtime()._spawn_pyasyncgen(coro)


spawn = _Spawn()


async def select(*coros) -> Any:
    scope = Scope()
    sentinel = Event()
    res = Result()

    async def wrapper(coro):
        try:
            ret = await coro
            res.store((False, ret))
        except Exception as exc:
            res.store((True, exc))
        finally:
            sentinel.set()

    async with scope:
        for coro in coros:
            scope.spawn(wrapper(coro))
        await sentinel.waiter(None)
        is_err, ret = res.fetch()
        scope.cancel()

    if is_err:
        raise ret
    return ret


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


def block_on(coro):
    ev = threading.Event()
    res = Result()

    async def wrapper():
        try:
            ret = await coro
            res.store((False, ret))
        except Exception as exc:
            res.store((True, exc))
        finally:
            ev.set()

    spawn.without_tracking(wrapper())
    ev.wait()
    err, val = res.fetch()
    if err:
        raise val
    return val


def map(fn: Callable[[_T], _Return], /, xs: Iterable[_T]) -> Awaitable[list[_Return]]:
    return spawn(*[fn(x) for x in xs])


def map_blocking(fn: Callable[[_T], _Return], /, xs: Iterable[_T]) -> Awaitable[list[_Return]]:
    return spawn(*[spawn_blocking(fn, x) for x in xs])
