import subprocess
import sys


def test_import_time(benchmark):
    # also measures interpreter startup etc., but is the best we can do now, since we
    # don't have a fully isolated module, and some per-process global state, so
    # re-importing purely within the current interpreter doesn't get reliable timings
    def do_import():
        subprocess.run([sys.executable, "-c", "import msgspec"], check=True)

    do_import()  # execute once to reduce possibility of a super cold FS cache

    benchmark(do_import)
