"""Process-wide TTL cache shared by every session.

Yahoo rate-limits aggressively (HTTP 429), so identical requests from different
visitors, tabs and the watchlist must hit the network once per TTL window.
"""

from __future__ import annotations

import functools
import threading
from collections import Counter
from typing import Callable, TypeVar

from cachetools import TTLCache

from .. import config

T = TypeVar("T")

_caches = {bucket: TTLCache(maxsize=512, ttl=ttl) for bucket, ttl in config.CACHE_TTL.items()}
_locks = {bucket: threading.Lock() for bucket in config.CACHE_TTL}

# Hit/miss counters, handy for checking that repeat visits avoid the network
stats: Counter[str] = Counter()


def cached(bucket: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Cache a provider method's result in ``bucket``, keyed by its arguments (excluding self)."""
    cache = _caches[bucket]
    lock = _locks[bucket]

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            key = (func.__qualname__, id(self), args, tuple(sorted(kwargs.items())))
            with lock:
                if key in cache:
                    stats[f"{bucket}.hit"] += 1
                    return cache[key]
            stats[f"{bucket}.miss"] += 1
            value = func(self, *args, **kwargs)
            with lock:
                cache[key] = value
            return value

        return wrapper

    return decorator


def clear() -> None:
    for bucket, cache in _caches.items():
        with _locks[bucket]:
            cache.clear()
    stats.clear()
