use pyo3::{prelude::*, sync::PyOnceLock};

static SOCKET: PyOnceLock<Py<PyAny>> = PyOnceLock::new();

fn socket(py: Python<'_>) -> PyResult<&Bound<'_, PyAny>> {
    Ok(SOCKET
        .get_or_try_init(py, || py.import("socket").map(Into::into))?
        .bind(py))
}

pub(crate) fn sock(py: Python) -> PyResult<Bound<PyAny>> {
    socket(py)?.getattr(pyo3::intern!(py, "socket"))
}

pub(crate) fn copy_context(py: Python) -> Py<PyAny> {
    let ctx = unsafe {
        let ptr = pyo3::ffi::PyContext_CopyCurrent();
        Bound::from_owned_ptr(py, ptr)
    };
    ctx.unbind()
}

// macro_rules! run_in_ctx0 {
//     ($py:expr, $ctx:expr, $cb:expr) => {
//         unsafe {
//             pyo3::ffi::PyContext_Enter($ctx);
//             let ptr = pyo3::ffi::compat::PyObject_CallNoArgs($cb);
//             pyo3::ffi::PyContext_Exit($ctx);
//             Bound::from_owned_ptr_or_err($py, ptr)
//         }
//     };
// }

// macro_rules! run_in_ctx1 {
//     ($py:expr, $ctx:expr, $cb:expr, $arg:expr) => {
//         unsafe {
//             pyo3::ffi::PyContext_Enter($ctx);
//             let ptr = pyo3::ffi::PyObject_CallOneArg($cb, $arg);
//             pyo3::ffi::PyContext_Exit($ctx);
//             Bound::from_owned_ptr_or_err($py, ptr)
//         }
//     };
// }

// macro_rules! run_in_ctx {
//     ($py:expr, $ctx:expr, $cb:expr, $args:expr) => {
//         unsafe {
//             pyo3::ffi::PyContext_Enter($ctx);
//             let ptr = pyo3::ffi::PyObject_CallObject($cb, $args);
//             pyo3::ffi::PyContext_Exit($ctx);
//             Bound::from_owned_ptr_or_err($py, ptr)
//         }
//     };
// }

// pub(crate) use run_in_ctx;
// pub(crate) use run_in_ctx0;
// pub(crate) use run_in_ctx1;
