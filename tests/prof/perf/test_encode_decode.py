import datetime
import decimal
import enum
import random
import uuid
from typing import Literal

import pytest
from pytest_codspeed import BenchmarkFixture

import msgspec.json
import msgspec.msgpack
from benchmarks.bench_encodings import Directory
from benchmarks.generate_data import make_filesystem_data


@pytest.fixture()
def file_system_data():
    return make_filesystem_data(1000)


json_decoder = msgspec.json.Decoder(type=Directory)
json_encoder = msgspec.json.Encoder()

msgpack_decoder = msgspec.json.Decoder(type=Directory)
msgspec_encoder = msgspec.json.Encoder()


@pytest.mark.parametrize(
    "encoder",
    [
        pytest.param(json_encoder.encode, id="json"),
        pytest.param(msgspec_encoder.encode, id="msgpack"),
    ],
)
def test_encode(benchmark: BenchmarkFixture, encoder, file_system_data):
    res = benchmark(encoder, file_system_data)

    assert isinstance(res, bytes)


@pytest.mark.parametrize(
    "encoder,decoder",
    [
        pytest.param(json_encoder.encode, json_decoder.decode, id="json"),
        pytest.param(msgspec_encoder.encode, msgpack_decoder.decode, id="msgpack"),
    ],
)
def test_decode(benchmark: BenchmarkFixture, encoder, decoder, file_system_data):
    data = encoder(file_system_data)
    res = benchmark(decoder, data)

    assert isinstance(res, Directory)


@pytest.mark.parametrize(
    "encoder,decoder",
    [
        pytest.param(json_encoder.encode, json_decoder.decode, id="json"),
        pytest.param(msgspec_encoder.encode, msgpack_decoder.decode, id="msgpack"),
    ],
)
def test_roundtrip(benchmark: BenchmarkFixture, encoder, decoder, file_system_data):
    def func(data):
        return decoder(encoder(data))

    res = benchmark(func, file_system_data)

    assert isinstance(res, Directory)


@pytest.mark.memory
@pytest.mark.parametrize(
    "encoder,decoder",
    [
        pytest.param(json_encoder.encode, json_decoder.decode, id="json"),
        pytest.param(msgspec_encoder.encode, msgpack_decoder.decode, id="msgpack"),
    ],
)
def test_roundtrip_memory(benchmark: BenchmarkFixture, encoder, decoder):
    def func(data):
        return decoder(encoder(data))

    res = benchmark(func, make_filesystem_data(1000))

    assert isinstance(res, Directory)


class SomeEnum(enum.Enum):
    FIELD_1 = enum.auto()
    FIELD_2 = enum.auto()
    FIELD_3 = enum.auto()
    FIELD_4 = enum.auto()
    FIELD_5 = enum.auto()
    FIELD_6 = enum.auto()
    FIELD_7 = enum.auto()
    FIELD_8 = enum.auto()
    FIELD_9 = enum.auto()
    FIELD_10 = enum.auto()


@pytest.fixture(
    params=[
        pytest.param(msgspec.json, id="json"),
        pytest.param(msgspec.msgpack, id="msgpack"),
    ]
)
def proto(request):
    return request.param


sample_data_mark = pytest.mark.parametrize(
    "make_data,target_type",
    [
        pytest.param(
            lambda: random.sample(range(-100_000, 100_000), 10_000), list[int], id="int"
        ),
        pytest.param(
            lambda: [random.uniform(-100_000.0, 100_000.0) for _ in range(10_000)],
            list[float],
            id="float",
        ),
        pytest.param(
            lambda: [
                decimal.Decimal(random.uniform(-100_000.0, 100_000.0))
                for _ in range(10_000)
            ],
            list[decimal.Decimal],
            id="decimal",
        ),
        pytest.param(
            lambda: [
                datetime.date(2000, 1, 1) + datetime.timedelta(days=i)
                for i in range(1, 10_000)
            ],
            list[datetime.date],
            id="date",
        ),
        pytest.param(
            lambda: [
                datetime.datetime(2000, 1, 1) + datetime.timedelta(seconds=i)
                for i in range(1, 10_000)
            ],
            list[datetime.datetime],
            id="datetime",
        ),
        pytest.param(
            lambda: [
                datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC)
                + datetime.timedelta(seconds=i)
                for i in range(1, 10_000)
            ],
            list[datetime.datetime],
            id="datetimetz",
        ),
        pytest.param(
            lambda: [datetime.timedelta(seconds=i) for i in range(1, 10_000)],
            list[datetime.timedelta],
            id="timedelta",
        ),
        pytest.param(
            lambda: [
                datetime.time(h, m, s)
                for h in range(24)
                for m in range(60)
                for s in range(60)
            ],
            list[datetime.time],
            id="time",
        ),
        pytest.param(
            lambda: [None for _ in range(10_000)],
            list[None],
            id="None",
        ),
        pytest.param(
            lambda: [False for _ in range(10_000)],
            list[Literal[False]],
            id="False",
        ),
        pytest.param(
            lambda: [True for _ in range(10_000)],
            list[Literal[True]],
            id="True",
        ),
        pytest.param(
            lambda: random.randbytes(10_000),
            bytes,
            id="bytes",
        ),
        pytest.param(
            lambda: random.randbytes(10_000),
            bytearray,
            id="bytearray",
        ),
        pytest.param(
            lambda: random.randbytes(10_000),
            memoryview,
            id="memoryview",
        ),
        pytest.param(
            lambda: random.randbytes(10_000).hex(),
            str,
            id="long_string",
        ),
        pytest.param(
            lambda: [[] * 10_000],
            list[list],
            id="list",
        ),
        pytest.param(
            lambda: tuple(() * 10_000),
            tuple[tuple, ...],
            id="tuple",
        ),
        pytest.param(
            lambda: [set() for _ in range(10_000)],
            list[set],
            id="set",
        ),
        pytest.param(
            lambda: [frozenset() for _ in range(10_000)],
            list[frozenset],
            id="frozenset",
        ),
        pytest.param(
            lambda: {str(i): i for i in range(10_000)},
            dict[str, int],
            id="dict",
        ),
        pytest.param(
            lambda: [
                uuid.uuid5(uuid.NAMESPACE_DNS, f"test-{i}") for i in range(10_000)
            ],
            list[uuid.UUID],
            id="uuid",
        ),
        pytest.param(
            lambda: [random.choice(list(SomeEnum)) for _ in range(10_000)],
            list[SomeEnum],
            id="enum",
        ),
    ],
)


@sample_data_mark
def test_decode_type(benchmark: BenchmarkFixture, proto, make_data, target_type):
    data = make_data()
    encoded = proto.encode(data)

    res = benchmark.pedantic(
        proto.decode,
        args=(encoded,),
        kwargs={"type": target_type},
        warmup_rounds=10,
    )

    assert res == data


@sample_data_mark
def test_encode_type(benchmark: BenchmarkFixture, proto, make_data, target_type):
    data = make_data()

    res = benchmark.pedantic(
        proto.encode,
        args=(data,),
        warmup_rounds=10,
    )

    assert res == proto.encode(data)


@pytest.mark.parametrize(
    "make_data,target_type",
    [
        pytest.param(
            lambda: random.sample(range(-100_000, 100_000), 10_000), list[int], id="int"
        ),
        pytest.param(
            lambda: [random.uniform(-100_000.0, 100_000.0) for _ in range(10_000)],
            list[float],
            id="float",
        ),
    ],
)
@pytest.mark.parametrize(
    "encode,decode",
    [
        pytest.param(msgspec.json.encode, msgspec.json.decode, id="json"),
        pytest.param(msgspec.msgpack.encode, msgspec.msgpack.decode, id="msgpack"),
        pytest.param(lambda v: v, msgspec.convert, id="convert"),
    ],
)
def test_decode_convert_type_non_strict(
    benchmark: BenchmarkFixture, decode, encode, make_data, target_type
):
    data = make_data()

    encoded = encode(data)

    res = benchmark.pedantic(
        decode,
        args=(encoded,),
        kwargs={"strict": False, "type": target_type},
        warmup_rounds=10,
    )

    assert res == data
