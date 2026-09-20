import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..db.postgres import session_scope


class RequestCounterMiddleware(BaseHTTPMiddleware):
    """Best-effort counter of API traffic, bucketed by UTC calendar day —
    powers the "how many requests hit so far" number on the admin
    dashboard (see modules/admin).

    Two things keep this from ever affecting a real request:
      - The write is fired via asyncio.create_task rather than awaited, so
        recording a hit never adds a round trip's worth of latency to the
        response it's counting.
      - Any failure while recording (a Postgres hiccup, etc.) is
        swallowed — losing a count is fine, breaking a request to keep one
        is not.

    CORS preflights (OPTIONS), the bare /api/health check, and the admin
    endpoints themselves are excluded — none of them are "real" traffic,
    and counting /api/admin/* would mean checking the dashboard bumps the
    very number you're looking at.
    """

    SKIP_PATHS = {"/api/health"}
    SKIP_PREFIXES = ("/api/admin",)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        if (
            request.method != "OPTIONS"
            and path not in self.SKIP_PATHS
            and not path.startswith(self.SKIP_PREFIXES)
        ):
            asyncio.create_task(self._record(request.method))

        return response

    @staticmethod
    async def _record(method: str) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            async with session_scope() as session:
                # The Postgres equivalent of the old Mongo
                # $inc: {count: 1, f"methods.{method}": 1} upsert — one row
                # per UTC day, an atomic upsert so two concurrent requests
                # on the same day never race each other's increment.
                # Every :method bind is cast to (…)::text explicitly, in
                # parentheses — two things going on:
                #   1. Left uncast, asyncpg can't infer a type for it
                #      inside jsonb_build_object()/ARRAY[] on its own
                #      (raises AmbiguousParameterError).
                #   2. `:method::text` *without* the parentheses silently
                #      fails to bind at all — SQLAlchemy's text() reserves
                #      bare `name::type` for a literal Postgres cast on a
                #      column, so it never treats that `:method` as a bind
                #      parameter and leaves the literal text
                #      "':method::text'" in the SQL untouched. Wrapping the
                #      bind in parens (`(:method)::text`) sidesteps that
                #      entirely — confirmed against a real Postgres in this
                #      migration's smoke test.
                await session.execute(
                    text(
                        """
                        INSERT INTO request_stats (date, count, methods)
                        VALUES (:date, 1, jsonb_build_object((:method)::text, 1))
                        ON CONFLICT (date) DO UPDATE SET
                            count = request_stats.count + 1,
                            methods = jsonb_set(
                                request_stats.methods,
                                ARRAY[(:method)::text],
                                to_jsonb(COALESCE((request_stats.methods ->> (:method)::text)::int, 0) + 1)
                            )
                        """
                    ),
                    {"date": today, "method": method},
                )
        except Exception:
            # Stats bookkeeping should never take the app down with it.
            pass


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamps every response with a unique X-Request-ID (also stashed on
    request.state for anything downstream that wants to correlate a
    single request's log lines)."""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
