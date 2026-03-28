"""
Heavily inspired by `trio` code.

:source: (https://github.com/python-trio/trio)
:copyright: Contributors to the Trio project
:license: MIT
"""

import errno
import os
import socket as _stdlib_socket
import ssl as _stdlib_ssl
import sys
from typing import Any

from ..._net._hilvl import _accept_retry_errnos, _close_all_sockets, _close_on_error
from .._ctl import spawn
from .._events import Event
from .._scope import scope
from .._time import sleep
from ._socket import _Socket, getaddrinfo, socket
from ._streams import SocketListener, SocketStream
from ._tls import TLSListener, TLSStream


async def open_tcp_stream(
    host: str | bytes,
    port: int,
    *,
    happy_eyeballs_delay: float | None = None,
    local_address: str | None = None,
) -> SocketStream:
    if not isinstance(host, (str, bytes)):
        raise ValueError(f'host must be str or bytes, not {host!r}')
    if not isinstance(port, int):
        raise TypeError(f'port must be int, not {port!r}')

    if happy_eyeballs_delay is None:
        happy_eyeballs_delay = 0.250

    targets = await getaddrinfo(host, port, type=_stdlib_socket.SOCK_STREAM)
    # TODO: IPv4, IPv6 reorder
    # reorder_targets(targets)
    errs: list[OSError] = []
    winning_socket: _Socket | None = None

    async def attempt_connect(
        socket_args: tuple[int, int, int],
        sockaddr: Any,
        failed: Event,
    ):
        nonlocal winning_socket
        try:
            sock = socket(*socket_args)
            open_sockets.add(sock)

            if local_address is not None:
                # with suppress(OSError, AttributeError):
                #     sock.setsockopt(
                #         _stdlib_socket.IPPROTO_IP,
                #         _stdlib_socket.IP_BIND_ADDRESS_NO_PORT,
                #         1,
                #     )
                try:
                    await sock.bind((local_address, 0))
                except OSError:
                    raise OSError(
                        f'local_address={local_address!r} is incompatible with remote address {sockaddr!r}',
                    ) from None

            await sock.connect(sockaddr)
            winning_socket = sock
            _scope.cancel()
        except OSError as exc:
            errs.append(exc)
            failed.set()

    with _close_all_sockets() as open_sockets:
        async with scope() as _scope:
            for address_family, socket_type, proto, _, addr in targets:
                failed = Event()
                _scope.spawn(
                    attempt_connect(
                        (address_family, socket_type, proto),
                        addr,
                        failed,
                    )
                )
                await failed.wait(happy_eyeballs_delay)

        if winning_socket is None:
            assert len(errs) == len(targets)
            msg = f'all attempts to connect to {(host, port)} failed'
            raise OSError(msg) from ExceptionGroup(msg, errs)

        stream = SocketStream(winning_socket)
        open_sockets.remove(winning_socket)

        return stream


async def open_unix_socket(filename: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> SocketStream:
    sock = socket(_stdlib_socket.AF_UNIX, _stdlib_socket.SOCK_STREAM)
    with _close_on_error(sock):
        await sock.connect(os.fspath(filename))
    return SocketStream(sock)


async def open_tcp_listeners(
    port: int,
    *,
    host: str | bytes | None = None,
    backlog: int | None = None,
) -> list[SocketListener]:
    if not isinstance(port, int):
        raise TypeError(f'port must be an int not {port!r}')

    backlog = min(backlog or 0xFFFF, 0xFFFF)
    addresses = await getaddrinfo(
        host,
        port,
        type=_stdlib_socket.SOCK_STREAM,
        flags=_stdlib_socket.AI_PASSIVE,
    )

    listeners = []
    unsupported_address_families = []
    try:
        for family, type_, proto, _, sockaddr in addresses:
            try:
                sock = socket(family, type_, proto)
            except OSError as ex:
                if ex.errno == errno.EAFNOSUPPORT:
                    unsupported_address_families.append(ex)
                    continue
                else:
                    raise
            try:
                if sys.platform != 'win32':
                    sock.setsockopt(_stdlib_socket.SOL_SOCKET, _stdlib_socket.SO_REUSEADDR, 1)

                if family == _stdlib_socket.AF_INET6:
                    sock.setsockopt(_stdlib_socket.IPPROTO_IPV6, _stdlib_socket.IPV6_V6ONLY, 1)

                await sock.bind(sockaddr)
                sock.listen(backlog)

                listeners.append(SocketListener(sock))
            except:
                sock.close()
                raise
    except:
        for listener in listeners:
            listener.close()
        raise

    if unsupported_address_families and not listeners:
        msg = "This system doesn't support any of the kinds of socket that provided address could use"
        raise OSError(errno.EAFNOSUPPORT, msg) from ExceptionGroup(
            msg,
            unsupported_address_families,
        )

    return listeners


async def serve_listeners(
    handler: Any,
    listeners: list[SocketListener],
) -> None:
    async def _listener_handler(listener: SocketListener):
        with listener:
            while True:
                try:
                    stream = await listener.accept()
                except OSError as exc:
                    if exc.errno in _accept_retry_errnos:
                        await sleep(0.1)
                    else:
                        raise
                else:
                    spawn.without_tracking(handler(stream))

    tasks = []
    for listener in listeners:
        tasks.append(_listener_handler(listener))

    return spawn.without_results(*tasks)


async def serve_tcp(
    handler: Any,
    port: int,
    *,
    host: str | bytes | None = None,
    backlog: int | None = None,
) -> None:
    listeners = await open_tcp_listeners(port, host=host, backlog=backlog)
    await serve_listeners(handler, listeners)


async def open_tls_over_tcp_stream(
    host: str | bytes,
    port: int,
    *,
    https_compatible: bool = False,
    ssl_context: _stdlib_ssl.SSLContext | None = None,
    happy_eyeballs_delay: float | None = None,
) -> TLSStream:
    tcp_stream = await open_tcp_stream(
        host,
        port,
        happy_eyeballs_delay=happy_eyeballs_delay,
    )
    if ssl_context is None:
        ssl_context = _stdlib_ssl.create_default_context()

        if hasattr(_stdlib_ssl, 'OP_IGNORE_UNEXPECTED_EOF'):
            ssl_context.options &= ~_stdlib_ssl.OP_IGNORE_UNEXPECTED_EOF

    return TLSStream(
        tcp_stream,
        ssl_context,
        server_hostname=host,
        https_compatible=https_compatible,
    )


async def open_tls_over_tcp_listeners(
    port: int,
    ssl_context: _stdlib_ssl.SSLContext | None = None,
    *,
    host: str | bytes | None = None,
    https_compatible: bool = False,
    backlog: int | None = None,
) -> list[TLSListener]:
    tcp_listeners = await open_tcp_listeners(port, host=host, backlog=backlog)
    ssl_listeners = [
        TLSListener(tcp_listener, ssl_context, https_compatible=https_compatible) for tcp_listener in tcp_listeners
    ]
    return ssl_listeners


async def serve_tls_over_tcp(
    handler: Any,
    port: int,
    ssl_context: _stdlib_ssl.SSLContext,
    *,
    host: str | bytes | None = None,
    https_compatible: bool = False,
    backlog: int | None = None,
) -> None:
    listeners = await open_tls_over_tcp_listeners(
        port,
        ssl_context,
        host=host,
        https_compatible=https_compatible,
        backlog=backlog,
    )
    await serve_listeners(handler, listeners)
