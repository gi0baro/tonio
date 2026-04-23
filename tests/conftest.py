import pytest

import tonio
from tonio._utils import is_asyncg


_runtime = tonio.runtime(threads=4, blocking_threadpool_size=8, blocking_threadpool_idle_ttl=10, context=True)


@pytest.fixture(scope='function')
def run():
    def inner(coro):
        runner = _runtime.run_pyasyncgen_until_complete if is_asyncg(coro) else _runtime.run_pygen_until_complete
        return runner(coro)

    return inner
