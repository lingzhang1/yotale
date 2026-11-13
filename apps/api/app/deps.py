"""Dependency injection seam for the Story API.

The application depends on engine INTERFACES (Protocols), never on the
concrete Mock classes. These provider functions are the single place a
real AI engine gets swapped in for a mock — via FastAPI dependency
overrides in tests, or by editing these providers when real engines land.

Return TYPES are the Protocols; return VALUES are the Milestone A mocks.
"""

from __future__ import annotations

import os

from director_engine import DirectorEngine, MockDirectorEngine
from edit_engine import EditEngine, MockEditEngine
from story_engine import MockStoryEngine, StoryEngine
from model_gateway import BedrockModelGateway, ModelGateway
from creative_intent import (
    CreativeIntentEngine,
    MockCreativeIntentEngine,
    RealCreativeIntentEngine,
)
from scene_understanding import (
    MockSceneUnderstandingEngine,
    RealSceneUnderstandingEngine,
    SceneUnderstandingEngine,
)
from story_director import (
    MockStoryDirectorEngine,
    RealStoryDirectorEngine,
    StoryDirectorEngine,
)
from asset_engine import (
    AssetUnderstandingEngine,
    DEFAULT_AU_MODEL,
    MockAssetUnderstandingEngine,
    RealAssetUnderstandingEngine,
)
from story_coverage import (
    StoryCoverageEngine,
    DEFAULT_COVERAGE_MODEL,
    MockStoryCoverageEngine,
    RealStoryCoverageEngine,
)
from story_guide import (
    StoryGuideEngine,
    DEFAULT_GUIDE_MODEL,
    MockStoryGuideEngine,
    RealStoryGuideEngine,
)
from story_coverage_v2 import (
    DEFAULT_COVERAGE_MODEL as DEFAULT_COVERAGE_V2_MODEL,
    RealStoryCoverageV2Engine,
    StoryCoverageV2Engine,
)
from music_direction import (
    DeterministicMusicDirectionEngine,
    MusicDirectionEngine,
)
from edit_planner import (
    EditPlannerEngine,
    MODEL_ID as EDIT_PLANNER_MODEL,
    RealEditPlannerEngine,
)
from music_plan import (
    MODEL_ID as MUSIC_PLAN_MODEL,
    MusicPlanEngine,
    RealMusicPlanEngine,
)
from duration_planner import (
    MODEL_ID as DURATION_PLANNER_MODEL,
    DurationPlannerEngine,
    RealDurationPlannerEngine,
)


def get_story_engine() -> StoryEngine:
    """Provide the StoryEngine implementation (mock for Milestone A)."""
    return MockStoryEngine()


def get_director_engine() -> DirectorEngine:
    """Provide the DirectorEngine implementation (mock for Milestone A)."""
    return MockDirectorEngine()


def get_edit_engine() -> EditEngine:
    """Provide the EditEngine implementation (mock for Milestone A)."""
    return MockEditEngine()


def get_model_gateway() -> ModelGateway:
    """Provide the Model Gateway. ONE provider for C1 (Bedrock), config-driven
    (fixed default model; region via STORY_AWS_REGION). NOT provider-routed - see release notes."""
    return BedrockModelGateway()


def get_creative_intent_engine() -> CreativeIntentEngine:
    """Provide the Creative Intent resolver.

    Real (model-backed) by default. Set STORY_CREATIVE_INTENT_MOCK=1 to use the
    deterministic mock (dev/offline) — the mock is NEVER a silent production
    fallback; it is only selected explicitly here.
    """
    if os.environ.get("STORY_CREATIVE_INTENT_MOCK") == "1":
        return MockCreativeIntentEngine()
    if _provider_mode() == "direct":
        from model_gateway.provider import make_gateway
        return RealCreativeIntentEngine(make_gateway("creative_intent"))
    return RealCreativeIntentEngine(get_model_gateway())


def get_scene_understanding_engine() -> SceneUnderstandingEngine:
    """Provide the Scene Understanding analyzer.

    Task-specific, fixed VISION model constant, separate from
    the Creative Intent model (Creative Intent model != Scene Understanding model).
    Default amazon.nova-pro-v1:0 — on-demand-invocable, image-capable, no Anthropic
    form gate. Set STORY_SCENE_UNDERSTANDING_MOCK=1 for the dev/offline mock (never
    a silent production fallback).
    """
    if os.environ.get("STORY_SCENE_UNDERSTANDING_MOCK") == "1":
        return MockSceneUnderstandingEngine()
    model = "amazon.nova-pro-v1:0"
    return RealSceneUnderstandingEngine(routed_gateway("scene_understanding", model))


def get_story_director_engine() -> StoryDirectorEngine:
    """Provide the Story Director — the most intelligence-sensitive component.

    Task-specific, fixed model constant, independent of the
    Creative Intent / Scene Understanding / Shot Validation models. Default
    amazon.nova-pro-v1:0 (on-demand-invocable, no Anthropic use-case gate; passed
    the C3A offline quality gate). (Fixed constant; the direct router decides the real provider.)
    Set STORY_DIRECTOR_MOCK=1 for the dev/offline mock (never a silent fallback).
    """
    if os.environ.get("STORY_DIRECTOR_MOCK") == "1":
        return MockStoryDirectorEngine()
    model = "us.anthropic.claude-opus-4-5-20251101-v1:0"
    # P0 provider restore: route via the provider router so STORY_MODEL_PROVIDER=direct reaches OpenAI/Gemini
    # (the hardcoded BedrockModelGateway bypassed it and kept calling the restricted Anthropic model).
    return RealStoryDirectorEngine(routed_gateway("story_director", model))


def get_asset_understanding_engine() -> AssetUnderstandingEngine:
    """Provide the Asset Understanding analyzer (Milestone D, FROZEN).

    ONE model, fixed model constant (us.anthropic.claude-sonnet-4-6 —
    the frozen production AU model; used only in the explicit non-release Bedrock mode). NO routing/escalation/native-video. Set
    STORY_ASSET_UNDERSTANDING_MOCK=1 for the dev/offline mock (never a silent fallback).
    """
    if os.environ.get("STORY_ASSET_UNDERSTANDING_MOCK") == "1":
        return MockAssetUnderstandingEngine()
    model = DEFAULT_AU_MODEL
    return RealAssetUnderstandingEngine(routed_gateway("asset_understanding", model), model_id=model)


def get_story_coverage_engine() -> StoryCoverageEngine:
    """Provide the Story Coverage engine (Milestone E, FROZEN).

    ONE model, fixed model constant (us.anthropic.claude-opus-4-6-v1 —
    the experiment winner: uniquely avoided false-sufficient AND false-insufficient while missing
    zero worthwhile ideas; used only in the explicit non-release Bedrock mode). NO Nova/Sonnet fallback, NO routing. Set STORY_COVERAGE_MOCK=1 for the
    dev/offline mock (never a silent production fallback).
    """
    if os.environ.get("STORY_COVERAGE_MOCK") == "1":
        return MockStoryCoverageEngine()
    model = DEFAULT_COVERAGE_MODEL
    # R-d.2 reliability: Opus primary -> Sonnet fallback on ProviderError (daily-quota throttle), so a create
    # degrades rather than 503s at this stage. Same-version is a no-op (helper returns the bare gateway).
    return RealStoryCoverageEngine(routed_gateway("story_coverage", model), model_id=model)


def get_story_guide_engine() -> StoryGuideEngine:
    """Provide the Story Guide engine (Milestone E2-a, FROZEN).

    CreativeIntent -> persistent StoryGuide, ONCE per Story. ONE model, config-driven via
    fixed constant (us.anthropic.claude-opus-4-6-v1, non-release Bedrock mode only — the E2-a selection: restraint +
    scope discipline + framing voice; task-specific, NOT a general Opus rule). Set STORY_GUIDE_MOCK=1
    for the dev/offline mock (never a silent production fallback — Guide failure preserves CreativeIntent).
    """
    if os.environ.get("STORY_GUIDE_MOCK") == "1":
        return MockStoryGuideEngine()
    model = DEFAULT_GUIDE_MODEL
    # R-d.2 reliability: Opus primary -> Sonnet fallback on ProviderError (daily-quota throttle). Same-version
    # is a no-op (helper returns the bare gateway).
    return RealStoryGuideEngine(routed_gateway("story_guide", model), model_id=model)


def get_story_guide_v2_engine():
    """Provide the StoryGuide/2 engine — the AI SHOOTING SCRIPT (additive, 2026-10-23).

    CreativeIntent -> scene-based shooting script, ONCE per Story. Same model selection as v1
    (fixed model constant, Opus 4.6 id; direct router decides the real provider) with the Opus->Sonnet quota fallback. Set
    STORY_GUIDE_MOCK=1 for the dev/offline mock. The Guide v2 endpoints are always available;
    this getter only constructs the engine. Guide failure preserves CreativeIntent (never fabricate)."""
    from story_guide import RealStoryGuideV2Engine, MockStoryGuideV2Engine
    if os.environ.get("STORY_GUIDE_MOCK") == "1":
        return MockStoryGuideV2Engine()
    model = DEFAULT_GUIDE_MODEL
    return RealStoryGuideV2Engine(routed_gateway("story_guide", model), model_id=model)


def get_story_guide_refine_engine():
    """Provide the StoryGuide/2 REFINEMENT engine — "Update Guide" (Guide v2.1, 2026-10-23).

    current v2 shooting script + captured/pinned state + user update -> next v2 shooting script +
    change log. The MODEL proposes; the engine reconciles identity + history server-side (captured/
    pinned preserved, stable ids kept, new ids minted beyond max ordinal, dropped scenes archived).
    Same model selection + Opus->Sonnet quota fallback as v1/v2. STORY_GUIDE_MOCK=1 -> dev mock. The
    Endpoint is always available; refine failure preserves the CURRENT Guide (no fabricate)."""
    from story_guide import RealStoryGuideRefineEngine, MockStoryGuideRefineEngine
    if os.environ.get("STORY_GUIDE_MOCK") == "1":
        return MockStoryGuideRefineEngine()
    model = DEFAULT_GUIDE_MODEL
    return RealStoryGuideRefineEngine(routed_gateway("story_guide", model), model_id=model)


def get_story_coverage_v2_engine() -> StoryCoverageV2Engine:
    """Provide the StoryCoverage/2 engine (Milestone E2-b, FROZEN).

    Composes the internal two-call pipeline (Mapper story_coverage/mapper-v1 + Judge
    story_judgment/v2) into the public StoryCoverageContractV2. ONE model, config-driven via
    fixed constant (us.anthropic.claude-opus-4-6-v1, non-release Bedrock mode only) for BOTH internal calls. The
    deterministic evidence builder firewalls Guide/completion signals away from the Judge.
    """
    model = DEFAULT_COVERAGE_V2_MODEL
    # R-d.2 reliability: Opus primary -> Sonnet fallback on ProviderError. THIS is the stage whose daily-quota
    # throttle failed hiking creates ('story_coverage_v2_unavailable: Too many tokens per day') before the
    # (already fallback-protected) edit planner was ever reached. BOTH internal calls (mapper + judge) share
    # this gateway, so both degrade to Sonnet together. Same-version is a no-op (helper returns bare gateway).
    return RealStoryCoverageV2Engine(routed_gateway("story_coverage", model), model_id=model)


def get_music_direction_engine() -> MusicDirectionEngine:
    """Provide the MusicDirection inference engine (Milestone M-c).

    DETERMINISTIC — no model call. Projects the already-resolved CreativeIntent
    (+ optional StoryGuide.framing_summary) into the intended soundtrack character.
    No STORY_*_MODEL env var and no gateway: inference is a cheap categorical
    projection, not a second model surface (M-c owner decision).
    """
    return DeterministicMusicDirectionEngine()


# Provider mode + routing live in packages/model_gateway/provider.py (shared with the worker): default "direct"
# (OpenAI/Gemini, never Anthropic), explicit "bedrock" opt-in is non-release only, anything else fails.
from model_gateway.provider import provider_mode as _provider_mode, routed_gateway  # noqa: E402


def get_edit_planner_engine() -> EditPlannerEngine:
    """Provide the production Edit Planner engine (Milestone M-d, frozen edit_plan/2).

    One Opus 4.6 call via the generic ModelGateway + the frozen prompt edit_plan/2, under a DETERMINISTIC
    validator (the model never self-certifies). Model is a fixed constant (used only in the explicit non-release Bedrock mode):
    the frozen us.anthropic.claude-opus-4-6-v1. Music inputs are optional (no-music planning supported).
    """
    model = EDIT_PLANNER_MODEL
    # R-d.2 reliability: 2 bounded executability-repair attempts (was 1). v4's significance weighting can
    # overshoot the ±20% tolerance on a long-payoff Story; a single repair did not always pull it back
    # (observed on device: 66.4s vs 55s target -> 503). A second trim recovers these without touching the
    # frozen prompt, EditPlan/2 contract, model, or the ±20% tolerance. Bounded: at most 2 extra Opus calls.
    repairs = 2
    # Output cap for the plan JSON. The old 2600 truncated a 24-Moment plan (proven: stop_reason=max_tokens,
    # output_tokens=2600 -> empty segments[] -> 503). 8192 fits a full ~17-segment plan; on a still-truncated
    # plan the engine escalates ONCE to the ceiling (16384). Both are fixed code constants (never configured in any environment).
    max_tokens = 8192
    ceiling = 16384
    return RealEditPlannerEngine(routed_gateway("edit_plan", model), executability_repair_attempts=repairs,
                                 max_tokens=max_tokens, max_tokens_ceiling=ceiling)


def get_music_plan_engine() -> MusicPlanEngine:
    """Provide the production MusicPlan engine (Milestone R-d, frozen music_plan/1).

    One Opus 4.6 call via the generic ModelGateway + the frozen prompt music_plan/1. Produces the Story-level
    soundtrack SHAPE at creation time (not per Moment) from CreativeIntent + authoritative MusicDirection +
    StoryGuide + StoryCoverage/2 + target duration. Model is a fixed constant:
    defaults to the frozen us.anthropic.claude-opus-4-6-v1. Never fabricates — a failure propagates so the
    caller falls back to no-music creation.
    """
    model = MUSIC_PLAN_MODEL
    return RealMusicPlanEngine(routed_gateway("music", model))


def get_duration_planner_engine() -> DurationPlannerEngine:
    """Provide the production Duration Planner engine (Milestone R-d.2, frozen duration_recommendation/1).

    One Opus 4.6 call via the generic ModelGateway + the frozen prompt. RECOMMENDS a target duration from
    CreativeIntent + StoryGuide + StoryCoverage/2 + deterministic material evidence; it does NOT select cuts
    (Edit Planner v4) or render (Media Engine), and the user owns the final choice. Model is config-driven
    (fixed constant) defaulting to the validated us.anthropic.claude-opus-4-6-v1. Never
    fabricates — a failure propagates so the caller falls back to manual duration selection.
    """
    model = DURATION_PLANNER_MODEL
    # P0 provider restore: route via the provider router so STORY_MODEL_PROVIDER=direct reaches OpenAI/Gemini
    # (the _gateway_with_fallback helper is Bedrock-only and kept calling the restricted Anthropic model).
    return RealDurationPlannerEngine(routed_gateway("duration", model))
