from tonio.colored import spawn
from tonio.colored.net import socket


_SIZE = 1024 * 1024


async def _recv_all(sock: socket.SocketType, nbytes):
    buf = b''
    while len(buf) < nbytes:
        buf += await sock.recv(nbytes - len(buf))
    return buf


def test_socket_accept_recv(run):
    async def server():
        sock = socket.socket()

        with sock:
            await sock.bind(('127.0.0.1', 0))
            sock.listen()

            task = spawn(client(sock.getsockname()))

            client_sock, _ = await sock.accept()
            with client_sock:
                data = await _recv_all(client_sock, _SIZE)

            await task

        return data

    async def client(addr):
        sock = socket.socket()
        with sock:
            await sock.connect(addr)
            await sock.send(b'a' * _SIZE)

    data = run(server())
    assert data == b'a' * _SIZE


def test_socket_accept_send(run):
    state = {'data': b''}

    async def server():
        sock = socket.socket()

        with sock:
            await sock.bind(('127.0.0.1', 0))
            sock.listen()

            task = spawn(client(sock.getsockname()))

            client_sock, _ = await sock.accept()
            with client_sock:
                await client_sock.send(b'a' * _SIZE)

            await task

    async def client(addr):
        sock = socket.socket()
        with sock:
            await sock.connect(addr)
            while len(state['data']) < _SIZE:
                state['data'] += await sock.recv(1024 * 16)

    run(server())
    assert state['data'] == b'a' * _SIZE
