"""Per-call token + cost logging (`model_call_usage`) at the provider-adapter seam.

Every capability (guide, coverage, creative intent, interpret-revision, music plan, duration, scene
understanding, AU, edit plan, ...) funnels through the OpenAI/Gemini adapters, so one log line per billed
attempt gives complete cost visibility. Offline: fake transports, fake logger, no network.
"""
from __future__ import annotations

import json

import pytest

import observability
from model_gateway import StructuredRequest, log_model_call
from model_gateway.gemini_gateway import GeminiModelGateway
from model_gateway.openai_gateway import OpenAIModelGateway

SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


def _req(task="story_guide.v2"):
    return StructuredRequest(task=task, schema=SCHEMA, prompt_version="v1", system="s", user_content="u",
                             max_tokens=64, max_repair_attempts=1)


class _Capture:
    def __init__(self):
        self.lines: list[tuple[str, dict]] = []

    def info(self, msg, extra=None):
        self.lines.append((msg, extra or {}))


@pytest.fixture()
def cap(monkeypatch):
    c = _Capture()
    monkeypatch.setattr(observability, "get_logger", lambda name="story", level=20: c)
    return c


def _openai(usage, tool=True):
    msg = {"tool_calls": [{"function": {"name": "emit_structured", "arguments": json.dumps({"summary": "x"})}}]} \
        if tool else {}
    payload = {"choices": [{"finish_reason": "tool_calls" if tool else "stop", "message": msg}], "usage": usage}
    return lambda url, h, b, t: (200, json.dumps(payload).encode(), {})


def _gemini(um):
    payload = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"functionCall": {"name": "emit_structured", "args": {"summary": "x"}}}]}}], "usageMetadata": um}
    return lambda url, h, b, t: (200, json.dumps(payload).encode(), {})


def test_openai_attempt_logged_with_cost_and_task(cap):
    gw = OpenAIModelGateway("gpt-5.1", api_key="k", http_post=_openai(
        {"prompt_tokens": 10_000, "completion_tokens": 2_000, "total_tokens": 12_000,
         "completion_tokens_details": {"reasoning_tokens": 1_500}}))
    gw.generate_structured(_req("story_guide.v2"))
    (msg, f), = cap.lines
    assert msg == "model_call_usage"
    assert f["task"] == "story_guide.v2" and f["provider"] == "openai" and f["model_id"] == "gpt-5.1"
    assert f["input_tokens"] == 10_000 and f["output_tokens"] == 2_000
    # OpenAI completion_tokens already includes reasoning: NOT added again.
    assert f["billed_output_tokens"] == 2_000
    assert f["estimated_cost_usd"] == pytest.approx(10_000 / 1e6 * 1.25 + 2_000 / 1e6 * 10.0)
    assert f["pricing_known"] is True


def test_gemini_thinking_tokens_are_billed_as_output(cap):
    gw = GeminiModelGateway("gemini-3.8-flash", api_key="k", http_post=_gemini(
        {"promptTokenCount": 30_000, "candidatesTokenCount": 650, "totalTokenCount": 33_000,
         "thoughtsTokenCount": 2_350}))
    gw.generate_structured(_req("asset_understanding.analyze"))
    (_, f), = cap.lines
    assert f["output_tokens"] == 650 and f["reasoning_output_tokens"] == 2_350
    assert f["billed_output_tokens"] == 3_000  # candidates + thoughts
    assert f["estimated_cost_usd"] == pytest.approx(30_000 / 1e6 * 0.30 + 3_000 / 1e6 * 2.50)


def test_every_billed_attempt_is_logged_including_a_failed_one(cap):
    # First attempt: model answered without a tool call (still billed). Second: ok.
    calls = {"n": 0}
    ok = _openai({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})(None, None, None, None)
    bad = _openai({"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}, tool=False)(None, None, None, None)

    def t(url, h, b, to):
        calls["n"] += 1
        return bad if calls["n"] == 1 else ok

    OpenAIModelGateway("gpt-5.1", api_key="k", http_post=t).generate_structured(_req())
    assert [f["outcome"] for _, f in cap.lines] == ["no_tool_call", "ok"]
    assert [f["attempt"] for _, f in cap.lines] == [1, 2]


def test_no_usage_means_no_line(cap):
    log_model_call("t", {"provider": "openai", "model": "gpt-5.1", "n": 1, "outcome": "transport"})
    assert cap.lines == []


def test_unpriced_model_is_flagged_not_free(cap):
    log_model_call("t", {"provider": "openai", "model": "mystery-model", "n": 1, "outcome": "ok",
                         "input_tokens": 10, "output_tokens": 5})
    (_, f), = cap.lines
    assert f["pricing_known"] is False and f["estimated_cost_usd"] == 0.0


def test_logging_failure_never_breaks_the_call(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("logger down")
    monkeypatch.setattr(observability, "get_logger", boom)
    gw = OpenAIModelGateway("gpt-5.1", api_key="k", http_post=_openai(
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}))
    assert gw.generate_structured(_req()).data == {"summary": "x"}


def test_no_prompt_media_or_user_fields_are_logged(cap):
    OpenAIModelGateway("gpt-5.1", api_key="k", http_post=_openai(
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})).generate_structured(_req())
    (_, f), = cap.lines
    assert not ({"prompt", "user_content", "system", "story_user_id", "images"} & set(f))
    assert observability.scrub_log_fields(f) == f  # nothing would be redacted
