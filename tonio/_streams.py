from abc import ABC, abstractmethod
from types import TracebackType
from typing import final


class _Stream(ABC):
    @final
    class NotReady: ...

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @abstractmethod
    def close(self): ...
