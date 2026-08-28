"""快照内容指纹。同一 payload 必须得到同一哈希，供去重。"""

from __future__ import annotations

import hashlib
import json


def content_hash(payload: dict) -> str:
    blob = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
