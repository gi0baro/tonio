use pyo3::prelude::*;

mod socket;
mod tls;

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_class::<socket::Socket>()?;
    module.add_class::<tls::TLSStream>()?;

    Ok(())
}
