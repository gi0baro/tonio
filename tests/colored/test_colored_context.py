import contextvars

import tonio.colored as tonio


def test_contextvar(run_with_ctx):
    var = contextvars.ContextVar('_test')
    bef = []
    res = {}
    aft = []

    async def _step(i):
        bef.append(var.get())
        token = var.set(i)
        await tonio.yield_now()
        res[i] = var.get()
        var.reset(token)
        aft.append(var.get())

    async def _run():
        var.set('empty')
        out = await tonio.spawn(*[_step(i) for i in range(50)])
        return out

    run_with_ctx(_run())

    assert set(bef) == {'empty'}
    assert set(aft) == {'empty'}
    assert list(res.keys()) == list(res.values())
