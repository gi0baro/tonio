import contextlib
from typing import TypeVar

from ._events import Event
from ._tonio import CancelledError, ResultHolder, get_runtime
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
    res = ResultHolder()
    errs = []

    def wrapper():
        try:
            ret = yield coro
            res.store(ret)
        except CancelledError:
            pass
        except Exception as exc:
            errs.append(exc)
        finally:
            done.set()

    get_runtime()._spawn_pygen(wrapper())

    yield from done.wait(timeout)
    if not done.is_set():
        with contextlib.suppress(CancelledError):
            coro.throw(CancelledError)
        return None, False
    if errs:
        [err] = errs
        raise err
    return res.fetch(), True


def interval(period: int | float, at: int | None = None) -> Interval:
    period = round(max(0, period * 1_000_000))
    at = at or get_runtime()._clock
    return Interval(at, period)
