#ifndef MSGSPEC_PCRE2_REGEX_H
#define MSGSPEC_PCRE2_REGEX_H

static int
ms_python_pattern_match(PyObject *regex, PyObject *obj) {
    PyObject *res = PyObject_CallMethod(regex, "search", "O", obj);
    if (res == NULL) return -1;
    int out = res != Py_None;
    Py_DECREF(res);
    return out;
}

#ifndef Py_GIL_DISABLED
#include "pcre2_matcher_api.h"

typedef struct {
    PyObject_HEAD
    PyObject *pattern;
    PyObject *native;
    PyObject *capsule;
    PyObject *provider;
    PyObject *reference;
    PyObject *error_type;
    int (*match)(PyObject *, PyObject *);
} PatternMatcher;

static int
PatternMatcher_traverse(PatternMatcher *self, visitproc visit, void *arg) {
    Py_VISIT(self->pattern);
    Py_VISIT(self->native);
    Py_VISIT(self->capsule);
    Py_VISIT(self->provider);
    Py_VISIT(self->reference);
    Py_VISIT(self->error_type);
    return 0;
}

static int
PatternMatcher_clear(PatternMatcher *self) {
    self->match = NULL;
    Py_CLEAR(self->pattern);
    Py_CLEAR(self->native);
    Py_CLEAR(self->capsule);
    Py_CLEAR(self->provider);
    Py_CLEAR(self->reference);
    Py_CLEAR(self->error_type);
    return 0;
}

static void
PatternMatcher_dealloc(PatternMatcher *self) {
    PyObject_GC_UnTrack(self);
    PatternMatcher_clear(self);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyMemberDef PatternMatcher_members[] = {
    {"pattern", T_OBJECT, offsetof(PatternMatcher, pattern), READONLY, NULL},
    {NULL},
};

static PyTypeObject PatternMatcher_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "msgspec._PatternMatcher",
    .tp_basicsize = sizeof(PatternMatcher),
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,
    .tp_traverse = (traverseproc)PatternMatcher_traverse,
    .tp_clear = (inquiry)PatternMatcher_clear,
    .tp_dealloc = (destructor)PatternMatcher_dealloc,
    .tp_members = PatternMatcher_members,
};

/* Error codes from the external package's PCRE2 10.x interface. Only known
 * accelerator limits permit a return to the already compiled Python regex. */
static bool
ms_external_pattern_fallback(PyObject *error_type) {
    PyObject *type, *value, *traceback;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    bool fallback = false;
    if (type != NULL && PyErr_GivenExceptionMatches(type, error_type) && value != NULL) {
        PyObject *code = PyObject_GetAttrString(value, "code");
        if (code != NULL && PyLong_CheckExact(code)) {
            long rc = PyLong_AsLong(code);
            if (!PyErr_Occurred()) {
                fallback = rc == -46 || rc == -47 || rc == -53 || rc == -63;
            }
        }
        Py_XDECREF(code);
    }
    PyErr_Clear();
    if (fallback) {
        Py_XDECREF(type);
        Py_XDECREF(value);
        Py_XDECREF(traceback);
    }
    else {
        PyErr_Restore(type, value, traceback);
    }
    return fallback;
}

/* Prepare the optional provider before creating a native matcher. */
static PyObject *
ms_pattern_compile(PyObject *pattern, PyObject *reference) {
    MsgspecState *st = msgspec_get_global_state();
    PyObject *prepared = PyObject_CallOneArg(st->prepare_pattern, pattern);
    if (prepared == NULL) return NULL;
    if (prepared == Py_None) {
        Py_DECREF(prepared);
        return Py_NewRef(reference);
    }
    if (!PyTuple_CheckExact(prepared) || PyTuple_GET_SIZE(prepared) != 2) {
        Py_DECREF(prepared);
        PyErr_SetString(PyExc_RuntimeError, "Invalid pattern preparation result");
        return NULL;
    }
    PyObject *provider = Py_NewRef(PyTuple_GET_ITEM(prepared, 0));
    PyObject *capsule = Py_NewRef(PyTuple_GET_ITEM(prepared, 1));
    Py_DECREF(prepared);
    PyObject *compiled = NULL, *native = NULL, *error_type = NULL, *out = NULL;
    Pcre2MatcherAPI *api = PyCapsule_GetPointer(capsule, PCRE2_MATCHER_API_NAME);
    if (api == NULL) goto done;
    if (api->abi_version != PCRE2_MATCHER_API_VERSION || api->struct_size != sizeof(Pcre2MatcherAPI) ||
        api->matcher_type == NULL || !PyType_Check(api->matcher_type) ||
        api->new_matcher == NULL || api->search == NULL) {
        PyErr_SetString(PyExc_ImportError, "Incompatible pcre2 matcher API");
        goto done;
    }
    error_type = PyObject_GetAttrString(provider, "LibraryError");
    if (error_type == NULL) goto done;
    if (!PyExceptionClass_Check(error_type)) {
        PyErr_SetString(PyExc_ImportError, "Invalid pcre2 LibraryError type");
        goto done;
    }
    PyObject *result = PyObject_CallFunctionObjArgs(st->compile_pattern, pattern, error_type, NULL);
    if (result == NULL) goto done;
    if (result == Py_None) {
        Py_DECREF(result);
        out = Py_NewRef(reference);
        goto done;
    }
    if (!PyTuple_CheckExact(result) || PyTuple_GET_SIZE(result) != 1) {
        Py_DECREF(result);
        PyErr_SetString(PyExc_RuntimeError, "Invalid pattern compilation result");
        goto done;
    }
    compiled = Py_NewRef(PyTuple_GET_ITEM(result, 0));
    Py_DECREF(result);
    native = api->new_matcher(api->matcher_type, compiled, provider);
    if (native == NULL) {
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "pcre2 matcher creation failed without an exception");
        goto done;
    }
    if (PyErr_Occurred()) goto done;
    if (Py_TYPE(native) != api->matcher_type) {
        PyErr_SetString(PyExc_RuntimeError, "Invalid pcre2 matcher type");
        goto done;
    }
    PatternMatcher *matcher = (PatternMatcher *)PatternMatcher_Type.tp_alloc(&PatternMatcher_Type, 0);
    if (matcher == NULL) goto done;
    matcher->pattern = Py_NewRef(pattern);
    matcher->native = Py_NewRef(native);
    matcher->capsule = Py_NewRef(capsule);
    matcher->provider = Py_NewRef(provider);
    matcher->reference = Py_NewRef(reference);
    matcher->error_type = Py_NewRef(error_type);
    matcher->match = api->search;
    out = (PyObject *)matcher;
done:
    Py_XDECREF(native);
    Py_XDECREF(compiled);
    Py_XDECREF(error_type);
    Py_DECREF(capsule);
    Py_DECREF(provider);
    return out;
}

static int
ms_pattern_match(PyObject *regex, PyObject *obj) {
    if (Py_TYPE(regex) == &PatternMatcher_Type) {
        PatternMatcher *self = (PatternMatcher *)regex;
        if (!PyUnicode_CheckExact(obj) || !PyUnicode_IS_ASCII(obj))
            return ms_python_pattern_match(self->reference, obj);
        int out = self->match(self->native, obj);
        if (out < 0) {
            if (!PyErr_Occurred())
                PyErr_SetString(PyExc_RuntimeError, "pcre2 search failed without an exception");
            if (ms_external_pattern_fallback(self->error_type))
                return ms_python_pattern_match(self->reference, obj);
            return -1;
        }
        if (PyErr_Occurred()) return -1;
        if (out > 1) {
            PyErr_SetString(PyExc_RuntimeError, "Invalid pcre2 search result");
            return -1;
        }
        return out;
    }
    return ms_python_pattern_match(regex, obj);
}

static int
ms_pattern_init(void) {
    return PyType_Ready(&PatternMatcher_Type);
}
#else
static PyObject *
ms_pattern_compile(PyObject *pattern, PyObject *reference) {
    return Py_NewRef(reference);
}

static int
ms_pattern_match(PyObject *regex, PyObject *obj) {
    return ms_python_pattern_match(regex, obj);
}

static int
ms_pattern_init(void) {
    return 0;
}
#endif
#endif
