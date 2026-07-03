# fmt: off
from __future__ import annotations
import array
from collections.abc import Callable
import decimal
import pickle
from typing import Annotated, Any, Final, Literal

import msgspec
from typing_extensions import assert_type, Buffer


def check___version__() -> None:
    assert_type(msgspec.__version__, str)


def check_exceptions() -> None:
    assert_type(msgspec.MsgspecError, type[msgspec.MsgspecError])
    assert_type(msgspec.EncodeError, type[msgspec.EncodeError])
    assert_type(msgspec.DecodeError, type[msgspec.DecodeError])
    assert_type(msgspec.ValidationError, type[msgspec.ValidationError])


def check_unset() -> None:
    assert_type(msgspec.UNSET, Literal[msgspec.UnsetType.UNSET])
    assert_type(type(msgspec.UNSET), type[msgspec.UnsetType])
    str(msgspec.UNSET)
    pickle.dumps(msgspec.UNSET)


def check_unset_type_lowering(x: int | msgspec.UnsetType) -> None:
    if x is msgspec.UNSET:
        # this is a bug in `pyrefly` https://github.com/facebook/pyrefly/issues/3820:
        assert_type(x, Literal[msgspec.UnsetType.UNSET])  # pyrefly: ignore[assert-type]
    else:
        assert_type(x, int)


def check_unset_type_truthiness_lowering(x: str | msgspec.UnsetType) -> None:
    if x:
        assert_type(x, str)


def check_nodefault() -> None:
    assert_type(msgspec.NODEFAULT, Literal[msgspec._NoDefault.NODEFAULT])
    str(msgspec.NODEFAULT)
    pickle.dumps(msgspec.NODEFAULT)


##########################################################
# Structs                                                #
##########################################################

def check_struct() -> None:
    class Test(msgspec.Struct):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)

    t2 = Test(x=2, y="bar")
    assert_type(t2, Test)
    assert_type(t2.x, int)
    assert_type(t2.y, str)


def check_struct_field() -> None:
    class Test(msgspec.Struct):
        a: int
        b: int = msgspec.field(name="b_field")
        x: int = msgspec.field(default=1)
        y: list[int] = msgspec.field(default_factory=lambda: [1, 2, 3])
        x2: int = msgspec.field(default=1, name="x2_field")
        y2: list[int] = msgspec.field(default_factory=lambda: [1, 2, 3], name="y2_field")

    Test(1, 2)
    Test(1, 2, 3)
    Test(1, 2, 3, [4])
    Test(1, 2, 3, [4], 5)
    Test(1, 2, 3, [4], 5, [6])

    msgspec.field(default=1, default_factory=int)  # type: ignore[call-overload]  # pyright: ignore[reportCallIssue]  # pyrefly: ignore[no-matching-overload]


def check_struct_kw_only() -> None:
    class Test(msgspec.Struct, kw_only=True):
        x: int
        y: str

    t = Test(y="foo", x=1)


def check_struct_kw_only_base_class() -> None:
    class Base(msgspec.Struct, kw_only=True):
        d: bytes
        c: str = "default"

    class Test(Base):
        a: int
        b: list[int] = []

    Test(1, d=b"foo")
    Test(1, [1, 2, 3], d=b"foo", c="test")


def check_struct_kw_only_subclass() -> None:
    class Base(msgspec.Struct):
        d: bytes
        c: str = "default"

    class Test(Base, kw_only=True):
        a: int
        b: list[int] = []

    Test(b"foo", a=1)
    Test(b"foo", "test", a=1, b=[1, 2, 3])


def check_struct_final_fields() -> None:
    """Test that type checkers support `Final` fields for
    dataclass_transform"""
    class Test(msgspec.Struct):
        x: Final[int] = 0
        y: Final = 1

    t = Test(0, 1)
    assert_type(t.x, int)
    assert_type(t.y, Literal[1])

    t2 = Test(x=0, y=1)
    assert_type(t2.x, int)
    assert_type(t2.y, Literal[1])


def check_struct_repr_omit_defaults() -> None:
    class Test(msgspec.Struct, repr_omit_defaults=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_omit_defaults() -> None:
    class Test(msgspec.Struct, omit_defaults=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_forbid_unknown_fields() -> None:
    class Test(msgspec.Struct, forbid_unknown_fields=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_rename() -> None:
    class TestLower(msgspec.Struct, rename="lower"):
        x: int

    class TestUpper(msgspec.Struct, rename="upper"):
        x: int

    class TestCamel(msgspec.Struct, rename="camel"):
        x: int

    class TestPascal(msgspec.Struct, rename="pascal"):
        x: int

    class TestKebab(msgspec.Struct, rename="kebab"):
        x: int

    class TestCallable(msgspec.Struct, rename=lambda x: x.title()):
        x: int

    class TestCallableNone(msgspec.Struct, rename=lambda x: None):
        x: int

    class TestMapping(msgspec.Struct, rename={"x": "X"}):
        x: int

    class TestNone(msgspec.Struct, rename=None):
        x: int

    assert_type(TestLower(1).x, int)
    assert_type(TestUpper(2).x, int)
    assert_type(TestCamel(3).x, int)
    assert_type(TestPascal(4).x, int)
    assert_type(TestCallable(5).x, int)
    assert_type(TestNone(6).x, int)


def check_struct_array_like() -> None:
    class Test(msgspec.Struct, array_like=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_frozen() -> None:
    class Test(msgspec.Struct, frozen=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_eq() -> None:
    class Test(msgspec.Struct, eq=False):
        x: int
        y: str

    t = Test(1, "foo")
    t2 = Test(1, "foo")
    assert_type(t == t2, bool)
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_order() -> None:
    class Test(msgspec.Struct, order=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_gc() -> None:
    class Test(msgspec.Struct, gc=False):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_weakref() -> None:
    class Test(msgspec.Struct, weakref=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_dict() -> None:
    class Test(msgspec.Struct, dict=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_cache_hash() -> None:
    class Test(msgspec.Struct, cache_hash=True):
        x: int
        y: str

    t = Test(1, "foo")
    assert_type(t, Test)
    assert_type(t.x, int)
    assert_type(t.y, str)


def check_struct_tag_tag_field() -> None:
    class Test1(msgspec.Struct, tag=None):
        pass

    class Test2(msgspec.Struct, tag=True):
        pass

    class Test3(msgspec.Struct, tag=False):
        pass

    class Test4(msgspec.Struct, tag="mytag"):
        pass

    class Test5(msgspec.Struct, tag=123):
        pass

    class Test6(msgspec.Struct, tag=str.lower):
        pass

    class Test7(msgspec.Struct, tag=lambda n: len(n)):
        pass

    class Test8(msgspec.Struct, tag_field=None):
        pass

    class Test9(msgspec.Struct, tag_field="type"):
        pass


def check_struct_methods() -> None:
    class Point(msgspec.Struct):
        x: int
        y: int


    a = Point(1, 2)
    b = Point(3, 4)
    assert_type(a == b, bool)
    a.x = a.x + b.y
    repr(a)

    for item in a.__rich_repr__():
        assert_type(item, tuple[str, Any])


def check_struct_attributes() -> None:
    class Point(msgspec.Struct):
        x: int
        y: int

    for field in Point.__struct_fields__:
        assert_type(field, str)

    for field in Point.__match_args__:
        # mypy inferences `field` as `str`,
        # pyright inferences `field` as `Literal['x', 'y']`
        _field_str: str = field

    p = Point(1, 2)

    for field in p.__struct_fields__:
        assert_type(field, str)


def check_struct_config() -> None:
    class Point(msgspec.Struct):
        x: int
        y: int

    config = Point.__struct_config__

    assert_type(config, msgspec.structs.StructConfig)
    assert_type(config.frozen, bool)
    assert_type(config.eq, bool)
    assert_type(config.order, bool)
    assert_type(config.array_like, bool)
    assert_type(config.gc, bool)
    assert_type(config.repr_omit_defaults, bool)
    assert_type(config.omit_defaults, bool)
    assert_type(config.forbid_unknown_fields, bool)
    assert_type(config.weakref, bool)
    assert_type(config.dict, bool)
    assert_type(config.cache_hash, bool)
    assert_type(config.tag, str | int | None)
    assert_type(config.tag_field, str | None)


##########################################################
# defstruct                                              #
##########################################################


def check_defstruct() -> None:
    Test = msgspec.defstruct("Test", ["x", "y"])
    for field in Test.__struct_fields__:
        assert_type(field, str)
    Test(1, y=2)


def check_defstruct_field_types() -> None:
    Test = msgspec.defstruct(
        "Test",
        (
            "x",
            ("a", int),
            ("b", int | None),
            ("c", list[int]),
            ("d", Annotated[int, msgspec.Meta(ge=0)]),
            ("e", Literal["a", "b"]),
            ("f", str, "default"),
        ),
    )


def check_defstruct_bases() -> None:
    class Base(msgspec.Struct):
        pass

    class Mixin:
        pass

    msgspec.defstruct("Test", ["x", "y"], bases=(Mixin, Base))
    msgspec.defstruct("Test2", ["x", "y"], bases=None)


def check_defstruct_namespace() -> None:
    msgspec.defstruct("Test", ["x", "y"], namespace={"classval": 1})
    msgspec.defstruct("Test2", ["x", "y"], namespace=None)


def check_defstruct_module() -> None:
    msgspec.defstruct("Test", ["x", "y"], module="mymod")
    msgspec.defstruct("Test2", ["x", "y"], module=None)


def check_defstruct_config_options() -> None:
    Test = msgspec.defstruct(
        "Test",
        ("x", "y"),
        omit_defaults=True,
        forbid_unknown_fields=True,
        frozen=True,
        order=True,
        eq=True,
        kw_only=True,
        repr_omit_defaults=True,
        array_like=True,
        dict=True,
        weakref=True,
        cache_hash=True,
        gc=False,
        tag="mytag",
        tag_field="mytagfield",
        rename="lower"
    )

##########################################################
# msgspec.structs                                        #
##########################################################

def check_replace() -> None:
    class Test(msgspec.Struct):
        x: int
        y: int
        struct: int

    struct = Test(1, 2, 3)
    assert_type(msgspec.structs.replace(struct), Test)
    assert_type(msgspec.structs.replace(struct, x=1), Test)
    assert_type(msgspec.structs.replace(struct, struct=1), Test)

    msgspec.structs.replace(object(), x=1)  # type: ignore[type-var]  # pyright: ignore[reportArgumentType]  # pyrefly: ignore[bad-specialization]


def check_asdict() -> None:
    class Test(msgspec.Struct):
        x: int
        y: int

    x = Test(1, 2)
    o = msgspec.structs.asdict(x)
    assert_type(o, dict[str, Any])
    assert_type(o["foo"], Any)


def check_astuple() -> None:
    class Test(msgspec.Struct):
        x: int
        y: int

    x = Test(1, 2)
    o = msgspec.structs.astuple(x)
    assert_type(o, tuple[Any, ...])
    assert_type(o[0], Any)


def check_force_setattr() -> None:
    class Point(msgspec.Struct, frozen=True):
        x: int
        y: int

    obj = Point(1, 2)
    msgspec.structs.force_setattr(obj, "x", 3)


def check_fields() -> None:
    class Test(msgspec.Struct):
        x: int
        y: int

    x = Test(1, 2)
    res1 = msgspec.structs.fields(x)
    assert_type(res1, tuple[msgspec.structs.FieldInfo, ...])
    res2 = msgspec.structs.fields(Test)
    assert_type(res2, tuple[msgspec.structs.FieldInfo, ...])

    for field in res1:
        assert_type(field, msgspec.structs.FieldInfo)
        assert_type(field.required, bool)
        assert_type(field.name, str)


##########################################################
# Meta                                                   #
##########################################################

def check_meta_constructor() -> None:
    msgspec.Meta()
    for val in [1, 1.5, None]:
        msgspec.Meta(gt=val)
        msgspec.Meta(ge=val)
        msgspec.Meta(lt=val)
        msgspec.Meta(le=val)
        msgspec.Meta(multiple_of=val)
    for val2 in ["string", None]:
        msgspec.Meta(pattern=val2)
        msgspec.Meta(title=val2)
        msgspec.Meta(description=val2)
    for val3 in [1, None]:
        msgspec.Meta(min_length=val3)
        msgspec.Meta(max_length=val3)
    for val4 in [True, False, None]:
        msgspec.Meta(tz=val4)
    for val5 in [[1, 2, 3], None]:
        msgspec.Meta(examples=val5)
    for val6 in [{"foo": "bar"}, None]:
        msgspec.Meta(extra_json_schema=val6)
        msgspec.Meta(extra=val6)


def check_meta_attributes() -> None:
    c = msgspec.Meta()
    assert_type(c.title, str | None)
    assert_type(c.description, str | None)


def check_meta_equal() -> None:
    c1 = msgspec.Meta()
    c2 = msgspec.Meta()
    assert_type(c1 == c2, bool)


def check_meta_methods() -> None:
    c = msgspec.Meta()
    for field in c.__rich_repr__():
        assert_type(field, tuple[str, Any])


##########################################################
# Raw                                                    #
##########################################################

def check_raw_constructor() -> None:
    r = msgspec.Raw()
    r2 = msgspec.Raw(b"test")
    r3 = msgspec.Raw(bytearray(b"test"))
    r4 = msgspec.Raw(memoryview(b"test"))
    r2 = msgspec.Raw("test")


def check_raw_copy() -> None:
    r = msgspec.Raw()
    r2 = r.copy()
    assert_type(r2, msgspec.Raw)


def check_raw_methods() -> None:
    r1 = msgspec.Raw(b"a")
    r2 = msgspec.Raw(b"b")
    assert_type(r1 == r2, bool)
    memoryview(r1)  # buffer protocol


def check_raw_pass_to_decode() -> None:
    r = msgspec.Raw()
    res = msgspec.json.decode(r)
    res2 = msgspec.msgpack.decode(r)


##########################################################
# MessagePack                                            #
##########################################################

def check_msgpack_Encoder_encode() -> None:
    enc = msgspec.msgpack.Encoder()
    b = enc.encode([1, 2, 3])

    assert_type(b, bytes)


def check_msgpack_Encoder_encode_into() -> None:
    enc = msgspec.msgpack.Encoder()
    buf = bytearray(48)
    enc.encode_into([1, 2, 3], buf)
    enc.encode_into([1, 2, 3], buf, 2)


def check_msgpack_encode() -> None:
    b = msgspec.msgpack.encode([1, 2, 3])

    assert_type(b, bytes)


def check_msgpack_Decoder_decode_any() -> None:
    dec = msgspec.msgpack.Decoder()
    b = msgspec.msgpack.encode([1, 2, 3])
    o = dec.decode(b)

    assert_type(dec, msgspec.msgpack.Decoder[Any])
    assert_type(o, Any)


def check_msgpack_Decoder_decode_typed() -> None:
    dec = msgspec.msgpack.Decoder(list[int])
    b = msgspec.msgpack.encode([1, 2, 3])
    o = dec.decode(b)

    assert_type(dec, msgspec.msgpack.Decoder[list[int]])
    assert_type(o, list[int])


def check_msgpack_Decoder_decode_union() -> None:
    # Pyright doesn't require the annotation, but mypy does until TypeForm
    # is supported. This is mostly checking that no error happens here.
    dec: msgspec.msgpack.Decoder[int | str] = msgspec.msgpack.Decoder(int | str)
    o = dec.decode(b'')
    assert_type(o, int | str)


def check_msgpack_Decoder_decode_type_comment() -> None:
    dec = msgspec.msgpack.Decoder()  # type: msgspec.msgpack.Decoder[list[int]]  # pyright: ignore[reportTypeCommentUsage]
    b = msgspec.msgpack.encode([1, 2, 3])
    o = dec.decode(b)

    # pyrefly does not support type comments:
    assert_type(dec, msgspec.msgpack.Decoder[list[int]])  # pyrefly: ignore[assert-type]
    assert_type(o, list[int])  # pyrefly: ignore[assert-type]


def check_msgpack_decode_any() -> None:
    b = msgspec.msgpack.encode([1, 2, 3])
    o = msgspec.msgpack.decode(b)

    assert_type(o, Any)


def check_msgpack_decode_typed() -> None:
    b = msgspec.msgpack.encode([1, 2, 3])
    o = msgspec.msgpack.decode(b, type=list[int])

    assert_type(o, list[int])


def check_msgpack_decode_from_buffer() -> None:
    msg = msgspec.msgpack.encode([1, 2, 3])
    msgspec.toml.decode(memoryview(msg))


def check_msgpack_decode_typed_union() -> None:
    o: int | str = msgspec.msgpack.decode(b"", type=int | str)
    assert_type(o, int | str)


def check_msgpack_encode_enc_hook() -> None:
    msgspec.msgpack.encode(object(), enc_hook=lambda x: None)


def check_msgpack_Encoder_enc_hook() -> None:
    msgspec.msgpack.Encoder(enc_hook=lambda x: None)


def check_msgpack_order() -> None:
    enc = msgspec.msgpack.Encoder(order=None)
    msgspec.msgpack.Encoder(order='deterministic')
    msgspec.msgpack.Encoder(order='sorted')
    assert_type(enc.order, Literal['deterministic', 'sorted'] | None)

    msgspec.msgpack.encode({"a": 1}, order=None)
    msgspec.msgpack.encode({"a": 1}, order='deterministic')
    msgspec.msgpack.encode({"a": 1}, order='sorted')


def check_msgpack_Encoder_decimal_format() -> None:
    enc = msgspec.msgpack.Encoder(decimal_format="string")
    msgspec.msgpack.Encoder(decimal_format="number")
    msgspec.msgpack.Encoder(decimal_format=lambda x: str(x))
    assert_type(enc.decimal_format, Literal['string', 'number'] | Callable[[decimal.Decimal], Any])



def check_msgpack_Encoder_uuid_format() -> None:
    enc = msgspec.msgpack.Encoder(uuid_format="canonical")
    msgspec.msgpack.Encoder(uuid_format="hex")
    msgspec.msgpack.Encoder(uuid_format="bytes")
    assert_type(enc.uuid_format, Literal['canonical', 'hex', 'bytes'])


def check_msgpack_decode_dec_hook() -> None:
    def dec_hook(typ: type, obj: Any) -> Any:
        return typ(obj)

    msgspec.msgpack.decode(b"test", dec_hook=dec_hook)
    msgspec.msgpack.Decoder(dec_hook=dec_hook)


def check_msgpack_decode_ext_hook() -> None:
    def ext_hook(code: int, data: memoryview) -> Any:
        return pickle.loads(data)

    msgspec.msgpack.decode(b"test", ext_hook=ext_hook)
    msgspec.msgpack.Decoder(ext_hook=ext_hook)


def check_msgpack_Decoder_strict() -> None:
    dec = msgspec.msgpack.Decoder(list[int], strict=False)
    assert_type(dec.strict, bool)


def check_msgpack_decode_strict() -> None:
    out = msgspec.msgpack.decode(b'', type=list[int], strict=False)
    assert_type(out, list[int])


def check_msgpack_Ext() -> None:
    ext = msgspec.msgpack.Ext(1, b"test")
    assert_type(ext.code, int)
    assert_type(ext.data, Buffer)

    assert_type(msgspec.msgpack.Ext(1, bytearray()), msgspec.msgpack.Ext)
    assert_type(msgspec.msgpack.Ext(1, memoryview(b'')), msgspec.msgpack.Ext)
    assert_type(msgspec.msgpack.Ext(1, array.array('i', [1, 2, 3])), msgspec.msgpack.Ext)

    # Non buffers:
    msgspec.msgpack.Ext(1, {})  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]  # pyrefly: ignore[bad-argument-type]


##########################################################
# JSON                                                   #
##########################################################

def check_json_Encoder_encode() -> None:
    enc = msgspec.json.Encoder()
    b = enc.encode([1, 2, 3])

    assert_type(b, bytes)


def check_json_Encoder_encode_lines() -> None:
    enc = msgspec.json.Encoder()
    items = [{"x": 1}, 2]
    b = enc.encode_lines(items)
    b2 = enc.encode_lines(i for i in items)

    assert_type(b, bytes)
    assert_type(b2, bytes)


def check_json_Encoder_encode_into() -> None:
    enc = msgspec.json.Encoder()
    buf = bytearray(48)
    enc.encode_into([1, 2, 3], buf)
    enc.encode_into([1, 2, 3], buf, 2)


def check_json_encode() -> None:
    b = msgspec.json.encode([1, 2, 3])

    assert_type(b, bytes)


def check_json_Decoder_decode_any() -> None:
    dec = msgspec.json.Decoder()
    b = msgspec.json.encode([1, 2, 3])
    o = dec.decode(b)

    assert_type(dec, msgspec.json.Decoder[Any])
    assert_type(o, Any)


def check_json_Decoder_decode_typed() -> None:
    dec = msgspec.json.Decoder(list[int])
    b = msgspec.json.encode([1, 2, 3])
    o = dec.decode(b)

    assert_type(dec, msgspec.json.Decoder[list[int]])
    assert_type(o, list[int])


def check_json_Decoder_decode_type_comment() -> None:
    dec = msgspec.json.Decoder()  # type: msgspec.json.Decoder[list[int]]  # pyright: ignore[reportTypeCommentUsage]
    b = msgspec.json.encode([1, 2, 3])
    o = dec.decode(b)

    # pyrefly does not support type comments:
    assert_type(dec, msgspec.json.Decoder[list[int]])  # pyrefly: ignore[assert-type]
    assert_type(o, list[int])  # pyrefly: ignore[assert-type]


def check_json_Decoder_decode_union() -> None:
    dec: msgspec.json.Decoder[int | str] = msgspec.json.Decoder(int | str)
    o = dec.decode(b'')
    assert_type(o, int | str)


def check_json_Decoder_decode_from_str() -> None:
    dec = msgspec.json.Decoder(list[int])
    o = dec.decode("[1, 2, 3]")
    assert_type(o, list[int])


def check_json_Decoder_decode_lines_any() -> None:
    dec = msgspec.json.Decoder()
    o = dec.decode_lines(b'1\n2\n3')

    assert_type(o, list[Any])


def check_json_Decoder_decode_lines_typed() -> None:
    dec = msgspec.json.Decoder(int)
    o = dec.decode_lines(b'1\n2\n3')
    assert_type(o, list[int])


def check_json_decode_any() -> None:
    b = msgspec.json.encode([1, 2, 3])
    o = msgspec.json.decode(b)

    assert_type(o, Any)


def check_json_decode_typed() -> None:
    b = msgspec.json.encode([1, 2, 3])
    o = msgspec.json.decode(b, type=list[int])

    assert_type(o, list[int])


def check_json_decode_typed_union() -> None:
    o: int | str = msgspec.json.decode(b"", type=int | str)
    assert_type(o, int | str)


def check_json_decode_from_str() -> None:
    msgspec.json.decode("[1, 2, 3]")

    o = msgspec.json.decode("[1, 2, 3]", type=list[int])
    assert_type(o, list[int])


def check_json_decode_from_buffer() -> None:
    msgspec.json.decode(memoryview(b"[1, 2, 3]"))


def check_json_encode_enc_hook() -> None:
    msgspec.json.encode(object(), enc_hook=lambda x: None)


def check_json_Encoder_enc_hook() -> None:
    msgspec.json.Encoder(enc_hook=lambda x: None)


def check_json_order() -> None:
    enc = msgspec.json.Encoder(order=None)
    msgspec.json.Encoder(order='deterministic')
    msgspec.json.Encoder(order='sorted')
    assert_type(enc.order, Literal['deterministic', 'sorted'] | None)

    msgspec.json.encode({"a": 1}, order=None)
    msgspec.json.encode({"a": 1}, order='deterministic')
    msgspec.json.encode({"a": 1}, order='sorted')


def check_json_Encoder_decimal_format() -> None:
    enc = msgspec.json.Encoder(decimal_format="string")
    msgspec.json.Encoder(decimal_format="number")
    msgspec.json.Encoder(decimal_format=lambda x: str(x))
    assert_type(enc.decimal_format, Literal['string', 'number'] | Callable[[decimal.Decimal], Any])


def check_json_Encoder_uuid_format() -> None:
    enc = msgspec.json.Encoder(uuid_format="canonical")
    msgspec.json.Encoder(uuid_format="hex")
    assert_type(enc.uuid_format, Literal['canonical', 'hex'])


def check_json_decode_dec_hook() -> None:
    def dec_hook(typ: type, obj: Any) -> Any:
        return typ(obj)

    msgspec.json.decode(b"test", dec_hook=dec_hook)
    msgspec.json.Decoder(dec_hook=dec_hook)


def check_json_Decoder_float_hook() -> None:
    msgspec.json.Decoder(float_hook=None)
    msgspec.json.Decoder(float_hook=float)
    dec = msgspec.json.Decoder(float_hook=decimal.Decimal)
    if dec.float_hook is not None:
        assert_type(dec.float_hook("1.5"), Any)


def check_json_Decoder_strict() -> None:
    dec = msgspec.json.Decoder(list[int], strict=False)
    assert_type(dec.strict, bool)


def check_json_decode_strict() -> None:
    out = msgspec.json.decode(b'', type=list[int], strict=False)
    assert_type(out, list[int])


def check_json_format() -> None:
    assert_type(msgspec.json.format(b"test"), bytes)
    assert_type(msgspec.json.format(b"test", indent=4), bytes)
    assert_type(msgspec.json.format("test"), str)
    assert_type(msgspec.json.format("test", indent=4), str)

##########################################################
# YAML                                                   #
##########################################################

def check_yaml_encode() -> None:
    b = msgspec.yaml.encode([1, 2, 3])

    assert_type(b, bytes)


def check_yaml_decode_any() -> None:
    assert_type(msgspec.yaml.decode(b"[1, 2, 3]"), Any)
    assert_type(msgspec.yaml.decode("[1, 2, 3]"), Any)
    assert_type(msgspec.yaml.decode(bytearray()), Any)
    assert_type(msgspec.yaml.decode(memoryview(b'')), Any)

    # Not buffers:
    msgspec.yaml.decode([])  # type: ignore[call-overload]  # pyright: ignore[reportArgumentType]  # pyrefly: ignore[bad-argument-type]


def check_yaml_decode_typed() -> None:
    assert_type(msgspec.yaml.decode(b"[1, 2, 3]", type=list[int]), list[int])
    assert_type(msgspec.yaml.decode("[]", type=list[str]), list[str])


def check_yaml_decode_typed_union() -> None:
    o: int | str = msgspec.yaml.decode(b"1", type=int | str)
    assert_type(o, int | str)


def check_yaml_decode_from_str() -> None:
    msgspec.yaml.decode("[1, 2, 3]")
    o = msgspec.yaml.decode("[1, 2, 3]", type=list[int])
    assert_type(o, list[int])


def check_yaml_encode_enc_hook() -> None:
    assert_type(msgspec.yaml.encode(object(), enc_hook=lambda x: None), bytes)


def check_yaml_encode_order() -> None:
    assert_type(msgspec.yaml.encode(object(), order=None), bytes)
    assert_type(msgspec.yaml.encode(object(), order="deterministic"), bytes)
    assert_type(msgspec.yaml.encode(object(), order="sorted"), bytes)


def check_yaml_decode_dec_hook() -> None:
    def dec_hook(typ: type, obj: Any) -> Any:
        return typ(obj)

    assert_type(msgspec.yaml.decode(b"test", dec_hook=dec_hook), Any)


def check_yaml_decode_strict() -> None:
    out = msgspec.yaml.decode(b'', type=list[int], strict=False)
    assert_type(out, list[int])


##########################################################
# TOML                                                   #
##########################################################

def check_toml_encode() -> None:
    b = msgspec.toml.encode({"a": 1})

    assert_type(b, bytes)


def check_toml_decode_any() -> None:
    o = msgspec.toml.decode(b"a = 1")
    assert_type(o, Any)


def check_toml_decode_typed() -> None:
    o = msgspec.toml.decode(b"a = 1", type=dict[str, int])
    assert_type(o, dict[str, int])


def check_toml_decode_from_str() -> None:
    msgspec.toml.decode("a = 1")
    o = msgspec.toml.decode("a = 1", type=dict[str, int])
    assert_type(o, dict[str, int])


def check_toml_decode_from_buffer() -> None:
    assert_type(msgspec.toml.decode(bytearray()), Any)
    assert_type(msgspec.toml.decode(memoryview(b"a = 1")), Any)

    # Non buffers:
    msgspec.toml.decode({})  # type: ignore[call-overload]  # pyright: ignore[reportArgumentType]  # pyrefly: ignore[bad-argument-type]


def check_toml_encode_enc_hook() -> None:
    assert_type(msgspec.toml.encode(object(), enc_hook=lambda x: None), bytes)


def check_toml_encode_order() -> None:
    assert_type(msgspec.toml.encode(object(), order=None), bytes)
    assert_type(msgspec.toml.encode(object(), order="deterministic"), bytes)
    assert_type(msgspec.toml.encode(object(), order="sorted"), bytes)


def check_toml_decode_dec_hook() -> None:
    def dec_hook(typ: type, obj: Any) -> Any:
        return typ(obj)

    assert_type(msgspec.toml.decode(b"a = 1", dec_hook=dec_hook), Any)


def check_toml_decode_strict() -> None:
    out = msgspec.toml.decode(b'', type=list[int], strict=False)
    assert_type(out, list[int])


##########################################################
# msgspec.inspect                                        #
##########################################################

def check_inspect_type_info() -> None:
    assert_type(msgspec.inspect.type_info(list[int]), msgspec.inspect.Type)
    assert_type(msgspec.inspect.type_info(int), msgspec.inspect.Type)
    assert_type(msgspec.inspect.type_info(list), msgspec.inspect.Type)
    assert_type(msgspec.inspect.type_info(None), msgspec.inspect.Type)


def check_inspect_multi_type_info() -> None:
    o = msgspec.inspect.multi_type_info([int, float])
    assert_type(o, tuple[msgspec.inspect.Type, ...])

    o2 = msgspec.inspect.multi_type_info((int, float))
    assert_type(o2, tuple[msgspec.inspect.Type, ...])


def max_depth(t: msgspec.inspect.Type, depth: int = 0) -> int:
    # This isn't actually a complete max_depth implementation
    if isinstance(t, msgspec.inspect.CollectionType):
        assert_type(t.item_type, msgspec.inspect.Type)
        return max_depth(t.item_type, depth + 1)
    elif isinstance(t, msgspec.inspect.DictType):
        assert_type(t.key_type, msgspec.inspect.Type)
        return max(
            max_depth(t.key_type, depth + 1),
            max_depth(t.value_type, depth + 1)
        )
    elif isinstance(t, msgspec.inspect.TupleType):
        assert_type(t.item_types, tuple[msgspec.inspect.Type, ...])
        return max(max_depth(a, depth + 1) for a in t.item_types)
    else:
        return depth


def check_consume_inspect_types() -> None:
    t = msgspec.inspect.type_info(list[int])
    o = max_depth(t)
    assert_type(o, int)

    t = msgspec.inspect.UnionType(
        (msgspec.inspect.IntType(), msgspec.inspect.NoneType())
    )
    assert_type(t.includes_none, bool)


def check_inspect_is_struct() -> None:
    class Point(msgspec.Struct):
        x: int

    obj: Point | str = Point(1)
    if msgspec.inspect.is_struct(obj):
        assert_type(obj, Point)
    else:
        assert_type(obj, str)

    ns: object = object()
    if msgspec.inspect.is_struct(ns):
        assert_type(ns, msgspec.Struct)
    else:
        assert_type(ns, object)


def check_inspect_is_struct_type() -> None:
    class Point(msgspec.Struct):
        x: int

    class Other: ...

    tp: type[Point] | type[Other] = Point
    if msgspec.inspect.is_struct_type(tp):
        # this is a bug in `pyrefly` https://github.com/facebook/pyrefly/issues/3821:
        assert_type(tp, type[Point])  # pyrefly: ignore[assert-type]
    else:
        assert_type(tp, type[Other])

    other: type[Any] = type("NotStruct", (), {})
    if msgspec.inspect.is_struct_type(other):
        assert_type(other, type[msgspec.Struct])
    else:
        _other_type: type[Any] = other


##########################################################
# JSON Schema                                            #
##########################################################


def check_json_schema() -> None:
    o1 = msgspec.json.schema(list[int])
    assert_type(o1, dict[str, Any])

    o2 = msgspec.json.schema(list[int], schema_hook=lambda t: {"type": "object"})
    assert_type(o2, dict[str, Any])


def check_json_schema_components() -> None:
    s1, c1 = msgspec.json.schema_components([list[int]])
    assert_type(s1, tuple[dict[str, Any], ...])
    assert_type(c1, dict[str, Any])

    s2, c2 = msgspec.json.schema_components([list[int]], ref_template="#/definitions/{name}")
    assert_type(s2, tuple[dict[str, Any], ...])
    assert_type(c2, dict[str, Any])

    s3, c3 = msgspec.json.schema_components(
        [list[int]], schema_hook=lambda t: {"type": "object"}
    )
    assert_type(s3, tuple[dict[str, Any], ...])
    assert_type(c3, dict[str, Any])


##########################################################
# Converters                                             #
##########################################################

def check_to_builtins() -> None:
    msgspec.to_builtins(1)
    msgspec.to_builtins({1: 2}, str_keys=False)
    msgspec.to_builtins(b"test", builtin_types=(bytes, bytearray, memoryview))
    msgspec.to_builtins([1, 2, 3], enc_hook=lambda x: None)
    msgspec.to_builtins([1, 2, 3], order=None)
    msgspec.to_builtins([1, 2, 3], order="deterministic")
    msgspec.to_builtins([1, 2, 3], order="sorted")


def check_convert() -> None:
    o1 = msgspec.convert(1, int)
    assert_type(o1, int)

    o2 = msgspec.convert([1, 2], list[float])
    assert_type(o2, list[float])

    o3 = msgspec.convert(1, int, strict=False)
    assert_type(o3, int)

    o4 = msgspec.convert(1, int, from_attributes=True)
    assert_type(o4, int)

    o5 = msgspec.convert(1, int, dec_hook=lambda typ, x: None)
    assert_type(o5, int)

    o6 = msgspec.convert(1, int, builtin_types=(bytes, bytearray, memoryview))
    assert_type(o6, int)

    o7 = msgspec.convert("1", int, str_keys=True)
    assert_type(o7, int)
