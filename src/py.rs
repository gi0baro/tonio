use pyo3::{prelude::*, sync::PyOnceLock};

#[cfg(unix)]
static OS: PyOnceLock<Py<PyAny>> = PyOnceLock::new();
#[cfg(Py_GIL_DISABLED)]
static SYS: PyOnceLock<Py<PyAny>> = PyOnceLock::new();
static THREADING: PyOnceLock<Py<PyAny>> = PyOnceLock::new();

#[cfg(unix)]
fn os(py: Python<'_>) -> PyResult<&Bound<'_, PyAny>> {
    Ok(OS.get_or_try_init(py, || py.import("os").map(Into::into))?.bind(py))
}

#[cfg(Py_GIL_DISABLED)]
fn sys(py: Python<'_>) -> PyResult<&Bound<'_, PyAny>> {
    Ok(SYS.get_or_try_init(py, || py.import("sys").map(Into::into))?.bind(py))
}

fn threading(py: Python<'_>) -> PyResult<&Bound<'_, PyAny>> {
    Ok(THREADING
        .get_or_try_init(py, || py.import("threading").map(Into::into))?
        .bind(py))
}

#[cfg(unix)]
pub(crate) fn os_get_blocking(py: Python, fd: i32) -> PyResult<bool> {
    os(py)?
        .call_method1(pyo3::intern!(py, "get_blocking"), (fd,))?
        .extract::<bool>()
}

#[cfg(unix)]
pub(crate) fn os_set_blocking(py: Python, fd: i32, val: bool) -> PyResult<()> {
    os(py)?
        .call_method1(pyo3::intern!(py, "set_blocking"), (fd, val))
        .map(|_| ())
}

#[cfg(Py_GIL_DISABLED)]
pub(crate) fn sys_gil(py: Python) -> PyResult<bool> {
    sys(py)?
        .call_method0(pyo3::intern!(py, "_is_gil_enabled"))?
        .extract::<bool>()
}

pub(crate) fn thread_ident(py: Python) -> PyResult<u64> {
    threading(py)?
        .call_method0(pyo3::intern!(py, "get_ident"))?
        .extract::<u64>()
}
