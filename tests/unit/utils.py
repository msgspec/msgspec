import inspect
import sys
import sysconfig
import textwrap
import types
import uuid
from contextlib import contextmanager

import pytest

emscripten_stack_limited = pytest.mark.skipif(
    sys.platform == "emscripten",
    reason="Pyodide can overflow the JS/Wasm stack before raising RecursionError",
)

# The C recursion limit on Windows ARM64 was lowered from 3000 to 1000 in
# CPython 3.13 (python/cpython#117008); 3.12 still uses 3000.
win_arm64_py312_stack_limited = pytest.mark.skipif(
    sysconfig.get_platform() == "win-arm64" and sys.version_info[:2] == (3, 12),
    reason="Python 3.12 on Windows ARM64 can overflow the C stack before raising RecursionError",
)

py315_or_later_only = pytest.mark.skipif(
    sys.version_info < (3, 15), reason="frozendict was added in 3.15"
)


@contextmanager
def temp_module(code):
    """Mutually recursive struct types defined inside functions don't work (and
    probably never will). To avoid populating a bunch of test structs in the
    top level of this module, we instead create a temporary module per test to
    exec whatever is needed for that test"""
    code = textwrap.dedent(code)
    name = f"temp_{uuid.uuid4().hex}"
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    try:
        exec(code, mod.__dict__)
        yield mod
    finally:
        sys.modules.pop(name, None)


@contextmanager
def max_call_depth(n):
    cur_depth = len(inspect.stack(0))
    orig = sys.getrecursionlimit()
    try:
        # Our measure of the current stack depth can be off by a bit. Trying to
        # set a recursionlimit < the current depth will raise a RecursionError.
        # We just try again with a slightly higher limit, bailing after an
        # unreasonable amount of adjustments.
        for i in range(64):
            try:
                sys.setrecursionlimit(cur_depth + i + n)
                break
            except RecursionError:
                pass
        else:
            raise ValueError(
                "Failed to set low recursion limit, something is wrong here"
            )
        yield
    finally:
        sys.setrecursionlimit(orig)


@contextmanager
def package_not_installed(name):
    try:
        orig = sys.modules.get(name)
        sys.modules[name] = None
        yield
    finally:
        if orig is not None:
            sys.modules[name] = orig
        else:
            del sys.modules[name]
