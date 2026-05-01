from typing import Awaitable

from ._events import Event


def yield_now() -> Awaitable[None]:
    event = Event()
    event.set()
    return event.waiter(None)
