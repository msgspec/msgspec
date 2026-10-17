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
