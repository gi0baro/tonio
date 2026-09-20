import sys


if sys.platform == 'win32':
    from ._win import FdStream as FdStream
else:
    from ._unix import FdStream as FdStream
