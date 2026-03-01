from ._ctl import spawn
from ._signals import _signal_receiver, _SignalReceiver
from ._types import Coro
from .sync.channel import unbounded


class SignalReceiver(_SignalReceiver):
    def _init_channel(self):
        return unbounded()

    def _register_coros(self, runtime):
        coros = []

        def coro(sig, event):
            while True:
                yield event.waiter(None)
                event.clear()
                self._chw.send(sig)

        for sig in self._sigs:
            coros.append(coro(sig, runtime._sig_add(sig)))

        self._inner = spawn(*coros)

    def __next__(self) -> Coro[int]:
        sig = yield self._chr.receive()
        return sig


def signal_receiver(*signals: int) -> SignalReceiver:
    return _signal_receiver(SignalReceiver, *signals)
