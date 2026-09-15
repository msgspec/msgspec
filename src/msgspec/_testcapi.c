#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "msgspec.h"

static const Msgspec_CAPI_v1 *capi = NULL;
static PyObject *absent = NULL;

static PyObject *
testcapi_capabilities(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args))
{
    return PyLong_FromUnsignedLongLong(capi->capabilities);
}

static PyObject *
testcapi_prepare(PyObject *Py_UNUSED(self), PyObject *cls)
{
    PyObject *builder = NULL;
    int status = capi->struct_builder_prepare(cls, &builder);
    if (status == MSGSPEC_CAPI_OK) return builder;
    if (status == MSGSPEC_CAPI_UNSUPPORTED) Py_RETURN_NONE;
    return NULL;
}

static PyObject *
testcapi_build(PyObject *Py_UNUSED(self), PyObject *args)
{
    PyObject *builder;
    PyObject *items;
    if (!PyArg_ParseTuple(args, "OO!:build", &builder, &PyTuple_Type, &items)) {
        return NULL;
    }

    Py_ssize_t nslots = PyTuple_GET_SIZE(items);
    PyObject **values = PyMem_Calloc((size_t)nslots, sizeof(PyObject *));
    if (values == NULL && nslots != 0) return PyErr_NoMemory();

    for (Py_ssize_t i = 0; i < nslots; i++) {
        PyObject *item = PyTuple_GET_ITEM(items, i);
        if (item != absent) values[i] = Py_NewRef(item);
    }

    PyObject *out = capi->struct_builder_build_owned(builder, values, nslots);
    PyMem_Free(values);
    return out;
}

static PyMethodDef methods[] = {
    {"capabilities", testcapi_capabilities, METH_NOARGS, NULL},
    {"prepare", testcapi_prepare, METH_O, NULL},
    {"build", testcapi_build, METH_VARARGS, NULL},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "msgspec._testcapi",
    .m_size = -1,
    .m_methods = methods,
};

PyMODINIT_FUNC
PyInit__testcapi(void)
{
    capi = Msgspec_ImportCAPI_v1();
    if (capi == NULL) return NULL;

    PyObject *mod = PyModule_Create(&module);
    if (mod == NULL) return NULL;

    absent = PyCapsule_New((void *)&absent, "msgspec._testcapi.ABSENT", NULL);
    if (absent == NULL) {
        Py_DECREF(mod);
        return NULL;
    }
    if (PyModule_AddObjectRef(mod, "ABSENT", absent) < 0) {
        Py_CLEAR(absent);
        Py_DECREF(mod);
        return NULL;
    }
    return mod;
}
