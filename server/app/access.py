"""A shared-password gate for deployments, until real auth exists.

HTTP basic auth on every request except the health check, configured by BM_AUTH_USER and
BM_AUTH_PASSWORD. Both unset: no gate (local development). Only one set: refuse to start.
Serve it behind HTTPS; basic auth sends the password with every request.
"""

import base64
import binascii
import secrets
from collections.abc import Mapping

OPEN_PATHS = frozenset({"/api/health"})
REALM = "Block model builder"


class GateConfigError(RuntimeError):
    """The gate is half-configured. The message names the missing variable."""


def credentials_from_env(env: Mapping[str, str]) -> tuple[str, str] | None:
    user, password = env.get("BM_AUTH_USER", ""), env.get("BM_AUTH_PASSWORD", "")
    if not user and not password:
        return None
    if not user or not password:
        missing = "BM_AUTH_USER" if not user else "BM_AUTH_PASSWORD"
        raise GateConfigError(
            f"{missing} is not set. Set both BM_AUTH_USER and BM_AUTH_PASSWORD to turn on the "
            "password gate, or unset both to run without it."
        )
    return user, password


class BasicAuthGate:
    """ASGI middleware: 401 with a Basic challenge unless the request carries the shared credentials."""

    def __init__(self, app, credentials: tuple[str, str]):
        self.app = app
        self.expected = f"{credentials[0]}:{credentials[1]}".encode()

    def _allowed(self, headers: list[tuple[bytes, bytes]]) -> bool:
        value = next((v for k, v in headers if k == b"authorization"), b"")
        scheme, _, token = value.partition(b" ")
        if scheme.lower() != b"basic":
            return False
        try:
            given = base64.b64decode(token.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        return secrets.compare_digest(given, self.expected)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS or self._allowed(scope["headers"]):
            await self.app(scope, receive, send)
            return
        body = b"Sign in with the shared username and password for this deployment."
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"www-authenticate", f'Basic realm="{REALM}", charset="UTF-8"'.encode()),
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
