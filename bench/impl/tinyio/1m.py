import json
import time

import tinyio


def _task():
    yield
    return 3 ** 2

def _run():
    t0 = time.monotonic()
    tasks = {_task() for _ in range(1_000_000)}
    t1 = time.monotonic()
    yield tasks
    t2 = time.monotonic()
    return (t1 - t0, t2 - t1, t2 - t0)


def main():
    res = []
    loop = tinyio.Loop()
    for _ in range(5):
        r = loop.run(_run())
        res.append(r)
    print(json.dumps(res))


if __name__ == '__main__':
    main()
