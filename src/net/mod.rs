use pyo3::prelude::*;

mod socket;

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<socket::Socket>()?;

    Ok(())
}
