use pyo3::prelude::*;

use crate::{
    events::{Suspension, SuspensionData, Waiter},
    runtime::{Runtime, RuntimeCBHandlerState},
};

pub trait Handle {
    fn run(&self, py: Python, runtime: Py<Runtime>, state: &mut RuntimeCBHandlerState);
    // fn cancelled(&self) -> bool {
    //     false
    // }
}

pub(crate) type BoxedHandle = Box<dyn Handle + Send>;

pub(crate) struct PyGenHandle {
    pub parent: Option<SuspensionData>,
    pub coro: Py<PyAny>,
    pub value: Py<PyAny>,
}

impl PyGenHandle {
    pub fn new(py: Python, coro: Py<PyAny>) -> Self {
        Self {
            parent: None,
            coro,
            value: py.None(),
        }
    }

    fn clone_ref(&self, py: Python) -> Self {
        PyGenHandle {
            parent: self.parent.clone(),
            coro: self.coro.clone_ref(py),
            value: self.value.clone_ref(py),
        }
    }

    fn call(&self, py: Python, runtime: Py<Runtime>) {
        // println!("coro iteration step {:?}", self.coro.bind(py));
        unsafe {
            let mut ret = std::ptr::null_mut::<pyo3::ffi::PyObject>();
            let result = pyo3::ffi::PyIter_Send(self.coro.as_ptr(), self.value.as_ptr(), &raw mut ret);

            match result {
                pyo3::ffi::PySendResult::PYGEN_NEXT => {
                    // println!("PYGEN_NEXT {:?}", self.coro.bind(py));
                    // if it's just a `yield`, reschedule
                    if ret == py.None().as_ptr() {
                        // reschedule
                        runtime.get().add_handle(Box::new(self.clone_ref(py)));
                        return;
                    }

                    // if it's a generator, schedule it to the loop, keeping track of where we came from
                    if pyo3::ffi::PyGen_Check(ret) != 0 {
                        let coro = Bound::from_owned_ptr(py, ret);
                        let parent = Suspension::from_pygen(py, self, None);
                        let next = PyGenHandle {
                            parent: Some((parent, 0)),
                            coro: coro.unbind(),
                            value: py.None(),
                        };
                        runtime.get().add_handle(Box::new(next));
                        return;
                    }

                    // otherwise, can only be a waiter
                    if let Ok(waiter) = Bound::from_owned_ptr(py, ret).extract::<Py<Waiter>>() {
                        // println!("PYGEN_NEXT regwait {:?}", self.coro.bind(py));
                        Waiter::register_pygen(waiter, py, runtime.clone_ref(py), self);
                        return;
                    }

                    // if we get here, we should raise/throw an error somehow
                    println!("GOING TO PANIC {:?}", Bound::from_owned_ptr(py, ret));
                    panic!()
                }
                pyo3::ffi::PySendResult::PYGEN_RETURN => {
                    // println!("PYGEN_RETURN {:?}", self.coro.bind(py));
                    if let Some((suspension, idx)) = &self.parent {
                        let obj = Bound::from_owned_ptr(py, ret);
                        // println!("WAKE FROM PYGEN_RETURN {:?}", obj);
                        suspension.resume(py, runtime.get(), obj.unbind(), *idx);
                    }
                }
                pyo3::ffi::PySendResult::PYGEN_ERROR => {
                    // println!("PYGEN_ERR {:?}", self.coro.bind(py));
                    let err = pyo3::PyErr::fetch(py);
                    if let Some((suspension, _idx)) = &self.parent {
                        // println!("WAKE FROM PYGEN_ERROR {:?}", self.coro.bind(py));
                        suspension.error(py, runtime.get(), err);
                    } else {
                        // TODO: we should raise to the runtime somehow
                        println!("UNHANDLED PYGEN_ERROR {err:?}");
                        err.display(py);
                    }
                    // println!("PYGEN_ERR {:?}", Bound::from_owned_ptr(py, ret));
                    // panic!()
                }
            }
        }
    }
}

impl Handle for PyGenHandle {
    fn run(&self, py: Python, runtime: Py<Runtime>, _state: &mut crate::runtime::RuntimeCBHandlerState) {
        self.call(py, runtime);
    }
}

pub(crate) struct PyGenThrower {
    pub parent: Option<SuspensionData>,
    pub coro: Py<PyAny>,
    pub value: Py<PyAny>,
}

impl Handle for PyGenThrower {
    fn run(&self, py: Python, runtime: Py<Runtime>, _state: &mut RuntimeCBHandlerState) {
        let throw_method = pyo3::intern!(py, "throw");

        unsafe {
            println!("GOING TO THROW {:?} {}", self.coro.bind(py), self.parent.is_some());
            let ret =
                pyo3::ffi::PyObject_CallMethodOneArg(self.coro.as_ptr(), throw_method.as_ptr(), self.value.as_ptr());
            let res = Bound::from_owned_ptr_or_err(py, ret);
            if let Some((suspension, idx)) = &self.parent {
                match res {
                    Ok(val) => suspension.resume(py, runtime.get(), val.unbind(), *idx),
                    Err(err) if err.is_instance_of::<pyo3::exceptions::PyStopIteration>(py) => {
                        let value = err.value(py).getattr(pyo3::intern!(py, "value")).unwrap().unbind();
                        suspension.resume(py, runtime.get(), value, *idx);
                    }
                    Err(err) => suspension.error(py, runtime.get(), err),
                }
                return;
            }
            if let Err(err) = res {
                println!("UNHANDLED THROW {:?}", self.coro.bind(py));
                err.print(py);
            }
        }
    }
}

// pub(crate) struct PyGenCtxHandle {
//     pub parent: Option<SuspensionData>,
//     pub coro: Py<PyAny>,
//     pub value: Py<PyAny>,
//     pub ctx: Py<PyAny>,
// }

pub(crate) struct PyAsyncGenHandle {
    pub parent: Option<SuspensionData>,
    pub coro: Py<PyAny>,
    pub value: Py<PyAny>,
}

impl PyAsyncGenHandle {
    pub fn new(py: Python, coro: Py<PyAny>) -> Self {
        Self {
            parent: None,
            coro,
            value: py.None(),
        }
    }

    fn clone_ref(&self, py: Python) -> Self {
        PyAsyncGenHandle {
            parent: self.parent.clone(),
            coro: self.coro.clone_ref(py),
            value: self.value.clone_ref(py),
        }
    }

    fn call(&self, py: Python, runtime: Py<Runtime>) {
        // println!("async coro iteration step {:?}", self.coro);

        unsafe {
            let mut ret = std::ptr::null_mut::<pyo3::ffi::PyObject>();
            let result = pyo3::ffi::PyIter_Send(self.coro.as_ptr(), self.value.as_ptr(), &raw mut ret);

            match result {
                pyo3::ffi::PySendResult::PYGEN_NEXT => {
                    // println!("PYGEN_NEXT");

                    // if it's just a `yield`, reschedule
                    if ret == py.None().as_ptr() {
                        // println!("GOT NONE");
                        // reschedule
                        runtime.get().add_handle(Box::new(self.clone_ref(py)));
                        return;
                    }

                    // if it's a generator, schedule it to the loop, keeping track of where we came from
                    if pyo3::ffi::PyAsyncGen_CheckExact(ret) != 0 {
                        // println!("GOT ASYNCGEN");
                        let coro = Bound::from_owned_ptr(py, ret);
                        let parent = Suspension::from_pyasyncgen(py, self, None);
                        let next = PyAsyncGenHandle {
                            parent: Some((parent, 0)),
                            coro: coro.unbind(),
                            value: py.None(),
                        };
                        runtime.get().add_handle(Box::new(next));
                        return;
                    }

                    // otherwise, can only be a waiter
                    if let Ok(waiter) = Bound::from_owned_ptr(py, ret).extract::<Py<Waiter>>() {
                        Waiter::register_pyasyncgen(waiter, py, runtime.clone_ref(py), self);
                        return;
                    }

                    // if we get here, we should raise/throw an error somehow
                    panic!()
                }
                pyo3::ffi::PySendResult::PYGEN_RETURN => {
                    // println!("PYGEN_RETURN");
                    if let Some((suspension, idx)) = &self.parent {
                        let obj = Bound::from_owned_ptr(py, ret);
                        // println!("WAKE FROM PYGEN_RETURN {obj:?}");
                        suspension.resume(py, runtime.get(), obj.unbind(), *idx);
                    }
                }
                pyo3::ffi::PySendResult::PYGEN_ERROR => {
                    // we should raise somehow
                    // println!("PYGEN_ERR {ret:?}");
                    let err = pyo3::PyErr::fetch(py);
                    // println!("LAST ERR {err:?}");
                    err.display(py);
                    // println!("PYGEN_ERR {:?}", Bound::from_owned_ptr(py, ret));
                    // panic!()
                }
            }
        }
    }
}

impl Handle for PyAsyncGenHandle {
    fn run(&self, py: Python, runtime: Py<Runtime>, _state: &mut RuntimeCBHandlerState) {
        self.call(py, runtime);
    }
}
