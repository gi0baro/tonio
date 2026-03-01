from functools import wraps

from ._runtime import run


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
            def wrapper():
                run(
                    coro(),
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
    def wrapper():
        run(coro())

    return wrapper
