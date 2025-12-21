import time

import tonio
import tonio.time


def test_time(run):
    stack = []

    def _run():
        stack.append(tonio.time.time())
        yield
        stack.append(tonio.time.time())

    run(_run())
    assert stack[1] > stack[0]


def test_sleep(run):
    def _run():
        start = time.monotonic()
        yield tonio.spawn(tonio.time.sleep(0.05), tonio.time.sleep(0.1))
        return time.monotonic() - start

    assert run(_run()) >= 0.1


def test_timeout(run):
    stack = []

    def _sleep(x):
        yield tonio.time.sleep(x)
        stack.append(x)
        return 3

    def _run():
        out1, success1 = yield tonio.time.timeout(_sleep(0.2), 0.3)
        out2, success2 = yield tonio.time.timeout(_sleep(0.2), 0.1)
        yield tonio.time.sleep(1)
        return (out1, out2, success1, success2)

    out1, out2, success1, success2 = run(_run())
    assert out1 == 3
    assert out2 is None
    assert success1 is True
    assert success2 is False
    assert len(stack) == 1
