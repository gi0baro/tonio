import contextlib
from types import TracebackType
from typing import Any

from ._tonio import (
    Barrier as _Barrier,
    Channel as _Channel,
    ChannelReceiver as _ChannelReceiver,
    ChannelSender as _ChannelSender,
    Lock as _Lock,
    LockCtx as _LockCtx,
    Semaphore as _Semaphore,
    SemaphoreCtx as _SemaphoreCtx,
    UnboundedChannel as _UnboundedChannel,
    UnboundedChannelReceiver as _UnboundedChannelReceiver,
    UnboundedChannelSender as UnboundedChannelSender,
)
from ._types import Coro


class Lock(_Lock):
    def __call__(self) -> Coro[contextlib.AbstractContextManager[None]]:
        if event := self.acquire():
            yield event.waiter(None)
        return _LockCtx(self)

    async def __aenter__(self):
        if event := self.acquire():
            await event.waiter(None)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ):
        self.release()


class Semaphore(_Semaphore):
    def __call__(self) -> Coro[contextlib.AbstractContextManager[None]]:
        if event := self.acquire():
            yield event.waiter(None)
        return _SemaphoreCtx(self)

    async def __aenter__(self):
        if event := self.acquire():
            await event.waiter(None)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ):
        self.release()


class Barrier(_Barrier):
    def wait(self) -> Coro[int]:
        count = self.ack()
        yield self._event.waiter(None)
        return count


class ChannelSender(_ChannelSender):
    def send(self, message) -> Coro[None]:
        yield self._send(message).waiter(None)


class ChannelReceiver(_ChannelReceiver):
    def receive(self) -> Coro[Any]:
        while True:
            event, blocking, message = self._receive()
            if not blocking:
                return message
            yield event.waiter(None)


class UnboundedChannelReceiver(_UnboundedChannelReceiver):
    def receive(self) -> Coro[Any]:
        while True:
            event, blocking, message = self._receive()
            if not blocking:
                return message
            yield event.waiter(None)


def channel(size) -> tuple[ChannelSender, ChannelReceiver]:
    inner = _Channel(size)
    return ChannelSender(inner), ChannelReceiver(inner)


def unbounded_channel() -> tuple[UnboundedChannelSender, UnboundedChannelReceiver]:
    inner = _UnboundedChannel()
    return UnboundedChannelSender(inner), UnboundedChannelReceiver(inner)
