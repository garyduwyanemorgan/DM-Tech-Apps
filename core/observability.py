"""Per-request correlation id (Layer 0 observability).

Every inbound HTTP request is assigned a short id, either propagated from an
``X-Request-Id`` header set by the caller or minted fresh. That id is:

  - echoed back on the response as ``X-Request-Id``,
  - available to any code running "inside" that request via
    :func:`current_request_id`, so ``core/audit.py`` can stamp every emitted
    audit event with it,
  - available to anything that logs, so a user-reported symptom ("the button
    did nothing at 14:32") can be traced to one exact server-side chain of
    audit rows and log lines.

WHY ``contextvars`` AND NOT A GLOBAL / THREAD-LOCAL
-----------------------------------------------------
This server is ASGI (FastAPI/Starlette) and handles many requests
concurrently on the same thread via ``asyncio``. A plain module-level global
would be shared and overwritten by whichever request last set it — two
concurrent requests would stamp each other's audit events with the wrong id.
A ``threading.local`` fares no better: asyncio multiplexes many concurrent
requests onto the same OS thread, so a thread-local is exactly as broken as a
global in that world, and it also does not propagate correctly across
``await`` points or into tasks spawned to handle a request.

``contextvars.ContextVar`` is the one primitive that gets this right: each
``asyncio`` Task (Starlette gives each request its own Task) gets its own
copy of the context, set once when the request comes in, visible to every
``await``-chained coroutine underneath it, and never bleeding into a sibling
request's task. It is also what Starlette's own internals (and libraries
like structlog) build on for exactly this reason.
"""
from __future__ import annotations

import contextvars
import logging
import secrets
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-Id"

_log = logging.getLogger(__name__)

# Module-level ContextVar — NOT a global value, a per-context slot. See the
# module docstring for why this is required instead of a plain global.
_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def new_request_id() -> str:
    """Mint a short, URL-safe request id. Cheap: one urandom call, no I/O."""
    # 12 hex chars == 6 random bytes; collision risk is irrelevant here since
    # the id is a correlation token, not a security credential.
    return secrets.token_hex(6)


def current_request_id() -> Optional[str]:
    """The request id for the currently executing request, if any.

    Returns ``None`` outside of a request context (e.g. a script, a test that
    never went through the middleware, a background job). Callers that must
    never raise (like ``core/audit.py``) should treat ``None`` as normal.
    """
    return _request_id_var.get()


def set_request_id(rid: str) -> contextvars.Token:
    """Set the current request id, returning a token for :func:`reset_request_id`."""
    return _request_id_var.set(rid)


def reset_request_id(token: contextvars.Token) -> None:
    """Undo a prior :func:`set_request_id` call, restoring the previous value."""
    _request_id_var.reset(token)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a request id and echoes it on the response.

    - If the inbound request carries ``X-Request-Id``, that value is reused
      (so an upstream caller — n8n, a load balancer, another service — can
      propagate its own id through this server).
    - Otherwise a fresh id is minted via :func:`new_request_id`.
    - The id is stashed in the contextvar for the lifetime of this request's
      Task (via :func:`set_request_id` / :func:`reset_request_id`), so
      ``core/audit.py`` and any log line can read it with
      :func:`current_request_id`.
    - The id is set on the response's ``X-Request-Id`` header, whether the
      request succeeded, raised, or was denied.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Resolution order matters, and the middle term is not optional.
        #
        # api_server.py registers this middleware on BOTH the outer portal app
        # and the api_app mounted beneath it, so for every /api/* request the
        # dispatch below runs TWICE. Minting unconditionally there produces two
        # different ids: the inner one reaches the route handler and every audit
        # row, while the outer one overwrites the response header on the way
        # out. The user is then handed an id that appears nowhere in the logs —
        # precisely the failure this layer exists to prevent.
        #
        # Checking the contextvar makes nesting idempotent: an inner instance
        # adopts the id an outer instance already established. An inbound header
        # still wins, so an upstream caller can force correlation across
        # services.
        rid = (
            request.headers.get(REQUEST_ID_HEADER)
            or current_request_id()
            or new_request_id()
        )
        token = set_request_id(rid)
        try:
            try:
                response = await call_next(request)
            except Exception:
                # An unhandled exception would otherwise propagate past this
                # middleware to Starlette's ServerErrorMiddleware, which sits
                # OUTSIDE us and builds its 500 with the raw `send` — so the
                # header line below would never run and the client would get
                # the one response with no correlation id on it. That is the
                # exact response a user reports, so it is the one that most
                # needs an id.
                #
                # We therefore answer the 500 ourselves. The traceback is not
                # lost: it is logged here at exception level before we return,
                # which is what ServerErrorMiddleware would have done.
                # HTTPException never reaches this branch — FastAPI's
                # ExceptionMiddleware handles those further in.
                _log.exception("unhandled error while handling request %s", rid)
                response = JSONResponse(
                    status_code=500,
                    # Surfacing the id in the body as well as the header lets a
                    # user quote it from the UI without opening devtools.
                    content={"detail": "Internal Server Error", "request_id": rid},
                )
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
