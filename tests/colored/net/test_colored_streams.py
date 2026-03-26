import tonio.colored as tonio
from tonio.colored.net import SocketStream, open_tcp_stream, serve_tcp, socket


_SIZE = 1024 * 1024


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
