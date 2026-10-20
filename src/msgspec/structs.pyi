from typing import Any, Final, TypeVar, final

from . import NODEFAULT, Struct

__all__ = (
    "FieldInfo",
    "StructConfig",
    "asdict",
    "astuple",
    "fields",
    "force_setattr",
    "replace",
)

_S = TypeVar("_S", bound=Struct)

def replace(struct: _S, /, **changes: Any) -> _S: ...
def asdict(struct: Struct, /) -> dict[str, Any]: ...
def astuple(struct: Struct, /) -> tuple[Any, ...]: ...
def force_setattr(struct: Struct, name: str, value: Any, /) -> None: ...

@final
class StructConfig:
    frozen: Final[bool]
    eq: Final[bool]
    order: Final[bool]
    array_like: Final[bool]
    gc: Final[bool]
    repr_omit_defaults: Final[bool]
    omit_defaults: Final[bool]
    forbid_unknown_fields: Final[bool]
    weakref: Final[bool]
    dict: Final[bool]
    cache_hash: Final[bool]
    tag: Final[str | int | None]
    tag_field: Final[str | None]

class FieldInfo(Struct):
    name: str
    encode_name: str
    type: Any
    default: Any = NODEFAULT
    default_factory: Any = NODEFAULT

    @property
    def required(self) -> bool: ...

def fields(type_or_instance: Struct | type[Struct]) -> tuple[FieldInfo, ...]: ...
