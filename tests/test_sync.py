import pytest

import tonio
import tonio.sync
import tonio.sync.channel as channel
import tonio.time


class AtomicError(RuntimeError): ...


def test_semaphore(run):
    stack = []

    def _count(semaphore, i, barrier):
        with (yield semaphore()):
            stack.append(i)
            if barrier:
                yield barrier.wait()
            if len(stack) > 2:
                raise AtomicError
            yield
            stack.pop(0)
        return i

    def _run(value, with_barrier=False):
        stack.clear()
        semaphore = tonio.sync.Semaphore(value)
        barrier = tonio.sync.Barrier(value) if with_barrier else None
        out = yield tonio.spawn(*[_count(semaphore, i, barrier) for i in range(50)])
        return out

    assert run(_run(2)) == list(range(50))

    with pytest.raises(ExceptionGroup):
        run(_run(50, True))


def test_semaphore_cancel_acquire(run):
    def _run():
        sem = tonio.sync.Semaphore(2)
        release_ev = tonio.Event()
        got = []

        def holder():
            with (yield sem()):
                yield release_ev.waiter(None)

        def doomed():
            with (yield sem()):
                got.append('doomed')

        with tonio.scope() as sc:
            sc.spawn(holder())
            sc.spawn(holder())
            yield tonio.sleep(0.1)
            for _ in range(3):
                with tonio.scope() as inner:
                    inner.spawn(doomed())
                    yield tonio.sleep(0.05)
                    inner.cancel()
                yield inner()

            release_ev.set()
            yield tonio.sleep(0.1)

            def pair():
                with (yield sem()):
                    with (yield sem()):
                        got.append('pair')

            _, completed = yield tonio.time.timeout(pair(), 2)
            assert completed, 'semaphore bled permits to cancelled acquirers'

        return got

    assert run(_run()) == ['pair']


def test_lock(run):
    stack = []

    def _count(lock, i):
        with (yield lock()):
            stack.append(i)
            if len(stack) > 1:
                raise AtomicError
            yield
            stack.pop(0)
        return i

    def _run():
        lock = tonio.sync.Lock()
        out = yield tonio.spawn(*[_count(lock, i) for i in range(50)])
        return out

    assert run(_run()) == list(range(50))


def test_lock_cancel_acquire(run):
    def _run():
        lock = tonio.sync.Lock()
        release_ev = tonio.Event()
        got = []

        def holder():
            with (yield lock()):
                yield release_ev.waiter(None)

        def doomed():
            with (yield lock()):
                got.append('doomed')

        with tonio.scope() as sc:
            sc.spawn(holder())
            yield tonio.sleep(0.1)
            with tonio.scope() as inner:
                inner.spawn(doomed())
                yield tonio.sleep(0.1)
                inner.cancel()
            yield inner()

            release_ev.set()

            def third():
                with (yield lock()):
                    got.append('third')

            _, completed = yield tonio.time.timeout(third(), 2)
            assert completed, 'lock wedged: handoff landed on a cancelled acquirer'

        return got

    assert run(_run()) == ['third']


def test_barrier(run):
    barrier = tonio.sync.Barrier(3)
    stack = []

    def _wait():
        stack.append(True)
        i = yield barrier.wait()
        assert len(stack) == 3
        return i

    def _run():
        out = yield tonio.spawn(*[_wait() for _ in range(3)])
        return out

    assert set(run(_run())) == {0, 1, 2}


def test_channel(run):
    def _produce(sender, barrier, offset, no):
        for i in range(no):
            message = offset + i
            yield sender.send(message)
        yield barrier.wait()

    def _consume(receiver):
        messages = []
        while True:
            try:
                message = yield receiver.receive()
                messages.append(message)
            except Exception:
                break
        return messages

    def _close(sender, barrier):
        yield barrier.wait()
        sender.close()

    def _run2p4c():
        sender, receiver = channel.channel(2)
        barrier = tonio.sync.Barrier(3)
        tasks = [
            _produce(sender, barrier, 100, 20),
            _produce(sender, barrier, 200, 20),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _close(sender, barrier),
        ]
        [_, _, c1, c2, c3, c4, _] = yield tonio.spawn(*tasks)
        return c1, c2, c3, c4

    def _run4p2c():
        sender, receiver = channel.channel(2)
        barrier = tonio.sync.Barrier(5)
        tasks = [
            _produce(sender, barrier, 100, 10),
            _produce(sender, barrier, 200, 10),
            _produce(sender, barrier, 300, 10),
            _produce(sender, barrier, 400, 10),
            _consume(receiver),
            _consume(receiver),
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


def test_channel_unbounded(run):
    def _produce(sender, barrier, offset, no):
        for i in range(no):
            message = offset + i
            sender.send(message)
        yield barrier.wait()

    def _consume(receiver):
        messages = []
        while True:
            try:
                message = yield receiver.receive()
                messages.append(message)
            except Exception:
                break
        return messages

    def _close(sender, barrier):
        yield barrier.wait()
        sender.close()

    def _run2p4c():
        sender, receiver = channel.unbounded()
        barrier = tonio.sync.Barrier(3)
        tasks = [
            _produce(sender, barrier, 100, 20),
            _produce(sender, barrier, 200, 20),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _consume(receiver),
            _close(sender, barrier),
        ]
        [_, _, c1, c2, c3, c4, _] = yield tonio.spawn(*tasks)
        return c1, c2, c3, c4

    def _run4p2c():
        sender, receiver = channel.unbounded()
        barrier = tonio.sync.Barrier(5)
        tasks = [
            _produce(sender, barrier, 100, 10),
            _produce(sender, barrier, 200, 10),
            _produce(sender, barrier, 300, 10),
            _produce(sender, barrier, 400, 10),
            _consume(receiver),
            _consume(receiver),
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
