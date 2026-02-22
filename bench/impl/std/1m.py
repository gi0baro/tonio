import asyncio
import json
import time


async def _task():
    future = asyncio.Future()
    future.set_result(None)
    await future
    return 3 ** 2


async def _run():
    t0 = time.monotonic()
    tasks = [_task() for _ in range(1_000_000)]
    t1 = time.monotonic()
    await asyncio.gather(*tasks)
    t2 = time.monotonic()
    return (t1 - t0, t2 - t1, t2 - t0)


def main():
    res = []
    for _ in range(5):
        r = asyncio.run(_run())
        res.append(r)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
