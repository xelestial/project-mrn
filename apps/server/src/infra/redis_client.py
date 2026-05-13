from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import urlparse


class RedisClientProtocol(Protocol):
    def ping(self) -> bool:
        ...

    def info(self, section: str | None = None) -> dict[str, object]:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class RedisConnectionSettings:
    url: str
    key_prefix: str = "mrn"
    socket_timeout_ms: int = 1000


class RedisConnection:
    def __init__(
        self,
        settings: RedisConnectionSettings,
        *,
        client_factory: Callable[[], RedisClientProtocol] | None = None,
    ) -> None:
        self._settings = settings
        self._uses_default_client_factory = client_factory is None
        self._client_factory = client_factory or self._build_default_client
        self._client: RedisClientProtocol | None = None

    @property
    def settings(self) -> RedisConnectionSettings:
        return self._settings

    @property
    def uses_default_client_factory(self) -> bool:
        return self._uses_default_client_factory

    def client(self) -> RedisClientProtocol:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def key(self, *parts: str) -> str:
        cleaned = [self._settings.key_prefix.strip(":")]
        for part in parts:
            normalized = str(part or "").strip(":")
            if normalized:
                cleaned.append(normalized)
        return ":".join(item for item in cleaned if item)

    def health_check(self) -> dict[str, object]:
        client = self.client()
        ping_ok = bool(client.ping())
        info = client.info("server")
        parsed = urlparse(self._settings.url)
        db_text = parsed.path.lstrip("/") if parsed.path else ""
        database = int(db_text) if db_text.isdigit() else 0
        hash_tag = self.cluster_hash_tag()
        return {
            "configured": True,
            "ok": ping_ok,
            "version": str(info.get("redis_version", "")),
            "key_prefix": self._settings.key_prefix,
            "cluster_hash_tag": hash_tag,
            "cluster_hash_tag_valid": bool(hash_tag),
            "database": database,
        }

    def cluster_hash_tag(self) -> str:
        prefix = str(self._settings.key_prefix or "")
        start = prefix.find("{")
        end = prefix.find("}", start + 1)
        if start < 0 or end < 0 or end <= start + 1:
            return ""
        if prefix.find("{", start + 1) >= 0 or prefix.find("}", end + 1) >= 0:
            return ""
        return prefix[start + 1 : end]

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.close()
        except Exception:
            pass
        self._client = None

    def _build_default_client(self) -> RedisClientProtocol:
        from redis import Redis

        timeout_seconds = max(0.05, self._settings.socket_timeout_ms / 1000)
        return Redis.from_url(
            self._settings.url,
            decode_responses=True,
            socket_timeout=timeout_seconds,
            socket_connect_timeout=timeout_seconds,
            health_check_interval=30,
        )
