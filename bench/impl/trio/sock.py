import argparse
import socket as _stdsock

import trio
import trio.socket as socket


async def _send_all(sock, buf):
    while buf:
        sent = await sock.send(buf)
        buf = buf[sent:]


async def echo_server(address):
    async with trio.open_nursery() as n:
        sock = socket.socket()
        with sock:
            await sock.bind(address)
            sock.listen()

            while True:
                client, _ = await sock.accept()
                n.start_soon(echo_client, client)


async def echo_client(conn):
    try:
        conn.setsockopt(_stdsock.IPPROTO_TCP, _stdsock.TCP_NODELAY, 1)
    except (OSError, NameError):
        pass

    with conn:
        while True:
            data = await conn.recv(102400)
            if not data:
                break
            await _send_all(conn, data)


def main(addr):
    addr = args.addr.split(':')
    addr[1] = int(addr[1])
    addr = tuple(addr)

    try:
        trio.run(echo_server, addr)
    except:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--addr', default='127.0.0.1:25000', type=str)
    args = parser.parse_args()
    main(**dict(parser.parse_args()._get_kwargs()))
