import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "msgspec",
        "msgspec.structs",
        "msgspec.json",
        "msgspec.msgpack",
        "msgspec.inspect",
        "msgspec.yaml",
        "msgspec.toml",
    ],
)
def test_import_time(benchmark, module_name):
    # also measures interpreter startup etc., but is the best we can do now, since we
    # don't have a fully isolated module, and some per-process global state, so
    # re-importing purely within the current interpreter doesn't get reliable timings
    def do_import():
        subprocess.run([sys.executable, "-c", f"import {module_name}"], check=True)

    do_import()  # execute once to reduce possibility of a super cold FS cache

    benchmark(do_import)
