from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from secrets import compare_digest


class Permission(StrEnum):
    READ = "READ"
    READ_WRITE = "READ_WRITE"


@dataclass(frozen=True)
class Principal:
    name: str
    permission: Permission


def database_url() -> str:
    return os.getenv("TASKRELAY_DATABASE_URL", "sqlite:////data/workspace.db")


def configured_tokens() -> dict[str, Principal]:
    """Parse TASKRELAY_TOKENS as token:permission entries separated by commas."""
    result: dict[str, Principal] = {}
    for index, entry in enumerate(filter(None, os.getenv("TASKRELAY_TOKENS", "").split(",")), 1):
        token, separator, raw_permission = entry.rpartition(":")
        if not separator or not token:
            raise RuntimeError("TASKRELAY_TOKENS entries must be token:READ or token:READ_WRITE")
        try:
            permission = Permission(raw_permission)
        except ValueError as exc:
            raise RuntimeError(f"Invalid permission in TASKRELAY_TOKENS entry {index}") from exc
        result[token] = Principal(name=f"token-{index}", permission=permission)
    return result


def authenticate(authorization: str | None) -> Principal | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    supplied = authorization.removeprefix("Bearer ")
    for token, principal in configured_tokens().items():
        if compare_digest(supplied, token):
            return principal
    return None
