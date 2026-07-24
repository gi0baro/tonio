import signal
import subprocess
import sys
import time

import pytest

import tonio.colored as tonio
from tonio._colored._subprocess import Process


def test_run_process(run):
    async def _run():
        return await tonio.run_process(
            [sys.executable, '-c', 'import sys; sys.stdout.write(sys.stdin.read()); sys.stderr.write("err")'],
            stdin=b'hello',
            capture_stdout=True,
            capture_stderr=True,
        )

    result = run(_run())
    assert result.returncode == 0
    assert result.stdout == b'hello'
    assert result.stderr == b'err'


def test_run_process_check(run):
    async def _run():
        return await tonio.run_process([sys.executable, '-c', 'import sys; sys.exit(3)'], check=False)

    assert run(_run()).returncode == 3


def test_run_process_check_raises(run):
    async def _run():
        return await tonio.run_process([sys.executable, '-c', 'import sys; sys.exit(3)'])

    with pytest.raises(subprocess.CalledProcessError):
        run(_run())


def test_open_process_wait(run):
    async def _run():
        proc = await tonio.open_process([sys.executable, '-c', 'import time; time.sleep(0.2)'])
        ret = await proc.wait()
        return proc, ret

    proc, ret = run(_run())
    assert ret == 0
    assert proc.returncode == 0
    assert proc._pidfd is None


def test_kill(run):
    async def _run():
        proc = await tonio.open_process([sys.executable, '-c', 'import time; time.sleep(10)'])
        proc.kill()
        return await proc.wait()

    assert run(_run()) == -signal.SIGKILL


def test_already_exited(run):
    popen = subprocess.Popen([sys.executable, '-c', ''])
    while popen.poll() is None:
        time.sleep(0.01)

    proc = Process(popen, None, None, None)
    assert proc._pidfd is None

    async def _run():
        return await proc.wait()

    assert run(_run()) == 0
