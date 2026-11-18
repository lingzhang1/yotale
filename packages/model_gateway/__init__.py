"""Model Gateway — provider-independent structured generation.

The ONLY module that knows a concrete model provider (03-system-architecture.md
§15). Engines call `generate_structured(StructuredRequest) -> StructuredResult`
and never import a provider SDK. Model selection is CONFIGURATION, keyed by task.

Milestone C1 ships ONE provider implementation (Amazon Bedrock via boto3,
Converse tool-use for schema-enforced structured output). No multi-provider
routing/fallback yet. A FakeModelGateway is provided for tests.

Design: milestone-c-creative-intent-design.md §6, milestone-c-scene-understanding
-design.md §6 (generic multimodal surface — `images` is accepted but unused by
Creative Intent).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Typed request/result surface (shared by all engines)
# ---------------------------------------------------------------------------


@dataclass
class ImageInput:
    """One image input (multimodal). data is raw bytes; media_type e.g. image/jpeg."""

    data: bytes
    media_type: str = "image/jpeg"


@dataclass
class StructuredRequest:
    task: str                       # domain task, e.g. "creative_intent.resolve"
    schema: dict[str, Any]          # JSON Schema the output MUST satisfy
    prompt_version: str             # e.g. "creative_intent/v1"
    system: str                     # system prompt text (externalized, versioned)
    user_content: str               # the user-facing content for this call
    images: list[ImageInput] = field(default_factory=list)
    max_repair_attempts: int = 1
    max_tokens: int = 1024
    temperature: float = 0.0
    # Absolute wall-clock deadline (time.time() epoch seconds) for the WHOLE operation, set by the caller (the
    # worker). Adapters never start an HTTP attempt that cannot finish before it, and clamp each socket timeout
    # to the time left. None = no caller deadline (adapter defaults only).
    deadline_ts: float | None = None


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None   # provider-reported hidden reasoning/thinking tokens, when reported


@dataclass
class StructuredResult:
    data: dict[str, Any]            # schema-valid payload (tool-use input)
    usage: Usage | None = None
    attempts: int = 1
    repaired: bool = False
    model: str | None = None
    provider: str | None = None
    stop_reason: str | None = None  # Bedrock stopReason: 'end_turn' | 'tool_use' | 'max_tokens' | ...
                                    # 'max_tokens' here means the output was TRUNCATED (a real cause of an
                                    # empty/short structured result, distinct from the model choosing empty).


class StructuredOutputError(RuntimeError):
    """Raised when the model could not produce schema-valid output within the
    allowed repair attempts. Engines convert this to a designed failure path —
    they must NEVER fabricate a contract instead."""


class OutputTruncatedError(StructuredOutputError):
    """The provider stopped because it hit the output-token limit (OpenAI finish_reason=length, Gemini
    finishReason=MAX_TOKENS, Bedrock stopReason=max_tokens), so no complete structured output exists. A
    SUBCLASS of StructuredOutputError so existing handlers and the error text are unchanged; callers that can
    retry with a larger output budget catch this type specifically. It is raised IMMEDIATELY: re-sending the
    same request at the same cap would just repeat the same long generation."""

    def __init__(self, message: str, *, provider: str | None = None, finish_reason: str | None = None,
                 max_tokens: int | None = None, usage: "Usage | None" = None):
        super().__init__(message)
        self.provider = provider
        self.finish_reason = finish_reason
        self.max_tokens = max_tokens
        self.usage = usage


class ProviderError(RuntimeError):
    """Provider/transport failure (network, throttling, timeout, 5xx). RECOVERABLE — eligible for a
    bounded retry and for provider FALLBACK."""


class ProviderTimeoutError(ProviderError):
    """A request timed out waiting for the provider. Recoverable by FALLBACK, but not retried against the same
    provider: repeating an identical long request that just timed out mostly repeats the wait."""


class ProviderDeadlineError(ProviderError):
    """The caller's overall deadline leaves no time for another provider attempt. Never fails over (the other
    provider would have no time either); surfaced so the job fails with an honest, bounded error."""


class ProviderPolicyError(ProviderError):
    """A content-policy OR account/access denial from a provider (e.g. HTTP 403 policy block, an
    Anthropic-style account revocation, an auth/authorization failure). A SUBCLASS of ProviderError so
    existing ``except ProviderError`` sites still surface it — but FallbackModelGateway refuses to fail
    over on it (a denial must stop the operation and be surfaced/recorded, never silently retried on the
    other provider). Also used for malformed-request 4xx that another provider would reject identically."""



# ---------------------------------------------------------------------------
# Per-attempt telemetry (safe metadata only: no prompts, images, raw responses or credentials)
# ---------------------------------------------------------------------------

_MAX_ATTEMPT_LOG = 12


def sanitize_error(exc: BaseException | str | None, limit: int = 160) -> str | None:
    """Bounded, single-line error description. Takes the type name and the message, and drops anything that
    looks like a URL query string (an API key travels there for Gemini)."""
    if exc is None:
        return None
    text = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"(key|token|secret|authorization)=\S+", r"\1=<redacted>", text, flags=re.I)
    return text[:limit]


def make_attempt(*, provider: str, model: str | None, n: int, max_tokens: int, latency_ms: int,
                 outcome: str, finish_reason: str | None = None, usage: "Usage | None" = None,
                 error: BaseException | str | None = None) -> dict:
    """One provider attempt record. `outcome` is a low-cardinality category: ok | truncated | no_tool_call |
    timeout | transport | rate_limited | server_error | policy | bad_body | deadline."""
    rec: dict = {"provider": provider, "model": model, "n": n, "max_tokens": max_tokens,
                 "latency_ms": latency_ms, "outcome": outcome, "finish_reason": finish_reason}
    if usage is not None:
        rec["input_tokens"] = usage.input_tokens
        rec["output_tokens"] = usage.output_tokens
        if usage.reasoning_tokens is not None:
            rec["reasoning_tokens"] = usage.reasoning_tokens
    if error is not None:
        rec["error"] = sanitize_error(error)
    return rec


def classify_provider_error(exc: BaseException) -> str:
    if isinstance(exc, ProviderDeadlineError):
        return "deadline"
    if isinstance(exc, ProviderTimeoutError):
        return "timeout"
    if isinstance(exc, ProviderPolicyError):
        return "policy"
    msg = str(exc)
    if "429" in msg:
        return "rate_limited"
    if re.search(r"\b5\d\d\b", msg):
        return "server_error"
    if isinstance(exc, ProviderError):
        return "transport"
    if isinstance(exc, OutputTruncatedError):
        return "truncated"
    return "no_tool_call" if isinstance(exc, StructuredOutputError) else "transport"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ModelGateway(Protocol):
    def generate_structured(self, req: StructuredRequest) -> StructuredResult:
        """Return a schema-conforming structured response, enforcing the schema
        and performing bounded repair/retry. Raises StructuredOutputError if the
        output never validates, or ProviderError on transport failure."""
        ...


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Default model. amazon.nova-lite-v1:0 is on-demand-invocable (no inference
# profile required) and does NOT need the Anthropic Bedrock use-case form, so it
# works out of the box on this account. Overridable by env so nothing is
# hardcoded through the app; switch to a Claude inference-profile id (e.g.
# "us.anthropic.claude-haiku-4-5-20251001-v1:0") once the account's Anthropic
# use-case form is approved. ONE provider for now.
DEFAULT_BEDROCK_MODEL = "amazon.nova-lite-v1:0"   # fixed constant; never configured in any environment
DEFAULT_AWS_REGION = os.environ.get("STORY_AWS_REGION", "us-east-1")
_TOOL_NAME = "emit_structured"


# ---------------------------------------------------------------------------
# Bedrock implementation (the one provider for C1)
# ---------------------------------------------------------------------------


class BedrockModelGateway:
    """Amazon Bedrock gateway using the Converse API with tool-use to force
    schema-valid structured output. boto3 is imported lazily so the package
    imports cleanly in environments without it (tests use the fake)."""

    def __init__(self, model_id: str | None = None, region: str | None = None, client: Any = None):
        self.model_id = model_id or DEFAULT_BEDROCK_MODEL
        self.region = region or DEFAULT_AWS_REGION
        self._client = client  # injectable for tests

    def _bedrock(self) -> Any:
        if self._client is None:
            try:
                import boto3  # lazy
            except ImportError as e:  # pragma: no cover
                raise ProviderError("boto3 not available") from e
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def generate_structured(self, req: StructuredRequest) -> StructuredResult:
        tool = {
            "toolSpec": {
                "name": _TOOL_NAME,
                "description": "Emit the single structured result for this task.",
                "inputSchema": {"json": req.schema},
            }
        }
        content: list[dict[str, Any]] = []
        for img in req.images:
            fmt = img.media_type.split("/")[-1]
            content.append({"image": {"format": fmt, "source": {"bytes": img.data}}})
        content.append({"text": req.user_content})

        kwargs = dict(
            modelId=self.model_id,
            system=[{"text": req.system}],
            messages=[{"role": "user", "content": content}],
            toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": _TOOL_NAME}}},
            inferenceConfig={"maxTokens": req.max_tokens, "temperature": req.temperature},
        )

        last_err: Exception | None = None
        attempts = 0
        for attempt in range(1 + max(0, req.max_repair_attempts)):
            attempts = attempt + 1
            try:
                resp = self._bedrock().converse(**kwargs)
            except Exception as e:  # botocore ClientError etc.
                raise ProviderError(f"bedrock converse failed: {type(e).__name__}: {e}") from e

            tool_input = self._extract_tool_input(resp)
            stop_reason = resp.get("stopReason")
            if tool_input is not None:
                usage = resp.get("usage") or {}
                return StructuredResult(
                    data=tool_input,
                    usage=Usage(
                        input_tokens=usage.get("inputTokens"),
                        output_tokens=usage.get("outputTokens"),
                        total_tokens=usage.get("totalTokens"),
                    ),
                    attempts=attempts,
                    repaired=attempt > 0,
                    model=self.model_id,
                    provider="bedrock",
                    stop_reason=stop_reason,
                )
            # No tool_use block. If Bedrock stopped at max_tokens the OUTPUT WAS TRUNCATED — surface that as
            # the error so the caller can log 'stop_reason=max_tokens' instead of a generic 'no output'.
            if stop_reason == "max_tokens":
                # Re-sending the same request at the same cap only repeats the long generation: raise now so the
                # caller can retry with a larger budget.
                raise OutputTruncatedError("output truncated at max_tokens (increase max_tokens)",
                                           provider="bedrock", finish_reason=stop_reason,
                                           max_tokens=req.max_tokens)
            else:
                last_err = StructuredOutputError(f"model did not return a tool_use block (stop_reason={stop_reason})")
            # On repair attempt, nudge the model to call the tool.
            kwargs["messages"] = [
                {"role": "user", "content": content},
                {"role": "user", "content": [{"text": f"You must call {_TOOL_NAME} with valid JSON."}]},
            ]
        raise last_err or StructuredOutputError("no structured output")

    @staticmethod
    def _extract_tool_input(resp: dict[str, Any]) -> dict[str, Any] | None:
        try:
            blocks = resp["output"]["message"]["content"]
        except (KeyError, TypeError):
            return None
        for b in blocks:
            if "toolUse" in b and isinstance(b["toolUse"].get("input"), dict):
                return b["toolUse"]["input"]
        return None


# ---------------------------------------------------------------------------
# Fake implementation (tests)
# ---------------------------------------------------------------------------


class FallbackModelGateway:
    """Primary model with a secondary FALLBACK on provider failure. Tries the primary gateway; if it raises
    ProviderError (transport/throttle/timeout/auth — Bedrock throttling surfaces here after botocore's own
    retries), it transparently retries ONCE on the fallback gateway. A StructuredOutputError (the model
    answered but the output never validated) is NOT a reason to switch models and propagates unchanged.

    Use it to keep a strong primary (Opus 4.6) while degrading gracefully to a higher-daily-quota model
    (Sonnet 4.6) when the Opus per-day token cap is hit, instead of failing the whole create. last_fallback
    records whether the fallback was used (for logging)."""

    def __init__(self, primary: "ModelGateway", fallback: "ModelGateway"):
        self._primary = primary
        self._fallback = fallback
        self.last_fallback: bool = False
        self.last_error: str | None = None
        # Provider attempts of the most recent generate_structured call, primary first, each tagged with its
        # role. Filled even when the call raised, so a failed job still has its attempt history.
        self.last_attempts: list[dict] = []

    # Model ids for diagnostics (which model actually produced a given call). Best-effort: a gateway without a
    # model_id (e.g. a test fake) yields None.
    @property
    def primary_model_id(self) -> str | None:
        return getattr(self._primary, "model_id", None)

    @property
    def fallback_model_id(self) -> str | None:
        return getattr(self._fallback, "model_id", None)

    def _collect(self, gw: "ModelGateway", role: str) -> None:
        for a in (getattr(gw, "last_attempts", None) or []):
            if len(self.last_attempts) < _MAX_ATTEMPT_LOG:
                self.last_attempts.append({**a, "role": role})

    def generate_structured(self, req: StructuredRequest) -> StructuredResult:
        self.last_fallback = False
        self.last_error = None
        self.last_attempts = []
        try:
            try:
                return self._primary.generate_structured(req)
            finally:
                self._collect(self._primary, "primary")
        except (ProviderPolicyError, ProviderDeadlineError):
            # Content-policy / account-access / auth denial, or a 4xx another provider would reject the
            # same way, or no time left for another attempt. NEVER fail over: stop and surface so the caller
            # records the incident. (Subclasses of ProviderError, so this except must come FIRST.)
            raise
        except ProviderError as e:
            self.last_fallback = True
            self.last_error = str(e)[:300]
            primary_cause = {"category": classify_provider_error(e), "error": sanitize_error(e)}
            try:
                try:
                    return self._fallback.generate_structured(req)
                finally:
                    self._collect(self._fallback, "fallback")
            except Exception as fe:
                # Keep WHY the primary failed even though the fallback failed too.
                try:
                    fe.primary_failure = primary_cause  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
                raise


class FakeModelGateway:
    """Deterministic fake for unit/endpoint tests. Returns a preset payload, or
    raises a preset error, without any network call."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        error: Exception | None = None,
        usage: Usage | None = None,
    ):
        self._response = response
        self._error = error
        self._usage = usage or Usage(input_tokens=100, output_tokens=40, total_tokens=140)
        self.calls: list[StructuredRequest] = []

    def generate_structured(self, req: StructuredRequest) -> StructuredResult:
        self.calls.append(req)
        if self._error is not None:
            raise self._error
        if self._response is None:
            raise StructuredOutputError("fake: no response configured")
        return StructuredResult(
            data=json.loads(json.dumps(self._response)),  # deep copy
            usage=self._usage,
            attempts=1,
            model="fake",
            provider="fake",
        )


__all__ = [
    "ImageInput",
    "StructuredRequest",
    "Usage",
    "StructuredResult",
    "StructuredOutputError",
    "ProviderError",
    "ProviderPolicyError",
    "OutputTruncatedError",
    "ProviderTimeoutError",
    "ProviderDeadlineError",
    "make_attempt",
    "sanitize_error",
    "classify_provider_error",
    "ModelGateway",
    "BedrockModelGateway",
    "FallbackModelGateway",
    "FakeModelGateway",
    "DEFAULT_BEDROCK_MODEL",
    "DEFAULT_AWS_REGION",
]
