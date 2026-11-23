"""Story Director Engine — the real Director (Milestone C3A).

INITIALIZE: CreativeIntent + SceneUnderstanding + CaptureConstraints
            -> StoryConcept + StoryPlan{beats,shots} + DirectorState + DirectorDecision
NEXT:       prior DirectorState + Story-progress descriptors
            -> updated DirectorState + one DirectorDecision

Owns (milestone-c-story-director-design.md; task §4-§11): the versioned prompt,
the output envelope schema (composed from the FROZEN canonical contracts —
StoryConcept / StoryPlan{StoryBeat,Shot} / DirectorDecision / DirectorState),
request construction, referential-integrity + scene-grounding + safety guards,
canonical validation, and no-fabrication failure behaviour.

Depends only on contracts + model_gateway (03 §40). No provider SDK, no Bedrock
coupling. Model is task-specific config (Director model != CI != SU != validation).
No real Shot Validation here — that is C4.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from contracts.schemas.ai_contracts import (
    CreativeIntentContract,
    DirectorDecision,
    DirectorState,
    SceneUnderstandingContract,
    StoryConceptContract,
    StoryPlanContract,
)
from language_policy import apply_language_suffix, contains_han
from model_gateway import (
    ModelGateway,
    StructuredOutputError,
    StructuredRequest,
    StructuredResult,
    Usage,
)

# v2 (Phase 1A visual Shooting Ideas): identical to v1 plus ONE optional per-shot
# `visual_reference_query` the model writes in the same call (no extra inference).
# v3 (AI Ideas latency): same direction rules, shorter OUTPUT. The model writes each shot once: the decision
# points at a plan shot by `plan_shot_id`, `alternatives` holds only the OTHER ideas (the server rebuilds
# candidates = [decision, *alternatives]), and director_state.last_decision / concept.rationale are not
# model-written. The wire DirectorOutput is unchanged.
# Rollback = point these back at v2 (prompts/story_director/v2 is kept unchanged).
PROMPT_VERSION = "story_director/v3"
SCHEMA_VERSION = "story_director.envelope/3"
TASK_INIT = "story_director.initialize"
TASK_NEXT = "story_director.next"

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "story_director" / "v3"

# ---- Lean model output (v3) -----------------------------------------------------
# MODEL-FACING ONLY keys, resolved in _mint_ids and never present on the validated DirectorOutput.
PLAN_SHOT_REF_KEY = "plan_shot_id"      # on a decision: "this decision's shot is plan.shots[id]"
ALTERNATIVES_KEY = "alternatives"       # up to MAX_ALTERNATIVES other decisions for the same slot
MAX_ALTERNATIVES = 2

# ---- Visual reference queries (Phase 1A) -----------------------------------
# The model may attach `visual_reference_query` to any shot it emits. It is NOT a field of the FROZEN
# canonical ShotContract: it exists only in the MODEL-FACING schema, is popped from every shot before
# canonical validation, sanitized, and surfaced on the engine envelope as
# `shot_reference_queries[<server-minted shot id>]`. iOS uses it to fetch ONE stock reference photo via
# the existing /v1/scene-image proxy (which re-sanitizes it). Absent/invalid => text-only card.
REFERENCE_QUERY_KEY = "visual_reference_query"
# Owner rule: NEVER withhold a reference photo because of the query's FORMAT. The query is normalized
# (never rejected for length / word count / punctuation); it is truncated to this many words.
REFERENCE_QUERY_MAX_WORDS = 12
_RQ_URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_RQ_EMAIL_RE = re.compile(r"\S+@\S+")
_RQ_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_RQ_NON_WORD_RE = re.compile(r"[^a-z\- ]+")
_RQ_SCHEMA_DESCRIPTION = (
    "3-6 plain GENERIC stock-photo search keywords for an example photo of this shot: ONE framing term, "
    "then the main subject TYPE, then at most one setting word, e.g. 'close up acoustic guitar bookshelf', "
    "'wide sofa living room', 'pan city window night'. No names, no personal details, no punctuation."
)


def sanitize_reference_query(raw: Any) -> str | None:
    """Normalize a model-written reference query; never rejects it for format. URL/email TOKENS are removed
    (privacy), control chars / digits / punctuation become spaces, case is lowered, the phrase is truncated
    to REFERENCE_QUERY_MAX_WORDS. Returns None only when no usable words remain. Never raises: a bad query
    must not fail the Director. (/v1/scene-image normalizes again and broadens on a no-match.)"""
    if not isinstance(raw, str):
        return None
    if contains_han(raw):
        # Search queries must be short ENGLISH keywords. A query that still carries Han characters would only
        # reach the stock-photo provider as garbage (or a half-translated fragment) -> unusable => text-only
        # card via the existing graceful no-image path. Never raises.
        return None
    q = _RQ_CONTROL_RE.sub(" ", raw)
    q = _RQ_URL_RE.sub(" ", q)
    q = _RQ_EMAIL_RE.sub(" ", q)
    q = _RQ_NON_WORD_RE.sub(" ", q.lower())
    words = [w.strip("-") for w in q.split()]
    words = [w for w in words if w]
    if not words:
        return None
    return " ".join(words[:REFERENCE_QUERY_MAX_WORDS])

# Deterministic safety backstop — the model must not emit these in any shot
# instruction/purpose (prompt is the primary guard; this is the hard gate).
_UNSAFE_SUBSTRINGS = (
    "walk backward",
    "walking backward",
    "step back toward",
    "into traffic",
    "onto the road",
    "into the road",
    "climb onto",
    "lean over the edge",
    "near the edge while",
    # Simplified-Chinese equivalents (content_language=zh-Hans output) — same hard safety backstop.
    "倒退着走", "倒着走", "后退着走", "边走边后退", "冲进车流", "走进车流", "走到马路中", "走上马路",
    "爬上栏杆", "爬上围栏", "探身出", "探出边缘", "靠近边缘时",
)


class DirectorOutput(BaseModel):
    """The Director's output envelope — composed from the frozen contracts.
    This is an ENGINE output shape, not a new canonical contract."""

    model_config = ConfigDict(extra="forbid")

    concept: StoryConceptContract
    plan: StoryPlanContract
    director_state: DirectorState
    decision: DirectorDecision
    # EPHEMERAL ranked ALTERNATIVES for the current recommendation slot (DIRECT UX).
    # candidates[0] == `decision`. These are session/UI data only — NOT persisted into
    # StoryPlan, NOT additional required captures. The user captures AT MOST ONE. They do
    # not add beats/shots and do not change Story coverage requirements.
    candidates: list[DirectorDecision] = Field(default_factory=list)
    # Phase 1A: server-minted shot id (str UUID) -> sanitized generic stock-photo query for that shot.
    # Instructional UI only (one optional reference photo per Shooting Idea); never persisted into
    # StoryPlan, never a Moment/asset. Additive: older clients ignore it, empty when the model omitted it.
    shot_reference_queries: dict[str, str] = Field(default_factory=dict)


def _load_system_prompt() -> str:
    return (_PROMPT_DIR / "system.md").read_text()


# Appended to the user content when requesting ephemeral alternatives (DIRECT UX).
# The server builds candidates = [decision, *alternatives], so the model never repeats the decision.
# Alternatives are genuinely different approaches to the SAME narrative need, not paraphrases. They are
# NOT a multi-shot plan and must NOT add beats/shots. The user captures at most one.
_CANDIDATES_INSTRUCTION = (
    "\n\nALTERNATIVES: also return `alternatives` — up to 2 RANKED alternative decisions for "
    "the SAME current slot, each with the SAME action as `decision`. Do NOT repeat `decision` "
    "in `alternatives`. Each must be a GENUINELY DIFFERENT creative approach (different "
    "subject_action / framing / angle) to serve the SAME narrative need, NOT a paraphrase. They "
    "are EPHEMERAL: the user captures AT MOST ONE. Do NOT add beats or shots to the plan for "
    "them, do NOT treat them as additional required captures, and keep plan.beats / plan.shots "
    "exactly as minimal as for a single recommendation. Every alternative must independently "
    "satisfy feasibility, safety, scene-grounding (or environment-agnosticism when the scene is "
    "null), and narrative relevance."
)


def _envelope_schema() -> dict:
    """JSON Schema the model must satisfy. Server owns ids (concept/plan/shot
    ids are minted by us if the model omits them), so we relax `required` to the
    creative content and reconcile ids in _to_output.

    v3 lean output: the model-facing schema drops `candidates` (rebuilt server-side from `decision` +
    `alternatives`), `director_state.last_decision` (server-filled) and `concept.rationale` (never shown),
    and lets a decision reference a plan shot by id instead of repeating it."""
    schema = copy.deepcopy(DirectorOutput.model_json_schema())
    props = schema.get("properties", {})
    defs = schema.get("$defs", {})
    # Server-computed, never model-authored.
    for key in ("shot_reference_queries", "candidates"):
        props.pop(key, None)
        if key in schema.get("required", []):
            schema["required"].remove(key)
    props[ALTERNATIVES_KEY] = {
        "type": "array",
        "maxItems": MAX_ALTERNATIVES,
        "items": {"$ref": "#/$defs/DirectorDecision"},
        "description": "Up to 2 OTHER ideas for the same slot. Never repeats `decision`.",
    }
    decision_def = defs.get("DirectorDecision")
    if isinstance(decision_def, dict):
        decision_def.setdefault("properties", {})[PLAN_SHOT_REF_KEY] = {
            "type": "string",
            "description": "id of the plan.shots entry this decision captures. When set, omit `shot`.",
        }
    state_def = defs.get("DirectorState")
    if isinstance(state_def, dict):
        state_def.get("properties", {}).pop("last_decision", None)
    concept_def = defs.get("StoryConceptContract")
    if isinstance(concept_def, dict):
        concept_def.get("properties", {}).pop("rationale", None)
    # MODEL-FACING ONLY: allow an optional per-shot reference query. The canonical (frozen) ShotContract
    # model is untouched; _mint_ids pops the key before canonical validation.
    shot_def = defs.get("ShotContract")
    if isinstance(shot_def, dict):
        shot_def.setdefault("properties", {})[REFERENCE_QUERY_KEY] = {
            "type": "string", "description": _RQ_SCHEMA_DESCRIPTION,
        }
    return schema


@runtime_checkable
class StoryDirectorEngine(Protocol):
    def initialize(
        self,
        creative_intent: dict[str, Any],
        scene_understanding: dict[str, Any] | None = None,
        capture_constraints: dict[str, Any] | None = None,
        selected_opportunity: dict[str, Any] | None = None,
        content_language: str | None = None,
    ) -> DirectorOutput: ...

    def next(
        self,
        prior: dict[str, Any],
        content_language: str | None = None,
    ) -> DirectorOutput: ...


class RealStoryDirectorEngine:
    def __init__(self, gateway: ModelGateway, max_repair_attempts: int = 1):
        self._gateway = gateway
        self._system = _load_system_prompt()
        self._schema = _envelope_schema()
        self._max_repair_attempts = max_repair_attempts
        # Token/cost accounting surface for the "AI Idea" (Director) capability. Mirrors the
        # `last_diagnostics` pattern used by the edit planner / AU engines: the frozen DirectorOutput
        # contract carries no usage, so the last call's usage is exposed HERE for the API layer to log
        # (privacy-safe token COUNTS + served model only). Populated by _to_output on every call; None
        # until the first call. Without this, direct-provider Director spend was never measured.
        self.last_usage: Usage | None = None
        self.last_model: str | None = None
        self.last_provider: str | None = None

    # ---- requests ----------------------------------------------------------

    def build_initialize_request(
        self,
        creative_intent: dict[str, Any],
        scene_understanding: dict[str, Any] | None,
        capture_constraints: dict[str, Any] | None,
        selected_opportunity: dict[str, Any] | None = None,
        content_language: str | None = None,
    ) -> StructuredRequest:
        import json
        null_scene = not scene_understanding
        content = {
            "operation": "initialize",
            "creative_intent": creative_intent,
            "scene_understanding": scene_understanding,   # may be null (Skip Scan)
            "capture_constraints": capture_constraints or {},
        }
        if selected_opportunity:
            # The high-level narrative opportunity the user EXPLICITLY chose (Story Idea -> Show me,
            # or Guide possibility -> Shoot). Semantic WHAT, not a literal shot/constraint.
            content["selected_opportunity"] = selected_opportunity
        prefix = ""
        if null_scene:
            # Skip Scan: no surroundings known. Prompt's SKIP-SCAN clause governs; this
            # just marks the mode explicitly in the user content.
            prefix = (
                "NOTE: scene_understanding is NULL — the user SKIPPED the scene scan, so you "
                "have NO information about their physical surroundings. Follow the SKIP-SCAN / "
                "NO SCENE rule: one actionable capture_shot grounded ONLY in the intent and the "
                "user, environment-agnostic, inventing nothing; exactly one beat and one shot; "
                "do not rescan.\n\n"
            )
        if selected_opportunity:
            prefix += (
                "NOTE: selected_opportunity is PRESENT — the user explicitly chose this high-level "
                "narrative goal. Decide HOW to realize it using only what the current scene genuinely "
                "supports; it is semantic, not a literal required shot. If the scene cannot meaningfully "
                "serve it, use rescan_scene rather than forcing a connection.\n\n"
            )
        return StructuredRequest(
            task=TASK_INIT,
            schema=self._schema,
            prompt_version=PROMPT_VERSION,
            system=apply_language_suffix(self._system, content_language),
            user_content=(
                prefix
                + "INITIALIZE. Produce the concept, plan (beats + shots), initial "
                "director_state, the first decision, and up to 2 `alternatives` (other ideas "
                "for this ONE slot, never repeating the decision; do NOT add beats/shots for "
                "them) for this task:\n"
                + json.dumps(content, ensure_ascii=False)
                + _CANDIDATES_INSTRUCTION
            ),
            max_repair_attempts=self._max_repair_attempts,
            max_tokens=2200,
            temperature=0.3,
        )

    def build_next_request(self, prior: dict[str, Any], content_language: str | None = None) -> StructuredRequest:
        import json
        return StructuredRequest(
            task=TASK_NEXT,
            schema=self._schema,
            prompt_version=PROMPT_VERSION,
            system=apply_language_suffix(self._system, content_language),
            user_content=(
                "NEXT. Given the prior plan/state and the Story progress so far, "
                "update director_state and return exactly ONE next decision. Keep "
                "the same concept unless the plan genuinely must change:\n"
                + json.dumps(prior, ensure_ascii=False)
            ),
            max_repair_attempts=self._max_repair_attempts,
            max_tokens=1600,
            temperature=0.3,
        )

    # ---- ops ---------------------------------------------------------------

    def initialize(self, creative_intent, scene_understanding=None, capture_constraints=None, selected_opportunity=None,
                   content_language=None) -> DirectorOutput:
        req = self.build_initialize_request(creative_intent, scene_understanding, capture_constraints, selected_opportunity,
                                            content_language)
        return self._to_output(self._gateway.generate_structured(req))

    def next(self, prior, content_language=None) -> DirectorOutput:
        req = self.build_next_request(prior, content_language)
        return self._to_output(self._gateway.generate_structured(req))

    # ---- validation --------------------------------------------------------

    def _to_output(self, result: StructuredResult) -> DirectorOutput:
        # Capture the call's token usage + served model for cost accounting BEFORE validation,
        # so even a validation failure's spend is attributable from the engine instance.
        self.last_usage = result.usage
        self.last_model = result.model
        self.last_provider = result.provider
        data = self._mint_ids(dict(result.data))
        try:
            out = DirectorOutput.model_validate(data)
        except Exception as e:
            raise StructuredOutputError(f"director output failed canonical validation: {e}") from e
        self._integrity_guard(out)
        self._safety_guard(out)
        return out

    @staticmethod
    def _mint_ids(data: dict[str, Any]) -> dict[str, Any]:
        """Server OWNS the opaque UUID ids (concept/plan/shot) — overwrite
        whatever the model emitted (it often returns 'shot1'/'s1'). StoryBeat.id
        is a free string and is left as-is; shot.beat_id references to those beats
        are preserved. The model's creative content is untouched."""
        shot_id_map: dict[str, str] = {}
        # Never trust a model-authored map; the server builds it from the per-shot queries below.
        data.pop("shot_reference_queries", None)
        ref_queries: dict[str, str] = {}

        def _take_reference_query(shot: dict[str, Any]) -> None:
            # Pop the MODEL-FACING key (the frozen ShotContract forbids extras) and keep it, sanitized,
            # under the shot's server-minted id. Call AFTER shot["id"] is minted.
            q = sanitize_reference_query(shot.pop(REFERENCE_QUERY_KEY, None))
            sid = shot.get("id")
            if q and isinstance(sid, str) and sid not in ref_queries:
                ref_queries[sid] = q

        concept = data.get("concept")
        if isinstance(concept, dict):
            concept["id"] = str(uuid4())
            concept.pop("preview_asset_id", None)       # asset-owned, not the model's
            concept.pop("target_narrative_need_id", None)
        plan = data.get("plan")
        if isinstance(plan, dict):
            plan["id"] = str(uuid4())
            if isinstance(concept, dict):
                plan["concept_id"] = concept["id"]
            # Map any model shot id -> a fresh UUID; keep the decision's shot id aligned.
            for shot in plan.get("shots", []) or []:
                if isinstance(shot, dict):
                    shot.pop("example_asset_id", None)   # asset-owned, not the model's
                    old = shot.get("id")
                    new = str(uuid4())
                    if isinstance(old, (str, int)) and not isinstance(old, bool):
                        shot_id_map[str(old)] = new
                    shot["id"] = new
                    _take_reference_query(shot)
        # The decision shot is minted even without a plan dict (create_now/rescan carry none anyway),
        # so its reference-query key is always popped before canonical validation.
        minted_plan_shots: dict[str, dict[str, Any]] = {}
        if isinstance(plan, dict):
            for shot in plan.get("shots", []) or []:
                if isinstance(shot, dict) and isinstance(shot.get("id"), str):
                    minted_plan_shots[shot["id"]] = shot

        def _prepare(dec: dict[str, Any]) -> None:
            # Mint a decision's shot id, or (v3) resolve `plan_shot_id` to a copy of the already-minted plan
            # shot so the validated output has the old full shape. An unknown ref with no shot leaves `shot`
            # absent, and _integrity_guard rejects a capture_shot without one.
            ref = dec.pop(PLAN_SHOT_REF_KEY, None)
            s = dec.get("shot")
            if isinstance(s, dict):
                s.pop("example_asset_id", None)
                old = s.get("id")
                # If the decision's shot matches a plan shot by old id, reuse its UUID.
                s["id"] = shot_id_map.get(old, str(uuid4())) if isinstance(old, str) else str(uuid4())
                _take_reference_query(s)
            elif isinstance(ref, (str, int)) and shot_id_map.get(str(ref)) in minted_plan_shots:
                dec["shot"] = copy.deepcopy(minted_plan_shots[shot_id_map[str(ref)]])

        decision = data.get("decision")
        if isinstance(decision, dict):
            _prepare(decision)
            if (decision.get("action") in ("capture_shot", "retry_shot")
                    and not isinstance(decision.get("shot"), dict) and minted_plan_shots):
                # A shot-bearing decision whose plan_shot_id did not resolve: fall back to the plan shot for the
                # current beat (else the first plan shot) rather than failing the user's AI Ideas request.
                ds0 = data.get("director_state") if isinstance(data.get("director_state"), dict) else {}
                beat = ds0.get("current_beat_id")
                pick = next((s for s in minted_plan_shots.values() if beat and s.get("beat_id") == beat),
                            next(iter(minted_plan_shots.values())))
                decision["shot"] = copy.deepcopy(pick)
        data.setdefault("director_state", {"beat_progress": []})
        # Ephemeral candidates[]: each carries a shot whose model id must be minted too.
        # Reuse the plan shot's UUID when a candidate references the same old id; otherwise
        # mint fresh. candidates do NOT create plan beats/shots.
        # v3: the model writes `alternatives` (never repeating the decision) and the server rebuilds
        # candidates = [decision, *alternatives]. A legacy `candidates` list (v2 output) is kept as-is.
        alternatives = data.pop(ALTERNATIVES_KEY, None)
        candidates = data.get("candidates")
        if isinstance(candidates, list):
            for cand in candidates:
                if isinstance(cand, dict):
                    _prepare(cand)
        elif isinstance(alternatives, list) and isinstance(decision, dict):
            alts = [a for a in alternatives if isinstance(a, dict)][:MAX_ALTERNATIVES]
            for alt in alts:
                _prepare(alt)
            # An alternative that needs a shot but has none (unresolved ref) is dropped, never fatal.
            alts = [a for a in alts
                    if a.get("action") not in ("capture_shot", "retry_shot") or isinstance(a.get("shot"), dict)]
            data["candidates"] = [copy.deepcopy(decision), *alts] if alts else []
        # director_state.last_decision may embed a shot with a model id too.
        ds = data.get("director_state")
        if isinstance(ds, dict):
            ds.setdefault("beat_progress", [])
            ld = ds.get("last_decision")
            if isinstance(ld, dict) and isinstance(ld.get("shot"), dict):
                ld["shot"].pop("example_asset_id", None)
                old = ld["shot"].get("id")
                ld["shot"]["id"] = shot_id_map.get(old, str(uuid4())) if isinstance(old, str) else str(uuid4())
                ld["shot"].pop(REFERENCE_QUERY_KEY, None)   # state echo: drop, never surfaced
            if isinstance(ld, dict):
                ld.pop(PLAN_SHOT_REF_KEY, None)
            elif isinstance(decision, dict):
                # v3: the model no longer writes last_decision; it is the decision just made.
                ds["last_decision"] = copy.deepcopy(decision)
        data["shot_reference_queries"] = ref_queries
        return data

    @staticmethod
    def _integrity_guard(out: DirectorOutput) -> None:
        action = out.decision.action.value
        # rescan_scene = Director declines this scene; create_now = enough already.
        # Both legitimately carry NO plan — do not force beats/shots on them.
        declines = action in ("rescan_scene", "create_now")
        beat_ids = {b.id for b in out.plan.beats}
        if not out.plan.beats and not declines:
            raise StructuredOutputError("plan has no beats; every shot must serve a beat")
        for s in out.plan.shots:
            if s.beat_id is None or s.beat_id not in beat_ids:
                raise StructuredOutputError(
                    f"shot {s.id} does not reference a real beat (beat_id={s.beat_id!r})"
                )
            if not (s.purpose and s.instruction):
                raise StructuredOutputError("every shot needs both a purpose and a user instruction")
        act = out.decision.action.value
        if act in ("capture_shot", "retry_shot") and out.decision.shot is None:
            raise StructuredOutputError(f"{act} decision must carry a shot")
        if act in ("create_now", "rescan_scene") and out.decision.shot is not None:
            raise StructuredOutputError(f"{act} decision must not carry a shot")
        # Ephemeral candidates must NOT inflate the plan (anti-over-planning), and
        # candidates[0] must mirror the primary decision's action. They add no beats/shots.
        if out.candidates:
            if out.candidates[0].action != out.decision.action:
                raise StructuredOutputError("candidates[0] must equal the primary decision")
            for c in out.candidates:
                if c.action in ("capture_shot", "retry_shot") and c.shot is None:
                    raise StructuredOutputError("a shot-bearing candidate is missing its shot")
                # a candidate shot (when present) must still reference a real beat
                if c.shot is not None and c.shot.beat_id is not None and c.shot.beat_id not in beat_ids:
                    raise StructuredOutputError("candidate shot references a non-existent beat")

    @staticmethod
    def _safety_guard(out: DirectorOutput) -> None:
        texts = []
        for s in out.plan.shots:
            texts += [s.instruction or "", s.purpose or "", s.subject_action or "", s.camera_motion or ""]
        if out.decision.shot is not None:
            d = out.decision.shot
            texts += [d.instruction or "", d.purpose or "", d.subject_action or "", d.camera_motion or ""]
        for c in out.candidates:                       # candidates must be safe too
            if c.shot is not None:
                texts += [c.shot.instruction or "", c.shot.purpose or "",
                          c.shot.subject_action or "", c.shot.camera_motion or ""]
        blob = " ".join(texts).lower()
        hit = next((s for s in _UNSAFE_SUBSTRINGS if s in blob), None)
        if hit is not None:
            raise StructuredOutputError(
                f"director output contained an unsafe instruction ({hit!r}); "
                "Director must stay conservative regardless of scene"
            )


class MockStoryDirectorEngine:
    """Deterministic mock (no model). Dev/tests only — never production direction."""

    def initialize(self, creative_intent, scene_understanding, capture_constraints=None, selected_opportunity=None,
                   content_language=None) -> DirectorOutput:
        cid, pid, sid, bid = uuid4(), uuid4(), uuid4(), "beat_open"
        from contracts.schemas.ai_contracts import ShotContract, StoryBeat
        concept = StoryConceptContract(id=cid, title="Mock concept", summary="A mock point of view.")
        shot = ShotContract(id=sid, order=1, instruction="Hold steady on the scene for a few seconds.",
                            beat_id=bid, purpose="Establish the place.")
        plan = StoryPlanContract(id=pid, concept_id=cid,
                                 beats=[StoryBeat(id=bid, purpose="Establish the place.")], shots=[shot])
        return DirectorOutput(
            concept=concept, plan=plan,
            director_state=DirectorState(current_beat_id=bid, beat_progress=[]),
            decision=DirectorDecision(action="capture_shot", shot=shot, reason="mock"),
        )

    def next(self, prior, content_language=None) -> DirectorOutput:
        return self.initialize(prior.get("creative_intent", {}), prior.get("scene_understanding", {}))


__all__ = [
    "PROMPT_VERSION", "SCHEMA_VERSION", "TASK_INIT", "TASK_NEXT",
    "REFERENCE_QUERY_KEY", "sanitize_reference_query",
    "PLAN_SHOT_REF_KEY", "ALTERNATIVES_KEY", "MAX_ALTERNATIVES",
    "DirectorOutput", "StoryDirectorEngine", "RealStoryDirectorEngine", "MockStoryDirectorEngine",
]
