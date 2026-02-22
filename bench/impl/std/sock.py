import argparse
import asyncio
import socket


async def echo_server(loop, address):
    sock = socket.socket()
    sock.bind(address)
    sock.listen()
    sock.setblocking(False)

    with sock:
        while True:
            client, _ = await loop.sock_accept(sock)
            loop.create_task(echo_client(loop, client))


async def echo_client(loop, conn):
    try:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except (OSError, NameError):
        pass

    with conn:
        while True:
            data = await loop.sock_recv(conn, 102400)
            if not data:
                break
            await loop.sock_sendall(conn, data)


def main(addr):
    addr = args.addr.split(':')
    addr[1] = int(addr[1])
    addr = tuple(addr)

    loop = asyncio.new_event_loop()

    loop.create_task(echo_server(loop, addr))
    try:
        loop.run_forever()
    finally:
        loop.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--addr', default='127.0.0.1:25000', type=str)
    args = parser.parse_args()
    main(**dict(parser.parse_args()._get_kwargs()))
