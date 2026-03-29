from __future__ import annotations


class AuthService:
    """Placeholder auth/token service for seat and host operations."""

    def verify(self, token: str) -> dict:
        return {"ok": bool(token)}

