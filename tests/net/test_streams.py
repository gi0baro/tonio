import errno
import os
import stat
import sys
import tempfile

import pytest

import tonio
from tonio.net import (
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


def _get_port():
    sock = socket.socket()

    with sock:
        yield sock.bind(('127.0.0.1', 0))
        name = sock.getsockname()
        return name[1]


def test_streams_tcp_recv(run):
    def server():
        done = tonio.Event()
        res = []
        port = yield _get_port()

        def _server_handler(stream: SocketStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += yield stream.receive_some()
            res.append(buf)
            done.set()

        with tonio.scope() as scope:
            scope.spawn(serve_tcp(_server_handler, host='127.0.0.1', port=port))
            scope.spawn(client(port))
            yield done.wait()
            scope.cancel()
        yield scope()

        return res[0]

    def client(port):
        yield tonio.sleep(0.5)
        stream: SocketStream = yield open_tcp_stream('127.0.0.1', port=port)
        yield stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_streams_tcp_send(run):
    done = tonio.Event()
    state = {'data': b''}

    def server():
        port = yield _get_port()

        def _server_handler(stream: SocketStream):
            yield stream.send_all(b'a' * _SIZE)
            stream.send_eof()

        with tonio.scope() as scope:
            scope.spawn(serve_tcp(_server_handler, host='127.0.0.1', port=port))
            scope.spawn(client(port))
            yield done.wait()
            scope.cancel()
        yield scope()

    def client(port):
        yield tonio.sleep(0.5)
        stream: SocketStream = yield open_tcp_stream('127.0.0.1', port=port)
        while len(state['data']) < _SIZE:
            state['data'] += yield stream.receive_some()
        done.set()

    run(server())
    assert state['data'] == b'a' * _SIZE


def test_streams_unix_roundtrip(run):
    path = _sock_path()

    def server():
        done = tonio.Event()
        res = []

        def _server_handler(stream: SocketStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += yield stream.receive_some()
            res.append(buf)
            done.set()

        with tonio.scope() as scope:
            scope.spawn(serve_unix(_server_handler, path))
            scope.spawn(client())
            yield done.wait()
            scope.cancel()
        yield scope()

        return res[0]

    def client():
        yield tonio.sleep(0.5)
        stream: SocketStream = yield open_unix_socket(path)
        yield stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE
    assert stat.S_ISSOCK(os.stat(path).st_mode)


def test_streams_unix_listener_accept(run):
    path = _sock_path()

    def main():
        listener = yield open_unix_listener(path)

        res = []

        def client():
            stream: SocketStream = yield open_unix_socket(path)
            yield stream.send_all(b'ping')
            stream.close()

        with tonio.scope() as scope:
            scope.spawn(client())
            stream = yield listener.accept()
            res.append((yield stream.receive_some()))
            stream.close()
        yield scope()

        listener.close()
        return res[0]

    assert run(main()) == b'ping'
    # closing the listener leaves the socket file behind: caller's job
    assert os.path.exists(path)


def test_streams_unix_mode(run):
    path = _sock_path()

    def main():
        listener = yield open_unix_listener(path, mode=0o600)
        listener.close()

    run(main())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_streams_unix_addr_in_use(run):
    path = _sock_path()

    def main():
        listener = yield open_unix_listener(path)
        try:
            with pytest.raises(OSError) as exc:
                yield open_unix_listener(path)
            # no automatic unlink: the live listener must survive
            assert exc.value.errno == errno.EADDRINUSE
            assert path in str(exc.value)
        finally:
            listener.close()

    run(main())


def test_streams_unix_missing_folder(run):
    path = os.path.join(tempfile.mkdtemp(), 'nope', 's')

    def main():
        with pytest.raises(FileNotFoundError):
            yield open_unix_listener(path)

    run(main())


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='abstract sockets are Linux-only')
def test_streams_unix_abstract_mode(run):
    def main():
        with pytest.raises(ValueError, match='abstract namespace'):
            yield open_unix_listener(b'\0tonio-test', mode=0o600)

    run(main())
