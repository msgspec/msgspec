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

T = TypeVar("T")

enc_hook_sig: TypeAlias = Callable[[Any], Any] | None
ext_hook_sig: TypeAlias = Callable[[int, memoryview], Any] | None
dec_hook_sig: TypeAlias = Callable[[type, Any], Any] | None

@final
class Ext:
    code: int
    data: bytes | bytearray | memoryview
    def __init__(self, code: int, data: bytes | bytearray | memoryview) -> None: ...

@final
class Decoder(Generic[T]):
    type: Type[T]  # needed for mypy, because of the same name
    strict: bool
    dec_hook: dec_hook_sig
    ext_hook: ext_hook_sig
    @overload
    def __init__(
        self: Decoder[Any],
        *,
        strict: bool = True,
        dec_hook: dec_hook_sig = None,
        ext_hook: ext_hook_sig = None,
    ) -> None: ...
    @overload
    def __init__(
        self: Decoder[T],
        type: Type[T] = ...,
        *,
        strict: bool = True,
        dec_hook: dec_hook_sig = None,
        ext_hook: ext_hook_sig = None,
    ) -> None: ...
    @overload
    def __init__(
        self: Decoder[Any],
        type: Any = ...,
        *,
        strict: bool = True,
        dec_hook: dec_hook_sig = None,
        ext_hook: ext_hook_sig = None,
    ) -> None: ...
    def decode(self, buf: Buffer, /) -> T: ...

@final
class Encoder:
    enc_hook: enc_hook_sig
    decimal_format: Literal["string", "number"]
    uuid_format: Literal["canonical", "hex", "bytes"]
    order: Literal[None, "deterministic", "sorted"]
    def __init__(
        self,
        *,
        enc_hook: enc_hook_sig = None,
        decimal_format: Literal["string", "number"] = "string",
        uuid_format: Literal["canonical", "hex", "bytes"] = "canonical",
        order: Literal[None, "deterministic", "sorted"] = None,
    ): ...
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
    dec_hook: dec_hook_sig = None,
    ext_hook: ext_hook_sig = None,
) -> Any: ...
@overload
def decode(
    buf: Buffer,
    /,
    *,
    type: type[T] = ...,
    strict: bool = True,
    dec_hook: dec_hook_sig = None,
    ext_hook: ext_hook_sig = None,
) -> T: ...
@overload
def decode(
    buf: Buffer,
    /,
    *,
    type: Any = ...,
    strict: bool = True,
    dec_hook: dec_hook_sig = None,
    ext_hook: ext_hook_sig = None,
) -> Any: ...
def encode(
    obj: Any,
    /,
    *,
    enc_hook: enc_hook_sig = None,
    order: Literal[None, "deterministic", "sorted"] = None,
) -> bytes: ...
