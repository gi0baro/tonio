"""Backend selection machinery

Everything that may use backend-cased imports should import from here.

The backend is resolved once, early and explicitly from the `TONIO_BACKEND`
environment variable:
- `native`: Rust-based
- `asyncio`: Stdlib-based for every place where Rust module cannot compile
- `auto`: `asyncio` on Windows, `native` on everything else.

Setting `TONIO_BACKEND` to `native` or forces that backend even if
the modules are not available, even on Windows,
not falling back to `asyncio` to mask not wrong assumptions about the backend.
Then the ImportError should raise when tried.

On the `native` path this module re-exports the compiled `._tonio` types.
On the `asyncio` path it re-exports from `._asyncio_backend` modules.
"""

import os
import sys


REQUESTED_BACKEND = os.environ.get('TONIO_BACKEND', 'auto')
if REQUESTED_BACKEND not in ('auto', 'native', 'asyncio'):
    raise RuntimeError(f"Invalid TONIO_BACKEND={REQUESTED_BACKEND!r}; expected 'auto', 'native', or 'asyncio'")

BACKEND = REQUESTED_BACKEND
if REQUESTED_BACKEND == 'auto':
    if sys.platform == 'win32':
        BACKEND = 'asyncio'
    else:
        BACKEND = 'native'

assert BACKEND != 'auto'

if BACKEND == 'asyncio':
    from ._asyncio_backend._events import Event, Result, Waiter
    from ._asyncio_backend._net import Socket, TLSStream
    from ._asyncio_backend._runtime import BlockingTaskCtl, Runtime, get_runtime, set_runtime
    from ._asyncio_backend._scope import PyAsyncGenScope, PyGenScope
    from ._asyncio_backend._sync import (
        Channel,
        ChannelReceiver,
        ChannelSender,
        LockCtx,
        SemaphoreCtx,
        UnboundedChannel,
        UnboundedChannelReceiver,
        UnboundedChannelSender,
        _Barrier as Barrier,
        _Lock as Lock,
        _Semaphore as Semaphore,
    )
    from ._asyncio_backend.exceptions import (
        CancelledError,
        ResourceBroken,
        RuntimeAlreadyInitializedError,
        RuntimeNotInitializedError,
        TimeoutError,
        WouldBlock,
    )
elif BACKEND == 'native':
    from ._tonio import (
        Barrier as Barrier,
        BlockingTaskCtl as BlockingTaskCtl,
        CancelledError as CancelledError,
        Channel as Channel,
        ChannelReceiver as ChannelReceiver,
        ChannelSender as ChannelSender,
        Event as Event,
        Lock as Lock,
        LockCtx as LockCtx,
        PyAsyncGenScope as PyAsyncGenScope,
        PyGenScope as PyGenScope,
        ResourceBroken as ResourceBroken,
        Result as Result,
        Runtime as Runtime,
        RuntimeAlreadyInitializedError as RuntimeAlreadyInitializedError,
        RuntimeNotInitializedError as RuntimeNotInitializedError,
        Semaphore as Semaphore,
        SemaphoreCtx as SemaphoreCtx,
        Socket as Socket,
        TimeoutError as TimeoutError,
        TLSStream as TLSStream,
        UnboundedChannel as UnboundedChannel,
        UnboundedChannelReceiver as UnboundedChannelReceiver,
        UnboundedChannelSender as UnboundedChannelSender,
        Waiter as Waiter,
        WouldBlock as WouldBlock,
        get_runtime as get_runtime,
        set_runtime as set_runtime,
    )
