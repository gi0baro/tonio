import argparse
import json
import time

import tonio.colored as tonio
import tonio.colored.sync.channel as channel


SCENARIOS = [
    # name, producers, consumers, size, messages
    ('spsc', 1, 1, 128, 100_000),
    ('mpsc', 4, 1, 128, 100_000),
    ('mpmc', 4, 4, 128, 100_000),
    ('tight', 1, 1, 1, 10_000),
    ('unbounded', 1, 1, None, 100_000),
]


def _scenario(nprod, ncons, size, nmsgs):
    if size is None:
        sender, receiver = channel.unbounded()
    else:
        sender, receiver = channel.channel(size)
    per_producer = nmsgs // nprod

    async def _produce_bounded():
        for i in range(per_producer):
            await sender.send(i)

    async def _produce_unbounded():
        for i in range(per_producer):
            sender.send(i)
        await tonio.yield_now()

    async def _consume():
        count = 0
        while True:
            try:
                await receiver.receive()
                count += 1
            except Exception:
                break
        return count

    async def _producers():
        produce = _produce_unbounded if size is None else _produce_bounded
        await tonio.spawn(*[produce() for _ in range(nprod)])
        sender.close()

    async def _main():
        t0 = time.monotonic()
        counts = await tonio.spawn(_producers(), *[_consume() for _ in range(ncons)])
        t1 = time.monotonic()
        assert sum(counts[1:]) == nmsgs
        return t1 - t0

    return _main


def main(threads, context):
    runtime = tonio.runtime(context=context, threads=threads)
    res = []
    for _ in range(5):
        run = {}
        for name, nprod, ncons, size, nmsgs in SCENARIOS:
            run[name] = runtime.run_until_complete(_scenario(nprod, ncons, size, nmsgs)())
        res.append(run)
    print(json.dumps(res))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--threads', default=1, type=int, help='no of threads')
    parser.add_argument('--context', default=False, type=bool, help='use context')
    main(**dict(parser.parse_args()._get_kwargs()))
