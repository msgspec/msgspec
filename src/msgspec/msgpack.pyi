import decimal
from collections.abc import Callable
from types import GenericAlias
from typing import (
    Any,
    Final,
    Generic,
    Literal,
    TypeAlias,
    TypeVar,
    final,
    overload,
)

from typing_extensions import Buffer, TypeForm

_T = TypeVar("_T")

_EncHookSig: TypeAlias = Callable[[Any], Any] | None
_ExtHookSig: TypeAlias = Callable[[int, memoryview], Any] | None
_DecHookSig: TypeAlias = Callable[[type[Any], Any], Any] | None
_DecimalFormatSig: TypeAlias = (
    Callable[[decimal.Decimal], Any] | Literal["string", "number"]
)

@final
class Ext:
    code: Final[int]
    data: Final[Buffer]
    def __init__(self, code: int, data: Buffer, /) -> None: ...

@final
class Decoder(Generic[_T]):
    strict: Final[bool]
    dec_hook: Final[_DecHookSig]
    ext_hook: Final[_ExtHookSig]

    @overload
    def __init__(
        self: Decoder[_T],
        type: TypeForm[_T],
        *,
        strict: bool = True,
        dec_hook: _DecHookSig = None,
        ext_hook: _ExtHookSig = None,
    ) -> None: ...
    @overload
    def __init__(
        self: Decoder[Any],
        type: Any = Any,
        *,
        strict: bool = True,
        dec_hook: _DecHookSig = None,
        ext_hook: _ExtHookSig = None,
    ) -> None: ...
    def decode(self, buf: Buffer, /) -> _T: ...
    def __class_getitem__(cls, item: Any, /) -> GenericAlias: ...
    # This is `READONLY` in C, but we can't use `Final` here:
    @property
    def type(self) -> TypeForm[_T]: ...

@final
class Encoder:
    enc_hook: Final[_EncHookSig]
    decimal_format: Final[_DecimalFormatSig]
    uuid_format: Final[Literal["canonical", "hex", "bytes"]]
    order: Final[Literal["deterministic", "sorted"] | None]
    def __init__(
        self,
        *,
        enc_hook: _EncHookSig = None,
        decimal_format: _DecimalFormatSig = "string",
        uuid_format: Literal["canonical", "hex", "bytes"] = "canonical",
        order: Literal["deterministic", "sorted"] | None = None,
    ) -> None: ...
    def encode(self, obj: Any, /) -> bytes: ...
    def encode_into(self, obj: Any, buffer: bytearray, offset: int = 0, /) -> None: ...

@overload
def decode(
    buf: Buffer,
    /,
    *,
    type: TypeForm[_T],
    strict: bool = True,
    dec_hook: _DecHookSig = None,
    ext_hook: _ExtHookSig = None,
) -> _T: ...
@overload
def decode(
    buf: Buffer,
    /,
    *,
    type: Any = Any,
    strict: bool = True,
    dec_hook: _DecHookSig = None,
    ext_hook: _ExtHookSig = None,
) -> Any: ...
def encode(
    obj: Any,
    /,
    *,
    enc_hook: _EncHookSig = None,
    order: Literal["deterministic", "sorted"] | None = None,
) -> bytes: ...
