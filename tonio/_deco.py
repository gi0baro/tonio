from functools import wraps

from ._runtime import run


def main(
    *coros, threads: int | None = None, threads_blocking: int | None = None, threads_blocking_timeout: int | None = None
):
    if not coros:
        #: opts
        def deco(coro):
            @wraps(coro)
            def wrapper():
                run(
                    coro(),
                    threads=threads,
                    threads_blocking=threads_blocking,
                    threads_blocking_timeout=threads_blocking_timeout,
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
