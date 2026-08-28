"""DeepSeek（OpenAI 兼容）适配。只做语义判断，禁止让模型输出坐标。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings

logger = logging.getLogger("jobe.extraction.llm")

_RETRY = (
    TimeoutError,
    ConnectionError,
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
    json.JSONDecodeError,
)


def _prompt_with_schema(prompt: str, schema: dict) -> str:
    return (
        f"{prompt.rstrip()}\n\n"
        "只输出一个 JSON 对象，不要 markdown 围栏，不要解释。"
        "不要输出字符位置、offset 或 bbox。\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def parse_json_content(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("根节点必须是对象", text, 0)
    return data


class DeepSeekClient:
    """ports.LLMClient。base_url / api_key / model 来自 Settings。"""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        model: str | None = None,
        client: Any | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._model = model or self._settings.llm_model
        self._client = client or AsyncOpenAI(
            api_key=self._settings.llm_api_key,
            base_url=self._settings.llm_base_url,
            timeout=timeout,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.05, min=0.05, max=2),
        retry=retry_if_exception_type(_RETRY),
        reraise=True,
    )
    async def complete_json(self, prompt: str, schema: dict, *, temperature: float = 0.0) -> dict:
        full = _prompt_with_schema(prompt, schema)
        raw = await self._chat(full, temperature=temperature, json_mode=True)
        return parse_json_content(raw)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.05, min=0.05, max=2),
        retry=retry_if_exception_type(_RETRY),
        reraise=True,
    )
    async def complete_text(self, prompt: str, *, temperature: float = 0.0) -> str:
        return await self._chat(prompt, temperature=temperature, json_mode=False)

    async def _chat(self, prompt: str, *, temperature: float, json_mode: bool) -> str:
        req_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        logger.info(
            "llm.request model=%s json=%s temperature=%s prompt_hash=%s prompt_len=%s",
            self._model,
            json_mode,
            temperature,
            req_hash,
            len(prompt),
        )
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        resp = await self._client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        rsp_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        logger.info(
            "llm.response model=%s prompt_hash=%s content_hash=%s content_len=%s latency_ms=%s",
            self._model,
            req_hash,
            rsp_hash,
            len(content),
            latency_ms,
        )
        logger.debug("llm.response.body prompt_hash=%s body=%s", req_hash, content)
        return content


def make_extractor_client(settings: Settings | None = None) -> DeepSeekClient:
    s = settings or get_settings()
    return DeepSeekClient(settings=s, model=s.llm_model)


def make_reviewer_client(settings: Settings | None = None) -> DeepSeekClient:
    s = settings or get_settings()
    return DeepSeekClient(settings=s, model=s.llm_reviewer_model)
