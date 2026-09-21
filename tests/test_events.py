import pytest

import tonio


def test_waiter_binop_any(run):
    def _run():
        e1, e2, e3 = tonio.Event(), tonio.Event(), tonio.Event()

        def _wait():
            yield e1.wait() | e2.wait() | e3.wait()
            return e1.is_set(), e2.is_set(), e3.is_set()

        def _set():
            yield
            e2.set()

        out = yield tonio.spawn(_wait(), _set())
        e1.set()
        e3.set()
        return out[0]

    assert run(_run()) == (False, True, False)


def test_waiter_binop_errors():
    e1, e2, e3 = tonio.Event(), tonio.Event(), tonio.Event()

    with pytest.raises(NotImplementedError):
        (e1.wait() | e2.wait()) & e3.wait()
    with pytest.raises(NotImplementedError):
        (e1.wait() & e2.wait()) | e3.wait()
    with pytest.raises(TypeError):
        e1.wait() & e1
