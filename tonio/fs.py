import sys

from ._fs._file import IOWrapper as IOWrapper, open_file as open, wrap_file as wrap_file  # noqa: F401
from ._fs._path import Path as Path


if sys.platform == 'win32':
    from ._fs._path import WindowsPath as WindowsPath
else:
    from ._fs._path import PosixPath as PosixPath
