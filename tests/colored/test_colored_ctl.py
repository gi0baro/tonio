import tonio.colored as tonio


def test_select(run):
    enter = []
    exit = []

    async def _sleep(idx, t):
        enter.append(idx)
        await tonio.sleep(t)
        exit.append(idx)

    async def _run():
        c1 = _sleep(1, 0.1)
        c2 = _sleep(2, 1)

        await tonio.select(c1, c2)
        await tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_select_rv(run):
    async def _coro(v, t):
        await tonio.sleep(t)
        return v

    async def _run():
        c1 = _coro(1, 0.1)
        c2 = _coro(2, 1)

        ret = await tonio.select(c1, c2)
        await tonio.sleep(2)
        return ret

    assert run(_run()) == 1


def test_select_events(run):
    exe = []

    async def _coro(v, ev):
        await ev.wait()
        exe.append(v)
        return v

    async def _run():
        e1, e2 = tonio.Event(), tonio.Event()
        c1 = _coro(1, e1)
        c2 = _coro(2, e2)

        e1.set()
        ret = await tonio.select(c1, c2)
        await tonio.sleep(0.2)
        return ret

    assert run(_run()) == 1
    assert set(exe) == {1}


def test_as_completed(run):
    async def _sleep(x):
        await tonio.sleep(x)
        return x

    async def _run():
        outs = []
        async for x in tonio.as_completed(_sleep(0.3), _sleep(0.1), _sleep(0.2)):
            outs.append(x)
        return outs

    assert run(_run()) == [0.1, 0.2, 0.3]
