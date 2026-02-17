import multiprocessing

from ._colored._events import Event as EventAw
from ._events import Event
from ._tonio import ResultHolder, Runtime as _Runtime, set_runtime as _set_runtime
from ._utils import is_asyncg


class Runtime(_Runtime):
    def run_forever(self):
        try:
            self._run_forever_pre()
            self._run()
        finally:
            self._run_forever_post()

    def _run_forever_pre(self):
        # TODO: signals
        pass

    def _run_forever_post(self):
        # TODO: signals
        self._stopping = False

    def run_pygen_until_complete(self, coro):
        done = Event()
        res = ResultHolder()
        is_exc = False

        def runner():
            nonlocal is_exc
            try:
                ret = yield coro
                res.store(ret)
            except Exception as exc:
                is_exc = True
                res.store(exc)
            finally:
                done.set()

        def watcher():
            yield from done.wait()
            self.stop()

        self._spawn_pygen(watcher())
        self._spawn_pygen(runner())
        self.run_forever()

        ret = res.fetch()
        if is_exc:
            raise ret
        return ret

    def run_pyasyncgen_until_complete(self, coro):
        done = EventAw()
        res = ResultHolder()
        is_exc = False

        async def runner():
            nonlocal is_exc
            try:
                ret = await coro
                res.store(ret)
            except Exception as exc:
                is_exc = True
                res.store(exc)
            finally:
                done.set()

        async def watcher():
            await done.wait()
            self.stop()

        self._spawn_pyasyncgen(watcher())
        self._spawn_pyasyncgen(runner())
        self.run_forever()

        ret = res.fetch()
        if is_exc:
            raise ret
        return ret

    def run_until_complete(self, coro):
        runner = self.run_pyasyncgen_until_complete if is_asyncg(coro) else self.run_pygen_until_complete
        return runner(coro)

    def stop(self):
        self._stopping = True


def new(
    context: bool = False,
    threads: int | None = None,
    blocking_threadpool_size: int = 128,
    blocking_threadpool_idle_ttl: int = 30,
) -> Runtime:
    threads = threads or multiprocessing.cpu_count()
    runtime = Runtime(
        threads=threads,
        threads_blocking=blocking_threadpool_size,
        threads_blocking_timeout=blocking_threadpool_idle_ttl,
        context=context,
    )
    _set_runtime(runtime)
    return runtime


def run(
    coro,
    context: bool = False,
    threads: int | None = None,
    blocking_threadpool_size: int = 128,
    blocking_threadpool_idle_ttl: int = 30,
):
    runtime = new(
        context=context,
        threads=threads,
        blocking_threadpool_size=blocking_threadpool_size,
        blocking_threadpool_idle_ttl=blocking_threadpool_idle_ttl,
    )
    return runtime.run_until_complete(coro)
