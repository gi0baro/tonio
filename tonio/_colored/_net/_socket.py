from __future__ import annotations

import os
import socket as _stdlib_socket
from typing import Any, Awaitable

from ..._net import _socket
from ..._tonio import get_runtime
from .._ctl import spawn_blocking


class _Socket(_socket._Socket):
    def __enter__(self) -> _Socket:
        return self

    def dup(self) -> _Socket:
        return _Socket(self._sock.dup())

    async def bind(self, address: Any) -> None:
        # TODO: error handling
        address = await self._resolve_address(address, local=True)
        await spawn_blocking(self._sock.bind, address)

    def _resolve_address(
        self,
        address: Any,
        *,
        local: bool,
    ) -> Awaitable[Any]:
        if self.family == _stdlib_socket.AF_INET6:
            ipv6_v6only = self._sock.getsockopt(
                _stdlib_socket.IPPROTO_IPV6,
                _stdlib_socket.IPV6_V6ONLY,
            )
        else:
            ipv6_v6only = False
        return _resolve_address(
            self.type,
            self.family,
            self.proto,
            ipv6_v6only=ipv6_v6only,
            address=address,
            local=local,
        )

    async def accept(self):
        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._reader_add(fd, False)

        while True:
            await event.waiter(None)
            try:
                conn, address = self._sock.accept()
            except (BlockingIOError, InterruptedError):
                event = runtime._reader_add(fd, False)
                continue
            except BaseException as exc:
                raise exc
            else:
                break

        return from_stdlib_socket(conn), address

    async def connect(self, address: Any) -> None:
        address = await self._resolve_address(address, local=False)

        try:
            self._sock.connect(address)
        except (BlockingIOError, InterruptedError):
            pass
        else:
            return

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._writer_add(fd, False)

        while True:
            await event.waiter(None)
            try:
                err = self._sock.getsockopt(_stdlib_socket.SOL_SOCKET, _stdlib_socket.SO_ERROR)
                if err != 0:
                    raise OSError(err, 'Connect call failed %s' % (address,))
            except (BlockingIOError, InterruptedError):
                event = runtime._writer_add(fd, False)
                continue
            except BaseException as exc:
                raise exc
            else:
                break

    async def recv(self, bufsize: int, flags: int = 0, /) -> bytes:
        try:
            data = self._sock.recv(bufsize, flags)
        except (BlockingIOError, InterruptedError):
            data = None

        if data is not None:
            return data

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._reader_add(fd, False)

        while True:
            await event.waiter(None)
            try:
                data = self._sock.recv(bufsize, flags)
            except (BlockingIOError, InterruptedError):
                event = runtime._reader_add(fd, False)
                continue
            except BaseException as exc:
                raise exc
            else:
                break

        return data

    async def send(self, data: Any, flags: int = 0, /) -> int:
        if not data:
            return 0

        try:
            n = self._sock.send(data, flags)
        except (BlockingIOError, InterruptedError):
            n = 0

        if n == len(data):
            return n

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._writer_add(fd, True)
        sent = n

        while True:
            await event.waiter(None)
            event.clear()

            try:
                n = self._sock.send(data[sent:], flags)
            except (BlockingIOError, InterruptedError):
                continue
            except BaseException as exc:
                runtime._writer_rem(fd)
                raise exc

            sent += n
            if sent == len(data):
                runtime._writer_rem(fd)
                break

        return sent


def from_stdlib_socket(sock: _stdlib_socket.socket) -> _Socket:
    return _Socket(sock)


def socket(
    family: int = _stdlib_socket.AF_INET,
    type: int = _stdlib_socket.SOCK_STREAM,
    proto: int = 0,
    fileno: int | None = None,
) -> _Socket:
    # TODO: handle fileno (get opts)
    stdlib_socket = _stdlib_socket.socket(family, type, proto, fileno)
    return from_stdlib_socket(stdlib_socket)


def getaddrinfo(
    host: bytes | str | None,
    port: bytes | str | int | None,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0,
) -> Awaitable[
    list[
        tuple[
            Any,
            int,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
        ]
    ]
]:
    return spawn_blocking(
        _stdlib_socket.getaddrinfo,
        host,
        port,
        family,
        type,
        proto,
        flags,
    )


async def _resolve_address(
    type_: int,
    family: Any,
    proto: int,
    *,
    ipv6_v6only: bool | int,
    address: Any,
    local: bool,
) -> Any:
    if family == _stdlib_socket.AF_INET:
        if not isinstance(address, tuple) or not len(address) == 2:
            raise ValueError('address should be a (host, port) tuple')
    elif family == _stdlib_socket.AF_INET6:
        if not isinstance(address, tuple) or not 2 <= len(address) <= 4:
            raise ValueError(
                'address should be a (host, port, [flowinfo, [scopeid]]) tuple',
            )
    elif hasattr(_stdlib_socket, 'AF_UNIX') and family == _stdlib_socket.AF_UNIX:
        assert isinstance(address, (str, bytes, os.PathLike))
        return os.fspath(address)
    else:
        return address

    host: str | None
    host, port, *_ = address
    if isinstance(port, int) and host is not None:
        try:
            _stdlib_socket.inet_pton(family, host)
        except (OSError, TypeError):
            pass
        else:
            return address

    if host == '':
        host = None
    if host == '<broadcast>':
        host = '255.255.255.255'
    flags = 0
    if local:
        flags |= _stdlib_socket.AI_PASSIVE
    if family == _stdlib_socket.AF_INET6 and not ipv6_v6only:
        flags |= _stdlib_socket.AI_V4MAPPED
    gai_res = await getaddrinfo(host, port, family, type_, proto, flags)
    assert len(gai_res) >= 1
    (*_, normed), *_ = gai_res
    if family == _stdlib_socket.AF_INET6:
        list_normed = list(normed)
        assert len(normed) == 4
        if len(address) >= 3:
            list_normed[2] = address[2]
        if len(address) >= 4:
            list_normed[3] = address[3]
        return tuple(list_normed)
    return normed
