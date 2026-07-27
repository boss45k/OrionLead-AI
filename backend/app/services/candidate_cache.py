"""
Candidate Cache
===============
Thread-safe, in-process cache for expensive lookups made during lead collection.
Prevents re-querying the same domain across multiple collection runs.

Keys stored (all keyed by domain string):
  domain:{domain}      → list of emails found on the contact/about page
  hunter:{domain}      → Hunter domain_search() result (list of lead dicts)
  mx:{domain}          → bool — does the domain have a valid MX record?
  failed:{domain}      → bool — all enrichment strategies failed for this domain

TTL: 24 hours by default (configurable per-key).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 86_400   # 24 hours in seconds
_MAX_ENTRIES = 5_000    # evict oldest when limit reached


class _CacheEntry:
    __slots__ = ('value', 'expires_at')

    def __init__(self, value: Any, ttl: int) -> None:
        self.value      = value
        self.expires_at = time.monotonic() + ttl


class CandidateCache:
    """
    Thread-safe TTL cache for domain-level lookups.

    Usage
    -----
    cache = CandidateCache()

    # Store Hunter results for a domain
    cache.set('hunter:acme.com', leads, ttl=3600)

    # Retrieve (returns None on miss or expiry)
    leads = cache.get('hunter:acme.com')

    # Mark a domain as permanently failed this session
    cache.mark_failed('baddomain.net')
    if cache.is_failed_domain('baddomain.net'):
        skip()
    """

    def __init__(self, default_ttl: int = _DEFAULT_TTL) -> None:
        self._store: Dict[str, _CacheEntry] = {}
        self._lock  = threading.Lock()
        self._default_ttl = default_ttl

    # ------------------------------------------------------------------
    # Core get / set
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Return cached value, or None if missing / expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value with the given TTL (seconds). Evicts oldest on overflow."""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = _CacheEntry(value, ttl)
            if len(self._store) > _MAX_ENTRIES:
                self._evict_oldest()

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    # ------------------------------------------------------------------
    # Domain-specific helpers
    # ------------------------------------------------------------------

    def get_domain_emails(self, domain: str) -> Optional[List[str]]:
        return self.get(f'domain:{domain}')

    def set_domain_emails(self, domain: str, emails: List[str], ttl: int = _DEFAULT_TTL) -> None:
        self.set(f'domain:{domain}', emails, ttl=ttl)

    def get_hunter_results(self, domain: str) -> Optional[List[dict]]:
        return self.get(f'hunter:{domain}')

    def set_hunter_results(self, domain: str, results: List[dict], ttl: int = _DEFAULT_TTL) -> None:
        self.set(f'hunter:{domain}', results, ttl=ttl)

    def get_mx(self, domain: str) -> Optional[bool]:
        return self.get(f'mx:{domain}')

    def set_mx(self, domain: str, has_mx: bool, ttl: int = _DEFAULT_TTL) -> None:
        self.set(f'mx:{domain}', has_mx, ttl=ttl)

    def is_failed_domain(self, domain: str) -> bool:
        """True if all enrichment attempts for this domain have already failed."""
        return bool(self.get(f'failed:{domain}'))

    def mark_failed(self, domain: str, ttl: int = _DEFAULT_TTL) -> None:
        """Record that this domain failed all enrichment — skip on next attempt."""
        self.set(f'failed:{domain}', True, ttl=ttl)
        logger.debug(f"[cache] marked failed domain: {domain}")

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            now = time.monotonic()
            active = sum(1 for e in self._store.values() if e.expires_at > now)
            return {'total': len(self._store), 'active': active, 'expired': len(self._store) - active}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _evict_oldest(self) -> None:
        """Remove the 10% oldest entries. Called under self._lock."""
        n_evict = max(1, len(self._store) // 10)
        # Sort by expiry ascending — oldest expire first
        sorted_keys = sorted(self._store, key=lambda k: self._store[k].expires_at)
        for k in sorted_keys[:n_evict]:
            del self._store[k]
        logger.debug(f"[cache] evicted {n_evict} oldest entries")


# ---------------------------------------------------------------------------
# Module-level singleton — shared across collectors within one worker process
# ---------------------------------------------------------------------------

_global_cache: Optional[CandidateCache] = None
_global_cache_lock = threading.Lock()


def get_candidate_cache() -> CandidateCache:
    """Return the process-wide CandidateCache singleton, creating it if needed."""
    global _global_cache
    if _global_cache is None:
        with _global_cache_lock:
            if _global_cache is None:
                _global_cache = CandidateCache()
                logger.info('[cache] CandidateCache singleton initialised')
    return _global_cache
