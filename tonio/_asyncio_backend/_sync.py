from __future__ import annotations

from collections import deque
from typing import Any

from ._events import Event
from .exceptions import WouldBlock


class _Semaphore:
    __slots__ = ['_value', '_waiters']

    def __init__(self, value: int):
        self._value = value
        self._waiters: deque[Event] = deque()

    def acquire(self) -> Event | None:
        if self._value > 0:
            self._value -= 1
            return None
        ev = Event()
        self._waiters.append(ev)
        return ev

    def try_acquire(self):
        if self._value <= 0:
            raise WouldBlock()
        self._value -= 1

    def release(self):
        if self._waiters:
            self._waiters.popleft().set()
        else:
            self._value += 1

    def tokens(self) -> int:
        return self._value

    def or_raise(self) -> SemaphoreCtx:
        self.try_acquire()
        return SemaphoreCtx(self)


class SemaphoreCtx:
    __slots__ = ['_semaphore']

    def __init__(self, semaphore: '_Semaphore'):
        self._semaphore = semaphore

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._semaphore.release()


class LockCtx(SemaphoreCtx):
    """Lock context manager."""
    __slots__ = []

    def __init__(self, lock: _Lock):
        super().__init__(lock)


class _Lock(_Semaphore):
    """A 1-position semaphore, i.e. a lock.

    Inherits all behaviour from _Semaphore with an initial value of 1.
    """

    __slots__ = []

    def __init__(self):
        super().__init__(1)

    @property
    def locked(self) -> bool:
        return self._value == 0

    def tokens(self) -> int:
        raise AttributeError("'_Lock' object has no attribute 'tokens'")

    def or_raise(self) -> LockCtx:
        self.try_acquire()
        return LockCtx(self)


class _Barrier:
    __slots__ = ['_count', '_event']

    def __init__(self, value: int):
        self._count = value
        self._event = Event()

    def ack(self) -> int:
        self._count -= 1
        if self._count <= 0:
            self._event.set()
        return self._count

    def value(self) -> int:
        return self._count


class Channel:
    __slots__ = ['_size', '_queue', '_send_waiters', '_recv_event', '_closed']

    def __init__(self, size: int):
        self._size = size
        self._queue: deque[Any] = deque()
        self._send_waiters: deque[tuple[Any, Event]] = deque()
        self._recv_event = Event()
        self._closed = False


class ChannelSender:
    __slots__ = ['_channel']

    def __init__(self, channel: Channel):
        self._channel = channel

    def _send(self, message: Any) -> Event:
        channel = self._channel
        event = Event()
        if len(channel._queue) < channel._size:
            channel._queue.append(message)
            event.set()
            channel._recv_event.set()  # level-triggered: stays set until queue drains
        else:
            channel._send_waiters.append((message, event))
        return event

    def close(self):
        self._channel._closed = True
        self._channel._recv_event.set()  # wake all receivers permanently


class ChannelReceiver:
    __slots__ = ['_channel']

    def __init__(self, channel: Channel):
        self._channel = channel

    def _receive(self) -> tuple:
        channel = self._channel
        if channel._queue:
            message = channel._queue.popleft()
            if channel._send_waiters:
                pending_msg, pending_ev = channel._send_waiters.popleft()
                channel._queue.append(pending_msg)
                pending_ev.set()
            elif not channel._queue:
                if not channel._closed:
                    channel._recv_event.clear()
            return channel._recv_event, False, message  # False = not blocking = return message
        if channel._closed:
            raise WouldBlock()
        channel._recv_event.clear()  # prevent spin on spurious deferred-set wakeups
        return channel._recv_event, True, None  # True = blocking = wait on event


class UnboundedChannel:
    __slots__ = ['_queue', '_recv_event', '_closed']

    def __init__(self):
        self._queue: deque[Any] = deque()
        self._recv_event = Event()
        self._closed = False


class UnboundedChannelSender:
    __slots__ = ['_channel']

    def __init__(self, channel: UnboundedChannel):
        self._channel = channel

    def send(self, message: Any):
        self._channel._queue.append(message)
        self._channel._recv_event.set()

    def close(self):
        self._channel._closed = True
        self._channel._recv_event.set()


class UnboundedChannelReceiver:
    __slots__ = ['_channel']

    def __init__(self, channel: UnboundedChannel):
        self._channel = channel

    def _receive(self) -> tuple:
        channel = self._channel
        if channel._queue:
            message = channel._queue.popleft()
            if not channel._queue:
                if not channel._closed:
                    channel._recv_event.clear()
            return channel._recv_event, False, message  # False = not blocking = return message
        if channel._closed:
            raise WouldBlock()
        channel._recv_event.clear()
        return channel._recv_event, True, None  # True = blocking = wait on event
