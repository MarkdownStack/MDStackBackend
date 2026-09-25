"""Request/response shapes for POST /api/chat/proxy.

The proxy endpoint is deliberately thin — it receives what the frontend
already constructed (a messages array, a model string, and the user's own
API key) and forwards it straight to Anthropic. No business logic lives
here; this file is just the wire contract.

The user's api_key travels in the request body rather than a header
because the frontend sends it via a regular JSON POST — the Authorization
header on this request already carries the user's own JWT (enforced by
get_current_user on the route). Keeping the two tokens in separate fields
makes it unambiguous which is which when the proxy reads them.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatProxyRequest(BaseModel):
    # The model string the frontend resolved from the user's provider
    # selection, e.g. "claude-sonnet-4-6". Validated only for
    # non-emptiness here — Anthropic's own API returns a clear error if the
    # model doesn't exist, which we pipe straight back to the browser.
    model: str = Field(..., min_length=1)

    # The user's own Anthropic API key — never stored, never logged,
    # forwarded once to api.anthropic.com and then forgotten.
    api_key: str = Field(..., min_length=1)

    # Full conversation history. The system prompt is prepended by the
    # router before forwarding, so callers don't need to include it — but
    # if a caller does send a system message first, it's passed through
    # as-is (Anthropic accepts it).
    messages: list[ChatMessage]

    # Token budget for the response. Capped at 4096 here so a misbehaving
    # client can't request an unbounded completion through our proxy and
    # burn through the user's quota unexpectedly — 4096 is generous for
    # a note-length response.
    max_tokens: int = Field(default=4096, ge=1, le=4096)
