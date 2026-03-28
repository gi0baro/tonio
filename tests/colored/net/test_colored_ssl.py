import ssl

import pytest
import trustme

import tonio.colored as tonio
from tonio.colored.net import socket
from tonio.colored.net.ssl import SSLStream, open_ssl_over_tcp_stream, serve_ssl_over_tcp


_SIZE = 1024 * 1024


@pytest.fixture(scope='session')
def ssl_ca():
    return trustme.CA()


@pytest.fixture(scope='session')
def ssl_cert(ssl_ca):
    return ssl_ca.issue_server_cert('127.0.0.1')


@pytest.fixture(scope='function')
def ssl_server_ctx(ssl_cert):
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_cert.configure_cert(ctx)
    return ctx


@pytest.fixture(scope='function')
def ssl_client_ctx(ssl_ca):
    ctx = ssl.create_default_context()
    ssl_ca.configure_trust(ctx)
    return ctx


async def _get_port():
    sock = socket.socket()

    with sock:
        await sock.bind(('127.0.0.1', 0))
        name = sock.getsockname()
        return name[1]


def test_ssl_tcp_recv(run, ssl_server_ctx, ssl_client_ctx):
    async def server():
        done = tonio.Event()
        res = []
        port = await _get_port()

        async def _server_handler(stream: SSLStream):
            buf = b''
            while len(buf) < _SIZE:
                buf += await stream.receive_some()
            res.append(buf)
            done.set()

        async with tonio.scope() as scope:
            scope.spawn(serve_ssl_over_tcp(_server_handler, host='127.0.0.1', port=port, ssl_context=ssl_server_ctx))
            scope.spawn(client(port))
            await done.wait()
            scope.cancel()

        return res[0]

    async def client(port):
        await tonio.sleep(0.5)
        stream: SSLStream = await open_ssl_over_tcp_stream('127.0.0.1', port=port, ssl_context=ssl_client_ctx)
        await stream.send_all(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_streams_tcp_send(run, ssl_server_ctx, ssl_client_ctx):
    done = tonio.Event()
    state = {'data': b''}

    async def server():
        port = await _get_port()

        async def _server_handler(stream: SSLStream):
            await stream.send_all(b'a' * _SIZE)

        async with tonio.scope() as scope:
            scope.spawn(serve_ssl_over_tcp(_server_handler, host='127.0.0.1', port=port, ssl_context=ssl_server_ctx))
            scope.spawn(client(port))
            await done.wait()
            scope.cancel()

    async def client(port):
        await tonio.sleep(0.5)
        stream: SSLStream = await open_ssl_over_tcp_stream('127.0.0.1', port=port, ssl_context=ssl_client_ctx)
        while len(state['data']) < _SIZE:
            state['data'] += await stream.receive_some()
        done.set()

    run(server())
    assert state['data'] == b'a' * _SIZE
