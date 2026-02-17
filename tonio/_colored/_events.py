from .._tonio import Event as _Event, Waiter as Waiter


class Event(_Event):
    def wait(self, timeout: int | float | None = None) -> Waiter:
        timeout = round(max(0, timeout * 1_000_000)) if timeout is not None else timeout
        return self.waiter(timeout)
