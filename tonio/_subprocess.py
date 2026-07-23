"""
Heavily inspired by `trio` code.

:source: (https://github.com/python-trio/trio)
:copyright: Contributors to the Trio project
:license: MIT
"""

from __future__ import annotations

import os
import subprocess
from contextlib import ExitStack
from functools import partial
from typing import (
    TYPE_CHECKING,
    Final,
    Protocol,
    TypeAlias,
)

from ._ctl import spawn_blocking
from ._fd import Fd
from ._scope import scope
from ._streams import _Stream
from ._sync import Lock
from ._types import Coro
from .exceptions import ResourceBroken


if TYPE_CHECKING:
    import signal
    from collections.abc import Sequence

StrOrBytesPath: TypeAlias = str | bytes | os.PathLike[str] | os.PathLike[bytes]


class HasFileno(Protocol):
    def fileno(self) -> int: ...


class Process:
    universal_newlines: Final = False
    encoding: Final = None
    errors: Final = None

    def __init__(
        self,
        popen: subprocess.Popen[bytes],
        stdin: _Stream | None,
        stdout: _Stream | None,
        stderr: _Stream | None,
    ) -> None:
        self._proc = popen
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr

        self.stdio: tuple[_Stream, _Stream] | None = None
        if self.stdin is not None and self.stdout is not None:
            self.stdio = (self.stdin, self.stdout)

        self._wait_lock: Lock = Lock()

        fd = os.pidfd_open(self._proc.pid, 0)
        self._pidfd = Fd(fd)
        self.args: StrOrBytesPath | Sequence[StrOrBytesPath] = self._proc.args
        self.pid: int = self._proc.pid

    def __repr__(self) -> str:
        returncode = self.returncode
        if returncode is None:
            status = f'running with PID {self.pid}'
        else:
            if returncode < 0:
                status = f'exited with signal {-returncode}'
            else:
                status = f'exited with status {returncode}'
        return f'<tonio.Process {self.args!r}: {status}>'

    @property
    def returncode(self) -> int | None:
        result = self._proc.poll()
        if result is not None:
            self._close_pidfd()
        return result

    def _close_pidfd(self) -> None:
        if self._pidfd is not None:
            self._pidfd.close()
            self._pidfd = None

    def wait(self) -> Coro[int]:
        with (yield self._wait_lock()):
            if self.poll() is None:
                yield self._pidfd._wait_readable()
                self._proc.wait()
                self._close_pidfd()

        return self._proc.returncode

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, sig: signal.Signals | int) -> None:
        self._proc.send_signal(sig)

    def terminate(self) -> None:
        self._proc.terminate()

    def kill(self) -> None:
        self._proc.kill()


def _pipe_to_child_stdin():
    rfd, wfd = os.pipe()
    return Fd(wfd), rfd


def _pipe_from_child_output():
    rfd, wfd = os.pipe()
    return Fd(rfd), wfd


def open_process(
    command: StrOrBytesPath | Sequence[StrOrBytesPath],
    *,
    stdin: int | HasFileno | None = None,
    stdout: int | HasFileno | None = None,
    stderr: int | HasFileno | None = None,
    **options: object,
) -> Coro[Process]:
    for key in ('universal_newlines', 'text', 'encoding', 'errors', 'bufsize'):
        if options.get(key):
            raise TypeError(
                'trio.Process only supports communicating over '
                f"unbuffered byte streams; the '{key}' option is not supported",
            )

    if os.name == 'posix':
        if isinstance(command, (str, bytes)) and not options.get('shell'):
            raise TypeError(
                'command must be a sequence (not a string or bytes) if shell=False on UNIX systems',
            )
        if not isinstance(command, (str, bytes)) and options.get('shell'):
            raise TypeError(
                'command must be a string or bytes (not a sequence) if shell=True on UNIX systems',
            )

    wstdin = None
    wstdout = None
    wstderr = None

    with ExitStack() as always_cleanup, ExitStack() as cleanup_on_fail:
        if stdin == subprocess.PIPE:
            wstdin, stdin = _pipe_to_child_stdin()
            always_cleanup.callback(os.close, stdin)
            cleanup_on_fail.callback(wstdin.close)
        if stdout == subprocess.PIPE:
            wstdout, stdout = _pipe_from_child_output()
            always_cleanup.callback(os.close, stdout)
            cleanup_on_fail.callback(wstdout.close)
        if stderr == subprocess.STDOUT:
            if stdout is not None:
                stderr = stdout
        elif stderr == subprocess.PIPE:
            wstderr, stderr = _pipe_from_child_output()
            always_cleanup.callback(os.close, stderr)
            cleanup_on_fail.callback(wstderr.close)

        popen = yield spawn_blocking(
            partial(
                subprocess.Popen,
                command,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                **options,
            ),
        )
        cleanup_on_fail.pop_all()

    return Process(popen, wstdin, wstdout, wstderr)


def run_process(
    command: StrOrBytesPath | Sequence[StrOrBytesPath],
    *,
    stdin: bytes | bytearray | memoryview | int | HasFileno | None = b'',
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    check: bool = True,
    **options: object,
) -> Coro[subprocess.CompletedProcess[bytes]]:
    if isinstance(stdin, str):
        raise UnicodeError('process stdin must be bytes, not str')
    if isinstance(stdin, (bytes, bytearray, memoryview)):
        input_ = stdin
        options['stdin'] = subprocess.PIPE
    else:
        input_ = None
        options['stdin'] = stdin

    if capture_stdout:
        if 'stdout' in options:
            raise ValueError("can't specify both stdout and capture_stdout")
        options['stdout'] = subprocess.PIPE
    if capture_stderr:
        if 'stderr' in options:
            raise ValueError("can't specify both stderr and capture_stderr")
        options['stderr'] = subprocess.PIPE

    stdout_chunks: list[bytes | bytearray] = []
    stderr_chunks: list[bytes | bytearray] = []

    def feed_input(stream):
        with stream:
            try:
                yield stream.send_all(input_)
            except ResourceBroken:
                pass

    def read_output(stream, chunks):
        with stream:
            while True:
                chunk = yield stream.receive_some()
                if not chunk:
                    break
                chunks.append(chunk)

    proc = yield open_process(command, **options)
    with scope() as sc:
        if input_ is not None:
            sc.spawn(feed_input(proc.stdin))
            proc.stdin = None
            proc.stdio = None
        if capture_stdout:
            sc.spawn(read_output(proc.stdout, stdout_chunks))
            proc.stdout = None
            proc.stdio = None
        if capture_stderr:
            sc.spawn(read_output(proc.stderr, stderr_chunks))
            proc.stderr = None

        yield proc.wait()
        sc.cancel()
    yield sc

    stdout = b''.join(stdout_chunks) if capture_stdout else None
    stderr = b''.join(stderr_chunks) if capture_stderr else None

    if proc.returncode and check:
        raise subprocess.CalledProcessError(
            proc.returncode,
            proc.args,
            output=stdout,
            stderr=stderr,
        )
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
