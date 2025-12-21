import time

import tonio.colored as tonio


def test_time(run):
    stack = []

    async def _run():
        stack.append(tonio.time.time())
        await tonio.yield_now()
        stack.append(tonio.time.time())

    run(_run())
    assert stack[1] > stack[0]


def test_sleep(run):
    async def _run():
        start = time.monotonic()
        await tonio.spawn(tonio.sleep(0.05), tonio.sleep(0.1))
        return time.monotonic() - start

    assert run(_run()) >= 0.1


def test_timeout(run):
    stack = []

    async def _sleep(x):
        await tonio.time.sleep(x)
        stack.append(x)
        return 3

    async def _run():
        out1, success1 = await tonio.time.timeout(_sleep(0.2), 0.3)
        out2, success2 = await tonio.time.timeout(_sleep(0.2), 0.1)
        await tonio.time.sleep(1)
        return (out1, out2, success1, success2)

    out1, out2, success1, success2 = run(_run())
    assert out1 == 3
    assert out2 is None
    assert success1 is True
    assert success2 is False
    assert len(stack) == 1
