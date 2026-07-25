import pathlib

import pytest

import tonio.colored.fs as fs


@pytest.fixture
def tree(tmp_path):
    (tmp_path / 'a.txt').write_text('l1\nl2\nl3\n')
    (tmp_path / 'b.bin').write_bytes(b'\x00\x01\x02')
    (tmp_path / 'sub').mkdir()
    (tmp_path / 'sub' / 'c.txt').write_text('nested')
    return tmp_path


def test_open_roundtrip(run, tmp_path):
    target = tmp_path / 'out.txt'

    async def _run():
        f = await fs.open(target, 'w', encoding='utf-8')
        written = await f.write('hello ünï\n')
        await f.close()

        f = await fs.open(target, 'r', encoding='utf-8')
        text = await f.read()
        await f.close()

        f = await fs.open(target, 'rb')
        peeked = await f.peek(1)
        buf = bytearray(5)
        count = await f.readinto(buf)
        await f.close()
        return written, text, peeked.startswith(b'h'), count, bytes(buf)

    assert run(_run()) == (10, 'hello ünï\n', True, 5, b'hello')


def test_missing_method_raises_attribute_error(run, tree):
    async def _run():
        f = await fs.open(tree / 'a.txt', 'r')
        try:
            await f.peek(1)  # text handles have no `peek`
        finally:
            await f.close()

    with pytest.raises(AttributeError):
        run(_run())


def test_async_iteration(run, tree):
    async def _run():
        f = await fs.open(tree / 'a.txt', 'r')
        lines = [line async for line in f]
        await f.close()
        return lines

    assert run(_run()) == ['l1\n', 'l2\n', 'l3\n']


def test_async_iteration_terminates_on_edge_cases(run, tmp_path):
    (tmp_path / 'empty.txt').write_text('')
    (tmp_path / 'no-newline.txt').write_text('only')

    async def _run():
        out = []
        for name in ('empty.txt', 'no-newline.txt'):
            f = await fs.open(tmp_path / name, 'r')
            out.append([line async for line in f])
            await f.close()
        return out

    assert run(_run()) == [[], ['only']]


def test_async_context_manager(run, tree):
    async def _run():
        async with await fs.open(tree / 'a.txt', 'r') as f:
            data = await f.read()
        return data, f.closed

    assert run(_run()) == ('l1\nl2\nl3\n', True)


def test_async_context_manager_closes_on_error(run, tree):
    holder = {}

    async def _run():
        async with await fs.open(tree / 'a.txt', 'r') as f:
            holder['f'] = f
            raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        run(_run())
    assert holder['f'].closed


def test_sync_attrs_bypass_the_threadpool(run, tree):
    async def _run():
        f = await fs.open(tree / 'a.txt', 'r')
        snapshot = (
            f.name,
            f.mode,
            f.closed,
            f.readable(),
            f.writable(),
            f.seekable(),
            f.encoding.lower(),
            isinstance(f.fileno(), int),
        )
        await f.close()
        return snapshot, f.closed

    snapshot, closed_after = run(_run())
    assert snapshot == (str(tree / 'a.txt'), 'r', False, True, False, True, 'utf-8', True)
    assert closed_after


def test_detach_rewraps(run, tree):
    async def _run():
        f = await fs.open(tree / 'b.bin', 'rb')
        raw = await f.detach()
        kinds = type(raw).__name__, type(raw.wrapped).__name__
        await raw.close()
        return kinds

    assert run(_run()) == ('IOWrapper', 'FileIO')


def test_errors_cross_the_threadpool_boundary(run, tmp_path):
    async def _run():
        await fs.open(tmp_path / 'nope.txt', 'r')

    with pytest.raises(FileNotFoundError):
        run(_run())


def test_path_open(run, tree):
    async def _run():
        f = await (fs.Path(tree) / 'a.txt').open('r')
        data = await f.read()
        await f.close()
        return data

    assert run(_run()) == 'l1\nl2\nl3\n'


def test_path_kwargs_reach_the_target(run, tmp_path):
    base = fs.Path(tmp_path)

    async def _run():
        await (base / 't.txt').write_text('ünï', encoding='utf-8')
        return await (base / 't.txt').read_text(encoding='utf-8')

    assert run(_run()) == 'ünï'


def test_path_listings_are_reusable_lists(run, tree):
    base = fs.Path(tree)

    async def _run():
        return await base.iterdir(), await base.glob('*.txt'), await base.rglob('*.txt')

    entries, globbed, rglobbed = run(_run())
    for listing in (entries, globbed, rglobbed):
        assert isinstance(listing, list)
        assert len(listing) == len(list(listing)) == len(list(listing))
        assert all(type(item) is fs.PosixPath for item in listing)
    assert sorted(p.name for p in entries) == ['a.txt', 'b.bin', 'sub']
    assert sorted(p.name for p in globbed) == ['a.txt']
    assert sorted(p.name for p in rglobbed) == ['a.txt', 'c.txt']


def test_path_returning_methods_return_tonio_paths(run, tmp_path):
    base = fs.Path(tmp_path)

    async def _run():
        await (base / 'src').touch()
        await (base / 'link').symlink_to(base / 'src')
        return [
            await (base / 'src').resolve(),
            await (base / 'src').absolute(),
            await (base / 'link').readlink(),
            await (base / 'src').rename(base / 'renamed'),
            await (base / 'renamed').replace(base / 'replaced'),
            await fs.Path('~').expanduser(),
            await fs.Path.cwd(),
            await fs.Path.home(),
            await fs.PosixPath.cwd(),
        ]

    for result in run(_run()):
        assert type(result) is fs.PosixPath


def test_path_walk_rebuilds_dirpaths(run, tree):
    async def _run():
        return await fs.Path(tree).walk()

    walked = run(_run())
    assert all(type(dirpath) is fs.PosixPath for dirpath, _, _ in walked)
    assert {dirpath.name: sorted(files) for dirpath, _, files in walked} == {
        tree.name: ['a.txt', 'b.bin'],
        'sub': ['c.txt'],
    }


@pytest.mark.parametrize('kind', ['str', 'pathlib', 'tonio'])
def test_path_samefile_accepts_every_path_flavour(run, tree, kind):
    base = fs.Path(tree)
    other = {
        'str': str(tree / 'a.txt'),
        'pathlib': pathlib.Path(tree / 'a.txt'),
        'tonio': base / 'a.txt',
    }[kind]

    async def _run():
        return await (base / 'a.txt').samefile(other), await (base / 'b.bin').samefile(other)

    assert run(_run()) == (True, False)


@pytest.mark.parametrize('kind', ['str', 'pathlib', 'tonio'])
def test_path_copy_accepts_every_path_flavour(run, tree, kind):
    base = fs.Path(tree)
    raw = tree / f'copy-{kind}.txt'
    target = {'str': str(raw), 'pathlib': pathlib.Path(raw), 'tonio': fs.Path(raw)}[kind]

    async def _run():
        return await (base / 'a.txt').copy(target)

    result = run(_run())
    assert type(result) is fs.PosixPath
    assert raw.read_text() == 'l1\nl2\nl3\n'


def test_path_copy_into_and_move(run, tree):
    base = fs.Path(tree)

    async def _run():
        copied = await (base / 'a.txt').copy_into(base / 'sub')
        moved = await (base / 'b.bin').move(base / 'sub' / 'moved.bin')
        moved_into = await (base / 'sub' / 'moved.bin').move_into(base)
        return copied, moved, moved_into

    copied, moved, moved_into = run(_run())
    assert all(type(p) is fs.PosixPath for p in (copied, moved, moved_into))
    assert (tree / 'sub' / 'a.txt').read_text() == 'l1\nl2\nl3\n'
    assert (tree / 'moved.bin').read_bytes() == b'\x00\x01\x02'
    assert not (tree / 'sub' / 'moved.bin').exists()
