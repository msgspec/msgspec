import copy
import pickle
import random
from typing import Annotated

import pytest
from pytest_codspeed import BenchmarkFixture

import msgspec
import msgspec.structs
from msgspec import defstruct
from msgspec.structs import replace as msgspec_replace

TEMPLATE = """
class C{n}(Struct, order=True):
    a: int
    b: int
    c: int
    d: int
    e: int
"""

TEMPLATE_EMPTY = """
class C{n}(Struct, order=True):
    pass
"""

TEMPLATE_WITH_TAG_TRUE = """
class C{n}(Struct, order=True, tag=True):
    a: int
    b: int
    c: int
    d: int
    e: int
"""

TEMPLATE_WITH_CUSTOM_TAG = """
class C{n}(Struct, order=True, tag='my_tag'):
    a: int
    b: int
    c: int
    d: int
    e: int
"""

TEMPLATE_WITH_CUSTOM_TAG_FIELD = """
class C{n}(Struct, order=True, tag_field="my_tag_field"):
    a: int
    b: int
    c: int
    d: int
    e: int
"""

N = 1000


class Item(msgspec.Struct, order=True):
    a: int
    b: int
    c: int
    d: int
    e: int


class EmptyStruct(msgspec.Struct):
    pass


class Point(msgspec.Struct, order=True):
    x: int
    y: int


class Account(msgspec.Struct, order=True):
    id: int
    balance: float
    active: bool


class Address(msgspec.Struct, order=True):
    street: str
    city: str
    location: Point


class Person(msgspec.Struct, order=True):
    name: str
    age: int
    address: Address
    accounts: list[Account]


def make_person(i: int) -> Person:
    return Person(
        name=f"person-{i}",
        age=i,
        address=Address(
            street=f"{i} Main St", city="Springfield", location=Point(i, i)
        ),
        accounts=[
            Account(id=i * 10 + j, balance=float(i), active=bool(j % 2))
            for j in range(3)
        ],
    )


@pytest.mark.parametrize(
    "template",
    [
        pytest.param(TEMPLATE_EMPTY, id="empty"),
        pytest.param(TEMPLATE, id="basic"),
        pytest.param(TEMPLATE_WITH_TAG_TRUE, id="tagged"),
        pytest.param(TEMPLATE_WITH_CUSTOM_TAG, id="custom_tag"),
        pytest.param(TEMPLATE_WITH_CUSTOM_TAG_FIELD, id="custom_tag_field"),
    ],
)
def test_define(benchmark: BenchmarkFixture, template: str):
    source = "\n".join(template.format(n=i) for i in range(200))
    code_obj = compile(source, "__main__", "exec")

    def fn():
        ns = {"Struct": msgspec.Struct}
        exec(code_obj, ns)

    benchmark.pedantic(fn, warmup_rounds=10)


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

    res = benchmark.pedantic(fn, warmup_rounds=10)
    assert issubclass(res, msgspec.Struct)


@pytest.mark.memory
def test_create(benchmark):
    benchmark.pedantic(
        lambda: [Item(i, i, i, i, i) for i in range(N)],
        warmup_rounds=10,
    )


@pytest.mark.memory
def test_empty_struct_create(benchmark: BenchmarkFixture):
    # empty struct to measure pure overhead without any type nodes
    benchmark.pedantic(
        lambda: [EmptyStruct() for _ in range(N)],
        warmup_rounds=10,
    )


@pytest.mark.memory
def test_equality(benchmark):
    needle = Item(N - 1, N - 1, N - 1, N - 1, N - 1)
    haystack = [Item(i, i, i, i, i) for i in range(N)]
    random.shuffle(haystack)
    benchmark(haystack.index, needle)


def test_equality_complex(benchmark: BenchmarkFixture):
    needle = make_person(N - 1)
    haystack = [make_person(i) for i in range(N)]
    random.shuffle(haystack)
    benchmark(haystack.index, needle)


@pytest.mark.memory
def test_order(benchmark: BenchmarkFixture):
    haystack = [Item(i, i, i, i, i) for i in range(N)]
    random.shuffle(haystack)

    benchmark(sorted, haystack)


def test_pickle_dump(benchmark: BenchmarkFixture):
    items = [Item(i, i, i, i, i) for i in range(N)]
    res = benchmark.pedantic(
        pickle.dumps,
        args=(items,),
        warmup_rounds=10,
    )

    assert pickle.loads(res) == items


def test_pickle_load(benchmark: BenchmarkFixture):
    items = [Item(i, i, i, i, i) for i in range(N)]
    dumped = pickle.dumps(items)
    res = benchmark.pedantic(
        pickle.loads,
        args=(dumped,),
        warmup_rounds=10,
    )

    assert res == items


@pytest.fixture(
    params=[
        "msgspec",
        pytest.param(
            "copy",
            marks=[
                pytest.mark.skipif(
                    "sys.version_info < (3, 13)",
                    reason="only available on 3.13+",
                )
            ],
        ),
    ]
)
def replace_fn(request):
    if request.param == "msgspec":
        return msgspec_replace
    return copy.replace


def test_replace(benchmark: BenchmarkFixture, replace_fn):
    item = Item(1, 2, 3, 4, 5)

    res = benchmark.pedantic(
        replace_fn,
        args=(item,),
        kwargs={"a": 0},
        warmup_rounds=10,
    )

    assert res == Item(0, 2, 3, 4, 5)


def test_copy(benchmark: BenchmarkFixture):
    item = Item(1, 2, 3, 4, 5)

    res = benchmark.pedantic(
        copy.copy,
        args=(item,),
        warmup_rounds=10,
    )

    assert res == item


def test_copy_complex(benchmark: BenchmarkFixture):
    person = make_person(1)

    res = benchmark.pedantic(
        copy.copy,
        args=(person,),
        warmup_rounds=10,
    )

    assert res == person


@pytest.mark.parametrize(
    "cls_or_instance",
    [
        pytest.param(Item, id="class"),
        pytest.param(Person, id="complex_class"),
        pytest.param(Item(1, 2, 3, 4, 5), id="instance"),
        pytest.param(make_person(1), id="complex_instance"),
    ],
)
def test_fields(benchmark: BenchmarkFixture, cls_or_instance):
    res = benchmark.pedantic(
        msgspec.structs.fields,
        args=(cls_or_instance,),
        warmup_rounds=10,
    )

    assert res == msgspec.structs.fields(cls_or_instance)
