import contextlib
from typing import TypeVar

from ._events import Event
from ._tonio import ResultHolder, TimeoutError, get_runtime
from ._types import Coro


_T = TypeVar('_T')


def clock() -> int:
    return get_runtime()._clock


def sleep(timeout: int | float) -> Coro[None]:
    yield from Event().wait(timeout)


def timeout(coro: Coro[_T], timeout: int | float) -> Coro[tuple[None | _T, bool]]:
    done = Event()
    res = ResultHolder()

    def wrapper():
        ret = yield coro
        res.store(ret)
        done.set()

    get_runtime()._spawn_pygen(wrapper())

    yield from done.wait(timeout)
    if not done.is_set():
        with contextlib.suppress(TimeoutError):
            coro.throw(TimeoutError)
        return None, False
    return res.fetch(), True
