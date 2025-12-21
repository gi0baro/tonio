# TonIO

TonIO is a multi-threaded async runtime for free-threaded Python, built in Rust on top of the [mio crate](https://github.com/tokio-rs/mio), and inspired by [tinyio](https://github.com/patrick-kidger/tinyio) and [trio](https://github.com/python-trio/trio).

> **Warning**: TonIO is currently a work in progress and very pre-alpha state. The APIs are subtle to breaking changes.

> **Note:** TonIO is available on free-threaded Python and on Unix systems only.

## In a nutshell

```python
import tonio

def wait_and_add(x: int) -> int:
    yield tonio.sleep(1)
    return x + 1

def foo():
    four, five = yield tonio.spawn(wait_and_add(3), wait_and_add(4))
    return four, five

out = tonio.run(foo())
assert out == (4, 5)
```

## Usage

### Entrypoint

Every TonIO program consist of an entrypoint, which should be passed to the `run` method:

```python
import tonio

def main():
    yield
    print("Hello world")

tonio.run(main())
```

TonIO also provides a `main` decorator, thus we can rewrite the previous example as:

```python
import tonio

@tonio.main
def main():
    yield
    print("Hello world")

main()
```

#### Runtime options

Both `run` and `main` accept options, specifically:

| option name | description | default |
| --- | --- | --- |
| `context` | enable `contextvars` usage in coroutines | `False` |
| `threads` | Number of runtime threads | # of CPU cores |
| `threads_blocking` | Maximum number of blocking threads | 128 |
| `threads_blocking_timeout` | Idle timeout for blocking threads (in seconds) | 30 |

### Events

The core object in TonIO is `Event`. It's basically a wrapper around an atomic boolean flag, initialised with `False`. `Event` provides the following methods:

- `is_set()`: return the value of the flag
- `set()`: set the flag to `True`
- `clear()`: set the flag to `False`
- `wait(timeout=None)`: returns a coroutine you can `yield` on that unblocks when the flag is set to `True` or the timeout expires. Timeout is seconds.
- `__call__(timeout=None)`: same of `wait`, but returns a coroutine you can `await` on.

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

### Spawning tasks

TonIO provides the `spawn` method to schedule new coroutines onto the runtime:

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

Coroutines passed to `spawn` get schedule onto the runtime immediately. Using `yield` on the return value of `spawn` just waits for the coroutines to complete and retreive the results.

#### Blocking tasks

TonIO provides the `spawn_blocking` method to schedule blocking operations onto the runtime:

```python
import tonio

def read_file(path):
    with open(file, "r") as f:
        return f.read()

@tonio.main
def main():
    file_data = yield tonio.spawn_blocking(read_file, "sometext.txt")
```

### Scopes and cancellations

TonIO provides a `scope` context, that lets you cancel work spawned within it:

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

When you `yield` on the scope, it will wait for all the spawned coroutines to end. If the scope was canceled, then all the pending coroutines will be canceled.

> **Note:** the *colored* version of scope, doesn't require to be `await`ed, as it will *yield* on exit.

### Time-related functions

- `tonio.time.time()`: a function returning the runtime's clock
- `tonio.time.sleep(delay)`: a coroutine you can `yield` on to sleep (delay is in seconds)
- `tonio.time.timeout(coro, timeout)`: a coroutine you can `yield` on returning a tuple `(output, success)`. If the coroutine succeeds in the given time then the pair `(output, True)` is returned. Otherwise this will return `(None, False)`.

> **Note**: `time.sleep` is also exported to the main `tonio` module.

### Synchronization primitives

Synchronization primitives are exposed in the `tonio.sync` module.

#### Lock

Implements a classic mutex, or a non-reentrant, single-owner lock for coroutines:

```python
import tonio
import tonio.sync

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
    
    lock = tonio.sync.Lock()
    yield tonio.spawn(*[_count(lock) for _ in range(10)])
```

#### Semaphore

A semaphore for coroutines:

```python
import tonio
import tonio.sync

@tonio.main
def main():
    # counter can't go above 2
    counter = 0

    def _count(lock):
        nonlocal counter
        with (yield lock()):
            counter += 1
            yield
            counter -= 1
    
    lock = tonio.sync.Semaphore(2)
    yield tonio.spawn(*[_count(lock) for _ in range(10)])
```

#### Barrier

A barrier for coroutines:

```python
import tonio
import tonio.sync

@tonio.main
def main():
    barrier = tonio.sync.Barrier(3)
    count = 0

    def _start_at_3():
        nonlocal count
        count += 1
        i = yield barrier.wait()
        assert count == 3
        return i

    yield tonio.spawn(*[_start_at_3() for _ in range(3)])
```

#### Channels

Multi-producer multi-consumer channels for inter-coroutine communication.    
The `tonio.sync.channel` module provides both a `channel` and `unbounded` constructors:

```python
import tonio
import tonio.sync
import tonio.sync.channel as channel

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
    barrier = tonio.sync.Barrier(3)
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

### Network module

Network primitives are exposed under the `tonio.net` module.

#### Low-level sockets

The `tonio.net.socket` module provides TonIO's basic low-level networking API.    
Generally, the API exposed by this module mirrors the standard library `socket` module.

TonIO socket objects are overall very similar to the standard library socket objects, with the main difference being that blocking methods become coroutines.

```python
import tonio
from toio.net import socket

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

### Using async/await notation

All TonIO primitives ships with an `async/await` syntax compatible variant under the `tonio.colored` module.

> **Warning:** despite the fact TonIO supports `async` and `await` notations, it's not compatible with any `asyncio` object like futures and tasks.

```python
import tonio.colored as tonio

@tonio.main
async def main():
    event = tonio.Event()

    async def setter():
        await tonio.sleep(1)
        event.set()

    tonio.spawn(setter())
    await event()
```

The only major syntax difference between the `yield` and `async/await` notation is around `with` blocks:

```python
from tonio.sync import Lock

lock = Lock()

def yield_lock():
    with (yield lock()):
        # do something

async def async_lock():
    async with lock:
        # do something
```

Also, the `colored` module provides the additional `yield_now` awaitable function, a quick way to define a suspension point:

```python
import tonio.colored as tonio

@tonio.main
async def main():
    await tonio.yield_now()
    print("hello world")
```

## License

TonIO is released under the BSD License.
