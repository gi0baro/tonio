def test_marked_test(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.tonio
        def test_ok():
            yield
        """
    )
    result = pytester.runpytest_subprocess('-v')
    result.assert_outcomes(passed=1)
    result.stdout.no_fnmatch_line('*tonio_runtime0*')


def test_module_and_class_level_marks(pytester):
    pytester.makepyfile(
        """
        import pytest

        pytestmark = pytest.mark.tonio

        def test_module_mark():
            yield

        class TestKlass:
            def test_class_mark(self):
                yield
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_parametrized_test(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.tonio
        @pytest.mark.parametrize('value', [1, 2, 3])
        def test_ok(value):
            yield
            assert value in (1, 2, 3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=3)


def test_failing_test(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.tonio
        def test_ko():
            yield
            assert False
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(failed=1)


def test_tonio_run_fixture(pytester):
    pytester.makepyfile(
        """
        import pytest

        def setup_coro(state):
            yield
            state.append('setup')
            return state

        def teardown_coro(state):
            yield
            state.append('teardown')

        @pytest.fixture
        def coro_fixture(tonio_run):
            state = tonio_run(setup_coro([]))
            yield state
            tonio_run(teardown_coro(state))
            assert state == ['setup', 'teardown']

        @pytest.mark.tonio
        def test_ok(coro_fixture):
            yield
            assert coro_fixture == ['setup']
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_auto_mode(pytester):
    pytester.makeini(
        """
        [pytest]
        tonio_mode = auto
        """
    )
    pytester.makepyfile(
        """
        def test_yield():
            yield
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_invalid_mode(pytester):
    pytester.makeini(
        """
        [pytest]
        tonio_mode = wat
        """
    )
    pytester.makepyfile('def test_ok(): pass')
    result = pytester.runpytest_subprocess()
    result.stderr.fnmatch_lines(['*tonio_mode must be either*'])


def test_runtime_options(pytester):
    pytester.makeconftest(
        """
        import pytest

        @pytest.fixture(scope='session')
        def tonio_runtime_options():
            return {'threads': 1}
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.tonio
        def test_ok():
            yield
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_existing_runtime_reused(pytester):
    pytester.makeconftest(
        """
        import tonio

        runtime = tonio.runtime(context=True, threads=1)
        """
    )
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.tonio
        def test_ok():
            yield
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
