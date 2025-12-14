from ._tonio import Event as _Event, Waiter as Waiter


class Event(_Event):
    def wait(self, timeout: int | float | None = None):
        timeout = round(max(0, timeout * 1_000_000)) if timeout else timeout
        yield self.waiter(timeout)

    def __call__(self, timeout: int | float | None = None):
        timeout = round(max(0, timeout * 1_000_000)) if timeout else timeout
        return self.waiter(timeout)
