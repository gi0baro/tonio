import contextlib

import tonio


def test_scope_cancel(run):
    enter = []
    exit = []
    g1, g2, b1, b2, e1, e2 = (tonio.Event() for _ in range(6))

    def _child(idx, g, b, e):
        enter.append(idx)
        b.set()
        try:
            yield g.wait()
            exit.append(idx)
        finally:
            e.set()

    def _run():
        with tonio.scope() as scope:
            scope.spawn(_child(1, g1, b1, e1))
            scope.spawn(_child(2, g2, b2, e2))
            yield b2.wait()
            g1.set()
            yield e1.wait()
            scope.cancel()

        # `spawn` calls after exit are noop
        scope.spawn(_child(3, tonio.Event(), tonio.Event(), None))

        yield scope()
        yield e2.wait()

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_on_exc(run):
    enter = []
    exit = []
    g1, g2, b1, b2, e1, e2 = (tonio.Event() for _ in range(6))

    def _child(idx, g, b, e):
        enter.append(idx)
        b.set()
        try:
            yield g.wait()
            exit.append(idx)
        finally:
            e.set()

    def _run():
        with contextlib.suppress(RuntimeError):
            with tonio.scope(cancel_on_exc=True) as scope:
                scope.spawn(_child(1, g1, b1, e1))
                scope.spawn(_child(2, g2, b2, e2))
                yield b2.wait()
                g1.set()
                yield e1.wait()
                raise RuntimeError

        yield scope()
        yield e2.wait()

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_takes_effect_on_exit(run):
    enter = []
    exit = []
    g, b, e = (tonio.Event() for _ in range(3))

    def _child(idx):
        enter.append(idx)
        b.set()
        try:
            yield g.wait()
            exit.append(idx)
        finally:
            e.set()

    def _run():
        with tonio.scope() as scope:
            scope.cancel()
            scope.spawn(_child(1))
            yield b.wait()
        # `spawn` calls after exit are noop
        scope.spawn(_child(2))

        yield scope()
        yield e.wait()

    run(_run())

    assert set(enter) == {1}
    assert not exit


def test_scope_cancellations_are_terminal(run):
    seen = []
    never, started, done = tonio.Event(), tonio.Event(), tonio.Event()

    def _child():
        started.set()
        try:
            yield never.wait()
        except tonio.exceptions.CancelledError:
            seen.append('abort1')
            try:
                yield never.wait()
                seen.append('resume')
            except tonio.exceptions.CancelledError:
                seen.append('abort2')
        finally:
            try:
                yield never.wait()
                seen.append('resume')
            except tonio.exceptions.CancelledError:
                seen.append('abort3')
            done.set()

    def _run():
        with tonio.scope() as scope:
            scope.spawn(_child())
            yield started.wait()
            scope.cancel()
        yield scope()
        yield done.wait(1)

    run(_run())

    assert seen == ['abort1', 'abort2', 'abort3']
    assert done.is_set()


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
