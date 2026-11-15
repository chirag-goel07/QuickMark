"""Tiny in-memory limiter (per server process) used against guessing: join codes, reset codes, reset requests.
The sliding-window logic (hash map of key -> deque of times) is the C++ class qm::SlidingWindowLimiter (cpp/rate_limiter.hpp)."""
import time

from services import core


def allow(key, limit, window_seconds, now=None):
    """True if `key` has done fewer than `limit` things in the last `window_seconds`; records this one."""
    now = time.time() if now is None else now
    return core.rate_allow(key, limit, window_seconds, now)


def reset_all():
    core.rate_reset()
