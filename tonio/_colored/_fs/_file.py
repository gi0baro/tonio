"""
Heavily inspired by `trio` code.

:source: (https://github.com/python-trio/trio)
:copyright: Contributors to the Trio project
:license: MIT
"""

from __future__ import annotations

import io
from collections.abc import Callable, Coroutine, Iterable
from functools import wraps
from typing import IO, TYPE_CHECKING, Any, AnyStr, BinaryIO, Literal, overload

from ..._fs._file import (
    _FILE_ASYNC_METHODS,
    _FILE_SYNC_ATTRS,
    FileT,
    FileT_co,
    T,
    _IOWrapper,
    _Opener,
    _OpenFile,
)
from .._ctl import spawn_blocking


if TYPE_CHECKING:
    from _typeshed import (
        OpenBinaryMode,
        OpenBinaryModeReading,
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextMode,
    )

    from ..._fs._file import (
        _CanClose,
        _CanDetach,
        _CanFlush,
        _CanPeek,
        _CanRead,
        _CanRead1,
        _CanReadAll,
        _CanReadInto,
        _CanReadInto1,
        _CanReadLine,
        _CanReadLines,
        _CanSeek,
        _CanTell,
        _CanTruncate,
        _CanWrite,
        _CanWriteLines,
    )


class IOWrapper(_IOWrapper[FileT_co]):
    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> object:
            if name in _FILE_SYNC_ATTRS:
                return getattr(self._wrapped, name)
            if name in _FILE_ASYNC_METHODS:
                meth = getattr(self._wrapped, name)

                @wraps(meth)
                def wrapper(*args: Callable[..., T], **kwargs: Any) -> Coroutine[T]:
                    return spawn_blocking(meth, *args, **kwargs)

                setattr(self, name, wrapper)
                return wrapper

            raise AttributeError(name)

    async def __aenter__(self) -> IOWrapper[FileT_co]:
        return self

    async def __aexit__(self: IOWrapper[_CanClose], *exc_info: object) -> None:
        await self.close()

    def __aiter__(self) -> IOWrapper[FileT_co]:
        return self

    async def __anext__(self: IOWrapper[_CanReadLine[AnyStr]]) -> AnyStr:
        line = await self.readline()
        if line:
            return line
        raise StopAsyncIteration

    async def detach(self: IOWrapper[_CanDetach[T]]) -> IOWrapper[T]:
        raw = await spawn_blocking(self._wrapped.detach)
        return wrap_file(raw)

    if TYPE_CHECKING:

        async def close(self: IOWrapper[_CanClose]) -> None: ...
        async def flush(self: IOWrapper[_CanFlush]) -> None: ...
        async def read(self: IOWrapper[_CanRead[AnyStr]], size: int | None = -1, /) -> AnyStr: ...
        async def read1(self: IOWrapper[_CanRead1], size: int | None = -1, /) -> bytes: ...
        async def readall(self: IOWrapper[_CanReadAll[AnyStr]]) -> AnyStr: ...
        async def readinto(self: IOWrapper[_CanReadInto], buf: Any, /) -> int | None: ...
        async def readline(self: IOWrapper[_CanReadLine[AnyStr]], size: int = -1, /) -> AnyStr: ...
        async def readlines(self: IOWrapper[_CanReadLines[AnyStr]]) -> list[AnyStr]: ...
        async def seek(self: IOWrapper[_CanSeek], target: int, whence: int = 0, /) -> int: ...
        async def tell(self: IOWrapper[_CanTell]) -> int: ...
        async def truncate(self: IOWrapper[_CanTruncate], size: int | None = None, /) -> int: ...
        async def write(self: IOWrapper[_CanWrite[T]], data: T, /) -> int: ...
        async def writelines(self: IOWrapper[_CanWriteLines[T]], lines: Iterable[T], /) -> None: ...
        async def readinto1(self: IOWrapper[_CanReadInto1], buffer: Any, /) -> int: ...
        async def peek(self: IOWrapper[_CanPeek[AnyStr]], size: int = 0, /) -> AnyStr: ...


@overload
async def open_file(
    file: _OpenFile,
    mode: OpenTextMode = 'r',
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[io.TextIOWrapper]: ...


@overload
async def open_file(
    file: _OpenFile,
    mode: OpenBinaryMode,
    buffering: Literal[0],
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[io.FileIO]: ...


@overload
async def open_file(
    file: _OpenFile,
    mode: OpenBinaryModeUpdating,
    buffering: Literal[-1, 1] = -1,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[io.BufferedRandom]: ...


@overload
async def open_file(
    file: _OpenFile,
    mode: OpenBinaryModeWriting,
    buffering: Literal[-1, 1] = -1,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[io.BufferedWriter]: ...


@overload
async def open_file(
    file: _OpenFile,
    mode: OpenBinaryModeReading,
    buffering: Literal[-1, 1] = -1,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[io.BufferedReader]: ...


@overload
async def open_file(
    file: _OpenFile,
    mode: OpenBinaryMode,
    buffering: int,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[BinaryIO]: ...


@overload
async def open_file(  # type: ignore[explicit-any]
    file: _OpenFile,
    mode: str,
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[IO[Any]]: ...


async def open_file(
    file: _OpenFile,
    mode: str = 'r',
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> IOWrapper[object]:
    file_ = await spawn_blocking(
        io.open,
        file,
        mode,
        buffering,
        encoding,
        errors,
        newline,
        closefd,
        opener,
    )
    return wrap_file(file_)


def wrap_file(file: FileT) -> IOWrapper[FileT]:
    def has(attr: str) -> bool:
        return hasattr(file, attr) and callable(getattr(file, attr))

    if not (has('close') and (has('read') or has('write'))):
        raise TypeError(
            f'{file} does not implement required duck-file methods: close and (read or write)',
        )

    return IOWrapper(file)
