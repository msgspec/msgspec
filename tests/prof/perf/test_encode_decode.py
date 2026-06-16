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
