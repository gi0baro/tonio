import argparse
import json
import time

import tonio


def _task():
    yield
    return 3 ** 2


def _run():
    t0 = time.monotonic()
    tasks = [_task() for _ in range(1_000_000)]
    t1 = time.monotonic()
    yield tonio.spawn(*tasks)
    t2 = time.monotonic()
    return (t1 - t0, t2 - t1, t2 - t0)


def main(threads, context):
    res = []
    runtime = tonio.runtime(context=context, threads=threads)
    for _ in range(5):
        r = runtime.run_until_complete(_run())
        res.append(r)
    print(json.dumps(res))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--threads', default=1, type=int, help='no of threads')
    parser.add_argument('--context', default=False, type=bool, help='use context')
    main(**dict(parser.parse_args()._get_kwargs()))
