from .._colored._ctl import spawn
from .._signals import _signal_receiver, _SignalReceiver
from .sync.channel import unbounded


class SignalReceiver(_SignalReceiver):
    def _init_channel(self):
        return unbounded()

    def _register_coros(self, runtime):
        coros = []

        async def coro(sig, event):
            while True:
                await event.waiter(None)
                event.clear()
                self._chw.send(sig)

        for sig in self._sigs:
            coros.append(coro(sig, runtime._sig_add(sig)))

        self._inner = spawn(*coros)

    async def __anext__(self) -> int:
        sig = await self._chr.receive()
        return sig


def signal_receiver(*signals: int) -> SignalReceiver:
    return _signal_receiver(SignalReceiver, *signals)
