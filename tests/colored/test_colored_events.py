import tonio.colored as tonio


def test_waiter_binop_any(run):
    async def _run():
        e1, e2, e3 = tonio.Event(), tonio.Event(), tonio.Event()

        async def _wait():
            await (e1.wait() | e2.wait() | e3.wait())
            return e1.is_set(), e2.is_set(), e3.is_set()

        async def _set():
            await tonio.yield_now()
            e2.set()

        out = await tonio.spawn(_wait(), _set())
        e1.set()
        e3.set()
        return out[0]

    assert run(_run()) == (False, True, False)
