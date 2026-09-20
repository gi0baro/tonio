import sys


if sys.platform == 'win32':
    from ._win import FdStream as FdStream
else:
    from ._unix import (
        Fd as Fd,
        FdStream as FdStream,
        ProcFd as ProcFd,
        open_proc_fd as open_proc_fd,
    )
