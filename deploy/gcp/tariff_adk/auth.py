"""Google ID tokens for calling the Cloud Run MCP server. Deploy-ready, not deployed.

Cloud Run with IAM invoker checks accepts `Authorization: Bearer <ID token>` whose
audience is the service URL, from a principal with roles/run.invoker
(run/docs/authenticating/service-to-service, checked 2026-09-28). On Google Cloud the
token comes from the metadata server through google-auth. Tokens live about an hour;
they are cached and refreshed five minutes before expiry.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from urllib.parse import urlparse


def audience_for(url: str) -> str:
    """Cloud Run expects the service URL (scheme and host, no path) as the audience."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:  # noqa: BLE001
        return time.time() + 300


class IdTokenHeaders:
    """ADK McpToolset header_provider: returns the Authorization header for each MCP session."""

    def __init__(self, audience: str, fetch=None):
        self.audience = audience
        self._fetch = fetch
        self._token = ""
        self._exp = 0.0
        self._lock = threading.Lock()

    def _default_fetch(self, audience: str) -> str:
        import google.auth.transport.requests
        import google.oauth2.id_token

        return google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)

    def token(self) -> str:
        with self._lock:
            if not self._token or time.time() > self._exp - 300:
                self._token = (self._fetch or self._default_fetch)(self.audience)
                self._exp = _exp(self._token)
            return self._token

    # Agent Runtime pickles the agent at deploy time; locks and tokens do not travel.
    def __getstate__(self) -> dict:
        return {"audience": self.audience, "_fetch": self._fetch}

    def __setstate__(self, state: dict) -> None:
        self.__init__(state["audience"], state["_fetch"])

    def __call__(self, _ctx=None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}
