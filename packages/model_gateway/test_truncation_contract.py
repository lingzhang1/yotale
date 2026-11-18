"""Output-truncation and attempt-telemetry contract for the direct provider adapters + the fallback wrapper.

No network and no keys: every test injects a fake transport. Covers genuine truncation (OpenAI `length`, Gemini
`MAX_TOKENS`) raising OutputTruncatedError at once (no same-cap re-send), non-truncation failures keeping their
own classification, timeout / deadline behaviour, fallback ordering, primary-cause retention and sanitized
telemetry.
"""
from __future__ import annotations

import json
import time
import urllib.error

import pytest

from model_gateway import (
    FallbackModelGateway, OutputTruncatedError, ProviderDeadlineError, ProviderError, ProviderPolicyError,
    ProviderTimeoutError, StructuredOutputError, StructuredRequest, sanitize_error,
)
from model_gateway.gemini_gateway import GeminiModelGateway
from model_gateway.openai_gateway import OpenAIModelGateway

SCHEMA = {"type": "object", "additionalProperties": False,
          "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


def _req(**kw):
    base = dict(task="t", schema=SCHEMA, prompt_version="v1", system="sys", user_content="SECRET-USER-TEXT",
                max_tokens=8192, temperature=0.0, max_repair_attempts=2)
    base.update(kw)
    return StructuredRequest(**base)


class Transport:
    """Scripted transport: each call pops the next (status, payload) or raises the next exception."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.last = steps[-1]
        self.calls = 0
        self.timeouts: list[float] = []

    def __call__(self, url, headers, body, timeout):
        self.calls += 1
        self.timeouts.append(timeout)
        step = self.steps.pop(0) if self.steps else self.last
        self.last = step
        if isinstance(step, Exception):
            raise step
        status, payload = step
        return status, json.dumps(payload).encode(), {}


def _oa(t):
    return OpenAIModelGateway("gpt-5.1", api_key="k", http_post=t, max_retries=2)


def _gm(t):
    return GeminiModelGateway("gemini-3.8-flash", api_key="k", http_post=t, max_retries=2)


OA_OK = (200, {"choices": [{"finish_reason": "stop", "message": {"tool_calls": [
    {"function": {"name": "emit_structured", "arguments": json.dumps({"summary": "ok"})}}]}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
              "completion_tokens_details": {"reasoning_tokens": 7}}})
# OpenAI truncation: the tool call exists but its JSON arguments are cut off mid-string.
OA_LENGTH = (200, {"choices": [{"finish_reason": "length", "message": {"tool_calls": [
    {"function": {"name": "emit_structured", "arguments": '{"summary": "abc'}}]}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 8192, "total_tokens": 8292}})
GM_OK = (200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [
    {"functionCall": {"name": "emit_structured", "args": {"summary": "ok"}}}]}}],
    "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "totalTokenCount": 150}})
GM_MAX = (200, {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 3000,
                                  "thoughtsTokenCount": 5192, "totalTokenCount": 8292}})


# 1. OpenAI truncated at the initial limit ------------------------------------------------------------------------
def test_openai_length_raises_truncation_immediately_without_same_cap_resend():
    t = Transport(OA_LENGTH, OA_LENGTH, OA_LENGTH)
    gw = _oa(t)
    with pytest.raises(OutputTruncatedError) as ei:
        gw.generate_structured(_req())
    assert t.calls == 1                                  # not 3: re-sending the same cap repeats the long generation
    e = ei.value
    assert isinstance(e, StructuredOutputError)          # existing handlers still catch it
    assert str(e) == "output truncated at max_tokens (increase max_tokens)"
    assert (e.provider, e.finish_reason, e.max_tokens) == ("openai", "length", 8192)
    (a,) = gw.last_attempts
    assert a["outcome"] == "truncated" and a["max_tokens"] == 8192 and a["output_tokens"] == 8192


# 2. Gemini truncated at the initial limit; thinking tokens are visible ---------------------------------------------
def test_gemini_max_tokens_raises_truncation_and_records_thinking_tokens():
    t = Transport(GM_MAX, GM_MAX, GM_MAX)
    gw = _gm(t)
    with pytest.raises(OutputTruncatedError) as ei:
        gw.generate_structured(_req())
    assert t.calls == 1
    assert ei.value.provider == "gemini" and ei.value.finish_reason == "MAX_TOKENS"
    assert str(ei.value) == "output truncated at maxOutputTokens (increase max_tokens)"
    (a,) = gw.last_attempts
    assert a["outcome"] == "truncated" and a["reasoning_tokens"] == 5192 and a["output_tokens"] == 3000


# 3. success records safe telemetry --------------------------------------------------------------------------------
def test_success_records_attempt_with_reasoning_tokens_and_no_content():
    gw = _oa(Transport(OA_OK))
    res = gw.generate_structured(_req())
    assert res.data == {"summary": "ok"} and res.usage.reasoning_tokens == 7
    (a,) = gw.last_attempts
    assert a["outcome"] == "ok" and a["provider"] == "openai" and a["model"] == "gpt-5.1"
    assert a["input_tokens"] == 100 and a["latency_ms"] >= 0
    blob = json.dumps(gw.last_attempts)
    assert "SECRET-USER-TEXT" not in blob and "emit_structured" not in blob


# 5. unrelated structured-output errors are NOT treated as truncation ----------------------------------------------
def test_no_tool_call_is_not_truncation_and_still_nudges():
    stop = (200, {"choices": [{"finish_reason": "stop", "message": {"content": "hi"}}]})
    t = Transport(stop, stop, stop)
    gw = _oa(t)
    with pytest.raises(StructuredOutputError) as ei:
        gw.generate_structured(_req())
    assert not isinstance(ei.value, OutputTruncatedError)
    assert t.calls == 3 and [a["outcome"] for a in gw.last_attempts] == ["no_tool_call"] * 3


def test_gemini_safety_block_is_policy_not_truncation():
    blocked = (200, {"candidates": [{"finishReason": "SAFETY"}]})
    with pytest.raises(ProviderPolicyError):
        _gm(Transport(blocked)).generate_structured(_req())


def test_auth_failure_is_policy_error_and_not_retried():
    t = Transport((401, {}))
    with pytest.raises(ProviderPolicyError):
        _oa(t).generate_structured(_req())
    assert t.calls == 1


# 6. timeout then fallback ------------------------------------------------------------------------------------------
def test_timeout_is_typed_and_not_resent_to_the_same_provider():
    t = Transport(TimeoutError("slow"))
    gw = _oa(t)
    with pytest.raises(ProviderTimeoutError):
        gw.generate_structured(_req())
    assert t.calls == 1 and gw.last_attempts[0]["outcome"] == "timeout"


def test_connection_reset_still_gets_bounded_retries(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    t = Transport(urllib.error.URLError(ConnectionResetError("x")), urllib.error.URLError(ConnectionResetError("x")),
                  OA_OK)
    assert _oa(t).generate_structured(_req()).data == {"summary": "ok"} and t.calls == 3


def test_primary_timeout_then_fallback_success_records_both_attempts():
    pt, ft = Transport(TimeoutError("slow")), Transport(GM_OK)
    fb = FallbackModelGateway(_oa(pt), _gm(ft))
    res = fb.generate_structured(_req())
    assert res.provider == "gemini" and fb.last_fallback is True
    assert [(a["role"], a["outcome"]) for a in fb.last_attempts] == [("primary", "timeout"), ("fallback", "ok")]


# 7. both fail: the ORIGINAL primary cause is retained ---------------------------------------------------------------
def test_primary_and_fallback_fail_keeps_primary_cause_and_both_attempts():
    fb = FallbackModelGateway(_oa(Transport(TimeoutError("slow"))), _gm(Transport(GM_MAX)))
    with pytest.raises(OutputTruncatedError) as ei:
        fb.generate_structured(_req())
    assert ei.value.primary_failure["category"] == "timeout"
    assert [(a["role"], a["outcome"]) for a in fb.last_attempts] == [("primary", "timeout"), ("fallback", "truncated")]


def test_truncation_on_primary_does_not_fail_over_or_loop():
    ft = Transport(GM_OK)
    fb = FallbackModelGateway(_oa(Transport(OA_LENGTH)), _gm(ft))
    with pytest.raises(OutputTruncatedError):
        fb.generate_structured(_req())
    assert ft.calls == 0 and fb.last_fallback is False


# 13. deadlines ----------------------------------------------------------------------------------------------------
def test_deadline_blocks_a_new_attempt_and_never_fails_over():
    pt, ft = Transport(OA_OK), Transport(GM_OK)
    fb = FallbackModelGateway(_oa(pt), _gm(ft))
    with pytest.raises(ProviderDeadlineError):
        fb.generate_structured(_req(deadline_ts=time.time() + 5))
    assert pt.calls == 0 and ft.calls == 0 and fb.last_attempts[0]["outcome"] == "deadline"


def test_socket_timeout_is_clamped_to_the_time_left():
    t = Transport(OA_OK)
    _oa(t).generate_structured(_req(deadline_ts=time.time() + 30))
    assert t.timeouts[0] <= 30.0 + 0.5 and t.timeouts[0] < 60.0


# 14. sanitized diagnostics ----------------------------------------------------------------------------------------
def test_sanitize_error_drops_urls_keys_and_long_text():
    s = sanitize_error("boom https://x.test/v1/m:gen?key=AIzaSECRET&a=1 token=abc123 " + "z" * 500)
    assert "AIzaSECRET" not in s and "abc123" not in s and "https://" not in s and len(s) <= 160
    assert "\n" not in sanitize_error("a\nb")


# per-request timeout -------------------------------------------------------------------------------------------
def test_request_timeout_overrides_the_adapter_default_and_is_still_clamped():
    t = Transport(OA_OK, OA_OK)
    gw = _oa(t)
    gw.generate_structured(_req(timeout_seconds=210))
    assert t.timeouts[-1] == 210.0                        # not the 60 s default
    gw.generate_structured(_req(timeout_seconds=210, deadline_ts=time.time() + 100))
    assert t.timeouts[-1] <= 100.5                        # never past the caller deadline


def test_gemini_honours_request_timeout():
    t = Transport(GM_OK)
    _gm(t).generate_structured(_req(timeout_seconds=150))
    assert t.timeouts == [150.0]


def test_attempt_records_omit_absent_values():
    gw = _oa(Transport(TimeoutError("slow")))
    with pytest.raises(ProviderTimeoutError):
        gw.generate_structured(_req())
    (a,) = gw.last_attempts
    assert "finish_reason" not in a and "input_tokens" not in a and None not in a.values()
