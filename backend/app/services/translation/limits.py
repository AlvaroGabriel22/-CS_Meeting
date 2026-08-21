"""Pacing and retrying — the policy every engine is held to.

A hosted model is rented, not owned.  Three requests a minute is a real quota,
and the difference between a product that works under it and one that does not
is entirely in the caller: batch generously, wait your turn, retry what the
service asked you to retry, and never let a queue of translations become a
queue of failures (ADR-0042).

None of this lives in a provider.  A provider knows how to ask one question; it
does not decide how often the system is allowed to ask, or what to do when the
answer is "not yet".
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: how long a caller may block waiting for its turn before giving up and
#: returning the source text — a meeting cannot wait five minutes for a title
DEFAULT_MAX_WAIT_SECONDS = 90.0


class RateLimiter:
    """Lets one request through every ``60 / rpm`` seconds, process-wide.

    Deliberately a simple interval, not a burst bucket: a quota of three a
    minute is usually enforced as "not more often than every twenty seconds",
    and a burst of three followed by silence is the shape most likely to be
    refused.

    ``rpm <= 0`` means "no limit" — a model on this machine answers as fast as
    it can and nothing is gained by holding it back.
    """

    def __init__(self, requests_per_minute: float, *, max_wait: float = DEFAULT_MAX_WAIT_SECONDS):
        self._interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._max_wait = max_wait
        self._lock = threading.Lock()
        self._next_at = 0.0

    @property
    def interval(self) -> float:
        return self._interval

    def acquire(self) -> bool:
        """Wait for this caller's turn.  False when the wait would be too long."""
        if self._interval <= 0:
            return True

        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_at)
            wait = start - now
            if wait > self._max_wait:
                logger.warning(
                    "translation would wait %.0fs for its turn (limit %.0fs); skipping",
                    wait,
                    self._max_wait,
                )
                return False
            self._next_at = start + self._interval

        if wait > 0:
            logger.info("waiting %.1fs for the engine's rate limit", wait)
            time.sleep(wait)
        return True


def retry_after_of(error: Exception) -> float | None:
    """The delay a service asked for, when it said so in a header."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def status_of(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def is_retryable(error: Exception) -> bool:
    """Too many requests, or the service having a moment.  Never a bad request."""
    status = status_of(error)
    if status is None:
        return True  # a connection that never answered is worth one more try
    return status == 408 or status == 429 or 500 <= status < 600


def call_with_retry(
    action: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    describe: str = "translation",
) -> T:
    """Run ``action``, retrying what is worth retrying.

    Honours ``Retry-After`` when the service sends one, and otherwise backs off
    exponentially with a little jitter, so several workers coming back at once
    do not arrive together.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception as error:  # noqa: BLE001 - the caller decides what a failure means
            last = error
            if attempt >= attempts or not is_retryable(error):
                break
            delay = retry_after_of(error)
            if delay is None:
                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                delay += random.uniform(0, delay * 0.25)
            logger.warning(
                "%s attempt %d/%d failed (%s); retrying in %.1fs",
                describe,
                attempt,
                attempts,
                status_of(error) or type(error).__name__,
                delay,
            )
            time.sleep(delay)

    assert last is not None
    raise last


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    """Split a list into batches of at most ``size`` — one request each."""
    if size <= 0:
        return [items] if items else []
    return [items[start : start + size] for start in range(0, len(items), size)]
