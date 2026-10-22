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
