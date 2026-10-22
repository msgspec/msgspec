import gc
import json
import random
import weakref
from typing import Generic, TypeVar

import pytest

import msgspec
import msgspec.json
import msgspec.msgpack
import msgspec.toml
import msgspec.yaml


@pytest.fixture(params=["json", "msgpack", "convert"])
def decode(request):
    if request.param == "convert":
        return lambda data, typ: msgspec.convert(data, type=typ)
    codec = getattr(msgspec, request.param)
    return lambda data, typ: codec.decode(codec.encode(data), type=typ)


@pytest.mark.parametrize(
    "codec", [msgspec.json, msgspec.msgpack, msgspec.toml, msgspec.yaml]
)
@pytest.mark.parametrize("nfields", [8, 16, 32, 63, 64, 65, 128, 256])
@pytest.mark.parametrize("order", ["ordered", "reverse", "shuffle"])
def test_struct_field_order(codec, nfields, order):
    if codec is msgspec.toml:
        pytest.importorskip("tomli_w")
    elif codec is msgspec.yaml:
        pytest.importorskip("yaml")
    fields = [(f"field_{i}", int) for i in range(nfields)]
    cls = msgspec.defstruct("Record", fields)
    pairs = [(name, i + 1) for i, (name, _) in enumerate(fields)]
    if order == "reverse":
        pairs.reverse()
    elif order == "shuffle":
        random.Random(42).shuffle(pairs)
    out = codec.decode(codec.encode(dict(pairs)), type=cls)
    assert msgspec.structs.astuple(out) == tuple(range(1, nfields + 1))


@pytest.mark.parametrize("nfields", [63, 64, 65, 256])
def test_struct_convert_field_order(decode, nfields):
    cls = msgspec.defstruct("Record", [(f"f{i}", int) for i in range(nfields)])
    data = {f"f{i}": i for i in reversed(range(nfields))}
    assert msgspec.structs.astuple(decode(data, cls)) == tuple(range(nfields))


@pytest.mark.parametrize("key", ["", "é", "a" * 63, "a" * 64, "a" * 65, "é" * 32])
def test_struct_renamed_field_lookup(decode, key):
    cls = msgspec.defstruct(
        "Record", [(f"f{i}", int, -1) for i in range(64)], rename={"f1": key}
    )
    out = decode({"f63": 63, key: 1, "f0": 0}, cls)
    assert out.f0 == 0
    assert out.f1 == 1
    assert out.f63 == 63
    assert out.f2 == -1


@pytest.mark.parametrize(
    "unknown",
    ["f01", "f0\x00", "é" * 32768],
    ids=["prefix", "embedded-nul", "long-unicode"],
)
@pytest.mark.parametrize("forbid", [False, True])
def test_struct_unknown_field_lookup(decode, unknown, forbid):
    cls = msgspec.defstruct(
        "Record",
        [(f"f{i}", int, -1) for i in range(64)],
        forbid_unknown_fields=forbid,
    )
    data = {"f63": 63, unknown: {"nested": [1, None]}, "f0": 0}
    if forbid:
        with pytest.raises(msgspec.ValidationError) as rec:
            decode(data, cls)
        assert str(rec.value) == f"Object contains unknown field `{unknown}`"
    else:
        out = decode(data, cls)
        assert (out.f0, out.f1, out.f63) == (0, -1, 63)


def test_struct_indexed_missing_and_invalid_fields(decode):
    cls = msgspec.defstruct("Record", [(f"f{i}", int) for i in range(64)])
    data = {f"f{i}": i for i in reversed(range(64))}
    data.pop("f0")
    with pytest.raises(msgspec.ValidationError, match="missing required field `f0`"):
        decode(data, cls)
    data["f0"] = "bad"
    with pytest.raises(
        msgspec.ValidationError, match=r"Expected `int`, got `str` - at `\$\.f0`"
    ):
        decode(data, cls)


@pytest.mark.parametrize("codec", [msgspec.json, msgspec.msgpack])
def test_struct_duplicate_field_lookup(codec):
    cls = msgspec.defstruct("Record", [(f"f{i}", int) for i in range(64)])
    pairs = [(f"f{i}", i) for i in reversed(range(64))] + [("f0", 999)]

    def encode_pairs(items):
        if codec is msgspec.json:
            return (
                "{"
                + ",".join(f"{json.dumps(k)}:{json.dumps(v)}" for k, v in items)
                + "}"
            ).encode()
        return (
            b"\xde"
            + len(items).to_bytes(2, "big")
            + b"".join(codec.encode(k) + codec.encode(v) for k, v in items)
        )

    out = codec.decode(encode_pairs(pairs), type=cls)
    assert msgspec.structs.astuple(out) == (999, *range(1, 64))
    pairs = [(k, v) for k, v in pairs if k != "f0"] + [("f1", 999)]
    with pytest.raises(msgspec.ValidationError, match="missing required field `f0`"):
        codec.decode(encode_pairs(pairs), type=cls)
    pairs.append(("f1", "bad"))
    with pytest.raises(
        msgspec.ValidationError, match=r"Expected `int`, got `str` - at `\$\.f1`"
    ):
        codec.decode(encode_pairs(pairs), type=cls)


def test_struct_wide_tagged_union(decode):
    fields = [(f"f{i}", int) for i in range(64)]
    first = msgspec.defstruct("First", fields, tag="first", tag_field="kind")
    second = msgspec.defstruct("Second", fields, tag="second", tag_field="kind")
    data = {f"f{i}": i for i in reversed(range(64))}
    data["kind"] = "second"
    out = decode(data, first | second)
    assert type(out) is second
    assert msgspec.structs.astuple(out) == tuple(range(64))


def test_struct_wide_generic(decode):
    t = TypeVar("t")

    class Record(msgspec.Struct, Generic[t]):
        __annotations__ = {f"f{i}": t for i in range(64)}

    for typ, values in [
        (Record[int], list(range(64))),
        (Record[str], list(map(str, range(64)))),
    ]:
        data = {f"f{i}": values[i] for i in reversed(range(64))}
        assert msgspec.structs.astuple(decode(data, typ)) == tuple(values)


def test_struct_wide_array_like(decode):
    cls = msgspec.defstruct(
        "Record", [(f"f{i}", int) for i in range(64)], array_like=True
    )
    assert msgspec.structs.astuple(decode(list(range(64)), cls)) == tuple(range(64))


def test_struct_field_lookup_lifetime():
    cls = msgspec.defstruct("Record", [(f"f{i}", int, 0) for i in range(64)])
    ref = weakref.ref(cls)
    decoder = msgspec.json.Decoder(cls)
    assert decoder.decode(b"{}") == cls()
    del decoder, cls
    gc.collect()
    assert ref() is None
