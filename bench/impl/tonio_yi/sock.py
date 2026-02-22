import argparse
import socket as _stdsock

import tonio
import tonio.net.socket as socket


def _send_all(sock, buf):
    while buf:
        sent = yield sock.send(buf)
        buf = buf[sent:]


def echo_server(address):
    sock = socket.socket()
    with sock:
        yield sock.bind(address)
        sock.listen()

        while True:
            client, _ = yield sock.accept()
            tonio.spawn(echo_client(client))


def echo_client(conn):
    try:
        conn.setsockopt(_stdsock.IPPROTO_TCP, _stdsock.TCP_NODELAY, 1)
    except (OSError, NameError):
        pass

    with conn:
        while True:
            data = yield conn.recv(102400)
            if not data:
                break
            yield _send_all(conn, data)


def main(addr, threads, context):
    addr = args.addr.split(':')
    addr[1] = int(addr[1])
    addr = tuple(addr)

    try:
        tonio.run(echo_server(addr), context=context, threads=threads)
    except:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--addr', default='127.0.0.1:25000', type=str)
    parser.add_argument('--threads', default=1, type=int, help='no of threads')
    parser.add_argument('--context', default=False, type=bool, help='use context')
    args = parser.parse_args()
    main(**dict(parser.parse_args()._get_kwargs()))
