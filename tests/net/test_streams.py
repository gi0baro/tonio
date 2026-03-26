import tonio
from tonio.net import SocketStream, open_tcp_stream, serve_tcp, socket


_SIZE = 1024 * 1024


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
