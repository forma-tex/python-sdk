"""Low-level HTTP transport for FormatEx API."""

from __future__ import annotations

import httpx

from formatex.exceptions import (
    FormatExError,
    AuthenticationError,
    CompilationError,
    RateLimitError,
    PlanLimitError,
)


class HTTPClient:
    """Thin wrapper around httpx providing auth and error mapping."""

    def __init__(self, api_key: str, base_url: str, timeout: float):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    # -- helpers ---------------------------------------------------------------

    def get_json(self, path: str) -> dict:
        resp = self._client.get(path)
        self._raise_for_status(resp)
        return resp.json()

    def post_json(self, path: str, body: dict) -> dict:
        """POST with JSON body, expect JSON back (uses Accept header)."""
        resp = self._client.post(
            path,
            json=body,
            headers={"Accept": "application/json"},
        )
        self._raise_for_status(resp)
        return resp.json()

    def post_pdf(self, path: str, body: dict) -> bytes:
        """POST with JSON body, get raw PDF bytes back."""
        resp = self._client.post(path, json=body)
        self._raise_for_status(resp)
        return resp.content

    # -- error mapping ---------------------------------------------------------

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return

        try:
            body = resp.json()
        except Exception:
            body = {}
        msg = body.get("error", resp.text[:200])

        if resp.status_code == 401:
            raise AuthenticationError(msg, status_code=401, body=body)
        if resp.status_code == 403:
            raise PlanLimitError(msg, status_code=403, body=body)
        if resp.status_code == 422:
            raise CompilationError(
                msg,
                log=body.get("log", ""),
                status_code=422,
                body=body,
            )
        if resp.status_code == 429:
            retry = float(resp.headers.get("Retry-After", "0"))
            raise RateLimitError(msg, retry_after=retry, status_code=429, body=body)

        raise FormatExError(msg, status_code=resp.status_code, body=body)
