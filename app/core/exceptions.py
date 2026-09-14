"""Domain exception hierarchy for service-layer code.

Nothing raises these yet — they exist so that as each module migrates in
Phase 3, its service.py can raise a domain-shaped error (NotFoundError,
ConflictError, ...) instead of importing FastAPI's HTTPException directly,
without changing a single byte of what the client actually receives: the
handler registered below emits exactly the same
``{"detail": ...}`` JSON body, status code, and headers that raising
``HTTPException`` produces today.

Until every router is migrated, existing code continues to raise
``HTTPException`` directly and that keeps working unchanged — this handler
only intercepts the new ``AppError`` subclasses, it doesn't touch
``HTTPException`` handling at all (FastAPI's own default handler for that
stays exactly as it is).
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base for every domain-level error a service.py may raise.

    ``detail`` mirrors HTTPException's own field name so the JSON body a
    caller receives is identical either way: ``{"detail": <detail>}``.
    """

    status_code: int = 500

    def __init__(self, detail: str, headers: dict[str, str] | None = None) -> None:
        self.detail = detail
        self.headers = headers
        super().__init__(detail)


class BadRequestError(AppError):
    status_code = 400


class AuthenticationError(AppError):
    """401 — mirrors get_current_user's existing
    ``headers={"WWW-Authenticate": "Bearer"}`` contract; pass no headers to
    get just that default."""

    status_code = 401

    def __init__(self, detail: str = "Could not validate credentials", headers: dict[str, str] | None = None) -> None:
        super().__init__(detail, headers or {"WWW-Authenticate": "Bearer"})


class PermissionDeniedError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
