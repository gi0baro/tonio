import multiprocessing

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

        def wrapper():
            ret = yield coro
            res.store(ret)
            done.set()

        def watcher():
            yield from done.wait()
            self.stop()

        self._spawn_pygen(watcher())
        self._spawn_pygen(wrapper())
        self.run_forever()

        return res.fetch()

    def run_pyasyncgen_until_complete(self, coro):
        done = Event()
        res = ResultHolder()

        async def wrapper():
            ret = await coro
            res.store(ret)
            done.set()

        async def watcher():
            await done()
            self.stop()

        self._spawn_pyasyncgen(watcher())
        self._spawn_pyasyncgen(wrapper())
        self.run_forever()

        return res.fetch()

    def stop(self):
        self._stopping = True


def run(coro, **opts):
    # print(
    #     coro,
    #     inspect.isasyncgen(coro),
    #     inspect.isasyncgenfunction(coro),
    #     inspect.iscoroutine(coro),
    #     inspect.iscoroutinefunction(coro),
    # )
    opts['threads'] = opts.get('threads') or multiprocessing.cpu_count()
    opts['threads_blocking'] = opts.get('threads_blocking') or 128
    opts['threads_blocking_timeout'] = opts.get('threads_blocking_timeout') or 30
    runtime = Runtime(**opts)
    _set_runtime(runtime)
    runner = runtime.run_pyasyncgen_until_complete if is_asyncg(coro) else runtime.run_pygen_until_complete
    return runner(coro)
