"""Backend selection machinery

Everything that may use native-backed imports should import from here.

The maybe native-backed resources source is resolved once, early and explicitly
from the `TONIO_USE_NATIVE` environment variable:
- `true`ish : Rust-based
- `false`ish : Stdlib-based for every place where Rust module cannot compile
- unsed: stdlib-based on Windows, Rust-based on everything else.

Setting `TONIO_USE_NATIVE` to `true` do forces native-based resources even if
the modules are not available, even on Windows,
not falling back to stdlib-based resources to mask not wrong assumptions.
Then the ImportError should raise when tried.

On the `native` path this module re-exports the compiled `._tonio` types.
On the stdlib path it re-exports from `._stdlib_fallback` modules.
"""

import os
import sys


_requested_use_native = os.environ.get('TONIO_USE_NATIVE', None)
if _requested_use_native not in (None, 'true', 'yes', '1', 'false', 'no', '0'):
    raise RuntimeError(f"Invalid TONIO_USE_NATIVE={_requested_use_native!r}. Expected 'true' or 'false'")

_using_native: bool = _requested_use_native
if _requested_use_native is None:
    if sys.platform == 'win32':
        _using_native = False
    else:
        _using_native = True
elif _requested_use_native in ('true', 'yet', '1'):
    _using_native = True
else:
    _using_native = False

# At this point the _using_native should already be resolved to True or False
assert _using_native is not None
assert isinstance(_using_native, bool)

if _using_native:
    # Using native bases
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
else:
    # Falling back to pure-python asyncio-backed bases
    from ._stdlib_fallback._events import Event as Event, Result as Result, Waiter as Waiter
    from ._stdlib_fallback._net import Socket as Socket, TLSStream as TLSStream
    from ._stdlib_fallback._runtime import (
        BlockingTaskCtl as BlockingTaskCtl,
        Runtime as Runtime,
        get_runtime as get_runtime,
        set_runtime as set_runtime,
    )
    from ._stdlib_fallback._scope import PyAsyncGenScope as PyAsyncGenScope, PyGenScope as PyGenScope
    from ._stdlib_fallback._sync import (
        Barrier as Barrier,
        Channel as Channel,
        ChannelReceiver as ChannelReceiver,
        ChannelSender as ChannelSender,
        Lock as Lock,
        LockCtx as LockCtx,
        Semaphore as Semaphore,
        SemaphoreCtx as SemaphoreCtx,
        UnboundedChannel as UnboundedChannel,
        UnboundedChannelReceiver as UnboundedChannelReceiver,
        UnboundedChannelSender as UnboundedChannelSender,
    )
    from ._stdlib_fallback.exceptions import (
        CancelledError as CancelledError,
        ResourceBroken as ResourceBroken,
        RuntimeAlreadyInitializedError as RuntimeAlreadyInitializedError,
        RuntimeNotInitializedError as RuntimeNotInitializedError,
        TimeoutError as TimeoutError,
        WouldBlock as WouldBlock,
    )
