# TonIO

TonIO is a multi-threaded async runtime for free-threaded Python, built in Rust on top of the [mio crate](https://github.com/tokio-rs/mio), and inspired by [tinyio](https://github.com/patrick-kidger/tinyio), [trio](https://github.com/python-trio/trio) and [tokio](https://github.com/tokio-rs/tokio).

> **Warning**: TonIO is currently a work in progress and in alpha state. The APIs are subtle to breaking changes.

> **Note:** TonIO is available on free-threaded Python and Unix systems only.

TonIO supports both using `yield` and the more canonical `async/await` notations, with the latter being available as part of the `tonio.colored` module. Following code snippets show both the usages.

> **Warning:** despite the fact TonIO supports `async` and `await` notations, it's not compatible with any `asyncio` object like futures and tasks.

## In a nutshell

<table><tr><td>

`yield` syntax

```python
import tonio

def wait_and_add(x: int) -> int:
    yield tonio.sleep(1)
    return x + 1

def foo():
    four, five = yield tonio.spawn(
        wait_and_add(3), 
        wait_and_add(4)
    )
    return four, five

out = tonio.run(foo())
assert out == (4, 5)
```
</td><td>

`await` syntax

```python
import tonio.colored as tonio

async def wait_and_add(x: int) -> int:
    await tonio.sleep(1)
    return x + 1

async def foo():
    four, five = await tonio.spawn(
        wait_and_add(3), 
        wait_and_add(4)
    )
    return four, five

out = tonio.run(foo())
assert out == (4, 5)
```
</td></tr></table>

## Usage

### Entrypoint

Every TonIO program consist of an entrypoint, which should be passed to the `run` method:

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
    print("Hellow world")

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

Coroutines passed to `spawn` get schedule onto the runtime immediately. Using `yield` or `await` on the return value of `spawn` just waits for the coroutines to complete and retreive the results.

#### Blocking tasks

TonIO provides the `spawn_blocking` method to schedule blocking operations onto the runtime:

<table><tr><td>

`yield` syntax

```python
import tonio

def read_file(path):
    with open(file, "r") as f:
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
    with open(file, "r") as f:
        return f.read()

@tonio.main
async def main():
    file_data = await tonio.spawn_blocking(
        read_file, 
        "sometext.txt"
    )
```
</td></tr></table>

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
        scope.spawn(_slow_push(values, 0.1))
        scope.spawn(_slow_push(values, 2))
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
        scope.spawn(_slow_push(values, 0.1))
        scope.spawn(_slow_push(values, 2))
        await tonio.sleep(0.2)
        scope.cancel()
    assert len(values) == 1
```
</td></tr></table>

When you `yield` on the scope, it will wait for all the spawned coroutines to end. If the scope was canceled, then all the pending coroutines will be canceled.

> **Note:** as you can see, the *colored* version of `scope` doesn't require to be `await`ed, as it will *yield* when exiting the context.

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
        async with lock():
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
        async with semaphore():
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
        message = offset + 1
        yield sender.send(message)
    yield barrier.wait()

def consumer(receiver):
    while True:
        try:
            message = yield receiver.receive()
            print(message)
        except Exception:
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
        message = offset + 1
        await sender.send(message)
    await barrier.wait()

async def consumer(receiver):
    while True:
        try:
            message = await receiver.receive()
            print(message)
        except Exception:
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
        message = offset + 1
        sender.send(message)
    yield barrier.wait()

def consumer(receiver):
    while True:
        try:
            message = yield receiver.receive()
            print(message)
        except Exception:
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
        message = offset + 1
        sender.send(message)
    await barrier.wait()

async def consumer(receiver):
    while True:
        try:
            message = await receiver.receive()
            print(message)
        except Exception:
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

### Network module

Network primitives are exposed under the `tonio.net` module.

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
        yield sock.send("message")
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
        await sock.send("message")
```
</td></tr></table>

## License

TonIO is released under the BSD License.
