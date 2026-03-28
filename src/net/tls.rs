use pyo3::prelude::*;
use std::sync::atomic;

#[repr(u8)]
enum TLSStreamState {
    Init = 0,
    Handshake = 1,
    Ready = 2,
    Broken = 3,
    Closed = 4,
}

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub(crate) struct TLSStream {
    state: atomic::AtomicU8,
}

#[pymethods]
impl TLSStream {
    #[new]
    #[pyo3(signature = (*_args, **_kwargs))]
    fn new(_args: &Bound<'_, PyAny>, _kwargs: Option<&Bound<'_, PyAny>>) -> Self {
        Self {
            state: (TLSStreamState::Ready as u8).into(),
        }
    }

    fn _handshake_pre(&self) -> PyResult<()> {
        if self
            .state
            .compare_exchange(
                TLSStreamState::Init as u8,
                TLSStreamState::Handshake as u8,
                atomic::Ordering::Release,
                atomic::Ordering::Relaxed,
            )
            .is_err()
        {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Invalid TLSStream state change",
            ));
        }
        Ok(())
    }

    fn _handshake_post(&self) -> PyResult<()> {
        if self
            .state
            .compare_exchange(
                TLSStreamState::Handshake as u8,
                TLSStreamState::Ready as u8,
                atomic::Ordering::Release,
                atomic::Ordering::Relaxed,
            )
            .is_err()
        {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Invalid TLSStream state change",
            ));
        }
        Ok(())
    }

    fn _set_broken(&self) {
        self.state
            .store(TLSStreamState::Broken as u8, atomic::Ordering::Release);
    }

    fn _set_closed(&self) {
        self.state
            .store(TLSStreamState::Closed as u8, atomic::Ordering::Release);
    }

    #[getter(_state)]
    fn _get_state(&self) -> u8 {
        self.state.load(atomic::Ordering::Acquire)
    }

    fn _check_ready(&self) -> PyResult<()> {
        match self.state.load(atomic::Ordering::Acquire) {
            val if val == TLSStreamState::Ready as u8 => Ok(()),
            _ => Err(pyo3::exceptions::PyRuntimeError::new_err("TLSStream in bad state")),
        }
    }
}
