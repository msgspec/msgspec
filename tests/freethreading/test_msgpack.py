import pytest

import msgspec


def test_encode_list_while_size_changes(race):
    """Encoding a list whose size changes concurrently must not crash."""
    lst = [[1], [2], [3], [4]]

    def mutate():
        lst.append([0])
        lst.pop()

    def check():
        msgspec.msgpack.encode(lst)

    race(mutate, check)


def test_encode_list_while_nested_list_changes_and_outer_shrinks(race):
    inner = [1, 2, 3]
    outer = [inner] * 64

    def mutate():
        inner.append(0)
        inner.pop()
        outer.clear()
        outer.extend([inner] * 64)

    def check():
        try:
            encoded = msgspec.msgpack.encode(outer)
        except RuntimeError as exc:
            # The outer list shrank while being encoded
            assert "changed size during encoding" in str(exc)
        else:
            # Decoding checks that the number of encoded items
            # matches the length written in the array header
            msgspec.msgpack.decode(encoded)

    race(mutate, check, mutators=3)


@pytest.mark.parametrize(
    "operation, decoder",
    [
        (msgspec.json.encode, msgspec.json.decode),
        (msgspec.msgpack.encode, msgspec.msgpack.decode),
        (msgspec.to_builtins, None),
    ],
)
def test_empty_nested_lists_while_outer_changes(race, operation, decoder):
    inner = []
    outer = [inner] * 64

    def mutate():
        outer.clear()
        outer.extend([inner] * 64)

    def check():
        try:
            result = operation(outer)
        except RuntimeError as exc:
            assert "changed size during encoding" in str(exc)
        else:
            if decoder is not None:
                result = decoder(result)
            assert len(result) in (0, 64)
            assert all(item == [] for item in result)

    race(mutate, check)
