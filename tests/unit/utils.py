import dataclasses
import inspect
import sys
import sysconfig
import textwrap
import types
import uuid
from contextlib import contextmanager
from typing import Annotated, NewType, TypeVar

import pytest

from msgspec import Meta, UnsetType

emscripten_stack_limited = pytest.mark.skipif(
    sys.platform == "emscripten",
    reason="Pyodide can overflow the JS/Wasm stack before raising RecursionError",
)

# The C recursion limit on Windows ARM64 was lowered from 3000 to 1000 in
# CPython 3.13 (python/cpython#117008); 3.12 still uses 3000.
win_arm64_py312_stack_limited = pytest.mark.skipif(
    sysconfig.get_platform() == "win-arm64" and sys.version_info[:2] == (3, 12),
    reason="Python 3.12 on Windows ARM64 can overflow the C stack before raising RecursionError",
)

py315_or_later_only = pytest.mark.skipif(
    sys.version_info < (3, 15), reason="frozendict was added in 3.15"
)


@contextmanager
def temp_module(code):
    """Mutually recursive struct types defined inside functions don't work (and
    probably never will). To avoid populating a bunch of test structs in the
    top level of this module, we instead create a temporary module per test to
    exec whatever is needed for that test"""
    code = textwrap.dedent(code)
    name = f"temp_{uuid.uuid4().hex}"
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    try:
        exec(code, mod.__dict__)
        yield mod
    finally:
        sys.modules.pop(name, None)


py312_plus = pytest.mark.skipif(sys.version_info < (3, 12), reason="3.12+ only")

# Ways to wrap a type, for `wrapped_type`. `annotated` adds no alias layer.
WRAP_KINDS = [
    "annotated",
    "newtype",
    "newtype_twice",
    pytest.param("alias", marks=py312_plus),
    pytest.param("alias_twice", marks=py312_plus),
    "unset_union",
    "typevar_bound",
]


@contextmanager
def wrapped_type(kind, inner):
    """Yield `inner` wrapped in zero, one or two `NewType` or `type` aliases,
    in a union with `UnsetType`, or as the bound of a `TypeVar`."""
    if kind == "annotated":
        yield inner
    elif kind == "newtype":
        yield NewType("A", inner)
    elif kind == "newtype_twice":
        yield NewType("B", NewType("A", inner))
    elif kind == "unset_union":
        yield inner | UnsetType
    elif kind == "typevar_bound":
        yield TypeVar("T", bound=inner)
    else:
        code = "type A = INNER"
        if kind == "alias_twice":
            code += "\ntype B = A"
        with temp_module(code) as mod:
            # Alias values are evaluated lazily, so this is seen on first use
            mod.INNER = inner
            yield mod.B if kind == "alias_twice" else mod.A


THREE_KINDS = [
    "annotated",
    "newtype",
    pytest.param("alias_of_newtype", marks=py312_plus),
]


def three_metas():
    """`Meta` objects for an inner, middle and outer layer. Every attribute is
    set by one, two or all three layers, to pin which layer wins."""
    inner = Meta(
        title="inner title",
        description="inner description",
        examples=["inner"],
        extra={"k": "inner", "im": "inner", "inner_only": 1},
        extra_json_schema={"x": "inner", "tags": ["i"], "inner_only": 1},
    )
    middle = Meta(
        title="middle title",
        description="middle description",
        examples=["middle"],
        extra={"k": "middle", "im": "middle", "middle_only": 2},
        extra_json_schema={"x": "middle", "tags": ["m"], "middle_only": 2},
    )
    outer = Meta(
        title="outer title",
        extra={"k": "outer", "outer_only": 3},
        extra_json_schema={"x": "outer", "tags": ["o"], "outer_only": 3},
    )
    return inner, middle, outer


@contextmanager
def layered_type(kind, inner, middle):
    """Yield `int` with `inner` then `middle` added behind NewType or alias
    layers, ready for an outer `Meta` to be added at the use site."""
    base = Annotated[int, inner]
    if kind == "annotated":
        yield Annotated[base, middle]
    elif kind == "newtype":
        yield NewType("B", Annotated[NewType("A", base), middle])
    else:
        with temp_module("type A = VALUE") as mod:
            mod.VALUE = Annotated[NewType("N", base), middle]
            yield mod.A


@contextmanager
def max_call_depth(n):
    cur_depth = len(inspect.stack(0))
    orig = sys.getrecursionlimit()
    try:
        # Our measure of the current stack depth can be off by a bit. Trying to
        # set a recursionlimit < the current depth will raise a RecursionError.
        # We just try again with a slightly higher limit, bailing after an
        # unreasonable amount of adjustments.
        for i in range(64):
            try:
                sys.setrecursionlimit(cur_depth + i + n)
                break
            except RecursionError:
                pass
        else:
            raise ValueError(
                "Failed to set low recursion limit, something is wrong here"
            )
        yield
    finally:
        sys.setrecursionlimit(orig)


@contextmanager
def package_not_installed(name):
    try:
        orig = sys.modules.get(name)
        sys.modules[name] = None
        yield
    finally:
        if orig is not None:
            sys.modules[name] = orig
        else:
            del sys.modules[name]


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
