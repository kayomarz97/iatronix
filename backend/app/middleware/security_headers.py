"""Baseline security response headers for all API responses.

Defense-in-depth: the browser-facing site (Next.js) sets its own headers, but the
API should not rely on that. These headers are safe for a JSON API — no CSP here
(the API serves data, not HTML), so nothing in the app breaks.
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_HEADERS = {
    # Force HTTPS for 2 years incl. subdomains (site is HTTPS-only on Cloud Run).
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    # Stop MIME sniffing.
    "X-Content-Type-Options": "nosniff",
    # This API is never meant to be framed.
    "X-Frame-Options": "DENY",
    # Do not leak URLs to third parties.
    "Referrer-Policy": "no-referrer",
    # Drop powerful browser features the API never uses.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for key, value in _HEADERS.items():
            response.headers.setdefault(key, value)
        return response
