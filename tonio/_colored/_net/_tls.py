"""
Heavily inspired by `trio` code.

:source: (https://github.com/python-trio/trio)
:copyright: Contributors to the Trio project
:license: MIT
"""

import contextlib
import ssl as _stdlib_ssl
from typing import Any

from ..._net._tls import _is_eof
from ..._tonio import ResourceBroken, TLSStream as _TLSStream
from .._sync import Lock
from ._streams import _Stream


class TLSStream(_Stream, _TLSStream):
    __slots__ = [
        'transport',
        '_ssl',
        '_egress',
        '_ingress',
        '_lock_recv',
        '_lock_send',
        '_egress_stack',
        '_recv_count',
        '_recv_est_size',
        '_compat_https',
    ]

    def __init__(
        self,
        transport: _Stream,
        ssl_context: _stdlib_ssl.SSLContext,
        *,
        server_hostname: str | bytes | None = None,
        server_side: bool = False,
        https_compatible: bool = False,
    ):
        self.transport = transport
        self._compat_https = https_compatible
        self._egress = _stdlib_ssl.MemoryBIO()
        self._ingress = _stdlib_ssl.MemoryBIO()
        self._lock_recv = Lock()
        self._lock_send = Lock()
        self._egress_stack = bytearray()
        self._recv_count = 0
        self._recv_est_size = 16384
        self._ssl = ssl_context.wrap_bio(
            self._ingress,
            self._egress,
            server_side=server_side,
            server_hostname=server_hostname,
        )

    async def _recv(self) -> None:
        recv_count = self._recv_count
        async with self._lock_recv:
            if recv_count == self._recv_count:
                data = await self.transport.receive_some()
                if not data:
                    self._ingress.write_eof()
                else:
                    self._recv_est_size = max(
                        self._recv_est_size,
                        len(data),
                    )
                    self._ingress.write(data)
                self._recv_count += 1

    async def _send(self, data) -> None:
        async with self._lock_send:
            try:
                self._egress_stack.extend(data)
                data = bytes(self._egress_stack)
                self._egress_stack.clear()
                await self.transport.send_all(data)
            except:
                self._set_broken()
                raise

    async def _ssl_dance(self, ssl_fn, *args) -> Any:
        done = False
        while not done:
            want_read = False
            try:
                ret = ssl_fn(*args)
            except _stdlib_ssl.SSLWantReadError:
                want_read = True
            except (_stdlib_ssl.SSLError, _stdlib_ssl.CertificateError) as exc:
                self._set_broken()
                raise ResourceBroken from exc
            else:
                done = True

            if to_send := self._egress.read():
                await self._send(to_send)
            elif want_read:
                await self._recv()

        return ret

    async def handshake(self) -> None:
        self._handshake_pre()

        done = False
        while not done:
            want_read = False
            try:
                self._ssl.do_handshake()
            except _stdlib_ssl.SSLWantReadError:
                want_read = True
            except (_stdlib_ssl.SSLError, _stdlib_ssl.CertificateError) as exc:
                self._set_broken()
                raise ResourceBroken from exc
            else:
                done = True

            to_send = self._egress.read()
            if not want_read and self._ssl.server_side and self._ssl.version() == 'TLSv1.3':
                self._egress_stack.extend(to_send)
                to_send = b''

            if to_send:
                await self._send(to_send)
            elif want_read:
                await self._recv()

        self._handshake_post()

    async def send_all(self, data: bytes | bytearray | memoryview) -> None:
        self._check_ready()
        if not data:
            return
        await self._ssl_dance(self._ssl.write, data)

    async def receive_some(self, max_bytes: int | None = None) -> bytes | bytearray:
        self._check_ready()
        if max_bytes is None:
            max_bytes = max(self._recv_est_size, self._ingress.pending)
        try:
            ret = await self._ssl_dance(self._ssl.read, max_bytes)
            return ret
        except ResourceBroken as exc:
            if self._compat_https and _is_eof(exc.__cause__):
                return b''
            raise

    async def close(self) -> None:
        if self._state == 4:
            return

        self._set_closed()
        if self._state == 3 or self._compat_https:
            self.transport.close()
            return

        try:
            with contextlib.suppress(ResourceBroken):
                done = False
                while not done:
                    try:
                        self._ssl.unwrap()
                    except _stdlib_ssl.SSLWantReadError:
                        done = True
                    except (_stdlib_ssl.SSLError, _stdlib_ssl.CertificateError) as exc:
                        self._set_broken()
                        raise ResourceBroken from exc
                    else:
                        done = True

                    if to_send := self._egress.read():
                        await self._send(to_send)
        finally:
            self.transport.close()

    def __exit__(self, *args, **kwargs) -> None:
        if self._state == 4:
            return

        if self._state == 3 or self._compat_https:
            self._set_closed()
            self.transport.close()
            return

        raise RuntimeError('TLSStream needs to be manually closed')


class TLSListener(_Stream):
    __slots__ = [
        'transport',
        '_ssl',
        '_compat_https',
    ]

    def __init__(
        self,
        transport,
        ssl_context: _stdlib_ssl.SSLContext,
        *,
        https_compatible: bool = False,
    ) -> None:
        self.transport = transport
        self._ssl = ssl_context
        self._compat_https = https_compatible

    async def accept(self) -> TLSStream:
        stream = await self.transport.accept()
        ret = TLSStream(
            stream,
            self._ssl,
            server_side=True,
            https_compatible=self._compat_https,
        )
        await ret.handshake()
        return ret

    def close(self) -> None:
        self.transport.close()
