from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, overload

from . import DecodeError, convert as _convert, to_builtins as _to_builtins

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal

    from typing_extensions import Buffer

__all__ = ("encode", "decode")


def __dir__():
    return __all__


def _import_error_with_msg(func_name: str):
    return ImportError(
        (
            f"`msgspec.json5.{func_name}` requires `pyjson5` or `json5` be installed.\n\n"
            "Please pip insall it as follows:\n\n"
            "  $ python -m pip install pyjson5 # for pyjson5 \n\n"
            "  $ python -m pip install json5   # for json5  "
        )
    )


def _import_json5_encode() -> Callable[[Any], str]:
    # use faster cython library before falling
    # back to pure json5 using fastest functions
    # known.
    try:
        import pyjson5  # type: ignore

        return pyjson5.encode
    except ImportError:
        pass

    try:
        import functools

        import json5  # type: ignore

        return functools.partial(json5.dumps, quote_keys=True)
    except ImportError:
        raise _import_error_with_msg("encode") from None


def _import_json5_decode() -> Callable[[Buffer | str], Any]:
    # use faster cython library before falling
    # back to pure json5 using fastest functions
    # known.
    try:
        import pyjson5  # type: ignore

        def decode(bits: Buffer | str) -> Any:
            try:
                if isinstance(bits, str):
                    return pyjson5.decode(bits)
                return pyjson5.decode_buffer(bytes(bits))
            except pyjson5.Json5Exception as e:
                raise DecodeError(e.message) from e

        return decode
    except ImportError:
        pass

    try:
        import json5  # type: ignore

        def decode(bits: Buffer | str) -> Any:
            try:
                if isinstance(bits, str):
                    return json5.loads(bits)
                return json5.loads(bytes(bits))
            except (ValueError, UnicodeDecodeError) as e:
                raise DecodeError(e.args) from e

        return decode
    except ImportError:
        raise _import_error_with_msg("decode") from None


def encode(
    obj: Any,
    *,
    enc_hook: Callable[[Any], Any] | None = None,
    order: Literal["deterministic", "sorted"] | None = None,
) -> bytes:
    """Serialize an object as JSON5.

    Parameters
    ----------
    obj : Any
        The object to serialize.
    enc_hook : callable, optional
        A callable to call for objects that aren't supported msgspec types.
        Takes the unsupported object and should return a supported object, or
        raise a ``NotImplementedError`` if unsupported.
    order : {None, 'deterministic', 'sorted'}, optional
        The ordering to use when encoding unordered compound types.
            - ``None``: All objects are encoded in the most efficient manner
              matching their in-memory representations. The default.
            - `'deterministic'`: Dict keys and set elements are sorted so that
              values which compare equal produce identical encoded output,
              regardless of insertion or iteration order. Useful when
              comparison/hashing of the encoded binary output is necessary.
            - `'sorted'`: Like `'deterministic'`, but *all* object-like types
              (structs, dataclasses, ...) are also sorted by field name before
              encoding. This is slower than `'deterministic'`, but may produce more
              human-readable output.

    Returns
    -------
    data : bytes
        The serialized object.

    Notes
    -----
    This function requires that either `Cython PyJson5 library
    <https://pyjson5.k6i.de/en/latest/>`_ or
    `Pure Python Json5 library <https://github.com/dpranke/pyjson5>`_ is installed.
    `PyJson5` will be attempted before `Json5` as fallback.

    See Also
    --------
    decode
    """

    json5_encode = _import_json5_encode()
    return json5_encode(_to_builtins(obj, enc_hook=enc_hook, order=order)).encode(
        "utf-8"
    )


_T = TypeVar("_T")


@overload
def decode(
    buf: Buffer | str,
    *,
    type: type[_T],
    strict: bool = True,
    dec_hook: Callable[[type[Any], Any], Any] | None = None,
) -> _T: ...


@overload
def decode(
    buf: Buffer | str,
    *,
    type: Any = ...,
    strict: bool = True,
    dec_hook: Callable[[type[Any], Any], Any] | None = None,
) -> Any: ...


def decode(
    buf: Buffer | str,
    *,
    type: Any = Any,
    strict: bool = True,
    dec_hook: Callable[[type[Any], Any], Any] | None = None,
) -> Any:
    """Deserialize an object from JSON5.

    Parameters
    ----------
    buf : bytes-like or str
        The message to decode.

    type : type, optional
        A Python type (in type annotation form) to decode the object as. If
        provided, the message will be type checked and decoded as the specified
        type. Defaults to `Any`, in which case the message will be decoded
        using the default JSON5 types.
    strict : bool, optional
            Whether type coercion rules should be strict. Setting to False enables
            a wider set of coercion rules from string to non-string types for all
            values. Default is True.
    dec_hook : callable, optional
            An optional callback for handling decoding custom types. Should have
            the signature ``dec_hook(type: Type, obj: Any) -> Any``, where ``type``
            is the expected message type, and ``obj`` is the decoded representation
            composed of only basic JSON5 types. This hook should transform ``obj``
            into type ``type``, or raise a ``NotImplementedError`` if unsupported.

    Returns
    -------
    obj : Any
        The deserialized object.

    Notes
    -----
    This function requires that either `Cython PyJson5 library
    <https://pyjson5.k6i.de/en/latest/>`_ or `Pure Python Json5
    library <https://github.com/dpranke/pyjson5>`_ is installed.
    `PyJson5` will be attempted before `Json5` as fallback.

    See Also
    --------
    encode
    """
    json5_decode = _import_json5_decode()

    return _convert(
        json5_decode(buf),
        type,
        dec_hook=dec_hook,
        strict=strict,
    )
