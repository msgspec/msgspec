import collections
import gc
from typing import Annotated, Any, Generic, Optional, TypeVar

import pytest

import msgspec

te = pytest.importorskip("typing_extensions")
if not hasattr(te, "NoExtraItems"):
    pytest.skip("requires PEP 728 typed extras", allow_module_level=True)
ReadOnly = te.ReadOnly
TypedDict = te.TypedDict


def convert(data, tp, kind):
    if kind == "json":
        return msgspec.json.decode(msgspec.json.encode(data), type=tp)
    if kind == "msgpack":
        return msgspec.msgpack.decode(msgspec.msgpack.encode(data), type=tp)
    if kind == "mapping":
        return msgspec.convert(collections.UserDict(data), tp)
    return msgspec.convert(data, tp)


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
@pytest.mark.parametrize(
    "annotation,value",
    [
        (Any, {"x": [1, 2]}),
        (int, 4),
        (None, None),
        (Optional[int], None),
        (ReadOnly[int], 4),
        (Annotated[int, msgspec.Meta(ge=2)], 3),
    ],
)
def test_extra_roundtrip(kind, annotation, value):
    class Meta(TypedDict, extra_items=annotation):
        source: str

    data = {"source": "x", "extra": value, "é": value, "": value, "a\x00b": value}
    assert convert(data, Meta, kind) == data


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
@pytest.mark.parametrize(
    "annotation,value",
    [
        (int, "x"),
        (None, 1),
        (ReadOnly[int], "x"),
        (Annotated[int, msgspec.Meta(ge=2)], 1),
    ],
)
def test_extra_validation(kind, annotation, value):
    class Meta(TypedDict, extra_items=annotation):
        source: str

    with pytest.raises(msgspec.ValidationError, match=r"\$\.extra"):
        convert({"source": "x", "extra": value}, Meta, kind)


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
def test_extra_required_and_known_fields(kind):
    class Meta(TypedDict, extra_items=int):
        source: str

    with pytest.raises(
        msgspec.ValidationError, match="missing required field `source`"
    ):
        convert({"extra": 1}, Meta, kind)
    with pytest.raises(msgspec.ValidationError, match="Expected `str`"):
        convert({"source": 1}, Meta, kind)


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
def test_extra_inheritance_and_generic(kind):
    T = TypeVar("T")

    class Base(TypedDict, Generic[T], extra_items=T):
        source: str

    class Child(Base[int]):
        known: bool

    data = {"source": "x", "extra": 1, "known": True}
    assert convert(data, Child, kind) == data
    with pytest.raises(msgspec.ValidationError):
        convert({**data, "extra": "x"}, Child, kind)
    assert convert({"source": "x", "extra": 1}, Base[int], kind) == {
        "source": "x",
        "extra": 1,
    }


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
def test_recursive_extras(kind):
    class Recursive(TypedDict, extra_items="Recursive"):
        value: int

    # Bind the local recursive type in the module just as existing recursive
    # TypedDict tests do, since runtime metadata has no closure scope.
    globals()["Recursive"] = Recursive
    try:
        data = {"value": 1, "child": {"value": 2}}
        assert convert(data, Recursive, kind) == data
    finally:
        del globals()["Recursive"]
        gc.collect()


def test_schema_extra():
    class Meta(TypedDict, extra_items=int):
        source: str

    schema = msgspec.json.schema(Meta)["$defs"]["Meta"]
    assert schema["additionalProperties"] == {"type": "integer"}
    assert msgspec.inspect.type_info(Meta).extra_items == msgspec.inspect.IntType()


def test_duplicate_json_keys_and_required_count():
    class Meta(TypedDict, extra_items=int):
        source: str
        other: str

    with pytest.raises(msgspec.ValidationError, match="missing required field `other`"):
        msgspec.json.decode(b'{"source":"x","extra":1,"extra":2}', type=Meta)
    assert (
        msgspec.json.decode(
            b'{"source":"x","other":"y","extra":1,"extra":2}', type=Meta
        )["extra"]
        == 2
    )


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
def test_readonly_annotated_and_closed_child(kind):
    class Base(TypedDict, extra_items=Annotated[ReadOnly[int], msgspec.Meta(ge=2)]):
        source: str

    data = {"source": "x", "extra": 2}
    assert convert(data, Base, kind) == data
    with pytest.raises(msgspec.ValidationError):
        convert({"source": "x", "extra": 1}, Base, kind)

    class Child(Base, closed=True):
        pass

    # Preserve main's existing behavior for closed types, handled in #1307.
    assert convert(data, Child, kind) == {"source": "x"}


def test_schema_extra_component_reference():
    import jsonschema

    class Item(msgspec.Struct):
        value: int

    class Meta(TypedDict, extra_items=Item):
        source: str

    schema = msgspec.json.schema(Meta)
    assert "Item" in schema["$defs"]
    jsonschema.validate({"source": "x", "extra": {"value": 1}}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"source": "x", "extra": {"value": "x"}}, schema)


def test_recursive_extra_schema():
    class Recursive(TypedDict, extra_items="Recursive"):
        value: int

    globals()["Recursive"] = Recursive
    try:
        schema = msgspec.json.schema(Recursive)
        assert schema["$defs"]["Recursive"]["additionalProperties"] == {
            "$ref": "#/$defs/Recursive"
        }
    finally:
        del globals()["Recursive"]


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
def test_optional_extras_and_nested_validation_path(kind):
    class Meta(TypedDict, total=False, extra_items=list[int]):
        source: str

    assert convert({}, Meta, kind) == {}
    assert convert({"extra": [1]}, Meta, kind) == {"extra": [1]}
    with pytest.raises(msgspec.ValidationError, match=r"\$\.extra\[1\]"):
        convert({"extra": [1, "x"]}, Meta, kind)


@pytest.mark.parametrize("kind", ["json", "msgpack", "dict", "mapping"])
def test_declared_extra_type_can_be_overridden(kind):
    class Base(TypedDict, extra_items=ReadOnly[int | str]):
        source: str

    class Child(Base, extra_items=int):
        pass

    assert convert({"source": "x", "extra": 1}, Child, kind) == {
        "source": "x",
        "extra": 1,
    }
    with pytest.raises(msgspec.ValidationError):
        convert({"source": "x", "extra": "x"}, Child, kind)


def test_mapping_key_error_and_duplicate_keys():
    class Meta(TypedDict, extra_items=int):
        source: str
        other: str

    class Mapping:
        def keys(self):
            return ["source", "source", "extra"]

        def __getitem__(self, key):
            return "x" if key == "source" else 1

    with pytest.raises(msgspec.ValidationError, match="missing required field `other`"):
        msgspec.convert(Mapping(), Meta)

    class BadKeys(Mapping):
        def keys(self):
            raise ValueError("keys error")

    with pytest.raises(ValueError, match="keys error"):
        msgspec.convert(BadKeys(), Meta)


def test_failed_extra_type_does_not_poison_cache():
    class Meta(TypedDict, extra_items=42):
        value: int

    for _ in range(3):
        with pytest.raises(TypeError, match="not supported"):
            msgspec.json.Decoder(Meta)
        assert not hasattr(Meta, "__msgspec_cache__")
    gc.collect()
