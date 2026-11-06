#ifndef PCRE2_MATCHER_API_H
#define PCRE2_MATCHER_API_H

#include <Python.h>
#include <stddef.h>

#define PCRE2_MATCHER_API_NAME "pcre2._cy._MATCHER_API_v1"
#define PCRE2_MATCHER_API_VERSION 1

/* Obtain this table from the named capsule in pcre2._cy. Check abi_version,
 * struct_size and all pointers before use. The table and matcher_type are
 * borrowed: retain the provider module and capsule while using either.
 * Do not modify the table or use it across interpreters.
 *
 * All calls require the GIL and non-NULL arguments. Free-threaded Python
 * builds are unsupported, including when their GIL is enabled at runtime.
 * new_matcher returns a new owned reference, or NULL with an exception.
 * Pass matcher_type from this table, a compiled pcre2.Pattern, and the
 * provider module. The matcher retains the provider and compiled code;
 * later changes to the Pattern do not replace that compiled-code snapshot.
 * Patterns with a callout callback are unsupported.
 *
 * search scans the whole subject, like Pattern.search(subject), without
 * returning captures or a Match object. It returns 1 for a match, 0 for no
 * match, or -1 with a Python exception. It accepts the same string and
 * bytes-like subject types as Pattern.search. Release matchers with DECREF.
 */
typedef struct {
    unsigned int abi_version;
    size_t struct_size;
    PyTypeObject *matcher_type;
    PyObject *(*new_matcher)(
        PyTypeObject *matcher_type, PyObject *pattern, PyObject *provider);
    int (*search)(PyObject *matcher, PyObject *subject);
} Pcre2MatcherAPI;

#endif
