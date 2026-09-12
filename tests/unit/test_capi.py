import gc
import weakref

import pytest

import msgspec

testcapi = pytest.importorskip(
    "msgspec._testcapi",
    reason="build with MSGSPEC_COMPILE_TEST_CAPI=1 to test the native C API",
)


def test_capability_is_advertised():
    assert testcapi.capabilities() & 1


def test_declared_order_and_none_value():
    class Example(msgspec.Struct, kw_only=True, rename="camel"):
        first_name: str
        value: object

    builder = testcapi.prepare(Example)
    out = testcapi.build(builder, ("a", None))
    assert out == Example(first_name="a", value=None)


def test_defaults_factories_and_post_init():
    seen = []

    class Example(msgspec.Struct):
        required: int
        defaulted: int = 2
        generated: list = msgspec.field(default_factory=list)

        def __post_init__(self):
            seen.append(self)

    builder = testcapi.prepare(Example)
    out = testcapi.build(
        builder,
        (1, testcapi.ABSENT, testcapi.ABSENT),
    )
    assert (out.required, out.defaulted, out.generated) == (1, 2, [])
    assert out.generated == []
    assert seen == [out]


def test_required_and_slot_count_errors():
    class Example(msgspec.Struct):
        value: int

    builder = testcapi.prepare(Example)
    with pytest.raises(TypeError, match="Missing required argument 'value'"):
        testcapi.build(builder, (testcapi.ABSENT,))
    with pytest.raises(TypeError, match="expected 1 declared-order fields, got 0"):
        testcapi.build(builder, ())


def test_abstractness_is_checked_at_build_time():
    class Example(msgspec.Struct):
        value: int

    builder = testcapi.prepare(Example)
    Example.__abstractmethods__ = frozenset({"value"})
    with pytest.raises(TypeError, match="abstract"):
        testcapi.build(builder, (1,))


def test_custom_struct_meta_uses_fallback():
    class Meta(msgspec.StructMeta):
        pass

    class Example(msgspec.Struct, metaclass=Meta):
        value: int

    assert testcapi.prepare(Example) is None


def test_builder_cycle_is_collectable():
    def make_cycle():
        class Example(msgspec.Struct):
            value: int

        ref = weakref.ref(Example)
        Example._builder_cycle = testcapi.prepare(Example)
        return ref

    ref = make_cycle()
    assert ref() is not None
    gc.collect()
    assert ref() is None
