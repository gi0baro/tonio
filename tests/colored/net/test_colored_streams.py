import errno
import os
import stat
import sys
import tempfile

import pytest

import tonio.colored as tonio
from tonio.colored.net import (
    SocketStream,
    open_tcp_stream,
    open_unix_listener,
    open_unix_socket,
    serve_tcp,
    serve_unix,
    socket,
)


_SIZE = 1024 * 1024


# AF_UNIX paths are capped at ~104 bytes on darwin, so keep the tmp root and the
# socket names short: `tmp_path` fixtures are already too long on macOS
def _sock_path(name='s'):
    return os.path.join(tempfile.mkdtemp(), name)


async def _get_port():
    sock = socket.socket()

    with sock:
        await sock.bind(('127.0.0.1', 0))
        name = sock.getsockname()
        return name[1]


def test_streams_tcp_recv(run):
    async def server():
        done = tonio.Event()
        res = []
        port = await _get_port()

        async def _server_handler(stream: SocketStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += await stream.receive_some()
            res.append(buf)
            done.set()

        async with tonio.scope() as scope:
            scope.spawn(serve_tcp(_server_handler, host='127.0.0.1', port=port))
            scope.spawn(client(port))
            await done.wait()
            scope.cancel()

        return res[0]

    async def client(port):
        await tonio.sleep(0.5)
        stream: SocketStream = await open_tcp_stream('127.0.0.1', port=port)
        await stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_streams_tcp_send(run):
    done = tonio.Event()
    state = {'data': b''}

    async def server():
        port = await _get_port()

        async def _server_handler(stream: SocketStream):
            await stream.send_all(b'a' * _SIZE)
            stream.send_eof()

        async with tonio.scope() as scope:
            scope.spawn(serve_tcp(_server_handler, host='127.0.0.1', port=port))
            scope.spawn(client(port))
            await done.wait()
            scope.cancel()

    async def client(port):
        await tonio.sleep(0.5)
        stream: SocketStream = await open_tcp_stream('127.0.0.1', port=port)
        while len(state['data']) < _SIZE:
            state['data'] += await stream.receive_some()
        done.set()

    run(server())
    assert state['data'] == b'a' * _SIZE


def test_streams_unix_roundtrip(run):
    path = _sock_path()

    async def server():
        done = tonio.Event()
        res = []

        async def _server_handler(stream: SocketStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += await stream.receive_some()
            res.append(buf)
            done.set()

        async with tonio.scope() as scope:
            scope.spawn(serve_unix(_server_handler, path))
            scope.spawn(client())
            await done.wait()
            scope.cancel()

        return res[0]

    async def client():
        await tonio.sleep(0.5)
        stream: SocketStream = await open_unix_socket(path)
        await stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE
    assert stat.S_ISSOCK(os.stat(path).st_mode)


def test_streams_unix_listener_accept(run):
    path = _sock_path()

    async def main():
        listener = await open_unix_listener(path)

        res = []

        async def client():
            stream: SocketStream = await open_unix_socket(path)
            await stream.send_all(b'ping')
            stream.close()

        async with tonio.scope() as scope:
            scope.spawn(client())
            stream = await listener.accept()
            res.append(await stream.receive_some())
            stream.close()

        listener.close()
        return res[0]

    assert run(main()) == b'ping'
    # closing the listener leaves the socket file behind: caller's job
    assert os.path.exists(path)


def test_streams_unix_mode(run):
    path = _sock_path()

    async def main():
        listener = await open_unix_listener(path, mode=0o600)
        listener.close()

    run(main())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_streams_unix_addr_in_use(run):
    path = _sock_path()

    async def main():
        listener = await open_unix_listener(path)
        try:
            with pytest.raises(OSError) as exc:
                await open_unix_listener(path)
            # no automatic unlink: the live listener must survive
            assert exc.value.errno == errno.EADDRINUSE
            assert path in str(exc.value)
        finally:
            listener.close()

    run(main())


def test_streams_unix_missing_folder(run):
    path = os.path.join(tempfile.mkdtemp(), 'nope', 's')

    async def main():
        with pytest.raises(FileNotFoundError):
            await open_unix_listener(path)

    run(main())


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='abstract sockets are Linux-only')
def test_streams_unix_abstract_mode(run):
    async def main():
        with pytest.raises(ValueError, match='abstract namespace'):
            await open_unix_listener(b'\0tonio-test', mode=0o600)

    run(main())
