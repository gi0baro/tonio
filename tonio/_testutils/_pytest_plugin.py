from __future__ import annotations

from collections.abc import Generator
from functools import wraps
from inspect import isasyncgenfunction, iscoroutinefunction, isgeneratorfunction, ismethod
from typing import Any

import pytest
from _pytest.outcomes import Exit

import tonio
from tonio._tonio import get_runtime
from tonio.exceptions import RuntimeAlreadyInitializedError


_sentinel = object()
_default_runtime_options = {'context': True, 'threads': 2}


def _iterate_exceptions(
    exception: BaseException,
) -> Generator[BaseException, None, None]:
    if isinstance(exception, BaseExceptionGroup):
        for exc in exception.exceptions:
            yield from _iterate_exceptions(exc)
    else:
        yield exception


async def _asyncgen_step(agen: Any) -> tuple[bool, Any]:
    try:
        return True, await agen.asend(None)
    except StopAsyncIteration:
        return False, None


def _run_test(runtime: Any, func: Any, kwargs: dict[str, Any]) -> None:
    try:
        runtime.run_until_complete(func(**kwargs))
    except BaseExceptionGroup as excgrp:
        for exc in _iterate_exceptions(excgrp):
            if isinstance(exc, (Exit, KeyboardInterrupt, SystemExit)):
                raise exc from excgrp

        raise


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        'tonio_mode',
        default='strict',
        help='tonio plugin mode: "strict" handles only tests marked with `tonio`, "auto" handles every async test',
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getini('tonio_mode') not in ('strict', 'auto'):
        raise pytest.UsageError('tonio_mode must be either "strict" or "auto"')

    config.addinivalue_line(
        'markers',
        'tonio: mark the (coroutine function) test to be run asynchronously via tonio.',
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef: Any, request: Any) -> Generator[Any]:
    def wrapper(tonio_runtime: Any, request: Any, **kwargs: Any) -> Any:
        # Rebind any fixture methods to the request instance
        if request.instance and ismethod(func) and type(func.__self__) is type(request.instance):
            local_func = func.__func__.__get__(request.instance)
        else:
            local_func = func

        if has_runtime_arg:
            kwargs['tonio_runtime'] = tonio_runtime

        if has_request_arg:
            kwargs['request'] = request

        if isasyncgenfunction(local_func):
            agen = local_func(**kwargs)
            yielded, value = tonio_runtime.run_until_complete(_asyncgen_step(agen))
            if not yielded:
                raise RuntimeError('Async generator fixture did not yield')

            yield value

            yielded, _ = tonio_runtime.run_until_complete(_asyncgen_step(agen))
            if yielded:
                raise RuntimeError('Async generator fixture yielded more than once')
        else:
            yield tonio_runtime.run_until_complete(local_func(**kwargs))

    # Only apply this to coroutine functions and async generator functions in requests
    # that involve the tonio_runtime fixture.
    # NOTE: generator functions are standard pytest setup/teardown fixtures, and thus
    #       are left to pytest; `yield` syntax coroutines can use the tonio_run fixture.
    func = fixturedef.func
    if isasyncgenfunction(func) or iscoroutinefunction(func):
        if 'tonio_runtime' in request.fixturenames:
            fixturedef.func = wrapper
            original_argnames = fixturedef.argnames

            if not (has_runtime_arg := 'tonio_runtime' in fixturedef.argnames):
                fixturedef.argnames += ('tonio_runtime',)

            if not (has_request_arg := 'request' in fixturedef.argnames):
                fixturedef.argnames += ('request',)

            try:
                return (yield)
            finally:
                fixturedef.func = func
                fixturedef.argnames = original_argnames

    return (yield)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makeitem(
    collector: pytest.Module | pytest.Class, name: str, obj: object
) -> list[pytest.Function] | None:
    if not collector.istestfunction(obj, name):
        return None

    inner_func = obj.hypothesis.inner_test if hasattr(obj, 'hypothesis') else obj
    if not (iscoroutinefunction(inner_func) or isgeneratorfunction(inner_func)):
        return None

    if collector.config.getini('tonio_mode') != 'auto':
        own_markers = getattr(obj, 'pytestmark', ())
        if not (collector.get_closest_marker('tonio') or any(marker.name == 'tonio' for marker in own_markers)):
            return None

    pytest.mark.usefixtures('tonio_runtime')(obj)
    if isgeneratorfunction(obj):
        # pytest refuses to collect generator functions as tests, collect them ourselves
        return list(collector._genfunctions(name, obj))

    return None


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    def run_with_hypothesis(**kwargs: Any) -> None:
        _run_test(runtime, original_func, kwargs)

    runtime = pyfuncitem.funcargs.get('tonio_runtime', _sentinel)
    if runtime is _sentinel:
        return None

    if hasattr(pyfuncitem.obj, 'hypothesis'):
        # Wrap the inner test function unless it's already wrapped
        original_func = pyfuncitem.obj.hypothesis.inner_test
        if not getattr(original_func, '_tonio_hypothesis_wrapper', False) and (
            iscoroutinefunction(original_func) or isgeneratorfunction(original_func)
        ):
            wraps(original_func)(run_with_hypothesis)
            run_with_hypothesis._tonio_hypothesis_wrapper = True
            pyfuncitem.obj.hypothesis.inner_test = run_with_hypothesis

        return None

    if iscoroutinefunction(pyfuncitem.obj) or isgeneratorfunction(pyfuncitem.obj):
        funcargs = pyfuncitem.funcargs
        testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
        _run_test(runtime, pyfuncitem.obj, testargs)
        return True

    return None


@pytest.fixture(scope='session')
def tonio_runtime_options() -> dict[str, Any]:
    return {}


@pytest.fixture(scope='session')
def tonio_runtime(tonio_runtime_options: dict[str, Any]) -> tonio.Runtime:
    options = {**_default_runtime_options, **tonio_runtime_options}
    try:
        return tonio.runtime(**options)
    except RuntimeAlreadyInitializedError:
        # A runtime already exists (eg: created in a conftest), reuse it
        return get_runtime()


@pytest.fixture(scope='session')
def tonio_run(tonio_runtime: tonio.Runtime) -> Any:
    return tonio_runtime.run_until_complete
