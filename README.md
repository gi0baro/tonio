# TonIO

TonIO is a multi-threaded async runtime for free-threaded Python, built in Rust on top of the [mio crate](https://github.com/tokio-rs/mio), and inspired by [tinyio](https://github.com/patrick-kidger/tinyio), [trio](https://github.com/python-trio/trio) and [tokio](https://github.com/tokio-rs/tokio).

> **Warning**: TonIO is currently a work in progress. The APIs are subject to breaking changes.

> **Note:** TonIO is available on free-threaded Python only. Windows is supported on a best-effort basis.

TonIO supports both using `yield` and the more canonical `async/await` notations, with the latter being available as part of the `tonio.colored` module. Following code snippets show both the usages.

> **Warning:** despite the fact TonIO supports `async` and `await` notations, it's not compatible with any `asyncio` object like futures and tasks. The [TonIO-Monkey](https://github.com/gi0baro/tonio-monkey) project provides patches for some popular `asyncio` packages.

## In a nutshell

<table><tr><td>

`yield` syntax

```python
import tonio

def wait_and_add(x):
    yield tonio.sleep(1)
    return x + 1

@tonio.main
def main():
    parallel = tonio.spawn(
        wait_and_add(3), 
        wait_and_add(4)
    )
    six = yield wait_and_add(5)
    four, five = yield parallel
    return four, five, six

assert main() == (4, 5, 6)
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def wait_and_add(x):
    await tonio.sleep(1)
    return x + 1

@tonio.main
async def main():
    parallel = tonio.spawn(
        wait_and_add(3), 
        wait_and_add(4)
    )
    six = await wait_and_add(5)
    four, five = await parallel
    return four, five, six

assert main() == (4, 5, 6)
```
</td></tr></table>

## Usage

### Entrypoint

Every TonIO program consists of an entrypoint, which should be passed to the `run` method:

<table><tr><td>

`yield` syntax

```python
import tonio

def main():
    yield
    print("Hello world")

tonio.run(main())
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def main():
    await tonio.yield_now()
    print("Hello world")

tonio.run(main())
```
</td></tr></table>

TonIO also provides a `main` decorator, thus we can rewrite the previous example as:

<table><tr><td>

`yield` syntax

```python
import tonio

@tonio.main
def main():
    yield
    print("Hello world")

main()
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

@tonio.main
async def main():
    await tonio.yield_now()
    print("Hello world")

main()
```
</td></tr></table>

> **Note:** as you can see the `colored` module provides the additional `yield_now` coroutine, a quick way to define a suspension point, given you cannot just `yield` as in the non-colored notation.

> **Note:** both `run` and `main` can only be called once per program. To run the runtime multiple times in the same program, follow the section below.

#### Manually managing the runtime

TonIO also provides the `runtime` function, to manually manage the runtime lifecycle:

```python
import tonio

def _run1():
    ...

async def _run2():
    ...

def main():
    runtime = tonio.runtime()
    runtime.run_until_complete(_run1())
    runtime.run_until_complete(_run2())
```

#### Runtime options

The `run`, `main` and `runtime` methods accept options, specifically:

| option name | description | default |
| --- | --- | --- |
| `context` | enable `contextvars` usage in coroutines | `False` |
| `signals` | list of signals to listen to | |
| `threads` | Number of runtime threads | # of CPU cores |
| `blocking_threadpool_size` | Maximum number of blocking threads | 128 |
| `blocking_threadpool_idle_ttl` | Idle timeout for blocking threads (in seconds) | 30 |

### Events

The core object in TonIO is `Event`. It's basically a wrapper around an atomic boolean flag, initialised with `False`. `Event` provides the following methods:

- `is_set()`: return the value of the flag
- `set()`: set the flag to `True`
- `clear()`: set the flag to `False`
- `wait(timeout=None)`: returns a coroutine you can yield on that unblocks when the flag is set to `True` or the timeout expires. Timeout is in seconds.

<table><tr><td>

`yield` syntax

```python
import tonio

@tonio.main
def main():
    event = tonio.Event()

    def setter():
        yield tonio.sleep(1)
        event.set()

    tonio.spawn(setter())
    yield event.wait()
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

@tonio.main
async def main():
    event = tonio.Event()

    async def setter():
        await tonio.sleep(1)
        event.set()

    tonio.spawn(setter())
    await event.wait()
```
</td></tr></table>

#### Waiters

`Event.wait` returns a `Waiter`, the object the runtime actually suspends on. Waiters can be combined: `w1 & w2` unblocks when both are set, `w1 | w2` when either is. When the operands carry timeouts, `&` keeps the longest and `|` the shortest.

Waiters can also be built directly from events with `Waiter(ev1, ev2)` (all) and `Waiter.any(ev1, ev2)`. Both accept a `timeout` that applies to the waiter as a whole, and expressed in **microseconds**.

<table><tr><td>

`yield` syntax

```python
import tonio

@tonio.main
def main():
    ready, stop = tonio.Event(), tonio.Event()
    yield ready.wait() | stop.wait()
    if stop.is_set():
        return
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

@tonio.main
async def main():
    ready, stop = tonio.Event(), tonio.Event()
    await (ready.wait() | stop.wait())
    if stop.is_set():
        return
```
</td></tr></table>

#### Result

`Result` is a thread-safe slot to hand values across coroutines, typically paired with an `Event`. `store(value)` writes it and `fetch()` reads it back. Built with a `size`, it holds that many slots, `store(value, index)` fills one and `fetch()` returns them as a list.

### Spawning tasks

TonIO provides the `spawn` method to schedule new coroutines onto the runtime:

<table><tr><td>

`yield` syntax

```python
import tonio

def doubv(v):
    yield
    return v * 2

@tonio.main
def main():
    parallel = tonio.spawn(doubv(2), doubv(3))
    v3 = yield doubv(4)
    v1, v2 = yield parallel
    print([v1, v2, v3])
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def doubv(v):
    await tonio.yield_now()
    return v * 2

@tonio.main
async def main():
    parallel = tonio.spawn(doubv(2), doubv(3))
    v3 = await doubv(4)
    v1, v2 = await parallel
    print([v1, v2, v3])
```
</td></tr></table>

Coroutines passed to `spawn` get scheduled onto the runtime immediately. Using `yield` or `await` on the return value of `spawn` just waits for the coroutines to complete and retrieve the results.

When results are not needed, `spawn.without_results` waits for completion without collecting them. `spawn.without_tracking` schedules the coroutines and returns nothing at all, for fire-and-forget work.

#### Blocking tasks

TonIO provides the `spawn_blocking` method to schedule blocking operations onto the runtime:

<table><tr><td>

`yield` syntax

```python
import tonio

def read_file(path):
    with open(path, "r") as f:
        return f.read()

@tonio.main
def main():
    file_data = yield tonio.spawn_blocking(
        read_file, 
        "sometext.txt"
    )
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

def read_file(path):
    with open(path, "r") as f:
        return f.read()

@tonio.main
async def main():
    file_data = await tonio.spawn_blocking(
        read_file, 
        "sometext.txt"
    )
```
</td></tr></table>

#### Running tasks from synchronous contexts

TonIO provides the `block_on` method to spawn coroutines from a synchronous context. It works the same way of `spawn`, except it accepts a single coroutine and it blocks the current thread until the coroutine is completed.

> **Warning:** using `block_on` from within a coroutine might produce a runtime deadlock.

#### Map utilities

TonIO provides the `map` and `map_blocking` utilities to spawn the same operation with an iterable of parameters:

<table><tr><td>

`yield` syntax

```python
import tonio

accum = []

def task(no):
    yield tonio.sleep(0.5)
    accum.append(no * 2)

@tonio.main
def main():
    yield tonio.map(task, range(4))
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

accum = []

async def task(no):
    await tonio.sleep(0.5)
    accum.append(no * 2)

@tonio.main
async def main():
    await tonio.map(task, range(4))
```
</td></tr></table>

#### Completion-based iterators

TonIO provides the `as_completed` utility to iterate over task results based on completion order:

<table><tr><td>

`yield` syntax

```python
import tonio

def _sleep(v):
    yield tonio.sleep(v)
    return v

@tonio.main
def main():
    vals = []
    for task in tonio.as_completed(
        _sleep(0.5),
        _sleep(0.1),
        _sleep(0.3),
    ):
        vals.append(yield task)
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def _sleep(v):
    await tonio.sleep(v)
    return v

@tonio.main
async def main():
    vals = []
    async for val in tonio.as_completed(
        _sleep(0.5),
        _sleep(0.1),
        _sleep(0.3),
    ):
        vals.append(val)
```
</td></tr></table>

### Scopes and cancellations

TonIO provides a `scope` context, that lets you cancel work spawned within it:

<table><tr><td>

`yield` syntax

```python
import tonio

def slow_push(target, sleep):
    yield tonio.sleep(sleep)
    target.append(True)

@tonio.main
def main():
    values = []
    with tonio.scope() as scope:
        scope.spawn(slow_push(values, 0.1))
        scope.spawn(slow_push(values, 2))
        yield tonio.sleep(0.2)
        scope.cancel()
    yield scope()
    assert len(values) == 1
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def slow_push(target, sleep):
    await tonio.sleep(sleep)
    target.append(True)

@tonio.main
async def main():
    values = []
    async with tonio.scope() as scope:
        scope.spawn(slow_push(values, 0.1))
        scope.spawn(slow_push(values, 2))
        await tonio.sleep(0.2)
        scope.cancel()
    assert len(values) == 1
```
</td></tr></table>

When you `yield` on the scope, it will wait for all the spawned coroutines to end. If the scope was canceled, then all the pending coroutines will be canceled. By default, an exception in the scope context won't cancel the scope itself. If you want those exceptions to cancel the scope, you can pass `cancel_on_exc=True` to `scope`.

> **Note:** as you can see, the *colored* version of `scope` doesn't require to be `await`ed, as it will *yield* when exiting the context.

#### Select first completing task

TonIO also provides a `select` utility to cancel remaining work on the first completing task:

<table><tr><td>

`yield` syntax

```python
import tonio

def slow_push(target, sleep):
    yield tonio.sleep(sleep)
    target.append(True)

@tonio.main
def main():
    values = []
    yield tonio.select(
        slow_push(values, 0.1),
        slow_push(values, 2)
    )
    assert len(values) == 1
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def slow_push(target, sleep):
    await tonio.sleep(sleep)
    target.append(True)

@tonio.main
async def main():
    values = []
    await tonio.select(
        slow_push(values, 0.1),
        slow_push(values, 2)
    )
    assert len(values) == 1
```
</td></tr></table>

`select` also accepts waiters, so an `Event.wait()` can race against coroutines.

### Time-related functions

- `tonio.time.time()`: a function returning the runtime's clock (in seconds, microsecond resolution)
- `tonio.time.sleep(delay)`: a coroutine you can yield on to sleep (delay is in seconds)
- `tonio.time.timeout(coro, timeout)`: a coroutine you can yield on returning a tuple `(output, success)`. If the coroutine succeeds in the given time then the pair `(output, True)` is returned. Otherwise this will return `(None, False)`.

> **Note**: `time.sleep` is also exported to the main `tonio` module.

> **Note**: all of the above functions are also present in `tonio.colored.time` module.

#### Scheduling work

TonIO provides the `time.interval` function to create interval objects you can yield on a scheduled basis:

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio import time

def some_task():
    ...

def scheduler():
    interval = time.interval(1)
    while True:
        yield interval.tick()
        tonio.spawn(some_task())

@tonio.main
def main():
    tonio.spawn(scheduler())
    # do some other work
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored import time

async def some_task():
    ...

async def scheduler():
    interval = time.interval(1)
    while True:
        await interval.tick()
        tonio.spawn(some_task())

@tonio.main
async def main():
    tonio.spawn(scheduler())
    # do some other work
```
</td></tr></table>

The `interval` method first argument is the interval in seconds resolution, and the method also accepts an optional `at` argument, to delay the first execution at a specific time (from the runtime's clock perspective):

```python
from tonio import time

# tick every 500ms, with the first tick happening in 5 seconds from now
interval = time.interval(0.5, time.time() + 5)
```

### Synchronization primitives

Synchronization primitives are exposed in the `tonio.sync` module.

#### Lock

Implements a classic mutex, or a non-reentrant, single-owner lock for coroutines:

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio import sync

@tonio.main
def main():
    # counter can't go above 1
    counter = 0

    def _count(lock):
        nonlocal counter
        with (yield lock()):
            counter += 1
            yield
            counter -= 1
    
    lock = sync.Lock()
    yield tonio.spawn(*[
        _count(lock)
        for _ in range(10)
    ])
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored import sync

@tonio.main
async def main():
    # counter can't go above 1
    counter = 0

    async def _count(lock):
        nonlocal counter
        async with lock:
            counter += 1
            await tonio.yield_now()
            counter -= 1
    
    lock = sync.Lock()
    await tonio.spawn(*[
        _count(lock)
        for _ in range(10)
    ])
```
</td></tr></table>

The `Lock` object also implements an `or_raise` method, that will immediately fail when the lock cannot be acquired:

```python
from tonio.exceptions import WouldBlock

try:
    with lock.or_raise():
        ...
except WouldBlock:
    ...
```

#### Semaphore

A semaphore for coroutines:

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio import sync

@tonio.main
def main():
    # counter can't go above 2
    counter = 0

    def _count(semaphore):
        nonlocal counter
        with (yield semaphore()):
            counter += 1
            yield
            counter -= 1
    
    semaphore = sync.Semaphore(2)
    yield tonio.spawn(*[
        _count(semaphore)
        for _ in range(10)
    ])
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored import sync

@tonio.main
async def main():
    # counter can't go above 2
    counter = 0

    async def _count(semaphore):
        nonlocal counter
        async with semaphore:
            counter += 1
            await tonio.yield_now()
            counter -= 1
    
    semaphore = sync.Semaphore(2)
    await tonio.spawn(*[
        _count(semaphore)
        for _ in range(10)
    ])
```
</td></tr></table>

As for locks, the `Semaphore` object also implements an `or_raise` method, that will immediately fail when the lock cannot be acquired:

```python
from tonio.exceptions import WouldBlock

try:
    with semaphore.or_raise():
        ...
except WouldBlock:
    ...
```

The `Semaphore` object also implements a `tokens` method, that returns the number of available tokens.

#### Barrier

A barrier for coroutines:

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio import sync

@tonio.main
def main():
    barrier = sync.Barrier(3)
    count = 0

    def _start_at_3():
        nonlocal count
        count += 1
        i = yield barrier.wait()
        assert count == 3
        return i

    yield tonio.spawn(*[
        _start_at_3()
        for _ in range(3)
    ])
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored import sync

@tonio.main
async def main():
    barrier = sync.Barrier(3)
    count = 0

    async def _start_at_3():
        nonlocal count
        count += 1
        i = await barrier.wait()
        assert count == 3
        return i

    await tonio.spawn(*[
        _start_at_3()
        for _ in range(3)
    ])
```
</td></tr></table>

The `Barrier` object also implements a `value` method, which returns the current value of the barrier.

#### Channels

Multi-producer multi-consumer channels for inter-coroutine communication.

The `tonio.sync.channel` module provides both a `channel` and an `unbounded` constructors.    
The main difference between *bounded* and *unbounded* channels, as the names suggest, is that while the first will suspend sending messages once the specified length is reached, and it will resume accepting messages once the existing buffer is consumed, the latter will always accept new messages. That's also why, the sender part of a bounded channel is async, while in the unbounded is not.

##### Bounded channel

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio import sync
from tonio.sync import channel

def producer(sender, barrier, offset):
    for i in range(20):
        message = offset + i
        yield sender.send(message)
    yield barrier.wait()

def consumer(receiver):
    while True:
        try:
            message = yield receiver.receive()
            print(message)
        except BrokenPipeError:
            break

@tonio.main
def main():
    def close(sender, barrier):
        yield barrier.wait()
        sender.close()

    sender, receiver = channel.channel(2)
    barrier = sync.Barrier(3)
    yield tonio.spawn(*[
        producer(sender, barrier, 100),
        producer(sender, barrier, 200),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        close(sender, barrier),
    ])
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored import sync
from tonio.colored.sync import channel

async def producer(sender, barrier, offset):
    for i in range(20):
        message = offset + i
        await sender.send(message)
    await barrier.wait()

async def consumer(receiver):
    while True:
        try:
            message = await receiver.receive()
            print(message)
        except BrokenPipeError:
            break

@tonio.main
async def main():
    async def close(sender, barrier):
        await barrier.wait()
        sender.close()

    sender, receiver = channel.channel(2)
    barrier = sync.Barrier(3)
    await tonio.spawn(*[
        producer(sender, barrier, 100),
        producer(sender, barrier, 200),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        close(sender, barrier),
    ])
```
</td></tr></table>

##### Unbounded channel

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio import sync
from tonio.sync import channel

def producer(sender, barrier, offset):
    for i in range(20):
        message = offset + i
        sender.send(message)
    yield barrier.wait()

def consumer(receiver):
    while True:
        try:
            message = yield receiver.receive()
            print(message)
        except BrokenPipeError:
            break

@tonio.main
def main():
    def close(sender, barrier):
        yield barrier.wait()
        sender.close()

    sender, receiver = channel.unbounded()
    barrier = sync.Barrier(3)
    yield tonio.spawn(*[
        producer(sender, barrier, 100),
        producer(sender, barrier, 200),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        close(sender, barrier),
    ])
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored import sync
from tonio.colored.sync import channel

async def producer(sender, barrier, offset):
    for i in range(20):
        message = offset + i
        sender.send(message)
    await barrier.wait()

async def consumer(receiver):
    while True:
        try:
            message = await receiver.receive()
            print(message)
        except BrokenPipeError:
            break

@tonio.main
async def main():
    async def close(sender, barrier):
        await barrier.wait()
        sender.close()

    sender, receiver = channel.unbounded()
    barrier = sync.Barrier(3)
    await tonio.spawn(*[
        producer(sender, barrier, 100),
        producer(sender, barrier, 200),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        consumer(receiver),
        close(sender, barrier),
    ])
```
</td></tr></table>

##### Non-blocking operations

Receivers of both channel kinds offer `receive_nowait`, a synchronous variant that never suspends: it returns the message or one of the `Empty` and `Closed` sentinels. Bounded senders, the only suspending ones, offer `send_nowait` in the same way: it returns `None` on success or one of the `Full` and `Closed` sentinels. The sentinels are available as attributes on the objects exposing them:

```python
sender, receiver = channel.channel(8)

if sender.send_nowait(message) is sender.Full:
    ...
if (message := receiver.receive_nowait()) is receiver.Empty:
    ...
```

The same objects also expose `try_send` and `try_receive`, which raise instead: `WouldBlock` when the channel is full or empty, `BrokenPipeError` when it's closed.

### Markers

The `mark` module provides decorator shortcuts for `spawn_blocking` and `Semaphore`:

<table><tr><td>

`yield` syntax

```python
import tonio

# run through `spawn_blocking`
@tonio.mark.blocking
def read_file(path):
    ...

# no more than 2 running at the same time
@tonio.mark.max_concurrency(2)
def fetch(url):
    ...

# `blocking` + `max_concurrency`
@tonio.mark.cpu_bound(4)
def resize(image):
    ...
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

# run through `spawn_blocking`
@tonio.mark.blocking
def read_file(path):
    ...

# no more than 2 running at the same time
@tonio.mark.max_concurrency(2)
async def fetch(url):
    ...

# `blocking` + `max_concurrency`
@tonio.mark.cpu_bound(4)
def resize(image):
    ...
```
</td></tr></table>

### Network module

Network primitives are exposed under the `tonio.net` module.

#### Streams

The high-level network primitives in TonIO are centered around the `SocketStream` and `SocketListener` objects.

The `SocketListener` object implements an `accept` coroutine which returns a `SocketStream` object.    
The `SocketStream` object implements the `send_all` and `receive_some` coroutines to send and receive data, and a `send_eof` method to shutdown the sending side.    
Both objects implement a `close` method to shutdown the underlying socket.

You can create and interact with the above objects using some high-level helpers in the `net` module, specifically:

- `open_tcp_stream`: a coroutine to open a `SocketStream` connected to a TCP endpoint
- `open_unix_socket`: a coroutine to open a `SocketStream` connected to a Unix socket
- `open_tcp_listeners`: a coroutine to initialise `SocketListener` objects
- `open_unix_listener`: a coroutine to initialise a `SocketListener` on a Unix socket path
- `serve_listeners`: a coroutine to spawn `SocketListener` accept loops targeting a handler
- `serve_tcp`: a coroutine that joins `open_tcp_listeners` and `serve_listeners` in one call
- `serve_unix`: a coroutine that joins `open_unix_listener` and `serve_listeners` in one call

<table><tr><td>

`yield` syntax

```python
from tonio.net import open_tcp_stream, serve_tcp

def server():
    yield serve_tcp(
        server_handle, 
        host='127.0.0.1', 
        port=8000
    )

def server_handle(stream):
    # receive some data
    data = yield stream.receive_some()

def client():
    stream = yield open_tcp_stream(
        host='127.0.0.1', 
        port=8000
    )
    # send some data
    yield stream.send_all(b"message")
```
</td><td>

`await` syntax

```python
from tonio.colored.net import open_tcp_stream, serve_tcp

async def server():
    await serve_tcp(
        server_handle, 
        host='127.0.0.1', 
        port=8000
    )

async def server_handle(stream):
    # receive some data
    data = await stream.receive_some()

async def client():
    stream = await open_tcp_stream(
        host='127.0.0.1', 
        port=8000
    )
    # send some data
    await stream.send_all(b"message")
```
</td></tr></table>

Unix domain sockets use the same objects, with `serve_unix` and `open_unix_socket`:

<table><tr><td>

`yield` syntax

```python
from tonio.net import open_unix_socket, serve_unix

def server():
    yield serve_unix(
        server_handle, 
        '/tmp/app.sock', 
        mode=0o600
    )

def client():
    stream = yield open_unix_socket(
        '/tmp/app.sock'
    )
    yield stream.send_all(b"message")
```
</td><td>

`await` syntax

```python
from tonio.colored.net import open_unix_socket, serve_unix

async def server():
    await serve_unix(
        server_handle, 
        '/tmp/app.sock', 
        mode=0o600
    )

async def client():
    stream = await open_unix_socket(
        '/tmp/app.sock'
    )
    await stream.send_all(b"message")
```
</td></tr></table>

##### Readiness and non-blocking operations

`SocketStream` also exposes its readiness state, for code that wants to decide when to read or write rather than just block on it:

- `wait_readable(timeout=None)` and `wait_writable(timeout=None)`: coroutines that suspend until the socket is ready, returning `False` if the timeout (in seconds) expires first
- `receive_some_nowait(max_bytes=None)`: a synchronous receive, returning the `NotReady` sentinel (available as `stream.NotReady`) when no data is available
- `try_receive_some(max_bytes=None)`: same, but raising `WouldBlock` instead
- `watch_readable()` and `watch_writable()`: context managers producing a watcher, whose `waiter()` method returns a `Waiter` (or `None` when ready) you can combine with others, and whose `ready()` method tells whether the socket is ready

<table><tr><td>

`yield` syntax

```python
def handler(stream, stop):
    while True:
        with stream.watch_readable() as watcher:
            if (waiter := watcher.waiter()) is not None:
                yield waiter | stop.wait()
            if stop.is_set():
                break
        data = stream.receive_some_nowait()
        if data is stream.NotReady:
            continue
        ...
```
</td><td>

`await` syntax

```python
async def handler(stream, stop):
    while True:
        with stream.watch_readable() as watcher:
            if (waiter := watcher.waiter()) is not None:
                await (waiter | stop.wait())
            if stop.is_set():
                break
        data = stream.receive_some_nowait()
        if data is stream.NotReady:
            continue
        ...
```
</td></tr></table>

#### TLS streams

TonIO implement TLS wrappers around the streaming APIs through primitives in the `tonio.net.tls` module.

TonIO provides the `TLSStream` and `TLSListener` object wrappers and the following high-level helpers:

- `open_tls_over_tcp_stream`: a coroutine to open a `TLSStream` wrapping a TCP `SocketStream`
- `open_tls_over_tcp_listeners`: a coroutine to initialise `TLSListener` objects
- `serve_tls_over_tcp`: a coroutine that joins `open_tls_over_tcp_listeners` and `serve_listeners` in one call

#### Low-level sockets

The `tonio.net.socket` module provides TonIO's basic low-level networking API.    
Generally, the API exposed by this module mirrors the standard library `socket` module.

TonIO socket objects are overall very similar to the standard library socket objects, with the main difference being that blocking methods become coroutines.

<table><tr><td>

`yield` syntax

```python
import tonio
from tonio.net import socket

def server():
    sock = socket.socket()
    with sock:
        yield sock.bind(('127.0.0.1', 8000))
        sock.listen()

        while True:
            client, _ = yield sock.accept()
            tonio.spawn(server_handle(client))

def server_handle(connection):
    with connection:
        # receive some data
        data = yield connection.recv(4096)

def client():
    sock = socket.socket()
    with sock:
        yield sock.connect(('127.0.0.1', 8000))
        yield sock.send(b"message")
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
from tonio.colored.net import socket

async def server():
    sock = socket.socket()
    with sock:
        await sock.bind(('127.0.0.1', 8000))
        sock.listen()

        while True:
            client, _ = await sock.accept()
            tonio.spawn(server_handle(client))

async def server_handle(connection):
    with connection:
        # receive some data
        data = await connection.recv(4096)

async def client():
    sock = socket.socket()
    with sock:
        await sock.connect(('127.0.0.1', 8000))
        await sock.send(b"message")
```
</td></tr></table>

### Filesystem module

TonIO's `fs` module exposes async API for filesystem operations (that are run in the blocking thread-pool).
It provides `open`, a `Path` class mirroring `pathlib.Path`, and `wrap_file` to
adopt an already-open file object.

<table><tr><td>

`yield` syntax

```python
import tonio
import tonio.fs as fs

def main():
    f = yield fs.open('data.txt', 'w')
    yield f.write('hello')
    yield f.close()

    path = fs.Path('data.txt')
    if (yield path.exists()):
        print((yield path.read_text()))

    for entry in (yield fs.Path('.').iterdir()):
        print(entry.name)
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio
import tonio.colored.fs as fs

async def main():
    async with await fs.open('data.txt', 'w') as f:
        await f.write('hello')

    path = fs.Path('data.txt')
    if await path.exists():
        print(await path.read_text())

    for entry in await fs.Path('.').iterdir():
        print(entry.name)
```
</td></tr></table>

Operations that touch the filesystem are asynchronous; everything else stays synchronous.

> **Note:** methods returning several paths (`iterdir`, `glob`, `rglob`, `walk`) are resolved in a single hop and give back a `list`. Since `walk` is fully materialised, mutating its `dirnames` does not prune the traversal, unlike `pathlib.Path.walk`.

Reading a file line by line differs between the two flavours. The `await` syntax supports `async for`
and `async with`, neither of which the `yield` syntax can express:

<table><tr><td>

`yield` syntax

```python
def read_lines(path):
    f = yield fs.open(path, 'r')
    try:
        while True:
            line = yield f.readline()
            if not line:
                break
            print(line)
    finally:
        yield f.close()
```
</td><td>

`await` syntax

```python
async def read_lines(path):
    async with await fs.open(path, 'r') as f:
        async for line in f:
            print(line)
```
</td></tr></table>

### Subprocesses

TonIO exposes two coroutines to run child processes: `run_process` for the common
"run it and collect the outcome" case, and `open_process` for interacting with a process while it
runs. Both spawn the process on the blocking thread-pool.

`run_process` returns a `subprocess.CompletedProcess` and accepts:

- `stdin`: bytes to feed to the child (defaults to `b''`, meaning "close stdin immediately"), or a file descriptor/`subprocess` constant
- `capture_stdout` / `capture_stderr`: when true, the relevant stream is collected and available on the result
- `check`: when true (the default), a non-zero exit code raises `subprocess.CalledProcessError`

Any other keyword argument is forwarded to `subprocess.Popen`.

<table><tr><td>

`yield` syntax

```python
import tonio

def main():
    result = yield tonio.run_process(
        ['echo', 'hello'],
        capture_stdout=True
    )
    print(result.returncode)
    print(result.stdout)
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def main():
    result = await tonio.run_process(
        ['echo', 'hello'],
        capture_stdout=True
    )
    print(result.returncode)
    print(result.stdout)
```
</td></tr></table>

`open_process` returns a `Process` object instead, giving access to the running child. Passing
`subprocess.PIPE` for `stdin`, `stdout` or `stderr` exposes the corresponding pipe as a stream on the
process object, implementing the same `send_all` and `receive_some` coroutines of network streams:

<table><tr><td>

`yield` syntax

```python
import subprocess
import tonio

def main():
    proc = yield tonio.open_process(
        ['cat'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    yield proc.stdin.send_all(b'hello')
    proc.stdin.close()
    data = yield proc.stdout.receive_some()
    code = yield proc.wait()
```
</td><td>

`await` syntax

```python
import subprocess
import tonio.colored as tonio

async def main():
    proc = await tonio.open_process(
        ['cat'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    await proc.stdin.send_all(b'hello')
    proc.stdin.close()
    data = await proc.stdout.receive_some()
    code = await proc.wait()
```
</td></tr></table>

The `Process` object exposes:

- `args` and `pid`: the command and the process identifier
- `stdin`, `stdout`, `stderr`: the piped streams, or `None` when not piped
- `stdio`: a `(stdin, stdout)` tuple, when both are piped
- `returncode` and `poll()`: the exit code, or `None` while the process is still running
- `wait`: a coroutine waiting for the process to exit, returning its exit code
- `send_signal`, `terminate`, `kill`: synchronous methods to signal the process

> **Note:** unlike `run_process`, `open_process` does not reap the child for you: remember to `wait` on it — possibly after a `kill` — otherwise the child outlives your task.

> **Note:** processes in TonIO only communicate over unbuffered byte streams: the `universal_newlines`, `text`, `encoding`, `errors` and `bufsize` options of `subprocess` are not supported.

> **Note:** on Windows, due to the platform's lack of features, the subprocess readiness implementation falls back to the blocking thread-pool. Thus, waiting on a process or read/write operations on pipes can't be interrupted while blocked: cancellations take effect only once the OS call returns.

### Driving your own I/O

The `io` module exposes the primitives TonIO's own sockets, pipes and processes are built on, so you can plug any file descriptor the platform poller understands into the runtime, with the same readiness model.

`register` puts a descriptor under the poller's watch, for both reading and writing, and returns a `ScheduledIO` object. The registration is edge-triggered and lasts until you `close` it. The descriptor itself is neither owned nor switched to non-blocking mode: that's up to you.

Readiness is consumed in user space through a small protocol: `arm_r` (or `arm_w`) returns `None` if the descriptor is known to be ready, otherwise a `Waiter` to suspend on. Once ready, you perform the actual system call. If it would block anyway, `clear_r` (or `clear_w`) drops the stale readiness, so the next `arm_r` suspends again.

<table><tr><td>

`yield` syntax

```python
import os
import tonio

def read_some(sched, fd, max_bytes=65536):
    while True:
        if (waiter := sched.arm_r()) is not None:
            yield waiter
            continue
        try:
            return os.read(fd, max_bytes)
        except BlockingIOError:
            sched.clear_r()

@tonio.main
def main():
    r, w = os.pipe()
    os.set_blocking(r, False)
    sched = tonio.io.register(r)
    os.write(w, b"hello")
    print((yield read_some(sched, r)))
    sched.close()
```
</td><td>

`await` syntax

```python
import os
import tonio.colored as tonio

async def read_some(sched, fd, max_bytes=65536):
    while True:
        if (waiter := sched.arm_r()) is not None:
            await waiter
            continue
        try:
            return os.read(fd, max_bytes)
        except BlockingIOError:
            sched.clear_r()

@tonio.main
async def main():
    r, w = os.pipe()
    os.set_blocking(r, False)
    sched = tonio.io.register(r)
    os.write(w, b"hello")
    print(await read_some(sched, r))
    sched.close()
```
</td></tr></table>

`arm_r` and `arm_w` accept a `timeout` in seconds. An expired waiter just resumes, so a further `arm_*` call tells whether the descriptor got ready in the meantime. Readiness also covers hang-ups and errors: you'll be woken up when the peer goes away, and the following system call will report it.

`consume_r` and `consume_w` drain a direction's readiness and tell whether it was set, for descriptors signalling through readiness alone.

#### Descriptor streams

`FdStream` wraps a pipe-like descriptor into the same stream interface of the network module, taking ownership of it. It provides the `send_all` and `receive_some` coroutines, `fileno` and `close`, the latter also invoked when leaving a `with` block. This is what the pipes of `Process` objects are.

<table><tr><td>

`yield` syntax

```python
import os
import tonio
from tonio.io import FdStream

@tonio.main
def main():
    r, w = os.pipe()
    with FdStream(r) as reader, FdStream(w) as writer:
        yield writer.send_all(b"hello")
        print((yield reader.receive_some()))
```
</td><td>

`await` syntax

```python
import os
import tonio.colored as tonio
from tonio.colored.io import FdStream

@tonio.main
async def main():
    r, w = os.pipe()
    with FdStream(r) as reader, FdStream(w) as writer:
        await writer.send_all(b"hello")
        print(await reader.receive_some())
```
</td></tr></table>

Concurrent operations on the same direction of a stream raise `WouldBlock`, and a broken pipe surfaces as `ResourceBroken`.

> **Note:** on Windows `FdStream` falls back to the blocking thread-pool, with the same limitations described for subprocesses.

### Signals

TonIO provides a context manager to catch signals.

The usage of such context manager requires to first configure the runtime to listen for such signals:

<table><tr><td>

`yield` syntax

```python
import signal
import tonio
from tonio.time import interval

def sig_handle():
    with tonio.signal_receiver(
        signal.SIGHUP, 
        signal.SIGUSR1
    ) as sigs:
        for ev in sigs:
            sig = yield ev
            if sig == signal.SIGHUP:
                ...

@tonio.main(
    signals=[signal.SIGHUP, signal.SIGUSR1]
)
def main():
    tonio.spawn(sig_handle())
    ticker = interval(1)
    while True:
        yield ticker.tick()
```
</td><td>

`await` syntax

```python
import signal
import tonio.colored as tonio
from tonio.colored.time import interval

async def sig_handle():
    with tonio.signal_receiver(
        signal.SIGHUP, 
        signal.SIGUSR1
    ) as sigs:
        async for sig in sigs:
            if sig == signal.SIGHUP:
                ...

@tonio.main(
    signals=[signal.SIGHUP, signal.SIGUSR1]
)
async def main():
    tonio.spawn(sig_handle())
    ticker = interval(1)
    while True:
        await ticker.tick()
```
</td></tr></table>

### Exceptions

The `tonio.exceptions` module exposes:

- `CancelledError`: raised inside a coroutine when it gets cancelled
- `TimeoutError`: raised when a timed operation expires
- `WouldBlock`: raised by the `or_raise` and `try_*` variants when the operation cannot complete immediately
- `ResourceBroken`: raised by streams when the underlying transport is unusable

> **Note:** `CancelledError` and `TimeoutError` derive from `BaseException`, so they pass through `except Exception` clauses.

### Testing

TonIO ships with a pytest plugin, which runs tests marked with the `tonio` marker on the runtime:

<table><tr><td>

`yield` syntax

```python
import pytest
import tonio

@pytest.mark.tonio
def test_sleep():
    yield tonio.sleep(0.1)
```
</td><td>

`await` syntax

```python
import pytest
import tonio.colored as tonio

@pytest.mark.tonio
async def test_sleep():
    await tonio.sleep(0.1)
```
</td></tr></table>

The marker can also be applied at module level with `pytestmark = pytest.mark.tonio`, or at class level.

To avoid marking tests entirely, the plugin also provides an *auto* mode, in which every async test gets run on the TonIO runtime. Auto mode can be enabled with the `tonio_mode` option in the pytest configuration:

```toml
[tool.pytest.ini_options]
tonio_mode = 'auto'
```

#### Async fixtures

For asynchronous fixtures where setup and teardown are required, the two syntaxes differ.

##### `await` syntax

Async fixtures involved in TonIO tests run on the runtime. Coroutine fixtures simply return their value, while async generator fixtures can `yield` it and run teardown code after the `yield`:

```python
import pytest
from tonio.colored.net import open_tcp_stream

@pytest.fixture
async def connection():
    stream = await open_tcp_stream(host='127.0.0.1', port=8000)
    yield stream
    stream.close()
```

##### `yield` syntax

Given non-colored TonIO coroutines are indistinguishable from standard pytest generator fixtures, the plugin never runs generator fixtures on the runtime. This is usually not a limitation: since `yield` syntax tests already run as coroutines, simple setup can just happen within the test itself:

```python
import pytest
from tonio.net import open_tcp_stream

def _connect():
    stream = yield open_tcp_stream(host='127.0.0.1', port=8000)
    return stream

@pytest.mark.tonio
def test_conn():
    stream = yield _connect()
    yield stream.send_all(b'ping')
```

When an actual teardown is required, the plugin provides the `tonio_run` fixture, which runs the given coroutine on the runtime:

```python
@pytest.fixture
def connection(tonio_run):
    stream = tonio_run(_connect())

    def _disconnect():
        yield stream.send_all(b'bye')
        stream.close()

    yield stream
    tonio_run(_disconnect())
```

#### Runtime configuration in pytest

The TonIO runtime is always initialised once per test session, with `context` enabled and 2 threads. Runtime options can be customized overriding the session-scoped `tonio_runtime_options` fixture, for example in `conftest.py`:

```python
import pytest

@pytest.fixture(scope='session')
def tonio_runtime_options():
    return {'threads': 4}
```

The runtime object itself is available to tests and fixtures via the session-scoped `tonio_runtime` fixture.

## Libraries built on TonIO

In addition to the patches provided by the [TonIO-Monkey](https://github.com/gi0baro/tonio-monkey) project,
the following libraries target TonIO natively:

- [httpunk](https://github.com/gi0baro/httpunk): a low-level async HTTP library
- [punkreq](https://github.com/gi0baro/punkreq): a high-level async HTTP client
- [punkasgi](https://github.com/gi0baro/punkasgi): an ASGI server built on TonIO

## License

TonIO is released under the BSD License.
