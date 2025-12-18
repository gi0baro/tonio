from .._tonio import (
    Barrier as _Barrier,
    Channel as _Channel,
    ChannelReceiver as _ChannelReceiver,
    ChannelSender as _ChannelSender,
    UnboundedChannel as _UnboundedChannel,
    UnboundedChannelReceiver as _UnboundedChannelReceiver,
    UnboundedChannelSender as UnboundedChannelSender,
)


class Barrier(_Barrier):
    async def wait(self) -> int:
        count = self.ack()
        await self._event.waiter(None)
        return count


class ChannelSender(_ChannelSender):
    async def send(self, message) -> None:
        await self._send(message).waiter(None)


class ChannelReceiver(_ChannelReceiver):
    async def receive(self):
        while True:
            event, blocking, message = self._receive()
            if not blocking:
                return message
            await event.waiter(None)


class UnboundedChannelReceiver(_UnboundedChannelReceiver):
    async def receive(self):
        while True:
            event, blocking, message = self._receive()
            if not blocking:
                return message
            await event.waiter(None)


def channel(size) -> tuple[ChannelSender, ChannelReceiver]:
    inner = _Channel(size)
    return ChannelSender(inner), ChannelReceiver(inner)


def unbounded_channel() -> tuple[UnboundedChannelSender, UnboundedChannelReceiver]:
    inner = _UnboundedChannel()
    return UnboundedChannelSender(inner), UnboundedChannelReceiver(inner)
