from __future__ import annotations

import os
import socket as _stdlib_socket
import sys
from types import TracebackType
from typing import Any

from .._ctl import spawn_blocking
from .._tonio import Socket as _SocketWrapper, get_runtime
from .._types import Coro


class _Socket(_SocketWrapper):
    def detach(self) -> int:
        return self._sock.detach()

    def fileno(self) -> int:
        return self._sock.fileno()

    def getpeername(self) -> Any:
        return self._sock.getpeername()

    def getsockname(self) -> Any:
        return self._sock.getsockname()

    def getsockopt(
        self,
        level: int,
        optname: int,
        buflen: int | None = None,
    ) -> int | bytes:
        if buflen is None:
            return self._sock.getsockopt(level, optname)
        return self._sock.getsockopt(level, optname, buflen)

    def setsockopt(
        self,
        level: int,
        optname: int,
        value: Any,
        optlen: int | None = None,
    ) -> None:
        if optlen is None:
            if value is None:
                raise TypeError(
                    "invalid value for argument 'value', must not be None when specifying optlen",
                )
            return self._sock.setsockopt(level, optname, value)
        if value is not None:
            raise TypeError(
                f"invalid value for argument 'value': {value!r}, must be None when specifying optlen",
            )

        return self._sock.setsockopt(level, optname, value, optlen)

    def listen(self, backlog: int = min(_stdlib_socket.SOMAXCONN, 128)) -> None:
        return self._sock.listen(backlog)

    def get_inheritable(self) -> bool:
        return self._sock.get_inheritable()

    def set_inheritable(self, inheritable: bool) -> None:
        return self._sock.set_inheritable(inheritable)

    def __enter__(self) -> _Socket:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return self._sock.__exit__(exc_type, exc_value, traceback)

    @property
    def family(self) -> Any:
        return self._sock.family

    @property
    def type(self) -> int:
        return self._sock.type

    @property
    def proto(self) -> int:
        return self._sock.proto

    # @property
    # def did_shutdown_SHUT_WR(self) -> bool:
    #     return self._did_shutdown_SHUT_WR

    def __repr__(self) -> str:
        return repr(self._sock).replace('socket.socket', 'tonio.net.socket.socket')

    def dup(self) -> _Socket:
        return _Socket(self._sock.dup())

    def close(self) -> None:
        if self._sock.fileno() != -1:
            # TODO: cleanup runtime refs
            # get_runtime().notify_closing(self._sock)
            self._sock.close()

    def bind(self, address: Any) -> Coro[None]:
        # TODO: error handling
        # print('BIND')
        address = yield self._resolve_address(address, local=True)
        # print('BIND', address)
        yield spawn_blocking(self._sock.bind, address)
        # print('BOUND')

    def shutdown(self, flag: int) -> None:
        self._sock.shutdown(flag)
        # if flag in [_stdlib_socket.SHUT_WR, _stdlib_socket.SHUT_RDWR]:
        #     self._did_shutdown_SHUT_WR = True

    def _resolve_address(
        self,
        address: Any,
        *,
        local: bool,
    ) -> Coro[Any]:
        # print('SRESADDR', self, address)
        if self.family == _stdlib_socket.AF_INET6:
            ipv6_v6only = self._sock.getsockopt(
                _stdlib_socket.IPPROTO_IPV6,
                _stdlib_socket.IPV6_V6ONLY,
            )
        else:
            ipv6_v6only = False
        addr = yield _resolve_address(
            self.type,
            self.family,
            self.proto,
            ipv6_v6only=ipv6_v6only,
            address=address,
            local=local,
        )
        return addr

    def accept(self):
        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._reader_add(fd, False)

        while True:
            yield event.waiter(None)
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

    def connect(self, address: Any) -> Coro[None]:
        # print('SOCK CONNECT', address)
        address = yield self._resolve_address(address, local=False)
        # print('SOCK CONNECT ADDR', address)

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
            yield event.waiter(None)
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

    def recv(self, bufsize: int, flags: int = 0, /) -> Coro[bytes]:
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
            yield event.waiter(None)
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

    def recv_into(self, /, buffer, nbytes: int = 0, flags: int = 0) -> Coro[int]:
        try:
            n = self._sock.recv_into(buffer, nbytes, flags)
        except (BlockingIOError, InterruptedError):
            n = -1

        if n >= 0:
            return n

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._reader_add(fd, False)

        while True:
            yield event.waiter(None)
            try:
                ret = self._sock.recv_into(buffer, nbytes, flags)
            except (BlockingIOError, InterruptedError):
                event = runtime._reader_add(fd, False)
                continue
            except BaseException as exc:
                raise exc
            else:
                break

        return ret

    def recvfrom(self, bufsize: int, flags: int = 0, /) -> Coro[tuple[bytes, Any]]:
        try:
            ret = self._sock.recvfrom(bufsize, flags)
        except (BlockingIOError, InterruptedError):
            ret = None

        if ret is not None:
            return ret

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._reader_add(fd, False)

        while True:
            yield event.waiter(None)
            try:
                ret = self._sock.recvfrom(bufsize, flags)
            except (BlockingIOError, InterruptedError):
                event = runtime._reader_add(fd, False)
                continue
            except BaseException as exc:
                raise exc
            else:
                break

        return ret

    def recvfrom_into(self, /, buffer, nbytes: int = 0, flags: int = 0) -> Coro[tuple[int, Any]]:
        try:
            ret = self._sock.recvfrom_into()
        except (BlockingIOError, InterruptedError):
            ret = None

        if ret is not None:
            return ret

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._reader_add(fd, False)

        while True:
            yield event.waiter(None)
            try:
                ret = self._sock.recvfrom_into(buffer, nbytes, flags)
            except (BlockingIOError, InterruptedError):
                event = runtime._reader_add(fd, False)
                continue
            except BaseException as exc:
                raise exc
            else:
                break

        return ret

    if sys.platform != 'win32':

        def recvmsg(
            self,
            bufsize: int,
            ancbufsize: int = 0,
            flags: int = 0,
            /,
        ) -> Coro[tuple[bytes, list[tuple[int, int, bytes]], int, object]]:
            try:
                ret = self._sock.recvmsg(bufsize, ancbufsize, flags)
            except (BlockingIOError, InterruptedError):
                ret = None

            if ret is not None:
                return ret

            runtime = get_runtime()
            fd = self.fileno()
            event = runtime._reader_add(fd, False)

            while True:
                yield event.waiter(None)
                try:
                    ret = self._sock.recvmsg(bufsize, ancbufsize, flags)
                except (BlockingIOError, InterruptedError):
                    event = runtime._reader_add(fd, False)
                    continue
                except BaseException as exc:
                    raise exc
                else:
                    break

            return ret

        def recvmsg_into(
            self,
            buffers,
            ancbufsize: int = 0,
            flags: int = 0,
            /,
        ) -> Coro[tuple[int, list[tuple[int, int, bytes]], int, object]]:
            try:
                ret = self._sock.recvmsg_into(buffers, ancbufsize, flags)
            except (BlockingIOError, InterruptedError):
                ret = None

            if ret is not None:
                return ret

            runtime = get_runtime()
            fd = self.fileno()
            event = runtime._reader_add(fd, False)

            while True:
                yield event.waiter(None)
                try:
                    ret = self._sock.recvmsg_into(buffers, ancbufsize, flags)
                except (BlockingIOError, InterruptedError):
                    event = runtime._reader_add(fd, False)
                    continue
                except BaseException as exc:
                    raise exc
                else:
                    break

            return ret

    def send(self, data: Any, flags: int = 0, /) -> Coro[int]:
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
            yield event.waiter(None)
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

    def sendto(self, data, address) -> Coro[int]:
        if not data:
            return

        address = yield self._resolve_address(address, local=False)
        try:
            n = self._sock.sendto(data, address)
        except (BlockingIOError, InterruptedError):
            n = 0

        if n == len(data):
            return n

        runtime = get_runtime()
        fd = self.fileno()
        event = runtime._writer_add(fd, True)
        sent = n

        while True:
            yield event.waiter(None)
            event.clear()

            try:
                n = self._sock.sendto(data[sent:], address)
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

    if sys.platform != 'win32':

        def sendmsg(
            self,
            buffers,
            ancdata: Any = (),
            flags: int = 0,
            address: Any = None,
        ) -> Coro[int]:
            if address is not None:
                address = yield self._resolve_address(address, local=False)

            try:
                n = self._sock.sendmsg(buffers, ancdata, flags, address)
            except (BlockingIOError, InterruptedError):
                n = -1

            if n >= 0:
                return n

            runtime = get_runtime()
            fd = self.fileno()
            event = runtime._writer_add(fd, False)

            while True:
                yield event.waiter(None)
                try:
                    ret = self._sock.sendmsg(buffers, ancdata, flags, address)
                except (BlockingIOError, InterruptedError):
                    event = runtime._writer_add(fd, False)
                    continue
                except BaseException as exc:
                    raise exc
                else:
                    break

            return ret

    # not impl:
    #   coro def sendfile
    # intentionally omitted:
    #   sendall
    #   makefile
    #   setblocking/getblocking
    #   settimeout/gettimeout
    #   timeout


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
) -> Coro[
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
    # print('GETADDRINFO')
    ret = yield spawn_blocking(
        _stdlib_socket.getaddrinfo,
        host,
        port,
        family,
        type,
        proto,
        flags,
    )
    return ret


def _resolve_address(
    type_: int,
    family: Any,
    proto: int,
    *,
    ipv6_v6only: bool | int,
    address: Any,
    local: bool,
) -> Coro[Any]:
    # print('RESADDR', address)
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
    gai_res = yield getaddrinfo(host, port, family, type_, proto, flags)
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
