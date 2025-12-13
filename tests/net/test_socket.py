import tonio
from tonio.net import socket


_SIZE = 1024 * 1024


def _recv_all(sock: socket.SocketType, nbytes):
    buf = b''
    while len(buf) < nbytes:
        buf += yield sock.recv(nbytes - len(buf))
    return buf


def test_socket_accept_recv(run):
    def server():
        sock = socket.socket()

        with sock:
            yield sock.bind(('127.0.0.1', 0))
            sock.listen()

            task = tonio.spawn(client(sock.getsockname()))

            client_sock, _ = yield sock.accept()
            with client_sock:
                data = yield _recv_all(client_sock, _SIZE)

            yield task

        return data

    def client(addr):
        sock = socket.socket()
        with sock:
            yield sock.connect(addr)
            yield sock.send(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_socket_accept_send(run):
    state = {'data': b''}

    def server():
        sock = socket.socket()

        with sock:
            yield sock.bind(('127.0.0.1', 0))
            sock.listen()

            task = tonio.spawn(client(sock.getsockname()))

            client_sock, _ = yield sock.accept()
            with client_sock:
                yield client_sock.send(b'a' * _SIZE)

            yield task

    def client(addr):
        sock = socket.socket()
        with sock:
            yield sock.connect(addr)
            while len(state['data']) < _SIZE:
                state['data'] += yield sock.recv(1024 * 16)

    run(server())
    assert state['data'] == b'a' * _SIZE
