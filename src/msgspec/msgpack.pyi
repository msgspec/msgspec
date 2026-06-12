from collections.abc import Callable
from typing import (
    Any,
    Generic,
    Literal,
    Type,
    TypeAlias,
    TypeVar,
    final,
    overload,
)

from typing_extensions import Buffer

_T = TypeVar("_T")

_enc_hook_sig: TypeAlias = Callable[[Any], Any] | None
_ext_hook_sig: TypeAlias = Callable[[int, memoryview], Any] | None
_dec_hook_sig: TypeAlias = Callable[[type, Any], Any] | None

@final
class Ext:
    code: int
    data: Buffer
    def __init__(self, code: int, data: Buffer) -> None: ...

@final
class Decoder(Generic[_T]):
    type: Type[_T]  # needed for mypy, because of the same name
    strict: bool
    dec_hook: _dec_hook_sig
    ext_hook: _ext_hook_sig
    @overload
    def __init__(
        self: Decoder[Any],
        *,
        strict: bool = True,
        dec_hook: _dec_hook_sig = None,
        ext_hook: _ext_hook_sig = None,
    ) -> None: ...
    @overload
    def __init__(
        self: Decoder[_T],
        type: Type[_T] = ...,
        *,
        strict: bool = True,
        dec_hook: _dec_hook_sig = None,
        ext_hook: _ext_hook_sig = None,
    ) -> None: ...
    @overload
    def __init__(
        self: Decoder[Any],
        type: Any = ...,
        *,
        strict: bool = True,
        dec_hook: _dec_hook_sig = None,
        ext_hook: _ext_hook_sig = None,
    ) -> None: ...
    def decode(self, buf: Buffer, /) -> _T: ...

@final
class Encoder:
    enc_hook: _enc_hook_sig
    decimal_format: Literal["string", "number"]
    uuid_format: Literal["canonical", "hex", "bytes"]
    order: Literal["deterministic", "sorted"] | None
    def __init__(
        self,
        *,
        enc_hook: _enc_hook_sig = None,
        decimal_format: Literal["string", "number"] = "string",
        uuid_format: Literal["canonical", "hex", "bytes"] = "canonical",
        order: Literal["deterministic", "sorted"] | None = None,
    ) -> None: ...
    def encode(self, obj: Any, /) -> bytes: ...
    def encode_into(
        self, obj: Any, buffer: bytearray, offset: int | None = 0, /
    ) -> None: ...

@overload
def decode(
    buf: Buffer,
    /,
    *,
    strict: bool = True,
    dec_hook: _dec_hook_sig = None,
    ext_hook: _ext_hook_sig = None,
) -> Any: ...
@overload
def decode(
    buf: Buffer,
    /,
    *,
    type: type[_T] = ...,
    strict: bool = True,
    dec_hook: _dec_hook_sig = None,
    ext_hook: _ext_hook_sig = None,
) -> _T: ...
@overload
def decode(
    buf: Buffer,
    /,
    *,
    type: Any = ...,
    strict: bool = True,
    dec_hook: _dec_hook_sig = None,
    ext_hook: _ext_hook_sig = None,
) -> Any: ...
def encode(
    obj: Any,
    /,
    *,
    enc_hook: _enc_hook_sig = None,
    order: Literal[None, "deterministic", "sorted"] = None,
) -> bytes: ...
