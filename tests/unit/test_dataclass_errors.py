import dataclasses
import gc
import sys

import pytest

import msgspec


class FieldDescriptor:
    def __set_name__(self, owner, name):
        self.name = "_" + name

    def __get__(self, obj, owner=None):
        if obj is None:
            return None
        value = getattr(obj, self.name)
        if isinstance(value, BaseException):
            raise value
        return value

    def __set__(self, obj, value):
        setattr(obj, self.name, value)


@dataclasses.dataclass
class DescriptorRow:
    first: object
    value: object = FieldDescriptor()
    last: int = 3


@dataclasses.dataclass
class CustomRow:
    first: object
    value: object
    last: int = 3

    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        if name == "value" and isinstance(value, BaseException):
            raise value
        return value


@pytest.fixture(
    params=[msgspec.json, msgspec.msgpack, None], ids=["json", "msgpack", "builtins"]
)
def operation(request):
    return request.param


def encode(operation, obj, order):
    if operation is None:
        return msgspec.to_builtins(obj, order=order)
    return operation.encode(obj, order=order)


def decoded(operation, result):
    return result if operation is None else operation.decode(result)


@pytest.mark.parametrize("row_type", [DescriptorRow, CustomRow])
@pytest.mark.parametrize(
    "error_type", [ValueError, RuntimeError, MemoryError, KeyboardInterrupt]
)
@pytest.mark.parametrize("order", [None, "sorted"])
def test_field_exception_identity(operation, row_type, error_type, order):
    error = error_type("field access failed")
    row = row_type([1, 2], error)
    with pytest.raises(error_type) as caught:
        encode(operation, row, order)
    assert caught.value is error


@pytest.mark.parametrize("row_type", [DescriptorRow, CustomRow])
@pytest.mark.parametrize("order", [None, "sorted"])
def test_attribute_error_key_error_and_unset_still_omitted(operation, row_type, order):
    for value in [AttributeError("missing"), KeyError("missing"), msgspec.UNSET]:
        assert decoded(operation, encode(operation, row_type(1, value), order)) == {
            "first": 1,
            "last": 3,
        }


@pytest.mark.parametrize("slots", [False, True])
@pytest.mark.parametrize("order", [None, "sorted"])
def test_deleted_fields_still_omitted(operation, slots, order):
    row_type = dataclasses.make_dataclass(
        "DeletedRow", [("first", int), ("value", int)], slots=slots
    )
    row = row_type(1, 2)
    del row.value
    assert decoded(operation, encode(operation, row, order)) == {"first": 1}


@pytest.mark.parametrize("order", [None, "sorted"])
@pytest.mark.parametrize(
    "module", [msgspec.json, msgspec.msgpack], ids=["json", "msgpack"]
)
def test_encoder_reuse_after_partial_field_failure(module, order):
    encoder = module.Encoder(order=order)
    error = RuntimeError("field failure")
    row = DescriptorRow(list(range(100)), error)
    for _ in range(3):
        with pytest.raises(RuntimeError) as caught:
            encoder.encode(row)
        assert caught.value is error
        assert module.decode(encoder.encode(DescriptorRow([1], 2))) == {
            "first": [1],
            "value": 2,
            "last": 3,
        }
        error.__traceback__ = None


@pytest.mark.parametrize("order", [None, "sorted"])
def test_partial_values_not_leaked(operation, order):
    first = [1, 2, 3]
    error = RuntimeError("field failure")
    row = DescriptorRow(first, error)
    # Warm iterator/schema and exception caches before checking retained references.
    for _ in range(2):
        try:
            encode(operation, row, order)
        except RuntimeError:
            pass
        error.__traceback__ = None
    gc.collect()
    baseline = sys.getrefcount(first)
    for _ in range(50):
        with pytest.raises(RuntimeError):
            encode(operation, row, order)
        error.__traceback__ = None
    gc.collect()
    assert sys.getrefcount(first) == baseline


@pytest.mark.parametrize("row_type", [DescriptorRow, CustomRow])
@pytest.mark.parametrize("order", [None, "sorted"])
def test_key_error_subclass_compatibility(operation, row_type, order):
    class MissingKey(KeyError):
        pass

    assert decoded(
        operation, encode(operation, row_type(1, MissingKey("missing")), order)
    ) == {"first": 1, "last": 3}
