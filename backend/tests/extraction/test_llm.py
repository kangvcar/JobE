from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.extraction.llm import DeepSeekClient, parse_json_content


def test_parse_json_content_strips_fence():
    assert parse_json_content('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_content('{"b": 2}') == {"b": 2}


def test_parse_json_rejects_array():
    with pytest.raises(json.JSONDecodeError):
        parse_json_content("[1]")


class _Completions:
    def __init__(self, content: str, boom_first: bool = False) -> None:
        self.content = content
        self.boom_first = boom_first
        self.n = 0
        self.kwargs: dict | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        self.n += 1
        if self.boom_first and self.n == 1:
            raise TimeoutError("timeout")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class _Chat:
    def __init__(self, completions: _Completions) -> None:
        self.completions = completions


class _Client:
    def __init__(self, completions: _Completions) -> None:
        self.chat = _Chat(completions)


@pytest.mark.asyncio
async def test_complete_json_forces_json_and_logs_no_coords():
    comp = _Completions('{"ok": true}')
    client = DeepSeekClient(
        settings=Settings(llm_api_key="x", llm_base_url="http://example.invalid"),
        model="deepseek-chat",
        client=_Client(comp),
    )
    out = await client.complete_json("抽取技能", {"type": "object"})
    assert out == {"ok": True}
    assert comp.kwargs is not None
    assert comp.kwargs["response_format"] == {"type": "json_object"}
    prompt = comp.kwargs["messages"][0]["content"]
    assert "不要输出字符位置" in prompt
    assert "bbox" in prompt.lower() or "offset" in prompt


@pytest.mark.asyncio
async def test_complete_text():
    comp = _Completions("hello")
    client = DeepSeekClient(settings=Settings(llm_api_key="x"), client=_Client(comp))
    assert await client.complete_text("ping") == "hello"
    assert comp.kwargs is not None
    assert "response_format" not in comp.kwargs


@pytest.mark.asyncio
async def test_complete_json_retries_timeout():
    comp = _Completions('{"ok": true}', boom_first=True)
    client = DeepSeekClient(
        settings=Settings(llm_api_key="x"),
        client=_Client(comp),
    )
    out = await client.complete_json("x", {"type": "object"})
    assert out["ok"] is True
    assert comp.n == 2
