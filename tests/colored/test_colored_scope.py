import contextlib

import tonio.colored as tonio


def test_scope_cancel(run):
    enter = []
    exit = []
    g1, g2, b1, b2, e1, e2 = (tonio.Event() for _ in range(6))

    async def _child(idx, g, b, e):
        enter.append(idx)
        b.set()
        try:
            await g.wait()
            exit.append(idx)
        finally:
            e.set()

    async def _run():
        async with tonio.scope() as scope:
            scope.spawn(_child(1, g1, b1, e1))
            scope.spawn(_child(2, g2, b2, e2))
            await b2.wait()
            g1.set()
            await e1.wait()
            scope.cancel()

        await e2.wait()

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_on_exc(run):
    enter = []
    exit = []
    g1, g2, b1, b2, e1, e2 = (tonio.Event() for _ in range(6))

    async def _child(idx, g, b, e):
        enter.append(idx)
        b.set()
        try:
            await g.wait()
            exit.append(idx)
        finally:
            e.set()

    async def _run():
        with contextlib.suppress(RuntimeError):
            async with tonio.scope(cancel_on_exc=True) as scope:
                scope.spawn(_child(1, g1, b1, e1))
                scope.spawn(_child(2, g2, b2, e2))
                await b2.wait()
                g1.set()
                await e1.wait()
                raise RuntimeError

        await e2.wait()

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_takes_effect_on_exit(run):
    enter = []
    exit = []
    g, b, e = (tonio.Event() for _ in range(3))

    async def _child():
        enter.append(1)
        b.set()
        try:
            await g.wait()
            exit.append(1)
        finally:
            e.set()

    async def _run():
        async with tonio.scope() as scope:
            scope.cancel()
            scope.spawn(_child())
            await b.wait()

        await e.wait()

    run(_run())

    assert set(enter) == {1}
    assert not exit


def test_scope_cancellations_are_terminal(run):
    seen = []
    never, started, done = tonio.Event(), tonio.Event(), tonio.Event()

    async def _child():
        started.set()
        try:
            await never.wait()
        except tonio.exceptions.CancelledError:
            seen.append('abort1')
            try:
                await never.wait()
                seen.append('resume')
            except tonio.exceptions.CancelledError:
                seen.append('abort2')
        finally:
            try:
                await never.wait()
                seen.append('resume')
            except tonio.exceptions.CancelledError:
                seen.append('abort3')
            done.set()

    async def _run():
        async with tonio.scope() as scope:
            scope.spawn(_child())
            await started.wait()
            scope.cancel()
        await done.wait(1)

    run(_run())

    assert seen == ['abort1', 'abort2', 'abort3']
    assert done.is_set()


def test_scope_checkpoint_finalize_children(run):
    checkpoint = tonio.Waiter.checkpoint()
    done = tonio.Event()
    seen = []

    async def _probe():
        try:
            await checkpoint
            checkpoint.abort()
            await tonio.sleep(0.001)
            seen.append('resumed')
        except tonio.exceptions.CancelledError:
            seen.append('cancelled')
        finally:
            seen.append('finally')
            done.set()

    async def _run():
        tonio.spawn.without_tracking(_probe())
        await done.wait(1)

    run(_run())

    assert seen == ['cancelled', 'finally']
