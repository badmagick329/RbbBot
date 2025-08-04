from typing import Generic, Optional, TypeVar, Union, cast

T = TypeVar("T")
E = TypeVar("E")


class Result(Generic[T, E]):
    __slots__ = ("_value", "_error")
    _NO_ARG = object()

    def __init__(
        self,
        value: Union[T, object] = _NO_ARG,
        error: Union[E, object] = _NO_ARG,
    ) -> None:
        if (value is self._NO_ARG) == (error is self._NO_ARG):
            raise ValueError(
                "Result must be created with exactly one of value or error"
            )

        self._value = None if value is self._NO_ARG else value
        self._error = None if error is self._NO_ARG else error

    @property
    def is_ok(self) -> bool:
        return self._error is None

    @property
    def is_err(self) -> bool:
        return self._error is not None

    @staticmethod
    def Ok(value: T) -> "Result[T, E]":
        return Result(value=value)

    @staticmethod
    def Err(error: E) -> "Result[T, E]":
        return Result(error=error)

    def unwrap(self) -> T:
        if self.is_err:
            raise RuntimeError(f"Called unwrap on Err: {self._error!r}")
        # mypy sees _value as Optional, so we cast
        return cast(T, self._value)

    def unwrap_or(self, default: T) -> T:
        return self._value if self.is_ok else default  # type: ignore

    def unwrap_err(self) -> E:
        if self.is_ok:
            raise RuntimeError("Called unwrap_err on Ok")
        # mypy sees _error as Optional, so we cast
        return cast(E, self._error)

    def __repr__(self) -> str:
        if self.is_ok:
            return f"Ok({self._value!r})"
        return f"Err({self._error!r})"
