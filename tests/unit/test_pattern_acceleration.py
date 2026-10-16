import gc
import importlib
import os
import re
import subprocess
import sys
import sysconfig
import textwrap
import warnings
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Annotated

import pytest

import msgspec


def run_python(code, *args):
    if sys.platform in {"emscripten", "wasi"}:
        pytest.skip("Subprocesses unavailable")
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def pcre2_available():
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        available = False
    else:
        try:
            provider = importlib.import_module("pcre2._cy")
        except ModuleNotFoundError as exc:
            if exc.name != "pcre2":
                raise
            available = False
        else:
            available = hasattr(provider, "_MATCHER_API_v1")
    expected = os.environ.get("MSGSPEC_TEST_PCRE2")
    if expected is not None:
        assert expected in ("0", "1")
        assert available == (expected == "1")
    return available


@pytest.fixture
def native(pcre2_available):
    if not pcre2_available:
        pytest.skip("Optional pcre2 matcher API unavailable")


def test_backend_missing_and_broken_imports():
    run_python(
        r"""
        import importlib.abc
        import importlib.machinery
        import sys
        import sysconfig
        from typing import Annotated
        import msgspec

        class BrokenBackend(importlib.abc.MetaPathFinder, importlib.abc.Loader):
            error = "pcre2"
            failure = None
            calls = 0

            def find_spec(self, fullname, path=None, target=None):
                if fullname == "pcre2":
                    self.calls += 1
                    return importlib.machinery.ModuleSpec(fullname, self)

            def create_module(self, spec):
                if self.failure is not None:
                    raise self.failure
                raise ModuleNotFoundError("missing", name=self.error)

            def exec_module(self, module):
                pass

        finder = BrokenBackend()
        sys.meta_path.insert(0, finder)
        sys.modules.pop("pcre2._cy", None)
        sys.modules.pop("pcre2", None)
        typ = Annotated[str, msgspec.Meta(pattern="^a$")]
        assert msgspec.json.decode(b'"a"', type=typ) == "a"
        if sysconfig.get_config_var("Py_GIL_DISABLED"):
            assert finder.calls == 0
            sys.exit(0)
        assert finder.calls == 1
        finder.error = "missing_backend_dependency"
        try:
            msgspec.Meta(pattern="^a$")
        except ModuleNotFoundError as exc:
            assert exc.name == finder.error
        else:
            raise AssertionError("Broken backend hidden")
        finder.failure = RuntimeError("SDK initialization failure")
        try:
            msgspec.Meta(pattern="^a$")
        except RuntimeError as exc:
            assert exc is finder.failure
        else:
            raise AssertionError("SDK initialization error hidden")
        calls = finder.calls
        msgspec.Meta(pattern=r"\w+")
        assert finder.calls == calls
        """
    )


def test_backend_module_removal_preserves_matcher(native):
    run_python(
        r"""
        import gc
        import importlib
        import sys
        from typing import Annotated
        import msgspec

        typ = Annotated[str, msgspec.Meta(pattern="^[A-Z]{2}$")]
        decoder = msgspec.json.Decoder(typ)
        package = importlib.import_module("pcre2")
        module = importlib.import_module("pcre2._cy")
        del sys.modules["pcre2._cy"], sys.modules["pcre2"]
        del package, module
        gc.collect()
        assert decoder.decode(b'"US"') == "US"
        next_type = Annotated[str, msgspec.Meta(pattern="^[A-Z]{2,3}$")]
        assert msgspec.json.decode(b'"GB"', type=next_type) == "GB"
        assert decoder.decode(b'"US"') == "US"
        """
    )


def test_incompatible_backend_interface():
    run_python(
        r"""
        import ctypes
        import sys
        import sysconfig
        import types
        import msgspec

        class API(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint), ("size", ctypes.c_size_t),
                ("type", ctypes.c_void_p), ("new_matcher", ctypes.c_void_p),
                ("search", ctypes.c_void_p),
            ]

        name = b"pcre2._cy._MATCHER_API_v1"
        capsule_new = ctypes.pythonapi.PyCapsule_New
        capsule_new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
        capsule_new.restype = ctypes.py_object
        package = types.ModuleType("pcre2")
        package.__path__ = []
        sys.modules["pcre2"] = package
        cases = [
            (2, ctypes.sizeof(API), None, None, None),
            (1, 0, None, None, None),
            (1, ctypes.sizeof(API), None, 1, 1),
            (1, ctypes.sizeof(API), id(str), None, 1),
            (1, ctypes.sizeof(API), id(str), 1, None),
        ]
        for values in cases:
            # A complete table is allocated, but invalid entries are never called.
            api = API(*values)
            module = types.ModuleType("pcre2._cy")
            module._MATCHER_API_v1 = capsule_new(ctypes.addressof(api), name, None)
            sys.modules["pcre2._cy"] = module
            if sysconfig.get_config_var("Py_GIL_DISABLED"):
                msgspec.Meta(pattern="^a$")
                continue
            try:
                msgspec.Meta(pattern="^a$")
            except ImportError as exc:
                assert "Incompatible" in str(exc)
            else:
                raise AssertionError("Incompatible interface accepted")
        """
    )


def test_optional_provider_lookup_errors():
    run_python(
        r"""
        import sys
        import sysconfig
        import types
        from typing import Annotated
        import msgspec

        package = types.ModuleType("pcre2")
        package.__path__ = []
        def unexpected_compile(*args, **kwargs):
            raise AssertionError("SDK compile used without a matcher API")
        package.compile = unexpected_compile
        sys.modules["pcre2"] = package
        provider = types.ModuleType("pcre2._cy")
        sys.modules["pcre2._cy"] = provider
        typ = Annotated[str, msgspec.Meta(pattern="^a$")]
        assert msgspec.json.decode(b'"a"', type=typ) == "a"
        try:
            msgspec.json.decode(b'"b"', type=typ)
        except msgspec.ValidationError:
            pass
        else:
            raise AssertionError("Fallback constraint omitted")

        for error in (AttributeError("dynamic provider failure"),
                      RuntimeError("dynamic provider failure")):
            def lookup(name):
                raise error
            provider.__getattr__ = lookup
            if sysconfig.get_config_var("Py_GIL_DISABLED"):
                msgspec.Meta(pattern="^a$")
                continue
            try:
                msgspec.Meta(pattern="^a$")
            except type(error) as exc:
                assert exc is error
            else:
                raise AssertionError("Dynamic provider error hidden")
        """
    )


@pytest.mark.skipif(
    bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
    reason="Free-threaded builds do not import the optional SDK",
)
def test_sdk_without_matcher_api(monkeypatch):
    try:
        provider = importlib.import_module("pcre2._cy")
    except ModuleNotFoundError as exc:
        if exc.name != "pcre2":
            raise
        pytest.skip("Optional pcre2 package not installed")
    package = importlib.import_module("pcre2")
    # This also exercises a published SDK that never defined the capsule.
    monkeypatch.delattr(provider, "_MATCHER_API_v1", raising=False)

    def unexpected_compile(*args, **kwargs):
        raise AssertionError("SDK compile used without a matcher API")

    monkeypatch.setattr(package, "compile", unexpected_compile)
    typ = Annotated[str, msgspec.Meta(pattern="^[A-Z]{2,17}$")]
    assert msgspec.json.decode(b'"US"', type=typ) == "US"
    with pytest.raises(msgspec.ValidationError):
        msgspec.json.decode(b'"bad"', type=typ)


def test_sdk_newline_setting_preserves_python_semantics(native, monkeypatch):
    package = importlib.import_module("pcre2")
    original_compile = package.compile
    pattern = "^[A-Z]{2,2}$"
    crlf_pattern = original_compile("(*CRLF)" + pattern)
    assert crlf_pattern.search("US\n") is None
    assert crlf_pattern.search("US\r\n") is not None
    compiled = []

    def crlf_compile(pattern):
        compiled.append(pattern)
        return original_compile("(*CRLF)" + pattern)

    monkeypatch.setattr(package, "compile", crlf_compile)
    typ = Annotated[str, msgspec.Meta(pattern=pattern)]
    assert len(compiled) == 1
    assert msgspec.inspect.type_info(typ).pattern == pattern
    assert msgspec.json.schema(typ)["pattern"] == pattern
    for subject in ("US", "US\n", "US\r\n", "US\r", "bad"):
        if re.search(pattern, subject) is None:
            with pytest.raises(msgspec.ValidationError):
                msgspec.convert(subject, type=typ)
        else:
            assert msgspec.convert(subject, type=typ) == subject


@pytest.mark.parametrize("code", [120, -45])
def test_sdk_compile_resource_fallback(native, monkeypatch, code):
    package = importlib.import_module("pcre2")
    error = package.LibraryError(code)

    def fail_compile(*args, **kwargs):
        raise error

    monkeypatch.setattr(package, "compile", fail_compile)
    typ = Annotated[str, msgspec.Meta(pattern="^[A-Z]{2,18}$")]
    assert msgspec.json.decode(b'"US"', type=typ) == "US"
    with pytest.raises(msgspec.ValidationError):
        msgspec.json.decode(b'"bad"', type=typ)


@pytest.mark.parametrize("kind", ["library", "memory", "unexpected"])
def test_sdk_compile_errors_propagate(native, monkeypatch, kind):
    package = importlib.import_module("pcre2")
    if kind == "library":
        error = package.LibraryError(-1)
    elif kind == "memory":
        error = MemoryError("SDK allocation failure")
    else:
        error = RuntimeError("SDK compilation failure")

    def fail_compile(*args, **kwargs):
        raise error

    monkeypatch.setattr(package, "compile", fail_compile)
    with pytest.raises(type(error)) as exc:
        msgspec.Meta(pattern="^[A-Z]{2}$")
    assert exc.value is error


def test_native_provider_cycle(native):
    run_python(
        r"""
        import gc
        import sys
        import types
        import weakref
        import pcre2
        import msgspec

        original = pcre2._cy
        provider = types.ModuleType("pcre2._cy")
        provider._MATCHER_API_v1 = original._MATCHER_API_v1
        provider.LibraryError = original.LibraryError
        provider._BooleanMatcher = original._BooleanMatcher
        sys.modules["pcre2._cy"] = provider
        try:
            before = sys.getrefcount(provider)
            meta = msgspec.Meta(pattern="^[A-Z]{2,19}$")
            assert sys.getrefcount(provider) > before
            provider.owner = meta
            provider_ref = weakref.ref(provider)
            del meta, provider
        finally:
            sys.modules["pcre2._cy"] = original
        gc.collect()
        assert provider_ref() is None
        """
    )


@pytest.fixture(params=["json", "msgpack", "convert"])
def validate(request):
    if request.param == "convert":
        return lambda value, typ: msgspec.convert(value, typ, strict=True)
    proto = getattr(msgspec, request.param)
    return lambda value, typ: proto.decode(proto.encode(value), type=typ, strict=True)


@pytest.mark.parametrize(
    "pattern",
    [
        "^[a-zA-Z][a-zA-Z0-9_.:-]{0,63}$",
        "^[A-Z]{2}$",
        "^$",
        "^[-a]+$",
        "^[a-]+$",
        "^[a]*$",
        "^[a]+?$",
        "^[a]?b$",
        "^[a]{2}$",
        "^[a]{1,3}$",
        "^[a]{1,}$",
        "^[a]{1,3}?$",
        "^[a]{0,65535}$",
        "^[a]{0,65536}$",
        r"^[a]\.[0-9]+$",
        r"^[a]\$$",
        r"^[a]\\$",
        "cat",
        "",
        r"^\w+$",
        r"^\d+$",
        r"^\s$",
        r"^\v$",
        r"(?a)^\w+$",
        "(?i)^[a-z]$",
        "(?m)^a$",
        "(?s)^.$",
        r"a\Z",
        r"a(?=b)",
        r"(?<=a)b",
        r"(a)\1",
        r"(a)?(?(1)b|c)",
        "[^a]",
        "a|b",
        ".",
    ],
)
def test_patterns_match_re(pattern):
    oracle = re.compile(pattern)
    subjects = [
        "",
        "a",
        "aa",
        "aaa",
        "aaaa",
        "ab",
        "b",
        "c",
        "US",
        "a.12",
        "a$",
        "a\\",
        "-",
        "xxcatyy",
        "a\n",
        "a\n\n",
        "a\r\n",
        "é",
        "İ",
        "K",
        "²",
        "١",
        "\u0301",
        "\u203f",
        "\u001c",
        "\v",
        "\n",
        "\r",
        "\x00",
        "🙂",
    ]
    typ = Annotated[str, msgspec.Meta(pattern=pattern)]
    for subject in subjects:
        if oracle.search(subject) is None:
            with pytest.raises(msgspec.ValidationError):
                msgspec.convert(subject, typ)
        else:
            assert msgspec.convert(subject, typ) == subject


@pytest.mark.parametrize("pattern", [r"a\z", r"^\B$", "a(?i)b", "a*+a", "(?>a|ab)c"])
def test_version_sensitive_python_contract(pattern):
    error = None
    with warnings.catch_warnings(record=True) as reference_warnings:
        warnings.simplefilter("always")
        re.purge()
        try:
            oracle = re.compile(pattern)
        except re.error as exc:
            error = (type(exc), str(exc))
    expected_warnings = [
        (item.category, str(item.message)) for item in reference_warnings
    ]
    with warnings.catch_warnings(record=True) as actual_warnings:
        warnings.simplefilter("always")
        re.purge()
        if error is not None:
            with pytest.raises(error[0]) as exc:
                msgspec.Meta(pattern=pattern)
            assert str(exc.value) == error[1]
        else:
            meta = msgspec.Meta(pattern=pattern)
    assert [
        (item.category, str(item.message)) for item in actual_warnings
    ] == expected_warnings
    if error is not None:
        return
    typ = Annotated[str, meta]
    for subject in ("", "a", "a\n", "aaaa", "abc", "ac"):
        if oracle.search(subject) is None:
            with pytest.raises(msgspec.ValidationError):
                msgspec.convert(subject, typ)
        else:
            assert msgspec.convert(subject, typ) == subject


@pytest.mark.parametrize("pattern", ["^[A-Z]{2}$", ".", "a", r"^\w+$"])
def test_surrogates_follow_python_convert(pattern):
    oracle = re.compile(pattern)
    typ = Annotated[str, msgspec.Meta(pattern=pattern)]
    for subject in ("\ud800", "\udc00", "a\ud800", "US\ud800"):
        if oracle.search(subject) is None:
            with pytest.raises(msgspec.ValidationError):
                msgspec.convert(subject, typ)
        else:
            assert msgspec.convert(subject, typ) == subject


def test_protocol_and_key_constraints(validate):
    pattern = "^[A-Z]{2}$"
    key = Annotated[str, msgspec.Meta(pattern=pattern)]
    assert validate("US", key) == "US"
    with pytest.raises(msgspec.ValidationError) as exc:
        validate("bad", key)
    assert repr(pattern) in str(exc.value)
    typ = dict[key, list[key]]
    assert validate({"US": ["GB", "DE"]}, typ) == {"US": ["GB", "DE"]}
    for value in ({"bad": ["GB"]}, {"US": ["bad"]}):
        with pytest.raises(msgspec.ValidationError):
            validate(value, typ)


@pytest.mark.parametrize("pattern", ["^[A-Z]{2,21}$", r"^\w{1,15}$"])
def test_partial_type_construction_cleanup(pattern):
    meta = msgspec.Meta(pattern=pattern)
    (matcher,) = gc.get_referents(meta)
    text = Annotated[str, meta]
    invalid = Annotated[int, msgspec.Meta(min_length=1)]
    before = sys.getrefcount(matcher)
    with pytest.raises(TypeError):
        msgspec.json.Decoder(tuple[text, invalid])
    decoder = msgspec.json.Decoder(list[text])
    assert decoder.decode(b'["US"]') == ["US"]
    del decoder
    assert sys.getrefcount(matcher) == before


@pytest.mark.skipif(
    sys.platform in {"emscripten", "wasi"}, reason="Threads unavailable"
)
def test_shared_decoder_threaded():
    typ = Annotated[str, msgspec.Meta(pattern="^[A-Z]{2}$")]
    decoder = msgspec.json.Decoder(typ)
    barrier = Barrier(4)

    def work(worker):
        barrier.wait(timeout=10)
        assert decoder.decode(b'"US"') == "US"
        with pytest.raises(msgspec.ValidationError):
            decoder.decode(b'"bad"')
        return worker

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(work, range(4))) == list(range(4))


@pytest.mark.skipif(
    sys.platform in {"emscripten", "wasi"}, reason="Threads unavailable"
)
def test_first_concurrent_pattern_constructors():
    run_python(
        r"""
        import importlib.abc
        import sys
        import sysconfig
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from typing import Annotated

        if sysconfig.get_config_var("Py_GIL_DISABLED"):
            class BlockSDK(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "pcre2" or fullname.startswith("pcre2."):
                        raise AssertionError("Free-threaded constructor imported SDK")
            sys.meta_path.insert(0, BlockSDK())
        before = getattr(sys, "_is_gil_enabled", lambda: True)()
        import msgspec
        assert getattr(sys, "_is_gil_enabled", lambda: True)() == before
        barrier = Barrier(4)

        def work(worker):
            barrier.wait(timeout=10)
            width = worker + 1
            typ = Annotated[str, msgspec.Meta(pattern="^[A-Z]{" + str(width) + "}$")]
            decoder = msgspec.json.Decoder(typ)
            value = "A" * width
            assert decoder.decode(msgspec.json.encode(value)) == value
            try:
                decoder.decode(b'"bad"')
            except msgspec.ValidationError:
                pass
            else:
                raise AssertionError("Invalid subject accepted")
            return worker

        with ThreadPoolExecutor(max_workers=4) as pool:
            assert sorted(pool.map(work, range(4))) == list(range(4))
        assert getattr(sys, "_is_gil_enabled", lambda: True)() == before
        """
    )


def test_native_and_fallback_call_paths_and_lifetime(pcre2_available):
    run_python(
        r"""
        import gc
        import re
        import sys
        from typing import Annotated
        import weakref

        compile_original = re.compile
        refs = []

        class Spy:
            def __init__(self, regex):
                self.regex = regex
                self.pattern = regex.pattern
                self.calls = 0
                self.owner = None
                refs.append(weakref.ref(self))

            def search(self, value):
                self.calls += 1
                return self.regex.search(value)

        def compile_spy(pattern, flags=0):
            regex = compile_original(pattern, flags)
            if pattern in ("^[A-Z]{2}$", r"^\w+$", r"^\w{1,16}$") and flags == 0:
                return Spy(regex)
            return regex

        re.compile = compile_spy
        import msgspec

        available = sys.argv[1] == "1"
        if available:
            import pcre2
            def unexpected_search(*args, **kwargs):
                raise AssertionError("Public SDK search used on native path")
            pcre2.Pattern.search = unexpected_search
        for pattern, expected_calls in [
            ("^[A-Z]{2}$", 0 if available else 1),
            (r"^\w+$", 1),
        ]:
            meta = msgspec.Meta(pattern=pattern)
            spy = refs[-1]()
            typ = Annotated[str, meta]
            decoder = msgspec.json.Decoder(typ)
            assert decoder.decode(b'"US"') == "US"
            assert spy.calls == expected_calls, (pattern, spy.calls)
            if pattern == "^[A-Z]{2}$":
                for value in ("ÜS", "US\ud800"):
                    before = spy.calls
                    try:
                        msgspec.convert(value, typ)
                    except msgspec.ValidationError:
                        pass
                    else:
                        raise AssertionError("Invalid subject accepted")
                    assert spy.calls == before + 1
            del decoder, typ, meta, spy

        # This Meta is not held by Annotated's cache.
        meta = msgspec.Meta(pattern=r"^\w{1,16}$")
        spy = refs[-1]()
        spy.owner = meta
        spy_ref = weakref.ref(spy)
        del meta, spy
        gc.collect()
        assert spy_ref() is None
        """,
        "1" if pcre2_available else "0",
    )
