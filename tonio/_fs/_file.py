"""
Heavily inspired by `trio` code.

:source: (https://github.com/python-trio/trio)
:copyright: Contributors to the Trio project
:license: MIT
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    AnyStr,
    BinaryIO,
    Generic,
    Literal,
    TypeVar,
    Union,
    overload,
)

from .._ctl import spawn_blocking
from .._types import Coro


if TYPE_CHECKING:
    from _typeshed import (
        OpenBinaryMode,
        OpenBinaryModeReading,
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextMode,
        StrOrBytesPath,
    )


_FILE_ASYNC_METHODS: set[str] = {
    'close',
    'flush',
    'read',
    'read1',
    'readall',
    'readinto',
    'readline',
    'readlines',
    'seek',
    'tell',
    'truncate',
    'write',
    'writelines',
    # not defined in *IOBase:
    'readinto1',
    'peek',
}


FileT = TypeVar('FileT')
FileT_co = TypeVar('FileT_co', covariant=True)
T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)
T_contra = TypeVar('T_contra', contravariant=True)
AnyStr_co = TypeVar('AnyStr_co', str, bytes, covariant=True)
AnyStr_contra = TypeVar('AnyStr_contra', str, bytes, contravariant=True)


if TYPE_CHECKING:
    from typing import Protocol

    class _HasClosed(Protocol):
        @property
        def closed(self) -> bool: ...

    class _HasEncoding(Protocol):
        @property
        def encoding(self) -> str: ...

    class _HasErrors(Protocol):
        @property
        def errors(self) -> str | None: ...

    class _HasFileNo(Protocol):
        def fileno(self) -> int: ...

    class _HasIsATTY(Protocol):
        def isatty(self) -> bool: ...

    class _HasNewlines(Protocol[T_co]):
        @property
        def newlines(self) -> T_co: ...

    class _HasReadable(Protocol):
        def readable(self) -> bool: ...

    class _HasSeekable(Protocol):
        def seekable(self) -> bool: ...

    class _HasWritable(Protocol):
        def writable(self) -> bool: ...

    class _HasBuffer(Protocol):
        @property
        def buffer(self) -> BinaryIO: ...

    class _HasRaw(Protocol):
        @property
        def raw(self) -> io.RawIOBase: ...

    class _HasLineBuffering(Protocol):
        @property
        def line_buffering(self) -> bool: ...

    class _HasCloseFD(Protocol):
        @property
        def closefd(self) -> bool: ...

    class _HasName(Protocol):
        @property
        def name(self) -> str: ...

    class _HasMode(Protocol):
        @property
        def mode(self) -> str: ...

    class _CanGetValue(Protocol[AnyStr_co]):
        def getvalue(self) -> AnyStr_co: ...

    class _CanGetBuffer(Protocol):
        def getbuffer(self) -> memoryview: ...

    class _CanFlush(Protocol):
        def flush(self) -> None: ...

    class _CanRead(Protocol[AnyStr_co]):
        def read(self, size: int | None = ..., /) -> AnyStr_co: ...

    class _CanRead1(Protocol):
        def read1(self, size: int | None = ..., /) -> bytes: ...

    class _CanReadAll(Protocol[AnyStr_co]):
        def readall(self) -> AnyStr_co: ...

    class _CanReadInto(Protocol):
        def readinto(self, buf: Any, /) -> int | None: ...

    class _CanReadInto1(Protocol):
        def readinto1(self, buffer: Any, /) -> int: ...

    class _CanReadLine(Protocol[AnyStr_co]):
        def readline(self, size: int = ..., /) -> AnyStr_co: ...

    class _CanReadLines(Protocol[AnyStr]):
        def readlines(self, hint: int = ..., /) -> list[AnyStr]: ...

    class _CanSeek(Protocol):
        def seek(self, target: int, whence: int = 0, /) -> int: ...

    class _CanTell(Protocol):
        def tell(self) -> int: ...

    class _CanTruncate(Protocol):
        def truncate(self, size: int | None = ..., /) -> int: ...

    class _CanWrite(Protocol[T_contra]):
        def write(self, data: T_contra, /) -> int: ...

    class _CanWriteLines(Protocol[T_contra]):
        def writelines(self, lines: Iterable[T_contra], /) -> None: ...

    class _CanPeek(Protocol[AnyStr_co]):
        def peek(self, size: int = 0, /) -> AnyStr_co: ...

    class _CanDetach(Protocol[T_co]):
        def detach(self) -> T_co: ...

    class _CanClose(Protocol):
        def close(self) -> None: ...


class _IOWrapper(Generic[FileT_co]):
    def __init__(self, file: FileT_co) -> None:
        self._wrapped = file

    @property
    def wrapped(self) -> FileT_co:
        return self._wrapped

    @property
    def closed(self: _IOWrapper[_HasClosed]) -> bool:
        return self._wrapped.closed

    @property
    def encoding(self: _IOWrapper[_HasEncoding]) -> str:
        return self._wrapped.encoding

    @property
    def errors(self: _IOWrapper[_HasErrors]) -> str | None:
        return self._wrapped.errors

    @property
    def newlines(self: _IOWrapper[_HasNewlines[T]]) -> T:
        return self._wrapped.newlines

    @property
    def buffer(self: _IOWrapper[_HasBuffer]) -> BinaryIO:
        return self._wrapped.buffer

    @property
    def raw(self: _IOWrapper[_HasRaw]) -> io.RawIOBase:
        return self._wrapped.raw

    @property
    def line_buffering(self: _IOWrapper[_HasLineBuffering]) -> bool:
        return self._wrapped.line_buffering

    @property
    def closefd(self: _IOWrapper[_HasCloseFD]) -> bool:
        return self._wrapped.closefd

    @property
    def name(self: _IOWrapper[_HasName]) -> str:
        return self._wrapped.name

    @property
    def mode(self: _IOWrapper[_HasMode]) -> str:
        return self._wrapped.mode

    def fileno(self: _IOWrapper[_HasFileNo]) -> int:
        return self._wrapped.fileno()

    def isatty(self: _IOWrapper[_HasIsATTY]) -> bool:
        return self._wrapped.isatty()

    def readable(self: _IOWrapper[_HasReadable]) -> bool:
        return self._wrapped.readable()

    def seekable(self: _IOWrapper[_HasSeekable]) -> bool:
        return self._wrapped.seekable()

    def writable(self: _IOWrapper[_HasWritable]) -> bool:
        return self._wrapped.writable()

    def getvalue(self: _IOWrapper[_CanGetValue[AnyStr]]) -> AnyStr:
        return self._wrapped.getvalue()

    def getbuffer(self: _IOWrapper[_CanGetBuffer]) -> memoryview:
        return self._wrapped.getbuffer()


class IOWrapper(_IOWrapper[FileT_co]):
    def __enter__(self) -> IOWrapper[FileT_co]:
        return self

    def __exit__(self: IOWrapper[_CanClose], *exc_info: object) -> None:
        return

    def detach(self: IOWrapper[_CanDetach[T]]) -> Coro[IOWrapper[T]]:
        raw = yield spawn_blocking(self._wrapped.detach)
        return wrap_file(raw)

    if TYPE_CHECKING:

        def close(self: IOWrapper[_CanClose]) -> Coro[None]: ...
        def flush(self: IOWrapper[_CanFlush]) -> Coro[None]: ...
        def read(self: IOWrapper[_CanRead[AnyStr]], size: int | None = -1, /) -> Coro[AnyStr]: ...
        def read1(self: IOWrapper[_CanRead1], size: int | None = -1, /) -> Coro[bytes]: ...
        def readall(self: IOWrapper[_CanReadAll[AnyStr]]) -> Coro[AnyStr]: ...
        def readinto(self: IOWrapper[_CanReadInto], buf: Any, /) -> Coro[int | None]: ...
        def readline(self: IOWrapper[_CanReadLine[AnyStr]], size: int = -1, /) -> Coro[AnyStr]: ...
        def readlines(self: IOWrapper[_CanReadLines[AnyStr]]) -> Coro[list[AnyStr]]: ...
        def seek(self: IOWrapper[_CanSeek], target: int, whence: int = 0, /) -> Coro[int]: ...
        def tell(self: IOWrapper[_CanTell]) -> Coro[int]: ...
        def truncate(self: IOWrapper[_CanTruncate], size: int | None = None, /) -> Coro[int]: ...
        def write(self: IOWrapper[_CanWrite[T]], data: T, /) -> Coro[int]: ...
        def writelines(self: IOWrapper[_CanWriteLines[T]], lines: Iterable[T], /) -> Coro[None]: ...
        def readinto1(self: IOWrapper[_CanReadInto1], buffer: Any, /) -> Coro[int]: ...
        def peek(self: IOWrapper[_CanPeek[AnyStr]], size: int = 0, /) -> Coro[AnyStr]: ...


if not TYPE_CHECKING:

    def _async_file_impl(name):
        def wrapper(self, /, *args: Callable[..., T], **kwargs: Any) -> Coro[T]:
            return spawn_blocking(getattr(self._wrapped, name), *args, **kwargs)

        wrapper.__name__ = wrapper.__qualname__ = name
        return wrapper

    for _name in _FILE_ASYNC_METHODS:
        setattr(IOWrapper, _name, _async_file_impl(_name))
    del _name
    del _async_file_impl


_OpenFile = Union['StrOrBytesPath', int]
_Opener = Callable[[str, int], int]


@overload
def open_file(
    file: _OpenFile,
    mode: OpenTextMode = 'r',
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[io.TextIOWrapper]]: ...


@overload
def open_file(
    file: _OpenFile,
    mode: OpenBinaryMode,
    buffering: Literal[0],
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[io.FileIO]]: ...


@overload
def open_file(
    file: _OpenFile,
    mode: OpenBinaryModeUpdating,
    buffering: Literal[-1, 1] = -1,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[io.BufferedRandom]]: ...


@overload
def open_file(
    file: _OpenFile,
    mode: OpenBinaryModeWriting,
    buffering: Literal[-1, 1] = -1,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[io.BufferedWriter]]: ...


@overload
def open_file(
    file: _OpenFile,
    mode: OpenBinaryModeReading,
    buffering: Literal[-1, 1] = -1,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[io.BufferedReader]]: ...


@overload
def open_file(
    file: _OpenFile,
    mode: OpenBinaryMode,
    buffering: int,
    encoding: None = None,
    errors: None = None,
    newline: None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[BinaryIO]]: ...


@overload
def open_file(  # type: ignore[explicit-any]
    file: _OpenFile,
    mode: str,
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[IO[Any]]]: ...


def open_file(
    file: _OpenFile,
    mode: str = 'r',
    buffering: int = -1,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
    closefd: bool = True,
    opener: _Opener | None = None,
) -> Coro[IOWrapper[object]]:
    file_ = yield spawn_blocking(
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
