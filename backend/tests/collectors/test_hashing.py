from __future__ import annotations

from app.collectors.hashing import content_hash
from app.collectors.rate_limit import RateLimiter


def test_content_hash_stable_and_order_insensitive():
    a = content_hash({"b": 1, "a": 2})
    b = content_hash({"a": 2, "b": 1})
    assert a == b
    assert len(a) == 64
    assert a != content_hash({"a": 3, "b": 1})


def test_rate_limiter_zero_delay_does_not_block():
    limiter = RateLimiter(0)
    limiter.wait()
    limiter.wait()
