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

## License

TonIO is released under the BSD License.
