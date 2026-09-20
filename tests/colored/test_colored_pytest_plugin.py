def test_marked_test(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.mark.tonio
        async def test_ok():
            await tonio.colored.yield_now()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_module_and_class_level_marks(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        pytestmark = pytest.mark.tonio

        async def test_module_mark():
            await tonio.colored.yield_now()

        class TestKlass:
            async def test_class_mark(self):
                await tonio.colored.yield_now()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_parametrized_test(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.mark.tonio
        @pytest.mark.parametrize('value', [1, 2, 3])
        async def test_ok(value):
            await tonio.colored.yield_now()
            assert value in (1, 2, 3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=3)


def test_failing_test(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.mark.tonio
        async def test_ko():
            await tonio.colored.yield_now()
            assert False
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(failed=1)


def test_pytest_yield_fixtures_untouched(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.fixture
        def teardown_fixture(tmp_path):
            yield tmp_path
            tmp_path.joinpath('teardown.txt').write_text('done')

        @pytest.mark.tonio
        async def test_ok(monkeypatch, teardown_fixture):
            monkeypatch.setenv('TONIO_PLUGIN_TEST', '1')
            await tonio.colored.yield_now()
            assert not teardown_fixture.joinpath('teardown.txt').exists()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_async_fixture(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.fixture
        async def async_fixture():
            await tonio.colored.yield_now()
            return 'value'

        @pytest.mark.tonio
        async def test_ok(async_fixture):
            assert async_fixture == 'value'
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_session_scoped_async_fixture(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.fixture(scope='session')
        async def async_fixture():
            await tonio.colored.yield_now()
            return []

        @pytest.mark.tonio
        async def test_first(async_fixture):
            async_fixture.append(1)

        @pytest.mark.tonio
        async def test_cached(async_fixture):
            assert async_fixture == [1]
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_async_generator_fixture(pytester):
    pytester.makepyfile(
        """
        import pytest
        import tonio.colored

        @pytest.fixture
        async def async_gen_fixture(tmp_path):
            await tonio.colored.yield_now()
            yield tmp_path
            await tonio.colored.yield_now()
            tmp_path.joinpath('teardown.txt').write_text('done')

        @pytest.mark.tonio
        async def test_ok(async_gen_fixture):
            assert not async_gen_fixture.joinpath('teardown.txt').exists()

        @pytest.mark.tonio
        async def test_teardown_ran(tmp_path_factory):
            path = tmp_path_factory.getbasetemp().joinpath('test_ok0', 'teardown.txt')
            assert path.read_text() == 'done'
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)


def test_async_generator_fixture_multiple_yields(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        async def async_gen_fixture():
            yield 'value'
            yield 'nope'

        @pytest.mark.tonio
        async def test_ok(async_gen_fixture):
            assert async_gen_fixture == 'value'
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, errors=1)


def test_strict_mode_ignores_unmarked_tests(pytester):
    pytester.makepyfile(
        """
        import tonio.colored

        async def test_unmarked():
            await tonio.colored.yield_now()
        """
    )
    result = pytester.runpytest_subprocess()
    assert result.parseoutcomes().get('passed', 0) == 0


def test_auto_mode(pytester):
    pytester.makeini(
        """
        [pytest]
        tonio_mode = auto
        """
    )
    pytester.makepyfile(
        """
        import tonio.colored

        async def test_async():
            await tonio.colored.yield_now()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
