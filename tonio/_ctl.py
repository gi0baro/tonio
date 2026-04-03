import contextlib
import threading
from typing import Any, Callable, Iterable, ParamSpec, TypeVar

from ._sync import Barrier
from ._tonio import CancelledError, ResultHolder, get_runtime
from ._types import Coro


_T = TypeVar('_T')
_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


class _Spawn:
    __slots__ = []

    @staticmethod
    def __call__(*coros: Coro) -> Coro[Any]:
        barrier = Barrier(len(coros) + 1)
        res = ResultHolder(len(coros))
        errs = []

        def wrapper(idx, coro, barrier):
            try:
                ret = yield coro
                res.store(ret, idx)
            except Exception as exc:
                errs.append(exc)
            finally:
                barrier.ack()

        for idx, coro in enumerate(coros):
            get_runtime()._spawn_pygen(wrapper(idx, coro, barrier))

        def join():
            yield barrier.wait()
            if errs:
                raise ExceptionGroup('SpawnExceptionGroup', errs)
            return res.fetch()

        return join()

    @staticmethod
    def without_results(*coros: Coro) -> Coro[None]:
        barrier = Barrier(len(coros) + 1)
        errs = []

        def wrapper(coro, barrier):
            try:
                yield coro
            except Exception as exc:
                errs.append(exc)
            finally:
                barrier.ack()

        for coro in coros:
            get_runtime()._spawn_pygen(wrapper(coro, barrier))

        def join():
            yield barrier.wait()
            if errs:
                raise ExceptionGroup('SpawnExceptionGroup', errs)

        return join()

    @staticmethod
    def without_tracking(*coros: Coro):
        for coro in coros:
            get_runtime()._spawn_pygen(coro)


spawn = _Spawn()


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


def block_on(coro: Coro[_T]) -> _T:
    ev = threading.Event()
    res = ResultHolder()

    def wrapper():
        try:
            ret = yield coro
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


def map(fn: Callable[[_T], _Return], /, xs: Iterable[_T]) -> Coro[list[_Return]]:
    return spawn(*[fn(x) for x in xs])


def map_blocking(fn: Callable[[_T], _Return], /, xs: Iterable[_T]) -> Coro[list[_Return]]:
    return spawn(*[spawn_blocking(fn, x) for x in xs])
