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
        await self.event.waiter(None)
        return count


class ChannelSender(_ChannelSender):
    async def send(self, message) -> None:
        if event := self._send_or_wait(message):
            await event.waiter(None)
            self._send(message)


class ChannelReceiver(_ChannelReceiver):
    async def receive(self):
        msg, event = self._receive()
        while event:
            await event.waiter(None)
            msg, event = self._receive()
        return msg


class UnboundedChannelReceiver(_UnboundedChannelReceiver):
    async def receive(self):
        msg, event = self._receive()
        while event:
            await event.waiter(None)
            msg, event = self._receive()
        return msg


def channel(size) -> tuple[ChannelSender, ChannelReceiver]:
    inner = _Channel(size)
    return ChannelSender(inner), ChannelReceiver(inner)


def unbounded_channel() -> tuple[UnboundedChannelSender, UnboundedChannelReceiver]:
    inner = _UnboundedChannel()
    return UnboundedChannelSender(inner), UnboundedChannelReceiver(inner)
