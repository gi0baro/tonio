"""
Heavily inspired by `trio` code.

:source: (https://github.com/python-trio/trio)
:copyright: Contributors to the Trio project
:license: MIT
"""

from __future__ import annotations

import os
import pathlib
from functools import update_wrapper, wraps
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    BinaryIO,
    ClassVar,
    Concatenate,
    Literal,
    TypeVar,
    overload,
)

from .._ctl import spawn_blocking
from .._types import Coro
from ._file import IOWrapper, wrap_file


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from io import BufferedRandom, BufferedReader, BufferedWriter, FileIO, TextIOWrapper
    from typing import ParamSpec, Self, TypeAlias

    from _typeshed import (
        OpenBinaryMode,
        OpenBinaryModeReading,
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextMode,
    )

    P = ParamSpec('P')

    PathT = TypeVar('PathT', bound='Path')
    T = TypeVar('T')

    _PathArg: TypeAlias = str | os.PathLike[str]


def _unwrap(path: _PathArg) -> _PathArg:
    if isinstance(path, pathlib.PurePath) and not isinstance(path, pathlib.Path):
        return pathlib.Path(path)
    return path


def _wraps_async(  # type: ignore[explicit-any]
    wrapped: Callable[..., object],
) -> Callable[[Callable[P, T]], Callable[P, Coro[T]]]:
    def decorator(fn: Callable[P, T]) -> Callable[P, Coro[T]]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Coro[T]:
            return spawn_blocking(fn, *args, **kwargs)

        update_wrapper(wrapper, wrapped)
        return wrapper

    return decorator


def _wrap_method(
    fn: Callable[Concatenate[pathlib.Path, P], T],
) -> Callable[Concatenate[Path, P], Coro[T]]:
    @_wraps_async(fn)
    def wrapper(self: Path, /, *args: P.args, **kwargs: P.kwargs) -> T:
        return fn(self._wrapped_cls(self), *args, **kwargs)

    return wrapper


def _wrap_method_path(
    fn: Callable[Concatenate[pathlib.Path, P], pathlib.Path],
) -> Callable[Concatenate[PathT, P], Coro[PathT]]:
    @_wraps_async(fn)
    def wrapper(self: PathT, /, *args: P.args, **kwargs: P.kwargs) -> PathT:
        return self.__class__(fn(self._wrapped_cls(self), *args, **kwargs))

    return wrapper


def _wrap_method_path_iterable(
    fn: Callable[Concatenate[pathlib.Path, P], Iterable[pathlib.Path]],
) -> Callable[Concatenate[PathT, P], Coro[list[PathT]]]:
    @_wraps_async(fn)
    def wrapper(self: PathT, /, *args: P.args, **kwargs: P.kwargs) -> list[PathT]:
        return [self.__class__(path) for path in fn(self._wrapped_cls(self), *args, **kwargs)]

    return wrapper


class Path(pathlib.PurePath):
    __slots__ = ()

    _wrapped_cls: ClassVar[type[pathlib.Path]]

    def __new__(cls, *args: str | os.PathLike[str]) -> Self:
        if cls is Path:
            cls = PosixPath  # type: ignore[assignment]
        return super().__new__(cls, *args)

    @classmethod
    @_wraps_async(pathlib.Path.cwd)
    def cwd(cls) -> Self:
        return cls(pathlib.Path.cwd())

    @classmethod
    @_wraps_async(pathlib.Path.home)
    def home(cls) -> Self:
        return cls(pathlib.Path.home())

    @overload
    def open(
        self,
        mode: OpenTextMode = 'r',
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Coro[IOWrapper[TextIOWrapper]]: ...

    @overload
    def open(
        self,
        mode: OpenBinaryMode,
        buffering: Literal[0],
        encoding: None = None,
        errors: None = None,
        newline: None = None,
    ) -> Coro[IOWrapper[FileIO]]: ...

    @overload
    def open(
        self,
        mode: OpenBinaryModeUpdating,
        buffering: Literal[-1, 1] = -1,
        encoding: None = None,
        errors: None = None,
        newline: None = None,
    ) -> Coro[IOWrapper[BufferedRandom]]: ...

    @overload
    def open(
        self,
        mode: OpenBinaryModeWriting,
        buffering: Literal[-1, 1] = -1,
        encoding: None = None,
        errors: None = None,
        newline: None = None,
    ) -> Coro[IOWrapper[BufferedWriter]]: ...

    @overload
    def open(
        self,
        mode: OpenBinaryModeReading,
        buffering: Literal[-1, 1] = -1,
        encoding: None = None,
        errors: None = None,
        newline: None = None,
    ) -> Coro[IOWrapper[BufferedReader]]: ...

    @overload
    def open(
        self,
        mode: OpenBinaryMode,
        buffering: int = -1,
        encoding: None = None,
        errors: None = None,
        newline: None = None,
    ) -> Coro[IOWrapper[BinaryIO]]: ...

    @overload
    def open(  # type: ignore[explicit-any]  # Any usage matches builtins.open().
        self,
        mode: str,
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> Coro[IOWrapper[IO[Any]]]: ...

    @_wraps_async(pathlib.Path.open)
    def open(self, *args: Any, **kwargs: Any) -> IOWrapper[IO[Any]]:  # type: ignore[misc, explicit-any]  # Overload return mismatch.
        return wrap_file(self._wrapped_cls(self).open(*args, **kwargs))

    def __repr__(self) -> str:
        return f'tonio.fs.Path({str(self)!r})'

    stat = _wrap_method(pathlib.Path.stat)
    chmod = _wrap_method(pathlib.Path.chmod)
    exists = _wrap_method(pathlib.Path.exists)
    glob = _wrap_method_path_iterable(pathlib.Path.glob)
    rglob = _wrap_method_path_iterable(pathlib.Path.rglob)
    is_dir = _wrap_method(pathlib.Path.is_dir)
    is_file = _wrap_method(pathlib.Path.is_file)
    is_symlink = _wrap_method(pathlib.Path.is_symlink)
    is_socket = _wrap_method(pathlib.Path.is_socket)
    is_fifo = _wrap_method(pathlib.Path.is_fifo)
    is_block_device = _wrap_method(pathlib.Path.is_block_device)
    is_char_device = _wrap_method(pathlib.Path.is_char_device)
    is_junction = _wrap_method(pathlib.Path.is_junction)
    iterdir = _wrap_method_path_iterable(pathlib.Path.iterdir)
    lchmod = _wrap_method(pathlib.Path.lchmod)
    lstat = _wrap_method(pathlib.Path.lstat)
    mkdir = _wrap_method(pathlib.Path.mkdir)
    owner = _wrap_method(pathlib.Path.owner)
    group = _wrap_method(pathlib.Path.group)
    is_mount = _wrap_method(pathlib.Path.is_mount)
    readlink = _wrap_method_path(pathlib.Path.readlink)
    rename = _wrap_method_path(pathlib.Path.rename)
    replace = _wrap_method_path(pathlib.Path.replace)
    resolve = _wrap_method_path(pathlib.Path.resolve)
    rmdir = _wrap_method(pathlib.Path.rmdir)
    symlink_to = _wrap_method(pathlib.Path.symlink_to)
    hardlink_to = _wrap_method(pathlib.Path.hardlink_to)
    touch = _wrap_method(pathlib.Path.touch)
    unlink = _wrap_method(pathlib.Path.unlink)
    absolute = _wrap_method_path(pathlib.Path.absolute)
    expanduser = _wrap_method_path(pathlib.Path.expanduser)
    read_bytes = _wrap_method(pathlib.Path.read_bytes)
    read_text = _wrap_method(pathlib.Path.read_text)
    write_bytes = _wrap_method(pathlib.Path.write_bytes)
    write_text = _wrap_method(pathlib.Path.write_text)

    @_wraps_async(pathlib.Path.samefile)
    def samefile(self, other_path: _PathArg) -> bool:
        return self._wrapped_cls(self).samefile(_unwrap(other_path))

    @_wraps_async(pathlib.Path.copy)
    def copy(self, target: _PathArg, **kwargs: Any) -> Self:  # type: ignore[explicit-any]
        return self.__class__(self._wrapped_cls(self).copy(_unwrap(target), **kwargs))

    @_wraps_async(pathlib.Path.copy_into)
    def copy_into(self, target_dir: _PathArg, **kwargs: Any) -> Self:  # type: ignore[explicit-any]
        return self.__class__(self._wrapped_cls(self).copy_into(_unwrap(target_dir), **kwargs))

    @_wraps_async(pathlib.Path.move)
    def move(self, target: _PathArg) -> Self:
        return self.__class__(self._wrapped_cls(self).move(_unwrap(target)))

    @_wraps_async(pathlib.Path.move_into)
    def move_into(self, target_dir: _PathArg) -> Self:
        return self.__class__(self._wrapped_cls(self).move_into(_unwrap(target_dir)))

    @_wraps_async(pathlib.Path.walk)
    def walk(self, *args: Any, **kwargs: Any) -> list[tuple[Self, list[str], list[str]]]:  # type: ignore[explicit-any]
        return [
            (self.__class__(dirpath), dirnames, filenames)
            for dirpath, dirnames, filenames in self._wrapped_cls(self).walk(*args, **kwargs)
        ]

    @classmethod
    def from_uri(cls, uri: str) -> Self:
        return cls(pathlib.Path.from_uri(uri))

    def as_uri(self) -> str:
        return pathlib.Path.as_uri(self)


class PosixPath(Path, pathlib.PurePosixPath):
    __slots__ = ()

    _wrapped_cls: ClassVar[type[pathlib.Path]] = pathlib.PosixPath
