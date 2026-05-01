import ssl

import pytest
import trustme

import tonio.colored as tonio
from tonio.colored.net import socket
from tonio.colored.net.tls import TLSStream, open_tls_over_tcp_stream, serve_tls_over_tcp


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


async def _get_port():
    sock = socket.socket()

    with sock:
        await sock.bind(('127.0.0.1', 0))
        name = sock.getsockname()
        return name[1]


def test_tls_tcp_recv(run, ssl_ctx_server, ssl_ctx_client):
    async def server():
        done = tonio.Event()
        res = []
        port = await _get_port()

        async def _server_handler(stream: TLSStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += await stream.receive_some()
            res.append(buf)
            done.set()

        async with tonio.scope() as scope:
            scope.spawn(serve_tls_over_tcp(_server_handler, host='127.0.0.1', port=port, ssl_context=ssl_ctx_server))
            scope.spawn(client(port))
            await done.wait()
            scope.cancel()

        return res[0]

    async def client(port):
        await tonio.sleep(0.5)
        stream: TLSStream = await open_tls_over_tcp_stream('127.0.0.1', port=port, ssl_context=ssl_ctx_client)
        await stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_tls_tcp_send(run, ssl_ctx_server, ssl_ctx_client):
    done = tonio.Event()
    state = {'data': b''}

    async def server():
        port = await _get_port()

        async def _server_handler(stream: TLSStream):
            await stream.send_all(b'a' * _SIZE)

        async with tonio.scope() as scope:
            scope.spawn(serve_tls_over_tcp(_server_handler, host='127.0.0.1', port=port, ssl_context=ssl_ctx_server))
            scope.spawn(client(port))
            await done.wait()
            scope.cancel()

    async def client(port):
        await tonio.sleep(0.5)
        stream: TLSStream = await open_tls_over_tcp_stream('127.0.0.1', port=port, ssl_context=ssl_ctx_client)
        while len(state['data']) < _SIZE:
            state['data'] += await stream.receive_some()
        done.set()

    run(server())
    assert state['data'] == b'a' * _SIZE
