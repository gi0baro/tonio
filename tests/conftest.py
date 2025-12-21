import pytest

import tonio
import tonio._colored
import tonio._colored._net._socket
import tonio._colored._scope
import tonio._colored._time
import tonio._net._socket
import tonio._time
from tonio._runtime import Runtime
from tonio._utils import is_asyncg


_runtime = Runtime(threads=4, threads_blocking=8, threads_blocking_timeout=10, context=False)
_runtime_wctx = Runtime(threads=4, threads_blocking=8, threads_blocking_timeout=10, context=True)


@pytest.fixture(scope='function')
def runtime(monkeypatch):
    monkeypatch.setattr(tonio._ctl, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._scope, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._time, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._net._socket, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._colored._ctl, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._colored._scope, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._colored._time, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._colored._net._socket, 'get_runtime', lambda: _runtime)
    return _runtime


@pytest.fixture(scope='function')
def runtime_with_ctx(monkeypatch):
    monkeypatch.setattr(tonio._ctl, 'get_runtime', lambda: _runtime_wctx)
    monkeypatch.setattr(tonio._scope, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._time, 'get_runtime', lambda: _runtime_wctx)
    monkeypatch.setattr(tonio._net._socket, 'get_runtime', lambda: _runtime_wctx)
    monkeypatch.setattr(tonio._colored._ctl, 'get_runtime', lambda: _runtime_wctx)
    monkeypatch.setattr(tonio._colored._scope, 'get_runtime', lambda: _runtime)
    monkeypatch.setattr(tonio._colored._time, 'get_runtime', lambda: _runtime_wctx)
    monkeypatch.setattr(tonio._colored._net._socket, 'get_runtime', lambda: _runtime_wctx)
    return _runtime_wctx


@pytest.fixture(scope='function')
def run(runtime):
    def inner(coro):
        runner = runtime.run_pyasyncgen_until_complete if is_asyncg(coro) else runtime.run_pygen_until_complete
        return runner(coro)

    return inner


@pytest.fixture(scope='function')
def run_with_ctx(runtime_with_ctx):
    def inner(coro):
        runner = (
            runtime_with_ctx.run_pyasyncgen_until_complete
            if is_asyncg(coro)
            else runtime_with_ctx.run_pygen_until_complete
        )
        return runner(coro)

    return inner
