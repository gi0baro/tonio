import json
import time

import trio


async def _task():
    ev = trio.Event()
    ev.set()
    await ev.wait()
    return 3 ** 2


async def _run():
    t0 = time.monotonic()
    async with trio.open_nursery() as n:
        for _ in range(1_000_000):
            n.start_soon(_task)
        t1 = time.monotonic()
    t2 = time.monotonic()
    return (t1 - t0, t2 - t1, t2 - t0)


def main():
    res = []
    for _ in range(5):
        r = trio.run(_run)
        res.append(r)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
