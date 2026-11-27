from __future__ import annotations

import pytest

import msgspec


class Point(msgspec.Struct):
    x: int
    y: int


class TestEncodeFunction:
    def test_encode(self):
        assert msgspec.json5.encode(1) == b"1"

    def test_encoding_struct(self):
        # json5 & pyjson5 can differ ever so slightly.
        assert msgspec.json5.encode(Point(1, 2)) in [
            b'{"x":1,"y":2}',
            b'{"x": 1, "y": 2}',
        ]


class TestDecodeFunction:
    @pytest.mark.parametrize(
        "b",
        [
            b"{x:1, y:2}",
            "{x:1, y:2}",
            '{"x":1, y:2}',
            '{"x":1,"y":2}',
            "{'x':1,'y':2}",
            "{x:1, y:2 /* Look at me, a comment :) */}",
            b"{/* Now it's Opposite day */ y:2, 'x':1}",
        ],
    )
    def test_decode(self, b: bytes | str):
        point = msgspec.json5.decode(b, type=Point)
        assert point.x == 1
        assert point.y == 2

    @pytest.mark.parametrize("array_like", [False, True])
    def test_decode_type_struct(self, array_like: bool):
        class Size(msgspec.Struct, array_like=array_like):
            width: int
            height: int

        msg = msgspec.json5.encode(Size(1, 2))
        for _ in range(2):
            assert msgspec.json5.decode(msg, type=Size) == Size(1, 2)

    def test_decode_type_struct_invalid_type(self):
        class Test(msgspec.Struct):
            x: 1

        with pytest.raises(TypeError):
            msgspec.json5.decode(b"{}", type=Test)

    def test_decode_invalid_type(self):
        with pytest.raises(TypeError, match="Type '1' is not supported"):
            msgspec.json5.decode(b"[]", type=1)

    def test_decode_with_trailing_characters_errors(self):
        with pytest.raises(msgspec.DecodeError):
            msgspec.json5.decode(b'[1, 2, 3]"trailing"')
