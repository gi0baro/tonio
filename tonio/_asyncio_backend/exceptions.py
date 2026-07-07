from asyncio import CancelledError as CancelledError


class TimeoutError(BaseException):
    pass


class ResourceBroken(Exception):
    pass


class WouldBlock(Exception):
    pass


class RuntimeAlreadyInitializedError(RuntimeError):
    pass


class RuntimeNotInitializedError(RuntimeError):
    pass
