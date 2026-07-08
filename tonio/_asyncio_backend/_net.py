"""Networking primitives for the asyncio backend.

Mimics the native (Rust) `Socket` and `TLSStream` wrappers.
As most of the non-blocking IO and SSL logic stays on `tonio/_net`,
the classes here only wrap a stdlib socket for tracking write-EOF
and TLS handshake states.

As asyncio event loop is single-thread, plain attributes are fine
regardless of their atomicity.
"""

from __future__ import annotations

import socket as _stdlib_socket


# TLS handshake states copied from Rust' TLSStreamState enum.
_TLS_INIT = 0
_TLS_HANDSHAKE = 1
_TLS_READY = 2
_TLS_BROKEN = 3
_TLS_CLOSED = 4


class Socket:
    """Wraps a non-blocking stdlib socket and tracks the write-EOF flag

    The wrapped socket is expected to be already set to non-blocking via `from_stdlib_socket`.
    The `_net._socket._Socket` mixin supplies `fileno()`, `recv` and friends,
    delegating to `self._sock`.
    """

    def __init__(self, stdlib_socket: _stdlib_socket.socket):
        self._sock = stdlib_socket
        self._eof = False

    def _eof_get(self) -> bool:
        return self._eof

    def _eof_set(self) -> None:
        self._eof = True


class TLSStream:
    """TLS handshake & lifecycle state machine

    Only guards the lifecycle transitions `_net._tls.TLSStream` it relies on.
    Transitions assign the instance state attribute.
    """

    _state: int = _TLS_INIT

    def _handshake_pre(self) -> None:
        if self._state != _TLS_INIT:
            raise RuntimeError('Invalid TLSStream state change')
        self._state = _TLS_HANDSHAKE

    def _handshake_post(self) -> None:
        if self._state != _TLS_HANDSHAKE:
            raise RuntimeError('Invalid TLSStream state change')
        self._state = _TLS_READY

    def _set_broken(self) -> None:
        self._state = _TLS_BROKEN

    def _set_closed(self) -> None:
        self._state = _TLS_CLOSED

    def _check_ready(self) -> None:
        if self._state != _TLS_READY:
            raise RuntimeError('TLSStream is not ready')
