from __future__ import annotations

import dataclasses
import types
from collections.abc import Callable, Coroutine, Generator, Iterator
from contextlib import ExitStack, contextmanager
from inspect import isasyncgenfunction, iscoroutinefunction, isgeneratorfunction, ismethod
from typing import Any, TypeVar

import pytest
from _pytest.fixtures import FuncFixtureInfo, SubRequest
from _pytest.outcomes import Exit
from _pytest.python import CallSpec2
from _pytest.scope import Scope

import tonio


_T = TypeVar('_T')
_sentinel = object()


def _iterate_exceptions(
    exception: BaseException,
) -> Generator[BaseException, None, None]:
    if isinstance(exception, BaseExceptionGroup):
        for exc in exception.exceptions:
            yield from _iterate_exceptions(exc)
    else:
        yield exception


class TestRunner:
    def __init__(self, runtime):
        self._runtime = runtime

    def __enter__(self) -> TestRunner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> bool | None: ...

    def _run(self, coro):
        return self._runtime.run_until_complete(coro)

    def run_fixture(
        self,
        fixture_func: Callable[..., Coroutine[Any, Any, _T]],
        kwargs: dict[str, Any],
    ) -> _T:
        return self._run(fixture_func(**kwargs))

    def run_test(self, test_func: Callable[..., Coroutine[Any, Any, Any]], kwargs: dict[str, Any]) -> None:
        return self._run(test_func(**kwargs))


_current_runner: TestRunner | None = None
_runner_stack: ExitStack | None = None


def extract_runtime_options(backend: object) -> dict[str, Any]:
    if isinstance(backend, dict):
        return backend
    return {}


@contextmanager
def get_runner(runtime_options: dict[str, Any]) -> Iterator[TestRunner]:
    global _current_runner, _runner_stack
    if _current_runner is None:
        _runner_stack = ExitStack()
        runtime_options = runtime_options or {}
        runtime = tonio.runtime(context=True, threads=runtime_options.get('threads', 2))
        _current_runner = _runner_stack.enter_context(TestRunner(runtime))

    yield _current_runner


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        'markers',
        'tonio: mark the (coroutine function) test to be run asynchronously via tonio.',
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_fixture_setup(fixturedef: Any, request: Any) -> Generator[Any]:
    def wrapper(tonio_runtime: Any, request: SubRequest, **kwargs: Any) -> Any:
        # Rebind any fixture methods to the request instance
        if request.instance and ismethod(func) and type(func.__self__) is type(request.instance):
            local_func = func.__func__.__get__(request.instance)
        else:
            local_func = func

        runtime_options = extract_runtime_options(tonio_runtime)
        if has_runtime_arg:
            kwargs['tonio_runtime'] = tonio_runtime

        if has_request_arg:
            kwargs['request'] = request

        with get_runner(runtime_options) as runner:
            yield runner.run_fixture(local_func, kwargs)

    # Only apply this to coroutine functions and async generator functions in requests
    # that involve the tonio_runtime fixture
    func = fixturedef.func
    if isasyncgenfunction(func) or iscoroutinefunction(func) or isgeneratorfunction(func):
        if 'tonio_runtime' in request.fixturenames:
            fixturedef.func = wrapper
            original_argname = fixturedef.argnames

            if not (has_runtime_arg := 'tonio_runtime' in fixturedef.argnames):
                fixturedef.argnames += ('tonio_runtime',)

            if not (has_request_arg := 'request' in fixturedef.argnames):
                fixturedef.argnames += ('request',)

            try:
                return (yield)
            finally:
                fixturedef.func = func
                fixturedef.argnames = original_argname

    return (yield)


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makeitem(collector: pytest.Module | pytest.Class, name: str, obj: object) -> None:
    if collector.istestfunction(obj, name):
        inner_func = obj.hypothesis.inner_test if hasattr(obj, 'hypothesis') else obj
        if iscoroutinefunction(inner_func) or isgeneratorfunction(inner_func):
            marker = collector.get_closest_marker('tonio')
            own_markers = getattr(obj, 'pytestmark', ())
            if marker or any(marker.name == 'tonio' for marker in own_markers):
                pytest.mark.usefixtures('tonio_runtime')(obj)


def pytest_collection_finish(session: pytest.Session) -> None:
    for i, item in reversed(list(enumerate(session.items))):
        if (
            isinstance(item, pytest.Function)
            and (iscoroutinefunction(item.function) or isgeneratorfunction(item.function))
            and item.get_closest_marker('tonio') is not None
            and 'tonio_runtime' not in item.fixturenames
        ):
            new_items = []
            try:
                cs_fields = {f.name for f in dataclasses.fields(CallSpec2)}
            except TypeError:
                cs_fields = set()

            if '_arg2scope' in cs_fields:  # pytest >= 8
                callspec = CallSpec2(
                    params={'tonio_runtime': None},
                    indices={'tonio_runtime': 0},
                    _arg2scope={'tonio_runtime': Scope.Module},
                    _idlist=[None],
                    marks=[],
                )
            else:  # pytest 7.x
                callspec = CallSpec2(  # type: ignore[call-arg]
                    funcargs={},
                    params={'tonio_runtime': None},
                    indices={'tonio_runtime': 0},
                    arg2scope={'tonio_runtime': Scope.Module},
                    idlist=[None],
                    marks=[],
                )

            fi = item._fixtureinfo
            new_names_closure = list(fi.names_closure)
            if 'tonio_runtime' not in new_names_closure:
                new_names_closure.append('tonio_runtime')

            new_fixtureinfo = FuncFixtureInfo(
                argnames=fi.argnames,
                initialnames=fi.initialnames,
                names_closure=new_names_closure,
                name2fixturedefs=fi.name2fixturedefs,
            )
            new_item = pytest.Function.from_parent(
                item.parent,
                name=f'{item.originalname}[tonio]',
                callspec=callspec,
                callobj=item.obj,
                fixtureinfo=new_fixtureinfo,
                keywords=item.keywords,
                originalname=item.originalname,
            )
            new_items.append(new_item)

            session.items[i : i + 1] = new_items


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    def run_with_hypothesis(**kwargs: Any) -> None:
        with get_runner(runtime_options) as runner:
            runner.run_test(original_func, kwargs)

    runtime = pyfuncitem.funcargs.get('tonio_runtime', _sentinel)
    if runtime is not _sentinel:
        runtime_options = extract_runtime_options(runtime)

        if hasattr(pyfuncitem.obj, 'hypothesis'):
            # Wrap the inner test function unless it's already wrapped
            original_func = pyfuncitem.obj.hypothesis.inner_test
            if original_func.__qualname__ != run_with_hypothesis.__qualname__:
                if iscoroutinefunction(original_func) or isgeneratorfunction(original_func):
                    pyfuncitem.obj.hypothesis.inner_test = run_with_hypothesis

            return None

        if iscoroutinefunction(pyfuncitem.obj) or isgeneratorfunction(pyfuncitem.obj):
            funcargs = pyfuncitem.funcargs
            testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
            with get_runner(runtime_options) as runner:
                try:
                    runner.run_test(pyfuncitem.obj, testargs)
                except ExceptionGroup as excgrp:
                    for exc in _iterate_exceptions(excgrp):
                        if isinstance(exc, (Exit, KeyboardInterrupt, SystemExit)):
                            raise exc from excgrp

                    raise

            return True

    return None


@pytest.fixture(scope='module', params=[{}])
def tonio_runtime(request: Any) -> Any:
    return request.param


@pytest.fixture
def tonio_runtime_options(tonio_runtime: Any) -> dict[str, Any]:
    if isinstance(tonio_runtime, dict):
        return tonio_runtime
    return {}
