# Most of the things here are copied from the CPython's test suite.

import sys
import sysconfig
import threading

import pytest

IS_FREE_THREADED_BUILD = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
GIL_ENABLED = getattr(sys, "_is_gil_enabled", lambda: True)()


def pytest_runtest_setup(item):
    if sys.version_info < (3, 14):
        pytest.skip("requires python3.4 or newer")
    if not IS_FREE_THREADED_BUILD:
        pytest.skip("requires a free-threaded (Py_GIL_DISABLED) build")
    if GIL_ENABLED:
        pytest.skip("requires the GIL to be disabled (run without `-X gil=1`)")


def _run_threads(targets):
    barrier = threading.Barrier(len(targets))
    errors = []
    lock = threading.Lock()

    def runner(target):
        try:
            barrier.wait()
            target()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=runner, args=(t,)) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]


def _run_concurrently(func, nthreads=4, *args, **kwargs):
    _run_threads([lambda: func(*args, **kwargs) for _ in range(nthreads)])


def _race(mutate, check, *, mutators=1, checkers=4, iterations=5000):
    """
    Race *mutate* against *check*.

    *mutate* should perform one mutation of the shared object. *check*
    should perform one operation on it and assert whatever is expected to
    hold; it must tolerate the object being in any state *mutate* can
    leave it in.

    See ``test_free_threading/test_races.py`` in CPython.
    """
    stop = threading.Event()
    remaining = [checkers]
    lock = threading.Lock()

    def mutator():
        while not stop.is_set():
            mutate()

    def checker():
        try:
            for _ in range(iterations):
                if stop.is_set():
                    break
                check()
        finally:
            with lock:
                remaining[0] -= 1
                if remaining[0] == 0:
                    stop.set()

    try:
        _run_threads([mutator] * mutators + [checker] * checkers)
    finally:
        stop.set()


@pytest.fixture(scope="session")
def run_concurrently():
    """Run one function in several threads at once.

    Usage::

        def test_something(run_concurrently):
            run_concurrently(lambda: msgspec.json.encode(obj), nthreads=8)
    """
    return _run_concurrently


@pytest.fixture(scope="session")
def race():
    """Run a ``check`` function in several threads while ``mutate`` runs.

    Usage::

        def test_something(race):
            lst = [1, 2, 3]

            def mutate():
                lst.append(4)
                lst.pop()

            def check():
                msgspec.json.encode(lst)

            race(mutate, check)

    See ``_race`` for the keyword arguments.
    """
    return _race
