"""Model helpers for the additive encrypted-storage migration."""

import json
from dataclasses import dataclass
from typing import Any, Callable

from rbb_bot.services.data_encryption_service import get_data_encryption_service


_MISSING = object()


@dataclass(frozen=True)
class EncryptedFieldSpec:
    ciphertext_field: str
    legacy_field: str | None = None
    default: Any = _MISSING
    encode: Callable[[Any], str] = str
    decode: Callable[[str], Any] = str
    lookup_field: str | None = None
    normalize_lookup: Callable[[Any], str] | None = None


class EncryptedValue:
    def __init__(
        self,
        ciphertext_field: str,
        legacy_field: str | None = None,
        *,
        default: Any = _MISSING,
        encode: Callable[[Any], str] = str,
        decode: Callable[[str], Any] = str,
        lookup_field: str | None = None,
        normalize_lookup: Callable[[Any], str] | None = None,
    ):
        self.spec = EncryptedFieldSpec(
            ciphertext_field=ciphertext_field,
            legacy_field=legacy_field,
            default=default,
            encode=encode,
            decode=decode,
            lookup_field=lookup_field,
            normalize_lookup=normalize_lookup,
        )

    def __set_name__(self, owner, name):
        self.name = name
        inherited = dict(getattr(owner, "_encrypted_field_specs", {}))
        inherited[name] = self.spec
        owner._encrypted_field_specs = inherited

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        ciphertext = getattr(instance, self.spec.ciphertext_field)
        if ciphertext is not None:
            return self.spec.decode(get_data_encryption_service().decrypt(ciphertext))
        if self.spec.legacy_field:
            legacy_value = getattr(instance, self.spec.legacy_field)
            if legacy_value is not None:
                return legacy_value
        if self.spec.default is not _MISSING:
            return self.spec.default
        return None

    def __set__(self, instance, value):
        if value is None:
            setattr(instance, self.spec.ciphertext_field, None)
            if self.spec.lookup_field:
                setattr(instance, self.spec.lookup_field, None)
            return
        service = get_data_encryption_service()
        setattr(
            instance,
            self.spec.ciphertext_field,
            service.encrypt(self.spec.encode(value)),
        )
        if self.spec.lookup_field and self.spec.normalize_lookup:
            setattr(
                instance,
                self.spec.lookup_field,
                service.lookup_token(self.spec.normalize_lookup(value)),
            )


class EncryptedModelMixin:
    """Accept encrypted public attributes during normal Tortoise model creation."""

    _encrypted_field_specs: dict[str, EncryptedFieldSpec] = {}

    def __init__(self, **kwargs):
        supplied = {
            name: kwargs.pop(name)
            for name in self._encrypted_field_specs
            if name in kwargs
        }
        super().__init__(**kwargs)
        for name, value in supplied.items():
            setattr(self, name, value)
        for name, spec in self._encrypted_field_specs.items():
            if (
                name not in supplied
                and spec.default is not _MISSING
                and getattr(self, spec.ciphertext_field) is None
                and (
                    spec.legacy_field is None
                    or getattr(self, spec.legacy_field) in {None, ""}
                )
            ):
                setattr(self, name, spec.default)


def encode_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def decode_json(value: str) -> Any:
    return json.loads(value)
