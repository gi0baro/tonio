use pyo3::prelude::*;

use crate::{
    events::{Suspension, SuspensionData, SuspensionTarget, Waiter},
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
        Self {
            parent: self.parent.clone(),
            coro: self.coro.clone_ref(py),
            value: self.value.clone_ref(py),
        }
    }

    fn call(&self, py: Python, runtime: Py<Runtime>) {
        unsafe {
            let mut ret = std::ptr::null_mut::<pyo3::ffi::PyObject>();
            let result = pyo3::ffi::PyIter_Send(self.coro.as_ptr(), self.value.as_ptr(), &raw mut ret);

            match result {
                pyo3::ffi::PySendResult::PYGEN_NEXT => {
                    // if it's just a `yield`, reschedule
                    if ret == py.None().as_ptr() {
                        runtime.get().add_handle(Box::new(self.clone_ref(py)));
                        return;
                    }

                    // if it's a generator, schedule it to the loop, keeping track of where we came from
                    if pyo3::ffi::PyGen_Check(ret) != 0 {
                        let coro = Bound::from_owned_ptr(py, ret);
                        let parent = Suspension::from_pygen(
                            SuspensionTarget::Gen(self.coro.clone_ref(py)),
                            self.parent.clone(),
                            None,
                            None,
                        );
                        let next = Self {
                            parent: Some((parent, 0)),
                            coro: coro.unbind(),
                            value: py.None(),
                        };
                        runtime.get().add_handle(Box::new(next));
                        return;
                    }

                    // otherwise, can only be a waiter
                    if let Ok(waiter) = Bound::from_owned_ptr(py, ret).extract::<Py<Waiter>>() {
                        Waiter::register_pygen(
                            waiter,
                            py,
                            runtime.clone_ref(py),
                            SuspensionTarget::Gen(self.coro.clone_ref(py)),
                            self.parent.clone(),
                        );
                        return;
                    }

                    // if we get here, we can't continue
                    panic!(
                        "Got unsupported value {:?} from gen iteration",
                        Bound::from_owned_ptr(py, ret)
                    );
                }
                pyo3::ffi::PySendResult::PYGEN_RETURN => {
                    if let Some((suspension, idx)) = &self.parent {
                        let obj = Bound::from_owned_ptr(py, ret);
                        suspension.resume(py, runtime.get(), obj.unbind(), *idx);
                    }
                }
                pyo3::ffi::PySendResult::PYGEN_ERROR => {
                    let err = pyo3::PyErr::fetch(py);
                    if let Some((suspension, _idx)) = &self.parent {
                        suspension.error(py, runtime.get(), err);
                    } else {
                        println!("UNHANDLED PYGEN_ERROR {:?}", self.coro.bind(py));
                        err.display(py);
                    }
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

pub(crate) struct PyGenCtxHandle {
    pub parent: Option<SuspensionData>,
    pub coro: Py<PyAny>,
    pub ctx: Py<PyAny>,
    pub value: Py<PyAny>,
}

impl PyGenCtxHandle {
    pub fn new(py: Python, coro: Py<PyAny>, ctx: Py<PyAny>) -> Self {
        Self {
            parent: None,
            coro,
            ctx,
            value: py.None(),
        }
    }

    fn clone_ref(&self, py: Python) -> Self {
        Self {
            parent: self.parent.clone(),
            coro: self.coro.clone_ref(py),
            ctx: self.ctx.clone_ref(py),
            value: self.value.clone_ref(py),
        }
    }

    fn call(&self, py: Python, runtime: Py<Runtime>) {
        unsafe {
            let mut ret = std::ptr::null_mut::<pyo3::ffi::PyObject>();
            let ctx = self.ctx.as_ptr();

            pyo3::ffi::PyContext_Enter(ctx);
            let result = pyo3::ffi::PyIter_Send(self.coro.as_ptr(), self.value.as_ptr(), &raw mut ret);
            pyo3::ffi::PyContext_Exit(ctx);

            match result {
                pyo3::ffi::PySendResult::PYGEN_NEXT => {
                    // if it's just a `yield`, reschedule
                    if ret == py.None().as_ptr() {
                        runtime.get().add_handle(Box::new(self.clone_ref(py)));
                        return;
                    }

                    // if it's a generator, schedule it to the loop, keeping track of where we came from
                    if pyo3::ffi::PyGen_Check(ret) != 0 {
                        let coro = Bound::from_owned_ptr(py, ret);
                        let parent = Suspension::from_pygen(
                            SuspensionTarget::GenCtx((self.coro.clone_ref(py), self.ctx.clone_ref(py))),
                            self.parent.clone(),
                            None,
                            None,
                        );
                        let next = Self {
                            parent: Some((parent, 0)),
                            coro: coro.unbind(),
                            ctx: self.ctx.clone_ref(py),
                            value: py.None(),
                        };
                        runtime.get().add_handle(Box::new(next));
                        return;
                    }

                    // otherwise, can only be a waiter
                    if let Ok(waiter) = Bound::from_owned_ptr(py, ret).extract::<Py<Waiter>>() {
                        Waiter::register_pygen(
                            waiter,
                            py,
                            runtime.clone_ref(py),
                            SuspensionTarget::GenCtx((self.coro.clone_ref(py), self.ctx.clone_ref(py))),
                            self.parent.clone(),
                        );
                        return;
                    }

                    // if we get here, we can't continue
                    panic!(
                        "Got unsupported value {:?} from gen iteration",
                        Bound::from_owned_ptr(py, ret)
                    );
                }
                pyo3::ffi::PySendResult::PYGEN_RETURN => {
                    if let Some((suspension, idx)) = &self.parent {
                        let obj = Bound::from_owned_ptr(py, ret);
                        suspension.resume(py, runtime.get(), obj.unbind(), *idx);
                    }
                }
                pyo3::ffi::PySendResult::PYGEN_ERROR => {
                    let err = pyo3::PyErr::fetch(py);
                    if let Some((suspension, _idx)) = &self.parent {
                        suspension.error(py, runtime.get(), err);
                    } else {
                        println!("UNHANDLED PYGEN_ERROR {:?}", self.coro.bind(py));
                        err.display(py);
                    }
                }
            }
        }
    }
}

impl Handle for PyGenCtxHandle {
    fn run(&self, py: Python, runtime: Py<Runtime>, _state: &mut crate::runtime::RuntimeCBHandlerState) {
        self.call(py, runtime);
    }
}

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
        Self {
            parent: self.parent.clone(),
            coro: self.coro.clone_ref(py),
            value: self.value.clone_ref(py),
        }
    }

    fn call(&self, py: Python, runtime: Py<Runtime>) {
        unsafe {
            let mut ret = std::ptr::null_mut::<pyo3::ffi::PyObject>();
            let result = pyo3::ffi::PyIter_Send(self.coro.as_ptr(), self.value.as_ptr(), &raw mut ret);

            match result {
                pyo3::ffi::PySendResult::PYGEN_NEXT => {
                    // if it's just a `yield`, reschedule
                    if ret == py.None().as_ptr() {
                        runtime.get().add_handle(Box::new(self.clone_ref(py)));
                        return;
                    }

                    // TODO: unneeded?
                    // if it's a generator, schedule it to the loop, keeping track of where we came from
                    // if pyo3::ffi::PyAsyncGen_CheckExact(ret) != 0 {
                    //     println!("GOT ASYNCGEN");
                    //     let coro = Bound::from_owned_ptr(py, ret);
                    //     let parent = Suspension::from_pygen(SuspensionTarget::AsyncGen(self.coro.clone_ref(py)), self.parent.clone(), None);
                    //     let next = Self {
                    //         parent: Some((parent, 0)),
                    //         coro: coro.unbind(),
                    //         value: py.None(),
                    //     };
                    //     runtime.get().add_handle(Box::new(next));
                    //     return;
                    // }

                    // otherwise, can only be a waiter
                    if let Ok(waiter) = Bound::from_owned_ptr(py, ret).extract::<Py<Waiter>>() {
                        Waiter::register_pygen(
                            waiter,
                            py,
                            runtime.clone_ref(py),
                            SuspensionTarget::AsyncGen(self.coro.clone_ref(py)),
                            self.parent.clone(),
                        );
                        return;
                    }

                    panic!(
                        "Got unsupported value {:?} from asyncgen iteration",
                        Bound::from_owned_ptr(py, ret)
                    );
                }
                pyo3::ffi::PySendResult::PYGEN_RETURN => {
                    if let Some((suspension, idx)) = &self.parent {
                        let obj = Bound::from_owned_ptr(py, ret);
                        suspension.resume(py, runtime.get(), obj.unbind(), *idx);
                    }
                }
                pyo3::ffi::PySendResult::PYGEN_ERROR => {
                    let err = pyo3::PyErr::fetch(py);
                    if let Some((suspension, _idx)) = &self.parent {
                        suspension.error(py, runtime.get(), err);
                    } else {
                        println!("UNHANDLED PYGEN_ERROR {:?}", self.coro.bind(py));
                        err.display(py);
                    }
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

pub(crate) struct PyAsyncGenCtxHandle {
    pub parent: Option<SuspensionData>,
    pub coro: Py<PyAny>,
    pub ctx: Py<PyAny>,
    pub value: Py<PyAny>,
}

impl PyAsyncGenCtxHandle {
    pub fn new(py: Python, coro: Py<PyAny>, ctx: Py<PyAny>) -> Self {
        Self {
            parent: None,
            coro,
            ctx,
            value: py.None(),
        }
    }

    fn clone_ref(&self, py: Python) -> Self {
        Self {
            parent: self.parent.clone(),
            coro: self.coro.clone_ref(py),
            ctx: self.ctx.clone_ref(py),
            value: self.value.clone_ref(py),
        }
    }

    fn call(&self, py: Python, runtime: Py<Runtime>) {
        unsafe {
            let mut ret = std::ptr::null_mut::<pyo3::ffi::PyObject>();
            let ctx = self.ctx.as_ptr();

            pyo3::ffi::PyContext_Enter(ctx);
            let result = pyo3::ffi::PyIter_Send(self.coro.as_ptr(), self.value.as_ptr(), &raw mut ret);
            pyo3::ffi::PyContext_Exit(ctx);

            match result {
                pyo3::ffi::PySendResult::PYGEN_NEXT => {
                    // if it's just a `yield`, reschedule
                    if ret == py.None().as_ptr() {
                        runtime.get().add_handle(Box::new(self.clone_ref(py)));
                        return;
                    }

                    // TODO: unneeded?
                    // if it's a generator, schedule it to the loop, keeping track of where we came from
                    // if pyo3::ffi::PyAsyncGen_CheckExact(ret) != 0 {
                    //     println!("GOT ASYNCGEN");
                    //     let coro = Bound::from_owned_ptr(py, ret);
                    //     let parent = Suspension::from_pygen(SuspensionTarget::AsyncGenCtx(self.coro.clone_ref(py)), self.parent.clone(), None);
                    //     let next = Self {
                    //         parent: Some((parent, 0)),
                    //         coro: coro.unbind(),
                    //         ctx: self.ctx.clone_ref(py),
                    //         value: py.None(),
                    //     };
                    //     runtime.get().add_handle(Box::new(next));
                    //     return;
                    // }

                    // otherwise, can only be a waiter
                    if let Ok(waiter) = Bound::from_owned_ptr(py, ret).extract::<Py<Waiter>>() {
                        Waiter::register_pygen(
                            waiter,
                            py,
                            runtime.clone_ref(py),
                            SuspensionTarget::AsyncGenCtx((self.coro.clone_ref(py), self.ctx.clone_ref(py))),
                            self.parent.clone(),
                        );
                        return;
                    }

                    panic!(
                        "Got unsupported value {:?} from asyncgen iteration",
                        Bound::from_owned_ptr(py, ret)
                    );
                }
                pyo3::ffi::PySendResult::PYGEN_RETURN => {
                    if let Some((suspension, idx)) = &self.parent {
                        let obj = Bound::from_owned_ptr(py, ret);
                        suspension.resume(py, runtime.get(), obj.unbind(), *idx);
                    }
                }
                pyo3::ffi::PySendResult::PYGEN_ERROR => {
                    let err = pyo3::PyErr::fetch(py);
                    if let Some((suspension, _idx)) = &self.parent {
                        suspension.error(py, runtime.get(), err);
                    } else {
                        println!("UNHANDLED PYGEN_ERROR {:?}", self.coro.bind(py));
                        err.display(py);
                    }
                }
            }
        }
    }
}

impl Handle for PyAsyncGenCtxHandle {
    fn run(&self, py: Python, runtime: Py<Runtime>, _state: &mut RuntimeCBHandlerState) {
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
            if let Err(err) = res
                && !err.is_instance_of::<pyo3::exceptions::PyStopIteration>(py)
            {
                println!("UNHANDLED THROW {:?}", self.coro.bind(py));
                err.print(py);
            }
        }
    }
}

pub(crate) struct PyGenCtxThrower {
    pub parent: Option<SuspensionData>,
    pub coro: Py<PyAny>,
    pub ctx: Py<PyAny>,
    pub value: Py<PyAny>,
}

impl Handle for PyGenCtxThrower {
    fn run(&self, py: Python, runtime: Py<Runtime>, _state: &mut RuntimeCBHandlerState) {
        let throw_method = pyo3::intern!(py, "throw");
        let ctx = self.ctx.as_ptr();

        unsafe {
            pyo3::ffi::PyContext_Enter(ctx);
            let ret =
                pyo3::ffi::PyObject_CallMethodOneArg(self.coro.as_ptr(), throw_method.as_ptr(), self.value.as_ptr());
            pyo3::ffi::PyContext_Exit(ctx);

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
            if let Err(err) = res
                && !err.is_instance_of::<pyo3::exceptions::PyStopIteration>(py)
            {
                println!("UNHANDLED THROW {:?}", self.coro.bind(py));
                err.print(py);
            }
        }
    }
}
