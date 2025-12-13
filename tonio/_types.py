from collections.abc import Generator
from typing import Any, TypeAlias, TypeVar


_Ret = TypeVar('_Ret')
Coro: TypeAlias = Generator[Any, Any, _Ret]
