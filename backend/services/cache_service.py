"""
Phase 14 — Performance & Scaling (Redis Caching)
===============================================
Caching layer for OCR results and snippets.
"""

import os
import json
import hashlib
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Conditional redis import — gracefully degrade if not installed
try:
    import redis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False
    logger.warning("[CACHE] redis package not installed. Caching disabled.")


class CacheService:
    def __init__(self):
        self.enabled = os.getenv("USE_CACHE", "true").lower() == "true"
        self.url = os.getenv("REDIS_URL")
        self.token = os.getenv("REDIS_TOKEN")

        self.client = None
        if self.enabled and self.url and _HAS_REDIS:
            try:
                self.client = redis.from_url(self.url, decode_responses=True)
                self.client.ping()
                logger.info("[CACHE] Redis connected.")
            except Exception as e:
                logger.warning(f"[CACHE] Redis connection failed: {e}. Caching disabled.")
                self.enabled = False
        elif not _HAS_REDIS:
            self.enabled = False

    @property
    def is_connected(self) -> bool:
        """Health check: returns True if Redis is reachable."""
        if not self.enabled or not self.client:
            return False
        try:
            return self.client.ping()
        except Exception:
            return False

    def _get_key(self, prefix: str, data: Any) -> str:
        """Generates a stable key based on data hash."""
        if isinstance(data, bytes):
            content = data
        else:
            content = str(data).encode('utf-8')
        h = hashlib.sha256(content).hexdigest()
        return f"pipeline:{prefix}:{h}"

    # ── OCR Result Caching ───────────────────────────────────────────────────

    def get_ocr(self, image_bytes: bytes) -> Optional[dict]:
        if not self.enabled or not self.client:
            return None

        key = self._get_key("ocr", image_bytes)
        try:
            cached = self.client.get(key)
            if cached:
                logger.debug(f"[CACHE] Hit: {key}")
                return json.loads(cached)
        except Exception:
            pass
        return None

    def set_ocr(self, image_bytes: bytes, result: dict, ttl: int = 86400):
        if not self.enabled or not self.client:
            return

        key = self._get_key("ocr", image_bytes)
        try:
            self.client.setex(key, ttl, json.dumps(result))
            logger.debug(f"[CACHE] Set: {key}")
        except Exception:
            pass

    # ── Snippet Caching ──────────────────────────────────────────────────────

    def get_snippet(self, request_id: str, field_id: str) -> Optional[str]:
        """Retrieve cached snippet (base64-encoded image crop)."""
        if not self.enabled or not self.client:
            return None

        key = f"pipeline:snippet:{request_id}:{field_id}"
        try:
            return self.client.get(key)
        except Exception:
            pass
        return None

    def set_snippet(self, request_id: str, field_id: str, data: str, ttl: int = 86400):
        """Cache a snippet (base64-encoded image crop) for fast retrieval."""
        if not self.enabled or not self.client:
            return

        key = f"pipeline:snippet:{request_id}:{field_id}"
        try:
            self.client.setex(key, ttl, data)
            logger.debug(f"[CACHE] Snippet cached: {key}")
        except Exception:
            pass


_cache_instance = None

def get_cache_service() -> CacheService:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheService()
    return _cache_instance
