import contextlib

import tonio.colored as tonio


def test_scope_cancel(run):
    enter = []
    exit = []

    async def _sleep(idx, t):
        enter.append(idx)
        await tonio.sleep(t)
        exit.append(idx)

    async def _run():
        async with tonio.scope() as scope:
            scope.spawn(_sleep(1, 0.1))
            scope.spawn(_sleep(2, 2))
            await tonio.sleep(0.2)
            scope.cancel()
        await tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_on_exc(run):
    enter = []
    exit = []

    async def _sleep(idx, t):
        enter.append(idx)
        await tonio.sleep(t)
        exit.append(idx)

    async def _run():
        with contextlib.suppress(RuntimeError):
            async with tonio.scope(cancel_on_exc=True) as scope:
                scope.spawn(_sleep(1, 0.1))
                scope.spawn(_sleep(2, 2))
                await tonio.sleep(0.2)
                raise RuntimeError

        await tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_immediate(run):
    enter = []
    exit = []

    async def _sleep(idx, t):
        enter.append(idx)
        await tonio.sleep(t)
        exit.append(idx)

    async def _run():
        async with tonio.scope() as scope:
            scope.cancel()
            scope.spawn(_sleep(1, 0.3))
            await tonio.sleep(0.1)

        await tonio.sleep(0.5)

    run(_run())

    assert set(enter) == {1}
    assert not exit


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
