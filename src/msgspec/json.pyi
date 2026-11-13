import decimal
from collections.abc import Callable, Iterable
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
_DecHookSig: TypeAlias = Callable[[type, Any], Any] | None
_FloatHookSig: TypeAlias = Callable[[str], Any] | None
_SchemaHookSig: TypeAlias = Callable[[type], dict[str, Any]] | None
_DecimalFormatSig: TypeAlias = (
    Callable[[decimal.Decimal], Any] | Literal["string", "number"]
)

@final
class Encoder:
    enc_hook: Final[_EncHookSig]
    decimal_format: Final[_DecimalFormatSig]
    uuid_format: Final[Literal["canonical", "hex"]]
    order: Final[Literal["deterministic", "sorted"] | None]

    def __init__(
        self,
        *,
        enc_hook: _EncHookSig = None,
        decimal_format: _DecimalFormatSig = "string",
        uuid_format: Literal["canonical", "hex"] = "canonical",
        order: Literal["deterministic", "sorted"] | None = None,
    ) -> None: ...
    def encode(self, obj: Any, /) -> bytes: ...
    def encode_lines(self, items: Iterable[Any], /) -> bytes: ...
    def encode_into(self, obj: Any, buffer: bytearray, offset: int = 0, /) -> None: ...

@final
class Decoder(Generic[_T]):
    strict: Final[bool]
    dec_hook: Final[_DecHookSig]
    float_hook: Final[_FloatHookSig]

    @overload
    def __init__(
        self: Decoder[_T],
        type: TypeForm[_T],
        *,
        strict: bool = True,
        dec_hook: _DecHookSig = None,
        float_hook: _FloatHookSig = None,
    ) -> None: ...
    @overload
    def __init__(
        self: Decoder[Any],
        type: Any = Any,
        *,
        strict: bool = True,
        dec_hook: _DecHookSig = None,
        float_hook: _FloatHookSig = None,
    ) -> None: ...
    def decode(self, buf: Buffer | str, /) -> _T: ...
    def decode_lines(self, buf: Buffer | str, /) -> list[_T]: ...
    def __class_getitem__(cls, item: Any, /) -> GenericAlias: ...
    # This is `READONLY` in C, but we can't use `Final` here:
    @property
    def type(self) -> TypeForm[_T]: ...

@overload
def decode(
    buf: Buffer | str,
    /,
    *,
    type: TypeForm[_T],
    strict: bool = True,
    dec_hook: _DecHookSig = None,
) -> _T: ...
@overload
def decode(
    buf: Buffer | str,
    /,
    *,
    type: Any = Any,
    strict: bool = True,
    dec_hook: _DecHookSig = None,
) -> Any: ...
def encode(
    obj: Any,
    /,
    *,
    enc_hook: _EncHookSig = None,
    order: Literal["deterministic", "sorted"] | None = None,
) -> bytes: ...
def schema(
    type: Any,
    *,
    schema_hook: _SchemaHookSig = None,
    ref_template: str = "#/$defs/{name}",
) -> dict[str, Any]: ...
def schema_components(
    types: Iterable[Any],
    *,
    schema_hook: _SchemaHookSig = None,
    ref_template: str = "#/$defs/{name}",
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]: ...
@overload
def format(buf: str, *, indent: int = 2) -> str: ...
@overload
def format(buf: Buffer, *, indent: int = 2) -> bytes: ...
