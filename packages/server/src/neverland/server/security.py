"""Token authentication for the API.

The API is guarded by a single shared secret (bearer token). It is the second
layer behind the network boundary (wireguard): even a device that reaches the
port cannot read or write without the token. When no token is configured the
guard is a no-op, which is only safe on loopback (enforced by the CLI).
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from .config import ServerConfig


def require_token(request: Request) -> None:
    """Reject requests that lack a valid ``Authorization: Bearer`` token.

    A no-op when the server has no token configured. Applied as a router-level
    dependency, so it guards every ``/api`` endpoint uniformly.

    Parameters
    ----------
    request : fastapi.Request
        Incoming request; the active :class:`ServerConfig` is read from
        ``request.app.state.config``.

    Raises
    ------
    fastapi.HTTPException
        401 when a token is configured and the request does not present it.
    """
    config: ServerConfig = request.app.state.config
    token = config.token
    if not token:
        return

    scheme, _, provided = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(provided, token):
        raise HTTPException(
            status_code=401,
            detail="invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
