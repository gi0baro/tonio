import datetime
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path


WD = Path(__file__).resolve().parent
CPU = multiprocessing.cpu_count()
MSGS = [1024, 1024 * 10, 1024 * 100]
CONCURRENCIES = [1, 2, 4, 8]


@contextmanager
def net_server(impl, **extras):
    exc_prefix = os.environ.get('BENCHMARK_EXC_PREFIX')
    py = 'python'
    if exc_prefix:
        py = f'{exc_prefix}/{py}'
    target = WD / 'impl' / impl / 'sock.py'
    cmd_parts = [
        py,
        str(target),
    ]
    for key, val in extras.items():
        cmd_parts.append(f'--{key} {val}')

    proc = subprocess.Popen(' '.join(cmd_parts), shell=True, preexec_fn=os.setsid)  # noqa: S602
    time.sleep(2)
    yield proc
    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def net_client(duration, concurrency, msgsize):
    exc_prefix = os.environ.get('BENCHMARK_EXC_PREFIX')
    py = 'python'
    if exc_prefix:
        py = f'{exc_prefix}/{py}'
    target = WD / 'harness' / 'net_client.py'
    cmd_parts = [
        py,
        str(target),
        f'--concurrency {concurrency}',
        f'--duration {duration}',
        f'--msize {msgsize}',
        '--output json',
    ]
    try:
        proc = subprocess.run(  # noqa: S602
            ' '.join(cmd_parts),
            shell=True,
            check=True,
            capture_output=True,
        )
        data = json.loads(proc.stdout.decode('utf8'))
        return data
    except Exception as e:
        print(f'WARN: got exception {e} while loading client data')
        return {}


def net_benchmark(msgs=None, concurrencies=None):
    concurrencies = concurrencies or CONCURRENCIES
    msgs = msgs or MSGS
    results = {}
    # primer
    net_client(1, 1, 1024)
    time.sleep(1)
    # warm up
    net_client(1, max(concurrencies), 1024 * 100)
    time.sleep(2)
    # bench
    for concurrency in concurrencies:
        cres = results[concurrency] = {}
        for msg in msgs:
            res = net_client(10, concurrency, msg)
            cres[msg] = res
            time.sleep(3)
        time.sleep(1)
    return results


def script_benchmark(bench, impl, **extras):
    exc_prefix = os.environ.get('BENCHMARK_EXC_PREFIX')
    py = 'python'
    if exc_prefix:
        py = f'{exc_prefix}/{py}'
    target = WD / 'impl' / impl / f'{bench}.py'
    cmd_parts = [
        py,
        str(target),
    ]
    for key, val in extras.items():
        cmd_parts.append(f'--{key} {val}')
    try:
        proc = subprocess.run(  # noqa: S602
            ' '.join(cmd_parts),
            shell=True,
            check=True,
            capture_output=True,
        )
        data = json.loads(proc.stdout.decode('utf8'))
        return data
    except Exception as e:
        print(f'WARN: got exception {e} while loading bench data')
        return {}


def filter_script_results(results, vidx=0, mode=1):
    vals = [(v[vidx], idx) for idx, v in enumerate(results)]
    vals.sort(key=lambda v: v[0], reverse=mode == 1)
    return results[vals[1][1]]


def one_million():
    results = []
    impls = [
        ('TonIO yield', 'tonio_yi', {}),
        ('TonIO async', 'tonio_aw', {}),
        ('TonIO yield (context)', 'tonio_yi', {'context': 't'}),
        ('TonIO async (context)', 'tonio_aw', {'context': 't'}),
        ('AsyncIO', 'std', {}),
        ('Trio', 'trio', {}),
        ('TinyIO', 'tinyio', {}),
    ]
    for label, impl, extras in impls:
        res = script_benchmark('1m', impl, **extras)
        results.append((label, filter_script_results(res, 2, -1)))
    return results


def net_sock():
    results = []
    impls = [
        ('TonIO yield', 'tonio_yi', {}),
        ('TonIO async', 'tonio_aw', {}),
        ('TonIO yield (context)', 'tonio_yi', {'context': 't'}),
        ('TonIO async (context)', 'tonio_aw', {'context': 't'}),
        ('AsyncIO', 'std', {}),
        ('Trio', 'trio', {}),
    ]
    for label, impl, extras in impls:
        with net_server(impl, **extras):
            res = net_benchmark(concurrencies=[4])
        results.append((label, res))
    return results


def concurrency():
    results = {'1m': [], 'net_sock': []}
    for label, impl, threads, extras in [
        ('TonIO yield', 'tonio_yi', 1, {}),
        ('TonIO async', 'tonio_aw', 1, {}),
        ('TonIO yield', 'tonio_yi', 2, {'threads': '2'}),
        ('TonIO async', 'tonio_aw', 2, {'threads': '2'}),
        ('TonIO yield', 'tonio_yi', 4, {'threads': '4'}),
        ('TonIO async', 'tonio_aw', 4, {'threads': '4'}),
        ('TonIO yield', 'tonio_yi', 8, {'threads': '8'}),
        ('TonIO async', 'tonio_aw', 8, {'threads': '8'}),
    ]:
        res = script_benchmark('1m', impl, **extras)
        results['1m'].append((label, threads, filter_script_results(res, 2, -1)))

        with net_server(impl, **extras):
            res = net_benchmark(concurrencies=[4])
        results['net_sock'].append((label, threads, res))

    return results


def _tonio_version():
    import tonio

    return tonio.__version__


def run():
    all_benchmarks = {
        '1m': one_million,
        'net_sock': net_sock,
        'concurrency': concurrency,
    }
    inp_benchmarks = sys.argv[1:] or ['1m']
    run_benchmarks = set(inp_benchmarks) & set(all_benchmarks.keys())

    now = datetime.datetime.utcnow()
    results = {}
    for benchmark_key in run_benchmarks:
        runner = all_benchmarks[benchmark_key]
        results[benchmark_key] = runner()

    with open('results/data.json', 'w') as f:
        pyver = sys.version_info
        f.write(
            json.dumps(
                {
                    'cpu': CPU,
                    'run_at': int(now.timestamp()),
                    'pyver': f'{pyver.major}.{pyver.minor}',
                    'results': results,
                    'tonio': _tonio_version(),
                }
            )
        )


if __name__ == '__main__':
    run()
