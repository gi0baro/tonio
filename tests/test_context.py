import contextvars

import tonio


def test_contextvar(run_with_ctx):
    var = contextvars.ContextVar('_test')
    bef = []
    res = {}
    aft = []

    def _step(i):
        bef.append(var.get())
        token = var.set(i)
        yield
        res[i] = var.get()
        var.reset(token)
        aft.append(var.get())

    def _run():
        var.set('empty')
        out = yield tonio.spawn(*[_step(i) for i in range(50)])
        return out

    run_with_ctx(_run())

    assert set(bef) == {'empty'}
    assert set(aft) == {'empty'}
    assert list(res.keys()) == list(res.values())
