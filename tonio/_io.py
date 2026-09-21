from __future__ import annotations

from ._tonio import ScheduledIO as ScheduledIO


def register(fd: int) -> ScheduledIO:
    return ScheduledIO(fd)
