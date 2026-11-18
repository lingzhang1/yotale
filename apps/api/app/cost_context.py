"""Cost attribution context for the request path.

Sets the model-gateway call context (story_user_id, correlation_id, operation) for the duration of a request so
every `model_call_usage` log line is attributable to a user and a route without changing any engine signature.
Registered INNERMOST (closest to the handler) so request.state.principal is already resolved by the auth
boundary. Opaque backend ids and the route template only: never prompts, media, tokens or emails.
"""
from __future__ import annotations

import uuid

from fastapi import Request

try:
    from model_gateway import call_context
except Exception:  # pragma: no cover - import-safe when the package is not bundled
    call_context = None  # type: ignore


def _uid(request: Request):
    p = getattr(request.state, "principal", None)
    if p is None or getattr(p, "is_legacy", False):
        return None
    return getattr(p, "story_user_id", None)


async def cost_context_middleware(request: Request, call_next):
    if call_context is None:
        return await call_next(request)
    route = request.scope.get("route")
    operation = f"{request.method} {getattr(route, 'path', None) or request.url.path}"
    # ContextVar set BEFORE call_next: the handler task/threadpool copies it. Reset on the way out.
    with call_context(story_user_id=_uid(request), correlation_id=str(uuid.uuid4()), operation=operation):
        return await call_next(request)
