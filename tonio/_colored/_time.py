from typing import Awaitable, TypeVar

from .._time import _Interval
from .._tonio import CancelledError, ResultHolder, Waiter, get_runtime
from ._events import Event


_T = TypeVar('_T')


class Interval(_Interval):
    __slots__ = []

    def tick(self) -> Awaitable[None]:
        timeout = self._poll()
        return Event().waiter(timeout)


def sleep(timeout: int | float) -> Awaitable[None]:
    return Event().wait(timeout)


async def timeout(coro: Awaitable[_T], timeout: int | float) -> tuple[None | _T, bool]:
    done = Event()
    res = ResultHolder()
    checkpoint = Waiter.checkpoint()

    async def glue():
        await checkpoint
        return await coro

    async def wrapper():
        try:
            ret = await glue()
            res.store((False, ret))
        except CancelledError:
            pass
        except Exception as exc:
            res.store((True, exc))
        finally:
            done.set()

    get_runtime()._spawn_pyasyncgen(wrapper())
    await done.wait(timeout)

    if not done.is_set():
        checkpoint.abort()
        return None, False

    is_err, ret = res.fetch()
    if is_err:
        raise ret
    return ret, True


def interval(period: int | float, at: int | None = None) -> Interval:
    period = round(max(0, period * 1_000_000))
    at = at or get_runtime()._clock
    return Interval(at, period)
