"""Middleware to detect reverse-proxy path prefix from x-forwarded-prefix header."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.security import SAFE_PREFIX_RE


class ProxyPrefixMiddleware(BaseHTTPMiddleware):
    """Read x-forwarded-prefix header and store it in request.state for downstream use."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        prefix = request.headers.get("x-forwarded-prefix", "")
        # Validate and store per-request (not in shared app.state)
        if prefix and SAFE_PREFIX_RE.match(prefix):
            request.state.forwarded_prefix = prefix
        else:
            request.state.forwarded_prefix = ""
        return await call_next(request)
