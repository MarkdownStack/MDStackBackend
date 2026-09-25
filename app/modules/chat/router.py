"""HTTP binding for POST /api/chat/proxy.

This is the only route in the chat module — a thin SSE proxy that exists
solely because api.anthropic.com blocks direct browser requests (CORS).
OpenAI and Groq are called browser-direct; only Anthropic traffic comes
through here. See frontend/src/hooks/useChat.js for the client side.

Auth required: the user's JWT gates this endpoint so strangers can't use
our server as an anonymous Anthropic proxy. Their own Anthropic API key
(in the request body) is what actually authenticates the upstream call —
this server has no Anthropic key of its own.

Streaming design: httpx opens an async stream to Anthropic and we yield
each raw SSE line straight to the browser via FastAPI's StreamingResponse.
No buffering, no parsing — the frontend already knows how to consume
Anthropic's SSE format. If Anthropic returns a non-2xx, we forward the
status code and body as a plain (non-streaming) JSON error instead so the
frontend's error handler can read it.
"""

import json

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...shared.dependencies import get_current_user
from .schemas import ChatProxyRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Anthropic's messages endpoint — the only upstream this proxy ever calls.
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# The version header Anthropic requires on every request.
ANTHROPIC_VERSION = "2023-06-01"

# System prompt prepended to every conversation. Instructs the model to
# respond with pure markdown so the frontend can create the note directly
# from the streamed text without any post-processing.
SYSTEM_PROMPT = """You are a note-writing assistant for MarkdownStack, a personal markdown vault app.

When asked to create a note, respond with ONLY the markdown content of the note:
- Start with a single `# Title` as the very first line
- Use proper markdown throughout: headings, **bold**, `code`, fenced code blocks, bullet lists, numbered lists, tables — whatever fits the content
- No preamble before the title
- No explanation or closing remarks after the note ends
- The entire response is the note content, nothing else

If the user asks a question rather than requesting a note, answer conversationally in plain markdown. You may still use headings and lists where they help clarity."""


async def _stream_anthropic(payload: dict, api_key: str):
    """Open an async stream to Anthropic and yield raw SSE bytes.

    Each chunk that comes back from Anthropic is a complete SSE line
    (e.g. `data: {"type":"content_block_delta",...}\n\n`). We yield them
    as-is so the browser's EventSource / fetch-reader loop sees exactly the
    same event stream Anthropic would have sent if CORS weren't in the way.

    On a non-2xx from Anthropic we raise an httpx.HTTPStatusError, which
    the caller (the route below) catches and converts into a plain JSON
    error response — same shape FastAPI's own exception handler uses so the
    frontend error path doesn't need a special case.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
        # Tells Anthropic to send the response as SSE rather than waiting
        # for the full completion and sending it all at once.
        "accept": "text/event-stream",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", ANTHROPIC_MESSAGES_URL, headers=headers, json=payload) as response:
            # Forward non-2xx as an exception so the route can return a
            # clean error instead of trying to stream a JSON error body.
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk


@router.post("/proxy")
async def chat_proxy(
    payload: ChatProxyRequest,
    current_user: dict = Depends(get_current_user),
):
    """Proxy a streaming chat request to Anthropic.

    Prepends the system prompt (so callers don't have to include it),
    forwards the rest of the payload as-is, and streams Anthropic's SSE
    response straight back to the browser.

    current_user is required but unused beyond gating access — we only
    need to know the caller is authenticated, not who they are, since the
    note creation step happens client-side after the stream completes.
    """
    # Build the upstream payload. System prompt is always first; the
    # caller's messages follow. Anthropic doesn't accept a "system" role
    # inside the messages array (that's OpenAI's convention) — it takes
    # system as a top-level field instead.
    upstream_payload = {
        "model": payload.model,
        "max_tokens": payload.max_tokens,
        "stream": True,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": m.role, "content": m.content} for m in payload.messages],
    }

    try:
        return StreamingResponse(
            _stream_anthropic(upstream_payload, payload.api_key),
            # Mirror Anthropic's own content-type so the browser's fetch
            # reader loop sees the expected SSE media type and doesn't
            # buffer the response waiting for it to "finish".
            media_type="text/event-stream",
            headers={
                # Disable any intermediary (nginx, CDN) from buffering the
                # stream — without this, some reverse proxies accumulate the
                # whole response before forwarding it, which defeats the
                # point of streaming entirely.
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
            },
        )
    except httpx.HTTPStatusError as exc:
        # Anthropic returned a non-2xx (bad key, model not found, quota
        # exceeded, etc.). Forward the status and body as plain JSON so the
        # frontend's error handler can surface a readable message.
        try:
            detail = exc.response.json()
        except Exception:
            detail = {"error": exc.response.text}
        from fastapi import HTTPException
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except httpx.TimeoutException:
        from fastapi import HTTPException
        raise HTTPException(status_code=504, detail={"error": "Upstream timeout from Anthropic"})
