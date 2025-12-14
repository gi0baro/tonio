import time

from tonio.colored import spawn
from tonio.colored.time import sleep, timeout


def test_sleep(run):
    async def f():
        start = time.monotonic()
        await spawn(sleep(0.05), sleep(0.1))
        return time.monotonic() - start

    assert run(f()) >= 0.1


async def _sleep(x):
    await sleep(x)
    return 3


async def _test_timeout():
    out1, success1 = await timeout(_sleep(0.2), 0.3)
    out2, success2 = await timeout(_sleep(0.2), 0.1)
    assert out1 == 3
    assert out2 is None
    assert success1 is True
    assert success2 is False


def test_timeout(run):
    run(_test_timeout())
