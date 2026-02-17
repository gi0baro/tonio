from functools import wraps

from ._runtime import run


def main(
    *coros,
    context: bool = False,
    threads: int | None = None,
    blocking_threadpool: int = 128,
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
                    threads=threads,
                    blocking_threadpool=blocking_threadpool,
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
