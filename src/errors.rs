use pyo3::{
    create_exception,
    exceptions::{PyBaseException, PyException, PyRuntimeError},
    prelude::*,
};

create_exception!(_tonio, CancelledError, PyBaseException, "CancelledError");
create_exception!(
    _tonio,
    RuntimeAlreadyInitializedError,
    PyRuntimeError,
    "RuntimeAlreadyInitializedError"
);
create_exception!(
    _tonio,
    RuntimeNotInitializedError,
    PyRuntimeError,
    "RuntimeNotInitializedError"
);
create_exception!(_tonio, TimeoutError, PyBaseException, "TimeoutError");
create_exception!(_tonio, WouldBlock, PyException, "WouldBlock");

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add("CancelledError", module.py().get_type::<CancelledError>())?;
    module.add(
        "RuntimeAlreadyInitializedError",
        module.py().get_type::<RuntimeAlreadyInitializedError>(),
    )?;
    module.add(
        "RuntimeNotInitializedError",
        module.py().get_type::<RuntimeNotInitializedError>(),
    )?;
    module.add("TimeoutError", module.py().get_type::<TimeoutError>())?;
    module.add("WouldBlock", module.py().get_type::<WouldBlock>())?;

    Ok(())
}
