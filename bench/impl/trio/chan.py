import json
import math
import time

import trio


SCENARIOS = [
    # name, producers, consumers, size, messages
    ('spsc', 1, 1, 128, 100_000),
    ('mpsc', 4, 1, 128, 100_000),
    ('mpmc', 4, 4, 128, 100_000),
    ('tight', 1, 1, 1, 10_000),
    ('unbounded', 1, 1, None, 100_000),
]


def _scenario(nprod, ncons, size, nmsgs):
    send_ch, recv_ch = trio.open_memory_channel(math.inf if size is None else size)
    per_producer = nmsgs // nprod

    async def _produce(ch):
        async with ch:
            for i in range(per_producer):
                await ch.send(i)

    async def _consume(ch, counts):
        count = 0
        async with ch:
            async for _ in ch:
                count += 1
        counts.append(count)

    async def _main():
        counts = []
        t0 = time.monotonic()
        async with trio.open_nursery() as nursery:
            for _ in range(nprod):
                nursery.start_soon(_produce, send_ch.clone())
            for _ in range(ncons):
                nursery.start_soon(_consume, recv_ch.clone(), counts)
            send_ch.close()
            recv_ch.close()
        t1 = time.monotonic()
        assert sum(counts) == nmsgs
        return t1 - t0

    return _main


def main():
    res = []
    for _ in range(5):
        run = {}
        for name, nprod, ncons, size, nmsgs in SCENARIOS:
            run[name] = trio.run(_scenario(nprod, ncons, size, nmsgs))
        res.append(run)
    print(json.dumps(res))


if __name__ == '__main__':
    main()
