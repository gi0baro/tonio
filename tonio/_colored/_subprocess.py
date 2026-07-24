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
from typing import TYPE_CHECKING

from .._fd import ProcFd, open_proc_fd
from .._streams import _Stream
from .._subprocess import HasFileno, Process as _Process, StrOrBytesPath
from ..exceptions import ResourceBroken
from ._ctl import spawn, spawn_blocking
from ._fd import FdStream
from ._sync import Lock


if TYPE_CHECKING:
    from collections.abc import Sequence


class Process(_Process):
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

        self._pidfd: ProcFd | None = open_proc_fd(self._proc.pid)
        self.args: StrOrBytesPath | Sequence[StrOrBytesPath] = self._proc.args
        self.pid: int = self._proc.pid

    async def wait(self) -> int:
        async with self._wait_lock:
            if self.poll() is None:
                if (waiter := self._pidfd._io_arm_r()) is not None:
                    await waiter
                self._proc.wait()
                self._close_pidfd()

        return self._proc.returncode


def _pipe_to_child_stdin():
    rfd, wfd = os.pipe()
    return FdStream(wfd), rfd


def _pipe_from_child_output():
    rfd, wfd = os.pipe()
    return FdStream(rfd), wfd


async def open_process(
    command: StrOrBytesPath | Sequence[StrOrBytesPath],
    *,
    stdin: int | HasFileno | None = None,
    stdout: int | HasFileno | None = None,
    stderr: int | HasFileno | None = None,
    **options: object,
) -> Process:
    for key in ('universal_newlines', 'text', 'encoding', 'errors', 'bufsize'):
        if options.get(key):
            raise TypeError(
                'tonio.Process only supports communicating over '
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

        popen = await spawn_blocking(
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


async def run_process(
    command: StrOrBytesPath | Sequence[StrOrBytesPath],
    *,
    stdin: bytes | bytearray | memoryview | int | HasFileno | None = b'',
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    check: bool = True,
    **options: object,
) -> subprocess.CompletedProcess[bytes]:
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

    async def feed_input(stream):
        with stream:
            try:
                await stream.send_all(input_)
            except ResourceBroken:
                pass

    async def read_output(stream, chunks):
        with stream:
            while True:
                chunk = await stream.receive_some()
                if not chunk:
                    break
                chunks.append(chunk)

    proc = await open_process(command, **options)
    tasks = []
    if input_ is not None:
        tasks.append(feed_input(proc.stdin))
        proc.stdin = None
        proc.stdio = None
    if capture_stdout:
        tasks.append(read_output(proc.stdout, stdout_chunks))
        proc.stdout = None
        proc.stdio = None
    if capture_stderr:
        tasks.append(read_output(proc.stderr, stderr_chunks))
        proc.stderr = None

    tasks = spawn.without_results(*tasks)
    await proc.wait()
    await tasks

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
