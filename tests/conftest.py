import pytest

from tonio._runtime import Runtime
from tonio._tonio import set_runtime
from tonio._utils import is_asyncg


@pytest.fixture(scope='session')
def runtime():
    rv = Runtime(threads=4, threads_blocking=8, threads_blocking_timeout=10)
    set_runtime(rv)
    return rv


@pytest.fixture(scope='session')
def run(runtime):
    def inner(coro):
        runner = runtime.run_pyasyncgen_until_complete if is_asyncg(coro) else runtime.run_pygen_until_complete
        return runner(coro)

    return inner
