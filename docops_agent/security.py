from __future__ import annotations

import re
from dataclasses import dataclass, field
from secrets import compare_digest

ROLE_PERMISSIONS = {
    "reader": frozenset({"read"}),
    "operator": frozenset({"read", "operate"}),
    "admin": frozenset({"read", "operate", "admin"}),
}
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


@dataclass(frozen=True, slots=True)
class Principal:
    name: str
    role: str


@dataclass(frozen=True, slots=True)
class ApiCredential:
    name: str
    role: str
    secret: str = field(repr=False)


class ApiKeyAuthenticator:
    """Authenticate static API keys configured as name:role:secret entries."""

    def __init__(self, specification: str = "", *, required: bool = False) -> None:
        self.credentials = self._parse(specification)
        self.enabled = bool(self.credentials)
        if required and not self.enabled:
            raise ValueError("DOCOPS_API_KEYS is required in production")

    @staticmethod
    def _parse(specification: str) -> tuple[ApiCredential, ...]:
        credentials: list[ApiCredential] = []
        seen_names: set[str] = set()
        seen_secrets: set[str] = set()
        for raw_entry in specification.split(","):
            entry = raw_entry.strip()
            if not entry:
                continue
            parts = entry.split(":", maxsplit=2)
            if len(parts) != 3:
                raise ValueError("DOCOPS_API_KEYS entries must use name:role:secret")
            name, role, secret = (part.strip() for part in parts)
            if not IDENTIFIER_PATTERN.fullmatch(name):
                raise ValueError("API key names must contain only letters, digits, _ or -")
            if role not in ROLE_PERMISSIONS:
                raise ValueError("API key role must be reader, operator, or admin")
            if len(secret) < 24:
                raise ValueError("API key secrets must contain at least 24 characters")
            if name in seen_names:
                raise ValueError(f"Duplicate API key name: {name}")
            if secret in seen_secrets:
                raise ValueError("API key secrets must be unique")
            seen_names.add(name)
            seen_secrets.add(secret)
            credentials.append(ApiCredential(name=name, role=role, secret=secret))
        return tuple(credentials)

    def authenticate(self, supplied_key: str | None) -> Principal | None:
        if not self.enabled:
            return Principal(name="development", role="admin")
        if not supplied_key:
            return None
        matched: ApiCredential | None = None
        for credential in self.credentials:
            if compare_digest(supplied_key, credential.secret):
                matched = credential
        return Principal(matched.name, matched.role) if matched is not None else None

    @staticmethod
    def authorize(principal: Principal, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS[principal.role]
