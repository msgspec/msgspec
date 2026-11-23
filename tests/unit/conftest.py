import math
import random
import string
import struct

import pytest


class Rand:
    """Random source controlled by `--randomly-seed`'s random state."""

    def __init__(self, state):
        self.state = state
        self.rand = random.Random()
        self.rand.setstate(self.state)

    def str(self, n, m=0):
        """
        str(n) -> random string of length `n`.
        str(n, m) -> random string between lengths `n` & `m`
        """
        if m:
            n = self.rand.randint(n, m)
        return "".join(self.rand.choices(string.ascii_letters, k=n))

    def bytes(self, n):
        """random bytes of length `n`"""
        return self.rand.getrandbits(8 * n).to_bytes(n, "little")

    def float(self):
        """random finite float"""
        while True:
            dbytes = self.rand.getrandbits(64).to_bytes(8, "big")
            x = struct.unpack("!d", dbytes)[0]
            if math.isfinite(x):
                return x

    def shuffle(self, obj):
        """random shuffle"""
        self.rand.shuffle(obj)


@pytest.fixture
def rand():
    # State that is seeded with `pytest-randomly` already
    yield Rand(state=random.getstate())


@pytest.fixture(scope="session")
def package_dir(pytestconfig):
    return pytestconfig.rootpath.joinpath("src", "msgspec")
