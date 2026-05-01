import ssl

import pytest
import trustme

import tonio
from tonio.net import socket
from tonio.net.tls import TLSStream, open_tls_over_tcp_stream, serve_tls_over_tcp


_SIZE = 1024 * 1024


@pytest.fixture(scope='session')
def tls_ca():
    return trustme.CA()


@pytest.fixture(scope='session')
def tls_cert(tls_ca):
    return tls_ca.issue_server_cert('127.0.0.1')


@pytest.fixture(scope='function')
def ssl_ctx_server(tls_cert):
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    tls_cert.configure_cert(ctx)
    return ctx


@pytest.fixture(scope='function')
def ssl_ctx_client(tls_ca):
    ctx = ssl.create_default_context()
    tls_ca.configure_trust(ctx)
    return ctx


def _get_port():
    sock = socket.socket()

    with sock:
        yield sock.bind(('127.0.0.1', 0))
        name = sock.getsockname()
        return name[1]


def test_tls_tcp_recv(run, ssl_ctx_server, ssl_ctx_client):
    def server():
        done = tonio.Event()
        res = []
        port = yield _get_port()

        def _server_handler(stream: TLSStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += yield stream.receive_some()
            res.append(buf)
            done.set()

        with tonio.scope() as scope:
            scope.spawn(serve_tls_over_tcp(_server_handler, host='127.0.0.1', port=port, ssl_context=ssl_ctx_server))
            scope.spawn(client(port))
            yield done.wait()
            scope.cancel()
        yield scope()

        return res[0]

    def client(port):
        yield tonio.sleep(0.5)
        stream: TLSStream = yield open_tls_over_tcp_stream('127.0.0.1', port=port, ssl_context=ssl_ctx_client)
        yield stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_tls_tcp_send(run, ssl_ctx_server, ssl_ctx_client):
    done = tonio.Event()
    state = {'data': b''}

    def server():
        port = yield _get_port()

        def _server_handler(stream: TLSStream):
            yield stream.send_all(b'a' * _SIZE)

        with tonio.scope() as scope:
            scope.spawn(serve_tls_over_tcp(_server_handler, host='127.0.0.1', port=port, ssl_context=ssl_ctx_server))
            scope.spawn(client(port))
            yield done.wait()
            scope.cancel()
        yield scope()

    def client(port):
        yield tonio.sleep(0.5)
        stream: TLSStream = yield open_tls_over_tcp_stream('127.0.0.1', port=port, ssl_context=ssl_ctx_client)
        while len(state['data']) < _SIZE:
            state['data'] += yield stream.receive_some()
        done.set()

    run(server())
    assert state['data'] == b'a' * _SIZE
