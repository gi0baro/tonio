import contextlib

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
            await event()

    async def __aexit__(self):
        self.release()


class Semaphore(_Semaphore):
    def __call__(self) -> Coro[contextlib.AbstractContextManager[None]]:
        if event := self.acquire():
            yield event.waiter(None)
        return _SemaphoreCtx(self)

    async def __aenter__(self):
        if event := self.acquire():
            await event()

    async def __aexit__(self):
        self.release()


class Barrier(_Barrier):
    def wait(self):
        count = self.ack()
        yield self.event.waiter(None)
        return count


class ChannelSender(_ChannelSender):
    def send(self, message) -> Coro[None]:
        if event := self._send_or_wait(message):
            yield event.waiter(None)
            self._send(message)


class ChannelReceiver(_ChannelReceiver):
    def receive(self) -> Coro[None]:
        msg, event = self._receive()
        while event:
            yield event.waiter(None)
            msg, event = self._receive()
        return msg


class UnboundedChannelReceiver(_UnboundedChannelReceiver):
    def receive(self) -> Coro[None]:
        msg, event = self._receive()
        while event:
            yield event.waiter(None)
            msg, event = self._receive()
        return msg


def channel(size) -> tuple[ChannelSender, ChannelReceiver]:
    inner = _Channel(size)
    return ChannelSender(inner), ChannelReceiver(inner)


def unbounded_channel() -> tuple[UnboundedChannelSender, UnboundedChannelReceiver]:
    inner = _UnboundedChannel()
    return UnboundedChannelSender(inner), UnboundedChannelReceiver(inner)
