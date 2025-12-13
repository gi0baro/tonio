import time

import tonio
import tonio.sync
import tonio.sync.channel as channel


def test_semaphore(run):
    counter = 0

    def _count(semaphore, i):
        nonlocal counter
        with (yield semaphore()):
            counter += 1
            if counter > 2:
                raise RuntimeError
            yield
            counter -= 1
        return i

    def _run(value):
        semaphore = tonio.sync.Semaphore(value)
        out = yield tonio.spawn(*[_count(semaphore, i) for i in range(50)])
        return out

    assert run(_run(2)) == list(range(50))

    # TODO: need global raise
    # with pytest.raises(RuntimeError):
    #     run(_run(3))


def test_lock(run):
    counter = 0

    def _count(semaphore, i):
        nonlocal counter
        with (yield semaphore()):
            counter += 1
            if counter > 1:
                raise RuntimeError
            yield
            counter -= 1
        return i

    def _run():
        semaphore = tonio.sync.Lock()
        out = yield tonio.spawn(*[_count(semaphore, i) for i in range(50)])
        return out

    assert run(_run()) == list(range(50))


def test_barrier(run):
    barrier = tonio.sync.Barrier(3)
    count = 0

    def _foo():
        nonlocal count
        count += 1
        i = yield barrier.wait()
        time.sleep(0.1)
        assert count == 3
        return i

    def _run():
        out = yield tonio.spawn(*[_foo() for _ in range(3)])
        return out

    assert set(run(_run())) == {0, 1, 2}


def test_channel(run):
    def _produce(sender, barrier, offset, no):
        for i in range(no):
            message = offset + i
            yield sender.send(message)
        yield barrier.wait()

    def _consume(receiver, target, count):
        messages = []
        while count < target:
            try:
                message = yield receiver.receive()
                count += 1
                messages.append(message)
            except Exception:
                break
        return messages

    def _close(sender, barrier):
        yield barrier.wait()
        sender.close()

    def _run2p4c():
        count = 0
        sender, receiver = channel.channel(2)
        barrier = tonio.sync.Barrier(3)
        tasks = [
            _produce(sender, barrier, 100, 20),
            _produce(sender, barrier, 200, 20),
            _consume(receiver, 40, count),
            _consume(receiver, 40, count),
            _consume(receiver, 40, count),
            _consume(receiver, 40, count),
            _close(sender, barrier),
        ]
        [_, _, c1, c2, c3, c4, _] = yield tonio.spawn(*tasks)
        return c1, c2, c3, c4

    def _run4p2c():
        count = 0
        sender, receiver = channel.channel(2)
        barrier = tonio.sync.Barrier(5)
        tasks = [
            _produce(sender, barrier, 100, 10),
            _produce(sender, barrier, 200, 10),
            _produce(sender, barrier, 300, 10),
            _produce(sender, barrier, 400, 10),
            _consume(receiver, 40, count),
            _consume(receiver, 40, count),
            _close(sender, barrier),
        ]
        [_, _, _, _, c1, c2, _] = yield tonio.spawn(*tasks)
        return c1, c2

    consumed = run(_run2p4c())
    consumed = {v for c in consumed for v in c}
    assert len(consumed) == 40
    assert consumed == ({*range(100, 120)} | {*range(200, 220)})

    consumed = run(_run4p2c())
    consumed = {v for c in consumed for v in c}
    assert len(consumed) == 40
    assert consumed == ({*range(100, 110)} | {*range(200, 210)} | {*range(300, 310)} | {*range(400, 410)})
