"""Thin async HTTP client around the MarkdownStack FastAPI backend.

Deliberate design choice: this talks to the backend over its existing REST
API (the same one the React frontend uses) instead of importing
`app.database` / Motor and hitting MongoDB directly. That means every write
this MCP server makes still goes through the routers' own validation —
unique-title checks, tag/link extraction, the recursive folder-delete
safety, the public/private boundary in routers/public.py, etc. — instead of
a second copy of that logic living here that could drift from the real
thing. The cost is one extra network hop per call, which is irrelevant for
an interactive MCP tool.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:5000"


class MarkdownStackError(RuntimeError):
    """Raised for any non-2xx backend response, carrying the backend's own
    `detail` message (FastAPI's standard error shape) when there is one."""


class MarkdownStackClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("MDSTACK_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        # A pre-issued token (MDSTACK_ACCESS_TOKEN) lets a caller skip
        # auth_login entirely. Otherwise we lazily log in on first
        # auth-requiring call using MDSTACK_EMAIL/MDSTACK_PASSWORD, if set.
        self._token: str | None = os.getenv("MDSTACK_ACCESS_TOKEN") or None
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    async def aclose(self) -> None:
        await self._http.aclose()

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            raise MarkdownStackError(
                "Not logged in. Call auth_login(email, password) first, or set "
                "MDSTACK_ACCESS_TOKEN (or MDSTACK_EMAIL + MDSTACK_PASSWORD) in the "
                "environment before starting this server."
            )
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            detail = None
            try:
                detail = response.json().get("detail")
            except Exception:
                pass
            raise MarkdownStackError(detail or f"{response.request.method} {response.request.url} -> {response.status_code}")

    async def _maybe_auto_login(self) -> None:
        if self._token:
            return
        email = os.getenv("MDSTACK_EMAIL")
        password = os.getenv("MDSTACK_PASSWORD")
        if email and password:
            await self.login(email, password)

    async def login(self, email: str, password: str) -> None:
        # /api/auth/login is an OAuth2PasswordRequestForm endpoint: form-encoded
        # body, field name "username" (routers/auth.py treats it as the email).
        response = await self._http.post("/api/auth/login", data={"username": email, "password": password})
        self._raise_for_status(response)
        self._token = response.json()["access_token"]

    async def register(self, email: str, password: str) -> dict:
        response = await self._http.post("/api/auth/register", json={"email": email, "password": password})
        self._raise_for_status(response)
        return response.json()

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        auth: str = "required",  # "required" | "optional" | "none"
        **kwargs: Any,
    ) -> Any:
        """auth="required" raises if there's no token available; "optional"
        attaches a token if one is available (auto-logging in if configured)
        but proceeds anonymously otherwise; "none" never attaches one."""
        headers = dict(kwargs.pop("headers", None) or {})
        if auth in ("required", "optional"):
            await self._maybe_auto_login()
        if auth == "required":
            headers.update(self._auth_headers())
        elif auth == "optional" and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        response = await self._http.request(method, path, headers=headers, **kwargs)
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def request_binary(self, method: str, path: str, *, json: Any = None) -> tuple[bytes, str]:
        """Like request_json, but for endpoints that stream a binary body
        (currently just /api/export) instead of JSON. Returns (content, filename),
        filename parsed out of Content-Disposition the same way the frontend does."""
        await self._maybe_auto_login()
        headers = self._auth_headers()
        response = await self._http.request(method, path, headers=headers, json=json)
        self._raise_for_status(response)
        content_disposition = response.headers.get("content-disposition", "")
        filename = "export.zip"
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=", 1)[1].strip('"; ')
        return response.content, filename
