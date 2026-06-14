import random
from typing import Annotated

import pytest
from pytest_codspeed import BenchmarkFixture

import msgspec
from msgspec import defstruct

template = """
class C{n}(Struct, order=True):
    a: int
    b: int
    c: int
    d: int
    e: int
"""

N = 1000
RAMDOM = random.Random(b"12345")


class Item(msgspec.Struct, order=True):
    a: int
    b: int
    c: int
    d: int
    e: int


def test_define(benchmark: BenchmarkFixture):
    source = "\n".join(template.format(n=i) for i in range(200))
    code_obj = compile(source, "__main__", "exec")

    def fn():
        ns = {"Struct": msgspec.Struct}
        exec(code_obj, ns)

    benchmark(fn)


def test_defstruct(benchmark: BenchmarkFixture):
    fields = [
        "one",
        "two",
        "three",
        "four",
        ("int", int),
        ("str", str),
        ("list", list[str]),
        ("dict_str", dict[str, str]),
        ("dict_int", dict[str, int]),
        ("tuple_str", tuple[str, ...]),
        ("int_default", int, 10),
        ("str_default", str, ""),
        ("tuple_default", tuple[str, ...], ()),
        ("int_annotated", Annotated[int, msgspec.Meta(gt=1)], 1),
        ("str_annotated", Annotated[str, msgspec.Meta(min_length=2)], "ab"),
        ("str_pattern", Annotated[str, msgspec.Meta(pattern=r"\w\w")], "ab"),
    ]

    def fn():
        return defstruct("SomeStruct", fields)

    res = benchmark(fn)
    assert issubclass(res, msgspec.Struct)


@pytest.mark.memory
def test_create(benchmark):
    benchmark(lambda: [Item(i, i, i, i, i) for i in range(N)])


@pytest.mark.memory
def test_equality(benchmark):
    needle = Item(N - 1, N - 1, N - 1, N - 1, N - 1)
    haystack = [Item(i, i, i, i, i) for i in range(N)]
    RAMDOM.shuffle(haystack)
    benchmark(haystack.index, needle)


@pytest.mark.memory
def test_order(benchmark: BenchmarkFixture):
    haystack = [Item(i, i, i, i, i) for i in range(N)]
    RAMDOM.shuffle(haystack)

    benchmark(sorted, haystack)
