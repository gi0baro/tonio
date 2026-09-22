from __future__ import annotations

import socket as _stdlib_socket
from contextlib import suppress
from types import CoroutineType
from typing import Any

from ..._net._streams import SocketStreamWatcher, _ignorable_accept_errnos, _Stream
from ..._tonio import Waiter, WouldBlock, get_runtime
from ._socket import _Socket


class SocketStream(_Stream):
    __slots__ = ['socket']

    def __init__(self, socket: _Socket):
        if not isinstance(socket, _Socket):
            raise TypeError('SocketStream requires a TonIO socket object')
        if socket.type != _stdlib_socket.SOCK_STREAM:
            raise ValueError('SocketStream requires a SOCK_STREAM socket')

        self.socket = socket

        with suppress(OSError):
            self.socket.setsockopt(_stdlib_socket.IPPROTO_TCP, _stdlib_socket.TCP_NODELAY, True)

        if hasattr(_stdlib_socket, 'TCP_NOTSENT_LOWAT'):
            with suppress(OSError):
                self.socket.setsockopt(_stdlib_socket.IPPROTO_TCP, _stdlib_socket.TCP_NOTSENT_LOWAT, 2**14)

    async def send_all(self, data: bytes | bytearray | memoryview) -> None:
        if self.socket._eof_get():
            raise RuntimeError("can't send data after sending EOF")
        with memoryview(data) as data:
            if not data:
                return
            total_sent = 0
            while total_sent < len(data):
                with data[total_sent:] as remaining:
                    sent = await self.socket.send(remaining)
                total_sent += sent

    def send_eof(self) -> None:
        if self.socket._eof_get():
            return
        self.socket.shutdown(_stdlib_socket.SHUT_WR)

    def receive_some(self, max_bytes: int | None = None) -> CoroutineType[Any, Any, bytes]:
        max_bytes = max_bytes or 65536
        return self.socket.recv(max_bytes)

    async def wait_readable(self, timeout: int | float | None = None) -> bool:
        if timeout is None:
            while (waiter := self.socket._io_arm_r()) is not None:
                await waiter
            return True
        runtime = get_runtime()
        remaining = round(max(timeout, 0) * 1_000_000)
        deadline = runtime._clock + remaining
        while (waiter := self.socket._io_arm_r(remaining)) is not None:
            if remaining == 0:
                return False
            await waiter
            remaining = max(deadline - runtime._clock, 0)
        return True

    async def wait_writable(self, timeout: int | float | None = None) -> bool:
        if timeout is None:
            while (waiter := self.socket._io_arm_w()) is not None:
                await waiter
            return True
        runtime = get_runtime()
        remaining = round(max(timeout, 0) * 1_000_000)
        deadline = runtime._clock + remaining
        while (waiter := self.socket._io_arm_w(remaining)) is not None:
            if remaining == 0:
                return False
            await waiter
            remaining = max(deadline - runtime._clock, 0)
        return True

    def waiter_readable(self, timeout: int | None = None) -> Waiter | None:
        return self.socket._io_arm_r(timeout)

    def waiter_writable(self, timeout: int | None = None) -> Waiter | None:
        return self.socket._io_arm_w(timeout)

    def watch_readable(self) -> SocketStreamWatcher:
        return SocketStreamWatcher(self.socket._io_arm_r)

    def watch_writable(self) -> SocketStreamWatcher:
        return SocketStreamWatcher(self.socket._io_arm_w)

    def receive_some_nowait(self, max_bytes: int | None = None) -> bytes | type[_Stream.NotReady]:
        try:
            return self.socket._sock.recv(max_bytes or 65536)
        except BlockingIOError:
            self.socket._io_clear_r()
            return self.NotReady

    def try_receive_some(self, max_bytes: int | None = None) -> bytes:
        if (ret := self.receive_some_nowait(max_bytes)) is self.NotReady:
            raise WouldBlock('Not ready')
        return ret

    def close(self):
        self.socket.close()


class SocketListener(_Stream):
    def __init__(self, socket: _Socket):
        if not isinstance(socket, _Socket):
            raise TypeError('SocketStream requires a TonIO socket object')
        if socket.type != _stdlib_socket.SOCK_STREAM:
            raise ValueError('SocketStream requires a SOCK_STREAM socket')

        self.socket = socket

    async def accept(self) -> SocketStream:
        while True:
            try:
                sock, _ = await self.socket.accept()
            except OSError as exc:
                if exc.errno not in _ignorable_accept_errnos:
                    raise
            else:
                return SocketStream(sock)

    def close(self):
        self.socket.close()
