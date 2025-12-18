import pytest

from tonio.colored import spawn, sync, yield_now
from tonio.colored.sync import channel


class AtomicError(RuntimeError): ...


def test_semaphore(run):
    stack = []

    async def _count(semaphore, i):
        async with semaphore:
            stack.append(i)
            if len(stack) > 2:
                raise AtomicError
            await yield_now()
            stack.pop(0)
        return i

    async def _run(value):
        semaphore = sync.Semaphore(value)
        out = await spawn(*[_count(semaphore, i) for i in range(50)])
        return out

    assert run(_run(2)) == list(range(50))

    with pytest.raises(ExceptionGroup):
        run(_run(3))


def test_lock(run):
    stack = []

    async def _count(lock, i):
        async with lock:
            stack.append(i)
            if len(stack) > 1:
                raise AtomicError
            await yield_now()
            stack.pop(0)
        return i

    async def _run():
        lock = sync.Lock()
        out = await spawn(*[_count(lock, i) for i in range(50)])
        return out

    assert run(_run()) == list(range(50))


def test_barrier(run):
    barrier = sync.Barrier(3)
    stack = []

    async def _wait():
        stack.append(True)
        i = await barrier.wait()
        assert len(stack) == 3
        return i

    async def _run():
        out = await spawn(*[_wait() for _ in range(3)])
        return out

    assert set(run(_run())) == {0, 1, 2}


def test_channel(run):
    async def _produce(sender, barrier, offset, no):
        for i in range(no):
            message = offset + i
            await sender.send(message)
        await barrier.wait()

    async def _consume(receiver):
        messages = []
        while True:
            try:
                message = await receiver.receive()
                messages.append(message)
            except Exception:
                break
        return messages

    async def _close(sender, barrier):
        await barrier.wait()
        sender.close()

    async def _run2p4c():
        sender, receiver = channel.channel(2)
        barrier = sync.Barrier(3)
        tasks = [
            _produce(sender, barrier, 100, 20),
            _produce(sender, barrier, 200, 20),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _close(sender, barrier),
        ]
        [_, _, c1, c2, c3, c4, _] = await spawn(*tasks)
        return c1, c2, c3, c4

    async def _run4p2c():
        sender, receiver = channel.channel(2)
        barrier = sync.Barrier(5)
        tasks = [
            _produce(sender, barrier, 100, 10),
            _produce(sender, barrier, 200, 10),
            _produce(sender, barrier, 300, 10),
            _produce(sender, barrier, 400, 10),
            _consume(receiver),
            _consume(receiver),
            _close(sender, barrier),
        ]
        [_, _, _, _, c1, c2, _] = await spawn(*tasks)
        return c1, c2

    consumed = run(_run2p4c())
    consumed = {v for c in consumed for v in c}
    assert len(consumed) == 40
    assert consumed == ({*range(100, 120)} | {*range(200, 220)})

    consumed = run(_run4p2c())
    consumed = {v for c in consumed for v in c}
    assert len(consumed) == 40
    assert consumed == ({*range(100, 110)} | {*range(200, 210)} | {*range(300, 310)} | {*range(400, 410)})


def test_channel_unbounded(run):
    async def _produce(sender, barrier, offset, no):
        for i in range(no):
            message = offset + i
            sender.send(message)
        await barrier.wait()

    async def _consume(receiver):
        messages = []
        while True:
            try:
                message = await receiver.receive()
                messages.append(message)
            except Exception:
                break
        return messages

    async def _close(sender, barrier):
        await barrier.wait()
        sender.close()

    async def _run2p4c():
        sender, receiver = channel.unbounded()
        barrier = sync.Barrier(3)
        tasks = [
            _produce(sender, barrier, 100, 20),
            _produce(sender, barrier, 200, 20),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _close(sender, barrier),
        ]
        [_, _, c1, c2, c3, c4, _] = await spawn(*tasks)
        return c1, c2, c3, c4

    async def _run4p2c():
        sender, receiver = channel.unbounded()
        barrier = sync.Barrier(5)
        tasks = [
            _produce(sender, barrier, 100, 10),
            _produce(sender, barrier, 200, 10),
            _produce(sender, barrier, 300, 10),
            _produce(sender, barrier, 400, 10),
            _consume(receiver),
            _consume(receiver),
            _close(sender, barrier),
        ]
        [_, _, _, _, c1, c2, _] = await spawn(*tasks)
        return c1, c2

    consumed = run(_run2p4c())
    consumed = {v for c in consumed for v in c}
    assert len(consumed) == 40
    assert consumed == ({*range(100, 120)} | {*range(200, 220)})

    consumed = run(_run4p2c())
    consumed = {v for c in consumed for v in c}
    assert len(consumed) == 40
    assert consumed == ({*range(100, 110)} | {*range(200, 210)} | {*range(300, 310)} | {*range(400, 410)})
