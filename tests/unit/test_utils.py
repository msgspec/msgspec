from __future__ import annotations

from typing import Generic, TypeVar

import pytest

from msgspec._utils import get_class_annotations

from .utils import temp_module

T = TypeVar("T")
S = TypeVar("S")
U = TypeVar("U")


class Base(Generic[T]):
    x: T


class Base2(Generic[T, S]):
    a: T
    b: S


class TestGetClassAnnotations:
    @pytest.mark.parametrize("future_annotations", [False, True])
    def test_eval_scopes(self, future_annotations):
        header = "from __future__ import annotations" if future_annotations else ""
        source = f"""
        {header}
        STR = str

        class Ex:
            LOCAL = float
            x: int
            y: LOCAL
            z: STR
        """
        with temp_module(source) as mod:
            assert get_class_annotations(mod.Ex) == {"x": int, "y": float, "z": str}

    def test_none_to_nonetype(self):
        class Ex:
            x: None

        assert get_class_annotations(Ex) == {"x": type(None)}

    def test_subclass(self):
        class Base:
            x: int
            y: str

        class Sub(Base):
            x: float
            z: list

        class Base2:
            a: int

        class Sub2(Sub, Base2):
            b: float
            y: list

        assert get_class_annotations(Base) == {"x": int, "y": str}
        assert get_class_annotations(Sub) == {"x": float, "y": str, "z": list}
        assert get_class_annotations(Sub2) == {
            "x": float,
            "y": list,
            "z": list,
            "a": int,
            "b": float,
        }

    def test_simple_generic(self):
        class Test(Generic[T]):
            x: T
            y: list[T]
            z: int

        assert get_class_annotations(Test) == {"x": T, "y": list[T], "z": int}
        assert get_class_annotations(Test[int]) == {"x": int, "y": list[int], "z": int}
        assert get_class_annotations(Test[set[T]]) == {
            "x": set[T],
            "y": list[set[T]],
            "z": int,
        }

    def test_generic_sub1(self):
        class Sub(Base):
            y: int

        assert get_class_annotations(Sub) == {"x": T, "y": int}

    def test_generic_sub2(self):
        class Sub(Base, Generic[T]):
            y: list[T]

        assert get_class_annotations(Sub) == {"x": T, "y": list[T]}
        assert get_class_annotations(Sub[int]) == {"x": T, "y": list[int]}

    def test_generic_sub3(self):
        class Sub(Base[int], Generic[T]):
            y: list[T]

        assert get_class_annotations(Sub) == {"x": int, "y": list[T]}
        assert get_class_annotations(Sub[float]) == {"x": int, "y": list[float]}

    def test_generic_sub4(self):
        class Sub(Base[T]):
            y: list[T]

        assert get_class_annotations(Sub) == {"x": T, "y": list[T]}
        assert get_class_annotations(Sub[int]) == {"x": int, "y": list[int]}

    def test_generic_sub5(self):
        class Sub(Base[T], Generic[T]):
            y: list[T]

        assert get_class_annotations(Sub) == {"x": T, "y": list[T]}
        assert get_class_annotations(Sub[int]) == {"x": int, "y": list[int]}

    def test_generic_sub6(self):
        class Sub(Base[S]):
            y: list[S]

        assert get_class_annotations(Sub) == {"x": S, "y": list[S]}
        assert get_class_annotations(Sub[int]) == {"x": int, "y": list[int]}

    def test_generic_sub7(self):
        class Sub(Base[list[T]]):
            y: set[T]

        assert get_class_annotations(Sub) == {"x": list[T], "y": set[T]}
        assert get_class_annotations(Sub[int]) == {"x": list[int], "y": set[int]}

    def test_generic_sub8(self):
        class Sub(Base[int], Base2[float, str]):
            pass

        assert get_class_annotations(Sub) == {"x": int, "a": float, "b": str}

    def test_generic_sub9(self):
        class Sub(Base[U], Base2[list[U], U]):
            y: str

        assert get_class_annotations(Sub) == {"y": str, "x": U, "a": list[U], "b": U}
        assert get_class_annotations(Sub[int]) == {
            "y": str,
            "x": int,
            "a": list[int],
            "b": int,
        }

        class Sub2(Sub[int]):
            x: list

        assert get_class_annotations(Sub2) == {
            "x": list,
            "y": str,
            "a": list[int],
            "b": int,
        }

    def test_generic_sub10(self):
        class Sub(Base[U], Base2[list[U], U]):
            y: str

        class Sub3(Sub[list[T]]):
            c: T

        assert get_class_annotations(Sub3) == {
            "c": T,
            "y": str,
            "x": list[T],
            "a": list[list[T]],
            "b": list[T],
        }
        assert get_class_annotations(Sub3[int]) == {
            "c": int,
            "y": str,
            "x": list[int],
            "a": list[list[int]],
            "b": list[int],
        }

    def test_generic_sub11(self):
        class Sub(Base[int]):
            y: float

        class Sub2(Sub, Base[int]):
            z: str

        assert get_class_annotations(Sub2) == {"x": int, "y": float, "z": str}

    def test_generic_invalid_parameters(self):
        class Invalid:
            @property
            def __parameters__(self):
                pass

        class Sub(Base[Invalid]):
            pass

        assert get_class_annotations(Sub) == {"x": Invalid}

    def test_union_backport_installed(self):
        class Ex:
            x: int | None = None

        assert get_class_annotations(Ex) == {"x": int | None}
