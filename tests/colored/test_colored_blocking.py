import time

import pytest

import tonio.colored as tonio


def test_spawn(run):
    stack = []

    def _blocking(v):
        time.sleep(0.1)
        stack.append(v)

    async def _run():
        a = tonio.spawn_blocking(_blocking, 1)
        b = tonio.spawn_blocking(_blocking, 2)
        await a
        await b

    run(_run())
    assert set(stack) == {1, 2}


def test_err(run):
    def _blocking():
        1 / 0

    async def _run():
        await tonio.spawn_blocking(_blocking)

    with pytest.raises(ZeroDivisionError):
        run(_run())


def test_abort(run):
    stack = []

    def _blocking():
        time.sleep(3)
        stack.append(True)

    async def _run():
        ret = await tonio.time.timeout(tonio.spawn_blocking(_blocking), 1)
        await tonio.time.sleep(3)
        return ret

    ret, completed = run(_run())
    assert not completed
    assert not ret
    assert not stack


def test_block_on(run):
    stack = []
    ev1 = tonio.Event()
    ev2 = tonio.Event()

    async def _coro1():
        stack.append(1)
        ev1.set()
        await ev2.wait()

    async def _coro2():
        await ev1.wait()
        stack.append(2)
        ev2.set()

    def _blocking():
        tonio.block_on(_coro2())

    async def _run():
        a = tonio.spawn(_coro1())
        b = tonio.spawn_blocking(_blocking)
        await b
        await a

    run(_run())
    assert set(stack) == {1, 2}
