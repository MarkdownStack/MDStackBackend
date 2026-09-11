import asyncio
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .database import request_stats_collection


class RequestCounterMiddleware(BaseHTTPMiddleware):
    """Best-effort counter of API traffic, bucketed by UTC calendar day —
    powers the "how many requests hit so far" number on the admin
    dashboard (see routers/admin.py).

    Two things keep this from ever affecting a real request:
      - The Mongo increment is fired via asyncio.create_task rather than
        awaited, so recording a hit never adds a round trip's worth of
        latency to the response it's counting.
      - Any failure while recording (Mongo hiccup, etc.) is swallowed —
        losing a count is fine, breaking a request to keep one is not.

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
            await request_stats_collection.update_one(
                {"_id": today},
                {"$inc": {"count": 1, f"methods.{method}": 1}},
                upsert=True,
            )
        except Exception:
            # Stats bookkeeping should never take the app down with it.
            pass
