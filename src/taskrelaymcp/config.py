from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class BootstrapAdmin:
    username: str
    display_name: str
    password: str


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    is_admin: bool
    channel: str
    mcp_key_id: int | None = None
    mcp_key_name: str | None = None
    cookie_authenticated: bool = False

    @property
    def actor(self) -> str:
        return self.username if self.channel == "WEB" else f"{self.username} via {self.mcp_key_name}"


def database_url() -> str:
    return os.getenv("TASKRELAY_DATABASE_URL", "sqlite:////data/workspace.db")


def bootstrap_admin() -> BootstrapAdmin:
    username = os.getenv("TASKRELAY_ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("TASKRELAY_ADMIN_PASSWORD", "")
    display_name = os.getenv("TASKRELAY_ADMIN_DISPLAY_NAME", "Administrator").strip()
    if not username or not password:
        raise RuntimeError("TASKRELAY_ADMIN_USERNAME and TASKRELAY_ADMIN_PASSWORD are required")
    return BootstrapAdmin(username, display_name or username, password)


def secure_cookies() -> bool:
    return os.getenv("TASKRELAY_SECURE_COOKIES", "true").lower() not in {"0", "false", "no"}


def public_origin() -> str | None:
    origin = os.getenv("TASKRELAY_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if not origin:
        return None
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError("TASKRELAY_PUBLIC_ORIGIN must be an http(s) origin without a path")
    return origin
