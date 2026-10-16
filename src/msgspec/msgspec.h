#ifndef MSGSPEC_CAPI_H
#define MSGSPEC_CAPI_H

#include <Python.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * msgspec native C API, ABI major 1.
 *
 * This header exposes no msgspec object layouts. The capsule table is an
 * opaque, versioned capability boundary implemented by msgspec.
 */
#define MSGSPEC_CAPI_CAPSULE_NAME "msgspec._core._C_API_v1"

#define MSGSPEC_CAPI_ABI_MAKE(major, minor) \
    ((((uint32_t)(major)) << 16) | ((uint32_t)(minor) & 0xffffu))
#define MSGSPEC_CAPI_ABI_VERSION MSGSPEC_CAPI_ABI_MAKE(1, 0)
#define MSGSPEC_CAPI_ABI_MAJOR(v) ((uint32_t)(v) >> 16)
#define MSGSPEC_CAPI_ABI_MINOR(v) ((uint32_t)(v) & 0xffffu)

#define MSGSPEC_CAPI_OK          0
#define MSGSPEC_CAPI_UNSUPPORTED 1
#define MSGSPEC_CAPI_ERROR      -1

#define MSGSPEC_CAPI_CAP_STRUCT_BUILD_OWNED_V1 (1ull << 0)

/*
 * struct_builder_prepare:
 * - OK returns a new opaque Python token in builder_out.
 * - UNSUPPORTED is a normal fallback signal and sets no exception.
 * - ERROR sets an exception.
 *
 * struct_builder_build_owned:
 * - values contains exactly nslots declared-field positions.
 * - each non-NULL entry is one owned reference transferred by the call.
 * - NULL means absent and carries no ownership.
 * - for a valid builder, all non-NULL entries are consumed on success or
 *   failure. The caller must treat every entry as moved after the call.
 * - success returns a new reference; failure returns NULL with an exception.
 */
typedef struct Msgspec_CAPI_v1 {
    uint32_t abi_version;
    uint32_t struct_size;
    uint64_t capabilities;

    int (*struct_builder_prepare)(PyObject *cls, PyObject **builder_out);
    PyObject *(*struct_builder_build_owned)(
        PyObject *builder,
        PyObject **values,
        Py_ssize_t nslots
    );
} Msgspec_CAPI_v1;

#define MSGSPEC_CAPI_V1_STRUCT_BUILD_OWNED_MIN_SIZE \
    (offsetof(Msgspec_CAPI_v1, struct_builder_build_owned) + \
     sizeof(((Msgspec_CAPI_v1 *)0)->struct_builder_build_owned))

static inline const Msgspec_CAPI_v1 *
Msgspec_ImportCAPI_v1(void)
{
    const Msgspec_CAPI_v1 *api = (const Msgspec_CAPI_v1 *)PyCapsule_Import(
        MSGSPEC_CAPI_CAPSULE_NAME, 0
    );
    if (api == NULL) return NULL;
    if (MSGSPEC_CAPI_ABI_MAJOR(api->abi_version) != 1 ||
        api->struct_size < MSGSPEC_CAPI_V1_STRUCT_BUILD_OWNED_MIN_SIZE ||
        !(api->capabilities & MSGSPEC_CAPI_CAP_STRUCT_BUILD_OWNED_V1)) {
        PyErr_SetString(PyExc_ImportError, "incompatible msgspec C API v1");
        return NULL;
    }
    return api;
}

#ifdef __cplusplus
}
#endif

#endif /* MSGSPEC_CAPI_H */
