from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar

from ._ctl import spawn_blocking
from ._sync import Semaphore


_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


def blocking(fn: Callable[_Params, _Return]) -> Callable[_Params, Awaitable[_Return]]:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return spawn_blocking(fn, *args, **kwargs)

    return wrapper


def max_concurrency(
    value: int,
) -> Callable[[Callable[_Params, Awaitable[_Return]]], Callable[_Params, Awaitable[_Return]]]:
    if value < 1:
        raise ValueError('`max_concurrency` value must be >= 1')
    guard = Semaphore(value)

    def deco(coro):
        @wraps(coro)
        async def wrapper(*args, **kwargs):
            async with guard:
                return await coro(*args, **kwargs)

        return wrapper

    return deco


def cpu_bound(
    concurrency: int | None = None,
) -> Callable[[Callable[_Params, _Return]], Callable[_Params, Awaitable[_Return]]]:
    def deco(fn):
        wrapper = blocking(fn)
        if concurrency:
            wrapper = max_concurrency(concurrency)(wrapper)
        return wrapper

    return deco
