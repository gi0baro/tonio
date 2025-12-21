use pyo3::prelude::*;
use std::sync::OnceLock;

mod blocking;
mod errors;
mod events;
mod handles;
mod io;
mod net;
mod py;
mod runtime;
mod scope;
mod sync;
mod time;

static RUNTIME: pyo3::sync::PyOnceLock<Py<runtime::Runtime>> = pyo3::sync::PyOnceLock::new();

pub(crate) fn get_lib_version() -> &'static str {
    static LIB_VERSION: OnceLock<String> = OnceLock::new();

    LIB_VERSION.get_or_init(|| {
        let version = env!("CARGO_PKG_VERSION");
        version.replace("-alpha", "a").replace("-beta", "b")
    })
}

#[pyfunction]
fn get_runtime(py: Python<'_>) -> PyResult<&Py<runtime::Runtime>> {
    RUNTIME
        .get(py)
        .ok_or_else(|| errors::RuntimeNotInitializedError::new_err(()))
}

#[pyfunction]
fn set_runtime(py: Python<'_>, runtime: Py<runtime::Runtime>) -> PyResult<()> {
    RUNTIME
        .set(py, runtime)
        .map_err(|_| errors::RuntimeAlreadyInitializedError::new_err(()))
}

#[pymodule(gil_used = false)]
fn _tonio(module: &Bound<PyModule>) -> PyResult<()> {
    module.add("__version__", get_lib_version())?;
    module.add_function(pyo3::wrap_pyfunction!(get_runtime, module)?)?;
    module.add_function(pyo3::wrap_pyfunction!(set_runtime, module)?)?;

    errors::init_pymodule(module)?;
    events::init_pymodule(module)?;
    net::init_pymodule(module)?;
    runtime::init_pymodule(module)?;
    scope::init_pymodule(module)?;
    sync::init_pymodule(module)?;

    Ok(())
}
