import contextlib
from typing import Awaitable, TypeVar

from .._events import Event
from .._tonio import CancelledError, ResultHolder, get_runtime


_T = TypeVar('_T')


def sleep(timeout: int | float) -> Awaitable[None]:
    return Event()(timeout)


async def timeout(coro: Awaitable[_T], timeout: int | float) -> tuple[None | _T, bool]:
    done = Event()
    res = ResultHolder()

    async def wrapper():
        ret = await coro
        res.store(ret)
        done.set()

    get_runtime()._spawn_pyasyncgen(wrapper())

    await done(timeout)
    if not done.is_set():
        with contextlib.suppress(CancelledError):
            coro.throw(CancelledError)
        return None, False
    return res.fetch(), True
