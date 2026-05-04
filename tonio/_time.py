from typing import TypeVar

from ._events import Event
from ._tonio import CancelledError, Result, Waiter, get_runtime
from ._types import Coro


_T = TypeVar('_T')


class _Interval:
    __slots__ = ['deadline', 'len']

    def __init__(self, deadline: int, len: int):
        self.deadline = deadline
        self.len = len

    def _poll(self):
        now = get_runtime()._clock
        if now >= self.deadline:
            next, delay = now + self.len, 0
        else:
            next = self.deadline + self.len
            delay = self.deadline - now
        self.deadline = next
        return delay


class Interval(_Interval):
    __slots__ = []

    def tick(self):
        timeout = self._poll()
        yield Event().waiter(timeout)


def time() -> float:
    return get_runtime()._clock / 1_000_000


def sleep(timeout: int | float) -> Coro[None]:
    yield from Event().wait(timeout)


def timeout(coro: Coro[_T], timeout: int | float) -> Coro[tuple[None | _T, bool]]:
    done = Event()
    res = Result()
    checkpoint = Waiter.checkpoint()

    def glue():
        yield checkpoint
        return (yield coro)

    def wrapper():
        try:
            ret = yield glue()
            res.store((False, ret))
        except CancelledError:
            pass
        except Exception as exc:
            res.store((True, exc))
        finally:
            done.set()

    get_runtime()._spawn_pygen(wrapper())
    yield from done.wait(timeout)

    if not done.is_set():
        checkpoint.unwind()
        return None, False

    is_err, ret = res.fetch()
    if is_err:
        raise ret
    return ret, True


def interval(period: int | float, at: int | float | None = None) -> Interval:
    period = round(max(0, period * 1_000_000))
    at = round((at or time()) * 1_000_000)
    return Interval(at, period)
