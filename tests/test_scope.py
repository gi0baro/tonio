import contextlib

import tonio


def test_scope_cancel(run):
    enter = []
    exit = []

    def _sleep(idx, t):
        enter.append(idx)
        yield tonio.sleep(t)
        exit.append(idx)

    def _run():
        with tonio.scope() as scope:
            scope.spawn(_sleep(1, 0.1))
            scope.spawn(_sleep(2, 2))
            yield tonio.sleep(0.2)
            scope.cancel()
        # `spawn` calls after exit are noop
        scope.spawn(_sleep(3, 0.1))

        yield scope()
        yield tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_on_exc(run):
    enter = []
    exit = []

    def _sleep(idx, t):
        enter.append(idx)
        yield tonio.sleep(t)
        exit.append(idx)

    def _run():
        with contextlib.suppress(RuntimeError):
            with tonio.scope(cancel_on_exc=True) as scope:
                scope.spawn(_sleep(1, 0.1))
                scope.spawn(_sleep(2, 2))
                yield tonio.sleep(0.2)
                raise RuntimeError

        yield scope()
        yield tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_immediate(run):
    enter = []
    exit = []

    def _sleep(idx, t):
        enter.append(idx)
        yield tonio.sleep(t)
        exit.append(idx)

    def _run():
        with tonio.scope() as scope:
            scope.cancel()
            scope.spawn(_sleep(1, 0.3))
            yield tonio.sleep(0.1)
        # `spawn` calls after exit are noop
        scope.spawn(_sleep(2, 1))

        yield scope()
        yield tonio.sleep(0.5)

    run(_run())

    assert set(enter) == {1}
    assert not exit


def test_scope_checkpoint_finalize_children(run):
    checkpoint = tonio.Waiter.checkpoint()
    done = tonio.Event()
    seen = []

    def _inner():
        yield checkpoint
        checkpoint.unwind()
        try:
            yield tonio.sleep(0.001)
            seen.append('resumed')
        except tonio.exceptions.CancelledError:
            seen.append('cancelled')
        finally:
            seen.append('finally')

    def _probe():
        try:
            yield _inner()
        finally:
            done.set()

    def _run():
        tonio.spawn.without_tracking(_probe())
        yield done.wait(1)

    run(_run())

    assert seen == ['cancelled', 'finally']
