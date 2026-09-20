from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from ._ctl import spawn_blocking
from ._runtime import run
from ._sync import Semaphore
from ._types import Coro


_Params = ParamSpec('_Params')
_Return = TypeVar('_Return')


def main(
    *coros,
    context: bool = False,
    signals: list[int] | None = None,
    threads: int | None = None,
    blocking_threadpool_size: int = 128,
    blocking_threadpool_idle_ttl: int = 30,
):
    if not coros:
        #: opts
        def deco(coro):
            @wraps(coro)
            def wrapper(*args, **kwargs):
                return run(
                    coro(*args, **kwargs),
                    context=context,
                    signals=signals,
                    threads=threads,
                    blocking_threadpool_size=blocking_threadpool_size,
                    blocking_threadpool_idle_ttl=blocking_threadpool_idle_ttl,
                )

            return wrapper

        return deco

    if len(coros) > 1:
        raise SyntaxError('Invalid argument for `main`')

    [coro] = coros

    @wraps(coro)
    def wrapper(*args, **kwargs):
        return run(coro(*args, **kwargs))

    return wrapper


def blocking(fn: Callable[_Params, _Return]) -> Callable[_Params, Coro[_Return]]:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        return spawn_blocking(fn, *args, **kwargs)

    return wrapper


def max_concurrency(
    value: int,
) -> Callable[[Callable[_Params, Coro[_Return]]], Callable[_Params, Coro[_Return]]]:
    if value < 1:
        raise ValueError('`max_concurrency` value must be >= 1')
    guard = Semaphore(value)

    def deco(coro):
        @wraps(coro)
        def wrapper(*args, **kwargs):
            with (yield guard()):
                return (yield coro(*args, **kwargs))

        return wrapper

    return deco


def cpu_bound(
    concurrency: int | None = None,
) -> Callable[[Callable[_Params, _Return]], Callable[_Params, Coro[_Return]]]:
    def deco(fn):
        wrapper = blocking(fn)
        if concurrency:
            wrapper = max_concurrency(concurrency)(wrapper)
        return wrapper

    return deco
