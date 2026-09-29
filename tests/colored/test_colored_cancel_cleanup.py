import contextvars
import subprocess
import sys
import types
from collections.abc import Generator
from pathlib import Path

import pytest

import tonio.colored as tonio


def cancellation_cleanup(context: bool, threads: int, first_yield: str) -> None:
    value = contextvars.ContextVar('cleanup', default='unset')
    started = tonio.Event()
    finished = tonio.Event()
    blocked = tonio.Event()
    seen = []

    @types.coroutine
    def yield_none() -> Generator[None]:
        yield

    async def child() -> None:
        value.set('child')
        started.set()
        try:
            await blocked.wait()
            seen.append('not cancelled')
        finally:
            seen.append('finally')
            if context:
                assert value.get() == 'child'
            token = value.set('cleanup')
            if first_yield == 'none':
                await yield_none()
            else:
                await tonio.sleep(0.001)
            for index in range(3):
                await tonio.sleep(0.001)
                await yield_none()
                await tonio.yield_now()
                if context:
                    assert value.get() == 'cleanup'
                seen.append(index)
            if context:
                value.reset(token)
                assert value.get() == 'child'
            finished.set()

    async def main() -> None:
        value.set('parent')
        victim = child()
        async with tonio.scope() as scope:
            scope.spawn(victim)
            await started.wait()
            scope.cancel()
        await finished.wait()
        if context:
            assert value.get() == 'parent'
        assert seen == ['finally', 0, 1, 2]

    tonio.run(main(), context=context, threads=threads)


@pytest.mark.parametrize('context', [False, True])
@pytest.mark.parametrize('threads', [1, 2])
@pytest.mark.parametrize('first_yield', ['sleep', 'none'])
def test_cancel_cleanup(context: bool, threads: int, first_yield: str, tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - Runs this test with fixed, parametrized arguments.
        [sys.executable, str(Path(__file__).resolve()), str(int(context)), str(threads), first_yield],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == '__main__':
    cancellation_cleanup(bool(int(sys.argv[1])), int(sys.argv[2]), sys.argv[3])
