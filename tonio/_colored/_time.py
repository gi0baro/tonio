import contextlib
from typing import Awaitable, TypeVar

from .._tonio import CancelledError, ResultHolder, get_runtime
from ._events import Event


_T = TypeVar('_T')


def sleep(timeout: int | float) -> Awaitable[None]:
    return Event().wait(timeout)


async def timeout(coro: Awaitable[_T], timeout: int | float) -> tuple[None | _T, bool]:
    done = Event()
    res = ResultHolder()
    errs = []

    async def wrapper():
        try:
            ret = await coro
            res.store(ret)
        except CancelledError:
            pass
        except Exception as exc:
            errs.append(exc)
        finally:
            done.set()

    get_runtime()._spawn_pyasyncgen(wrapper())

    await done.wait(timeout)
    if not done.is_set():
        with contextlib.suppress(CancelledError):
            coro.throw(CancelledError)
        return None, False
    if errs:
        [err] = errs
        raise err
    return res.fetch(), True
