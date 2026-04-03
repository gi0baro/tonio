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
            scope.spawn(_sleep(1, 0.2))
        await tonio.sleep(0.4)

    run(_run())

    assert set(enter) == {1}
    assert not exit
