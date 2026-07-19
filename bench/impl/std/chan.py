import asyncio
import json
import time


SCENARIOS = [
    # name, producers, consumers, size, messages
    ('spsc', 1, 1, 128, 100_000),
    ('mpsc', 4, 1, 128, 100_000),
    ('mpmc', 4, 4, 128, 100_000),
    ('tight', 1, 1, 1, 10_000),
    ('unbounded', 1, 1, None, 100_000),
]


def _scenario(nprod, ncons, size, nmsgs):
    queue = asyncio.Queue(size or 0)
    per_producer = nmsgs // nprod

    async def _produce():
        for i in range(per_producer):
            await queue.put(i)

    async def _consume():
        count = 0
        while True:
            try:
                await queue.get()
                count += 1
            except asyncio.QueueShutDown:
                break
        return count

    async def _producers():
        async with asyncio.TaskGroup() as tg:
            for _ in range(nprod):
                tg.create_task(_produce())
        queue.shutdown()

    async def _main():
        t0 = time.monotonic()
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_producers())
            consumers = [tg.create_task(_consume()) for _ in range(ncons)]
        t1 = time.monotonic()
        assert sum(c.result() for c in consumers) == nmsgs
        return t1 - t0

    return _main


def main():
    res = []
    for _ in range(5):
        run = {}
        for name, nprod, ncons, size, nmsgs in SCENARIOS:
            run[name] = asyncio.run(_scenario(nprod, ncons, size, nmsgs)())
        res.append(run)
    print(json.dumps(res))


if __name__ == '__main__':
    main()
