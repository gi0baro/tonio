import subprocess
import sys
import textwrap

import tonio.colored as tonio


def test_scope_cancel(run):
    enter = []
    exit = []

    async def _sleep(idx, t):
        enter.append(idx)
        await tonio.sleep(t)
        exit.append(idx)

    async def _run():
        async with tonio.scope() as scope:
            scope.spawn(_sleep(1, 0.1))
            scope.spawn(_sleep(2, 2))
            await tonio.sleep(0.2)
            scope.cancel()
        await tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}


def test_scope_cancel_immediate(run):
    enter = []
    exit = []

    async def _sleep(idx, t):
        enter.append(idx)
        await tonio.sleep(t)
        exit.append(idx)

    async def _run():
        async with tonio.scope() as scope:
            scope.cancel()
            scope.spawn(_sleep(1, 0.3))
            await tonio.sleep(0.1)

        await tonio.sleep(0.5)

    run(_run())

    assert set(enter) == {1}
    assert not exit


def test_scope_cancel_pending_sleep_hangs_not():
    # Run in a subprocess as a failure hangs forever
    script = textwrap.dedent("""
        import tonio
        from tonio import colored

        runtime = tonio.runtime(threads=4, blocking_threadpool_size=8, blocking_threadpool_idle_ttl=10, context=True)

        async def _run():
            async with colored.scope() as scope:
                for i in range(50):
                    scope.spawn(colored.sleep(0.01))
                await colored.yield_now()
                scope.cancel()
            await colored.sleep(0.3)

        runtime.run_pyasyncgen_until_complete(_run())
        print('OK')
    """)

    proc = subprocess.run(  # noqa: S603
        [sys.executable, '-c', script], capture_output=True, text=True, timeout=5.0
    )

    assert proc.returncode == 0, proc.stderr
    assert 'OK' in proc.stdout
