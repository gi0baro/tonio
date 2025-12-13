import time

import tonio


def test_sleep(run):
    def f():
        start = time.monotonic()
        yield tonio.spawn(tonio.sleep(0.05), tonio.sleep(0.1))
        return time.monotonic() - start

    assert run(f()) >= 0.1


def _sleep(x):
    yield tonio.sleep(x)
    return 3


def _test_timeout():
    out1, success1 = yield tonio.timeout(_sleep(0.2), 0.3)
    out2, success2 = yield tonio.timeout(_sleep(0.2), 0.1)
    assert out1 == 3
    assert out2 is None
    assert success1 is True
    assert success2 is False


def test_timeout(run):
    run(_test_timeout())
