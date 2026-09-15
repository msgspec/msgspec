from __future__ import annotations

from typing import Any

from . import NODEFAULT, Struct, field
from ._core import (  # noqa
    Factory as _Factory,
    StructConfig,
    StructMeta,
    asdict,
    astuple,
    force_setattr,
    replace,
)
from ._utils import get_class_annotations as _get_class_annotations

__all__ = (
    "FieldInfo",
    "StructConfig",
    "asdict",
    "astuple",
    "fields",
    "force_setattr",
    "replace",
)


def __dir__():
    return __all__


class FieldInfo(Struct):
    """A record describing a field in a struct type.

    Parameters
    ----------
    name: str
        The field name as seen by Python code (e.g. ``field_one``).
    encode_name: str
        The name used when encoding/decoding the field. This may differ if
        the field is renamed (e.g. ``fieldOne``).
    type: Any
        The full field type annotation.
    default: Any, optional
        A default value for the field. Will be `NODEFAULT` if no default value
        is set.
    default_factory: Any, optional
        A callable that creates a default value for the field. Will be
        `NODEFAULT` if no ``default_factory`` is set.
    int_key: int or None, optional
        The integer key used when encoding/decoding the field as msgpack, if the
        field is configured via the struct's ``int_keys`` mapping. ``None`` if the
        field uses its (string) ``encode_name`` instead.
    """

    name: str
    encode_name: str
    type: Any
    default: Any = field(default_factory=lambda: NODEFAULT)
    default_factory: Any = field(default_factory=lambda: NODEFAULT)
    int_key: "int | None" = None

    @property
    def required(self) -> bool:
        """A helper for checking whether a field is required"""
        return self.default is NODEFAULT and self.default_factory is NODEFAULT


def fields(type_or_instance: Struct | type[Struct]) -> tuple[FieldInfo]:
    """Get information about the fields in a Struct.

    Parameters
    ----------
    type_or_instance:
        A struct type or instance.

    Returns
    -------
    tuple[FieldInfo]
    """
    obj = type_or_instance

    # Struct class
    if isinstance(obj, StructMeta):
        annotated_cls = cls = obj
    # Struct instance
    elif isinstance(type(obj), StructMeta):
        annotated_cls = cls = type(obj)
    # Generic alias
    else:
        annotated_cls = obj
        cls = getattr(obj, "__origin__", obj)
        if not isinstance(cls, StructMeta):
            raise TypeError("Must be called with a struct type or instance")

    hints = _get_class_annotations(annotated_cls)
    npos = len(cls.__struct_fields__) - len(cls.__struct_defaults__)
    encode_int_keys = cls.__struct_encode_int_keys__  # tuple[int|None] or None
    fields = []
    for idx, (name, encode_name, default_obj) in enumerate(zip(
        cls.__struct_fields__,
        cls.__struct_encode_fields__,
        (NODEFAULT,) * npos + cls.__struct_defaults__,
    )):
        default = default_factory = NODEFAULT
        if isinstance(default_obj, _Factory):
            default_factory = default_obj.factory
        elif default_obj is not NODEFAULT:
            default = default_obj

        field = FieldInfo(
            name=name,
            encode_name=encode_name,
            type=hints[name],
            default=default,
            default_factory=default_factory,
            int_key=None if encode_int_keys is None else encode_int_keys[idx],
        )
        fields.append(field)

    return tuple(fields)
