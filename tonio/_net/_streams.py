from __future__ import annotations

import errno
import socket as _stdlib_socket
from abc import ABC, abstractmethod
from contextlib import suppress
from types import TracebackType

from .._types import Coro
from ._socket import _Socket


class _Stream(ABC):
    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @abstractmethod
    def close(self): ...


class SocketStream(_Stream):
    __slots__ = ['socket']

    def __init__(self, socket: _Socket):
        if not isinstance(socket, _Socket):
            raise TypeError('SocketStream requires a TonIO socket object')
        if socket.type != _stdlib_socket.SOCK_STREAM:
            raise ValueError('SocketStream requires a SOCK_STREAM socket')

        self.socket = socket

        if hasattr(_stdlib_socket, 'TCP_NOTSENT_LOWAT'):
            with suppress(OSError):
                self.socket.setsockopt(_stdlib_socket.IPPROTO_TCP, _stdlib_socket.TCP_NOTSENT_LOWAT, 2**14)

    def send_all(self, data: bytes | bytearray | memoryview) -> Coro[None]:
        if self.socket._eof_get():
            raise RuntimeError("can't send data after sending EOF")
        with memoryview(data) as data:
            if not data:
                return
            total_sent = 0
            while total_sent < len(data):
                with data[total_sent:] as remaining:
                    sent = yield self.socket.send(remaining)
                total_sent += sent

    def send_eof(self) -> None:
        if self.socket._eof_get():
            return
        self.socket.shutdown(_stdlib_socket.SHUT_WR)

    def receive_some(self, max_bytes: int | None = None) -> Coro[bytes]:
        max_bytes = max_bytes or 65536
        return self.socket.recv(max_bytes)

    def close(self):
        self.socket.close()


_ignorable_accept_errnos: set[int] = set()
for name in [
    'ECONNABORTED',
    'ECONNRESET',
    'EHOSTDOWN',
    'EHOSTUNREACH',
    'ENETDOWN',
    'ENETUNREACH',
    'ENONET',
    'ENOPROTOOPT',
    'ENOSR',
    'EOPNOTSUPP',
    'EPERM',
    'EPROTO',
    'EPROTONOSUPPORT',
    'ESOCKTNOSUPPORT',
    'ETIMEDOUT',
]:
    with suppress(AttributeError):
        _ignorable_accept_errnos.add(getattr(errno, name))


class SocketListener(_Stream):
    def __init__(self, socket: _Socket):
        if not isinstance(socket, _Socket):
            raise TypeError('SocketStream requires a TonIO socket object')
        if socket.type != _stdlib_socket.SOCK_STREAM:
            raise ValueError('SocketStream requires a SOCK_STREAM socket')

        self.socket = socket

    def accept(self) -> Coro[SocketStream]:
        while True:
            try:
                sock, _ = yield self.socket.accept()
            except OSError as exc:
                if exc.errno not in _ignorable_accept_errnos:
                    raise
            else:
                return SocketStream(sock)

    def close(self):
        self.socket.close()
