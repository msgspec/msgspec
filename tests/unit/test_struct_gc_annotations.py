import copy
import gc
import pickle
import sys
import types
import weakref

import pytest

import msgspec

from .utils import temp_module


class Sentinel:
    pass


def model_source(kind, array_like, *, future=False, has_gc=True):
    options = f"array_like={array_like}, gc={has_gc}"
    if kind == "direct":
        model = f"class Model(msgspec.Struct, {options}):\n    value: int = 1\n"
    elif kind == "inherited":
        model = (
            "class Base(msgspec.Struct):\n    value: int = 1\n"
            f"Model = msgspec.defstruct('Model', [], bases=(Base,), {options})\n"
        )
    else:
        model = (
            "class Grandparent:\n    __slots__ = ()\n    other: int\n"
            "class Mixin(Grandparent):\n    __slots__ = ()\n"
            "Model = msgspec.defstruct('Model', [('value', int, 1)], "
            f"bases=(msgspec.Struct, Mixin), {options})\n"
        )
    return (
        ("from __future__ import annotations\n" if future else "")
        + "import msgspec\n"
        + model
    )


def create_sample(model, operation, array_like):
    if operation == "construct":
        return model(1)
    if operation == "json":
        return msgspec.json.decode(
            b"[1]" if array_like else b'{"value": 1}', type=model
        )
    if operation == "msgpack":
        return msgspec.msgpack.decode(
            msgspec.msgpack.encode([1] if array_like else {"value": 1}), type=model
        )
    if operation == "json-default":
        return msgspec.json.decode(b"[]" if array_like else b"{}", type=model)
    if operation == "msgpack-default":
        return msgspec.msgpack.decode(
            msgspec.msgpack.encode([] if array_like else {}), type=model
        )
    if operation == "convert":
        return msgspec.convert([1] if array_like else {"value": 1}, model)
    if operation == "attributes":
        return msgspec.convert(
            types.SimpleNamespace(value=1), model, from_attributes=True
        )
    if operation == "replace":
        return msgspec.structs.replace(model(2), value=1)
    if operation == "copy":
        return copy.copy(model(1))
    return pickle.loads(pickle.dumps(model(1)))


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Requires deferred annotations")
@pytest.mark.parametrize("kind", ["direct", "inherited", "mixin"])
@pytest.mark.parametrize("array_like", [False, True])
@pytest.mark.parametrize(
    "operation",
    [
        "construct",
        "json",
        "msgpack",
        "json-default",
        "msgpack-default",
        "convert",
        "attributes",
        "replace",
        "copy",
        "pickle",
    ],
)
def test_deferred_annotations_do_not_retain_module_data(kind, array_like, operation):
    def create_module_data():
        with temp_module(model_source(kind, array_like)) as module:
            module.sentinel = Sentinel()
            module.sample = create_sample(module.Model, operation, array_like)
            assert module.sample.value == 1
            return weakref.ref(module.sentinel)

    ref = create_module_data()
    gc.collect()
    assert ref() is None


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Requires deferred annotations")
def test_frozen_nested_struct_roundtrip_does_not_retain_module_data():
    def create_module_data():
        with temp_module("""
            import msgspec

            class Row(msgspec.Struct, frozen=True, array_like=True):
                value: int

            class Snapshot(msgspec.Struct, frozen=True):
                rows: tuple[Row, ...]

            sample = Snapshot((Row(1),))
            encoded = msgspec.json.encode(sample)
            assert msgspec.json.decode(encoded, type=Snapshot) == sample
        """) as module:
            module.sentinel = Sentinel()
            return weakref.ref(module.sentinel)

    ref = create_module_data()
    gc.collect()
    assert ref() is None


@pytest.mark.parametrize("kind", ["direct", "inherited", "mixin"])
def test_stringized_annotations_retain_scalar_untracking(kind):
    with temp_module(model_source(kind, False, future=True)) as module:
        for operation in ["construct", "json", "msgpack", "convert", "replace", "copy"]:
            assert not gc.is_tracked(create_sample(module.Model, operation, False))


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Requires deferred annotations")
@pytest.mark.parametrize("kind", ["direct", "inherited", "mixin"])
def test_explicit_gc_false_still_disables_tracking(kind):
    with temp_module(model_source(kind, False, has_gc=False)) as module:
        for operation in ["construct", "json", "msgpack", "convert", "replace", "copy"]:
            assert not gc.is_tracked(create_sample(module.Model, operation, False))
        # Disabling GC explicitly leaves ownership of any cycles with the caller.
        module.__dict__.clear()


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Requires annotationlib")
def test_deferred_annotation_metadata_is_preserved():
    import annotationlib

    with temp_module(model_source("direct", False)) as module:
        annotate = module.Model.__annotate__
        module.sample = module.Model(1)
        assert module.Model.__annotate__ is annotate
        assert annotationlib.get_annotations(module.Model) == {"value": int}
        assert annotationlib.get_annotations(
            module.Model, format=annotationlib.Format.STRING
        ) == {"value": "int"}
