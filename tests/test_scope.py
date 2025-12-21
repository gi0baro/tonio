import tonio


def test_scope_cancel(run):
    enter = []
    exit = []

    def _sleep(idx, t):
        enter.append(idx)
        yield tonio.sleep(t)
        exit.append(idx)

    def _run():
        with tonio.scope() as scope:
            scope.spawn(_sleep(1, 0.1))
            scope.spawn(_sleep(2, 2))
            yield tonio.sleep(0.2)
            scope.cancel()
        yield scope()
        yield tonio.sleep(2)

    run(_run())

    assert set(enter) == {1, 2}
    assert set(exit) == {1}
