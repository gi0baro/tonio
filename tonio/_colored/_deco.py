from functools import wraps
from typing import Awaitable, Callable

from ._ctl import spawn_blocking
from ._sync import Semaphore


def blocking[**Params, Return](fn: Callable[Params, Return]) -> Callable[Params, Awaitable[Return]]:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return spawn_blocking(fn, *args, **kwargs)

    return wrapper


def max_concurrency[**Params, Return](
    value: int,
) -> Callable[[Callable[Params, Awaitable[Return]]], Callable[Params, Awaitable[Return]]]:
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


def cpu_bound[**Params, Return](
    concurrency: int | None = None,
) -> Callable[[Callable[Params, Return]], Callable[Params, Awaitable[Return]]]:
    def deco(fn):
        wrapper = blocking(fn)
        if concurrency:
            wrapper = max_concurrency(concurrency)(wrapper)
        return wrapper

    return deco
