import contextlib

from ._ctl import spawn
from ._signals import _signal_receiver, _SignalReceiver
from ._tonio import CancelledError, Waiter
from ._types import Coro
from .sync.channel import unbounded


class SignalReceiver(_SignalReceiver):
    def _init_channel(self):
        return unbounded()

    def _register_coros(self, runtime):
        coros = []

        def receiver(sig, event):
            while True:
                yield event.waiter(None)
                event.clear()
                self._chw.send(sig)

        def glue(sig, event, checkpoint):
            yield checkpoint
            yield receiver(sig, event)

        def coro(sig, event, checkpoint):
            with contextlib.suppress(CancelledError):
                yield glue(sig, event, checkpoint)

        for sig in self._sigs:
            checkpoint = Waiter.checkpoint()
            self._checkpoints.append(checkpoint)
            coros.append(coro(sig, runtime._sig_add(sig), checkpoint))

        spawn.without_tracking(*coros)

    def _cancel_coros(self):
        for checkpoint in self._checkpoints:
            checkpoint.unwind()

    def __next__(self) -> Coro[int]:
        sig = yield self._chr.receive()
        return sig


def signal_receiver(*signals: int) -> SignalReceiver:
    return _signal_receiver(SignalReceiver, *signals)
