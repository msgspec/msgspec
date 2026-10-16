#ifndef PCRE2_MATCHER_API_H
#define PCRE2_MATCHER_API_H

#include <Python.h>

#define PCRE2_MATCHER_API_NAME "pcre2._cy._MATCHER_API_v1"
#define PCRE2_MATCHER_API_VERSION 1

/* Calls require the GIL. Keep the provider module and capsule alive.
 * matcher_type is borrowed from the provider. new_matcher returns an owned
 * matcher with a snapshot of compiled code; callouts are unsupported in v1.
 * search scans the whole subject and returns 1/0, or -1 with an exception. */
typedef struct {
    unsigned int abi_version;
    size_t struct_size;
    PyTypeObject *matcher_type;
    PyObject *(*new_matcher)(PyTypeObject *, PyObject *, PyObject *);
    int (*search)(PyObject *, PyObject *);
} Pcre2MatcherAPI;

#endif
