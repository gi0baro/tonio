import sys

from .._colored._fd import FdStream as FdStream
from .._io import ScheduledIO as ScheduledIO, register as register


if sys.platform != 'win32':
    from .._fd import Fd as Fd, ProcFd as ProcFd, open_proc_fd as open_proc_fd
