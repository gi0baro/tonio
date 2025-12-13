use pyo3::prelude::*;
// use std::os::raw::c_int;

// use crate::py::sock;
// use crate::handles::Handle;
// use crate::events::Event;

#[pyclass(frozen, subclass, module = "tonio._tonio")]
pub(crate) struct Socket {
    fd: usize,
    #[pyo3(get)]
    _sock: Py<PyAny>,
}

// impl Socket {
//     pub fn from_fd(py: Python, fd: usize, family: i32, r#type: socket2::Type, proto: usize) -> Py<Self> {
//         Py::new(
//             py,
//             Self {
//                 fd,
//                 _sock: sock(py)
//                     .unwrap()
//                     .call1::<(i32, c_int, usize, usize)>((family, r#type.into(), proto, fd))
//                     .unwrap()
//                     .unbind(),
//             },
//         )
//         .unwrap()
//     }
// }

#[pymethods]
impl Socket {
    #[new]
    fn new(py: Python, stdlib_sock: Py<PyAny>) -> PyResult<Self> {
        let fd: usize = stdlib_sock.call_method0(py, pyo3::intern!(py, "fileno"))?.extract(py)?;
        stdlib_sock.call_method1(py, pyo3::intern!(py, "setblocking"), (false,))?;
        Ok(Self { fd, _sock: stdlib_sock })
    }
}

// pub(crate) struct SocketHandle {
//     event: Py<Event>,
// }

// impl Handle for SocketHandle {
//     fn run(&self, py: Python, _runtime: Py<crate::runtime::Runtime>, _state: &mut crate::runtime::RuntimeCBHandlerState) {
//         self.event.get().set(py);
//     }
// }
