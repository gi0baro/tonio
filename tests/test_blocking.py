import time

import pytest

import tonio
import tonio.time


def test_spawn(run):
    stack = []

    def _blocking(v):
        time.sleep(0.1)
        stack.append(v)

    def _run():
        a = tonio.spawn_blocking(_blocking, 1)
        b = tonio.spawn_blocking(_blocking, 2)
        yield a
        yield b

    run(_run())
    assert set(stack) == {1, 2}


def test_err(run):
    def _blocking():
        1 / 0

    def _run():
        yield tonio.spawn_blocking(_blocking)

    with pytest.raises(ZeroDivisionError):
        run(_run())


def test_abort(run):
    stack = []

    def _blocking():
        time.sleep(3)
        stack.append(True)

    def _run():
        ret = yield tonio.time.timeout(tonio.spawn_blocking(_blocking), 1)
        yield tonio.time.sleep(3)
        return ret

    ret, completed = run(_run())
    assert not completed
    assert not ret
    assert not stack
