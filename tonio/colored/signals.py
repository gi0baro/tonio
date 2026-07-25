import contextlib

from .._colored._ctl import spawn
from .._signals import _signal_receiver, _SignalReceiver
from .._tonio import CancelledError, Waiter
from .sync.channel import unbounded


class SignalReceiver(_SignalReceiver):
    def _init_channel(self):
        return unbounded()

    def _register_coros(self, runtime):
        coros = []

        async def receiver(sig, event):
            while True:
                await event.waiter(None)
                event.clear()
                self._chw.send(sig)

        async def glue(sig, event, checkpoint):
            await checkpoint
            await receiver(sig, event)

        async def coro(sig, event, checkpoint):
            with contextlib.suppress(CancelledError):
                await glue(sig, event, checkpoint)

        for sig in self._sigs:
            checkpoint = Waiter.checkpoint()
            self._checkpoints.append(checkpoint)
            coros.append(coro(sig, runtime._sig_add(sig), checkpoint))

        spawn.without_tracking(*coros)

    def _cancel_coros(self):
        for checkpoint in self._checkpoints:
            checkpoint.abort()

    async def __anext__(self) -> int:
        sig = await self._chr.receive()
        return sig


def signal_receiver(*signals: int) -> SignalReceiver:
    return _signal_receiver(SignalReceiver, *signals)
