#!/usr/bin/env python3
"""Editorial vNext — FROZEN-INPUT tooling (offline by default; no network, no model call unless `--live` is given).

Why: a planner A/B is only a prompt comparison when BOTH arms receive byte-identical requests. The real request is deleted
when a job ends and Coverage is recomputed after every render, so two runs on one Story never match. This module freezes
one request from durable data (AU records, a Story doc's Guide/Coverage/MusicPlan/intent, a saved evidence pack) into a case
file, then renders any planner version's prompts from it, measures where the tokens go, and (only with --live) replays it.

  freeze    AU dump + Story doc  -> case.json  (the moments[] payload is rebuilt with the iOS builder's rules)
  breakdown case.json            -> token/char budget per prompt component, per planner version
  replay    case.json            -> DRY RUN by default: prompts, token estimates, cost estimate. `--live` calls the model.

The rebuilt moments[] mirrors `EditPlanRequestBuilder` (RenderSupport.swift): summary, A1 evidence, v5.3 editorial/events/
sampled_frame_ms with the model `evidence` string dropped. It is a faithful reconstruction, not a byte copy of a device request.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "packages", ROOT / "scripts"):
    sys.path.insert(0, str(p))

import edit_planner as ep                                                    # noqa: E402
import editorial_eval as EV                                                  # noqa: E402
from edit_planner import EditPlanInputs                                      # noqa: E402

PROMPTS = ROOT / "prompts" / "edit_plan"


# ---------------------------------------------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------------------------------------------
_ENC = None


def count_tokens(text: str) -> int:
    """o200k_base token count when `tiktoken` is installed, else a chars/4 estimate (always flagged by `token_method`)."""
    global _ENC
    if _ENC is None:
        try:
            import tiktoken
            _ENC = tiktoken.get_encoding("o200k_base")
        except Exception:
            _ENC = False
    if _ENC:
        return len(_ENC.encode(text))
    return max(1, len(text) // 4)


def token_method() -> str:
    count_tokens("x")
    return "tiktoken/o200k_base" if _ENC else "chars/4 estimate"


def image_tokens_estimate(n_images: int, tokens_each: int = 765) -> int:
    """Rough OpenAI-style estimate for a tiled JPEG (a 2x2 high-detail tile set ~ 765). NOT measured; the worker records the
    provider's real input_tokens, from which image tokens = input_tokens - text tokens."""
    return n_images * tokens_each


# ---------------------------------------------------------------------------------------------------------------
# rebuilding the iOS moments[] payload from an AU record
# ---------------------------------------------------------------------------------------------------------------
def _clip(s: str, n: int) -> str:
    t = s.strip()
    return t[:n] + "…" if len(t) > n else t


def _r1(x: float) -> float:
    return math.floor(x * 10 + 0.5) / 10


def understanding_summary(obs: dict) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        t = s.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower()); parts.append(t)
    if isinstance(obs.get("summary"), str):
        add(obs["summary"])
    subj = [x for x in obs.get("subjects", []) if isinstance(x, str)][:6]
    if subj:
        add("subjects: " + ", ".join(subj))
    descs = [e["description"] for e in obs.get("events", []) if isinstance(e, dict) and isinstance(e.get("description"), str)][:4]
    if descs:
        add("events: " + "; ".join(descs))
    if isinstance(obs.get("temporal_order_note"), str):
        add(obs["temporal_order_note"])
    out = " · ".join(parts)
    return out[:600] + "…" if len(out) > 600 else out


def rich_evidence(obs: dict) -> dict | None:
    o: dict = {}
    if isinstance(obs.get("summary"), str) and obs["summary"]:
        o["summary"] = _clip(obs["summary"], 320)
    seen: set[str] = set(); names: list[str] = []
    for s in obs.get("subjects", []):
        if isinstance(s, str) and s.strip() and s.strip().lower() not in seen:
            seen.add(s.strip().lower()); names.append(_clip(s, 80))
            if len(names) >= 10:
                break
    if names:
        o["subjects"] = names
    evs = []
    for e in obs.get("events", []):
        if not isinstance(e, dict) or not isinstance(e.get("description"), str) or not e["description"]:
            continue
        ev = {"what": _clip(e["description"], 90)}
        if isinstance(e.get("start_time"), (int, float)):
            ev["t"] = _r1(e["start_time"])
        if isinstance(e.get("end_time"), (int, float)):
            ev["t_end"] = _r1(e["end_time"])
        evs.append(ev)
        if len(evs) >= 8:
            break
    if evs:
        o["events"] = evs
    if isinstance(obs.get("temporal_order_note"), str) and obs["temporal_order_note"]:
        o["temporal_order_note"] = _clip(obs["temporal_order_note"], 200)
    if not o:
        return None

    def tl(x: dict) -> int:
        n = 0
        for v in x.values():
            if isinstance(v, str):
                n += len(v)
            elif isinstance(v, list):
                for y in v:
                    n += len(y) if isinstance(y, str) else sum(len(z) for z in y.values() if isinstance(z, str))
        return n
    while tl(o) > 1400 and o.get("events"):
        o["events"] = o["events"][:-1]
        if not o["events"]:
            o.pop("events")
    return o


def ios_moment_payload(moment_id: str, understanding: dict, duration: float) -> dict:
    obs = understanding.get("observed") or {}
    us = [[s["start_time"], s["end_time"]] for s in obs.get("useful_segments", [])
          if isinstance(s, dict) and isinstance(s.get("start_time"), (int, float))
          and isinstance(s.get("end_time"), (int, float)) and s["end_time"] > s["start_time"]] or [[0.0, max(1.0, duration)]]
    m: dict = {"id": moment_id.upper(), "duration_seconds": duration, "useful_segments": us,
               "summary": understanding_summary(obs)}
    ev = rich_evidence(obs)
    if ev:
        m["evidence"] = ev
    ed = understanding.get("editorial")
    if isinstance(ed, dict):
        ed = dict(ed)
        ed["visual_candidates"] = [{k: v for k, v in vc.items() if k != "evidence"} for vc in ed.get("visual_candidates", [])]
        m["editorial"] = ed
    if isinstance(obs.get("events"), list):
        m["events"] = obs["events"]
    if isinstance(understanding.get("sampled_frame_ms"), list):
        m["sampled_frame_ms"] = understanding["sampled_frame_ms"]
    return m


# ---------------------------------------------------------------------------------------------------------------
# freeze
# ---------------------------------------------------------------------------------------------------------------
def _deser(v):
    return EV._deser(v)


def freeze_case(au_items: list[dict], story_doc: dict, *, editorial_type: str, target_s: float,
                sound: str = "balanced", n_placeholder_images: int | None = None, creative_brief: str | None = None) -> dict:
    """One frozen request from durable data. `story_doc` is a story_doc/2 body; Guide/Coverage/MusicPlan are taken AS THEY ARE in
    it NOW, so freeze ONCE and reuse the file for every arm (a later Coverage recompute never reaches a frozen case)."""
    au = {}
    for it in au_items:
        r = {k: _deser(v) for k, v in it.items()}
        au[str(r["moment_id"]).lower()] = json.loads(r["understanding_json"]) if isinstance(r["understanding_json"], str) else r["understanding_json"]
    refs = story_doc["moment_refs"]
    moments = []
    for ref in sorted(refs, key=lambda r: r.get("added_at") or 0):       # request order is stable per Story
        mid = str(ref["moment_id"]).lower()
        if mid not in au:
            continue
        dur = float(ref.get("duration_seconds") or 0.0)
        if dur <= 0:
            ms = au[mid].get("sampled_frame_ms") or [0]
            dur = round(ms[-1] / 1000.0 * len(ms) / max(1, len(ms) - 1), 2)
        moments.append(ios_moment_payload(mid, au[mid], dur))
    der = story_doc.get("derived") or {}

    def blob(key: str):
        v = der.get(key) or {}
        j = v.get("json") if isinstance(v, dict) else None
        return json.loads(j) if isinstance(j, str) and j else {}
    intent = dict(story_doc["story"]["intent"])
    intent["target_duration_seconds"] = float(target_s)
    return {
        "frozen_from": {"story_id": str(story_doc["story"].get("id")), "moments": len(moments)},
        "story_id": str(story_doc["story"].get("id") or "00000000-0000-4000-8000-000000000001"),
        "creative_intent_id": str(story_doc["story"].get("id") or "00000000-0000-4000-8000-000000000002"),
        "creative_intent": intent,
        "story_guide": blob("guide"), "story_coverage": blob("coverage"), "music_plan": blob("music_plan"),
        "moments": moments,
        "sound_preference": sound,
        "editorial_type": editorial_type,
        "editorial_mode": "highlights" if editorial_type == "highlights" else "full",
        "creative_brief": creative_brief if creative_brief is not None else ep_legacy_brief(),
        "n_placeholder_images": len(moments) if n_placeholder_images is None else n_placeholder_images,
    }


def ep_legacy_brief() -> str:
    return ("When user intent does not require chronology, prioritize visually engaging and meaningful footage. "
            "Find a compelling opening, construct coherent visual progression, preserve important actions and "
            "payoffs, and choose shot durations appropriate to the material. Do not force a conventional "
            "travel-diary structure.")


# ---------------------------------------------------------------------------------------------------------------
# breakdown
# ---------------------------------------------------------------------------------------------------------------
def _inputs(case: dict) -> EditPlanInputs:
    return EV._inputs_from_case(dict(case))


def _split_user(user: str) -> tuple[str, dict]:
    head, _, rest = user.partition("\nINPUT:\n")
    js = rest.rsplit("\n\nReturn ONLY", 1)[0]
    try:
        return head, json.loads(js)
    except Exception:
        return head, {}


def breakdown(case: dict, version: str) -> dict:
    """Token budget by component for `version`. Text only; images are reported as a count and an explicit estimate."""
    with EV._version(version):
        inp = _inputs(case)
        system = EV._system_text(version)
        user = ep._build_user(inp)
        repair_head = ep._build_repair(inp, {"segments": []}, ["e"])
    head, payload = _split_user(user)
    comp: dict[str, int] = {"system_prompt": count_tokens(system), "user_directives": count_tokens(head)}
    for k, v in payload.items():
        if k == "moments":
            continue
        comp[f"input.{k}"] = count_tokens(json.dumps(v, ensure_ascii=False))
    moments = payload.get("moments") or []
    per: dict[str, int] = {}
    for m in moments:
        for k, v in m.items():
            if k == "editorial" and isinstance(v, dict):
                for kk, vv in v.items():
                    per[f"editorial.{kk}"] = per.get(f"editorial.{kk}", 0) + count_tokens(json.dumps(vv, ensure_ascii=False))
            else:
                per[k] = per.get(k, 0) + count_tokens(json.dumps(v, ensure_ascii=False))
    for k, v in per.items():
        comp[f"moments.{k}"] = v
    comp["moments.(structure)"] = max(0, count_tokens(json.dumps(moments, ensure_ascii=False)) - sum(per.values()))
    text_total = count_tokens(system) + count_tokens(user)
    n_img = len(inp.images)
    return {"version": version, "editorial_type": inp.editorial_type, "token_method": token_method(),
            "components": comp, "system_words": len(system.split()), "user_chars": len(user),
            "text_tokens": text_total, "images": n_img, "image_tokens_estimate": image_tokens_estimate(n_img),
            "input_tokens_estimate": text_total + image_tokens_estimate(n_img),
            "moments": len(moments), "repair_user_tokens": count_tokens(repair_head)}


def estimate_cost_usd(input_tokens: int, output_tokens: int, model: str = "gpt-5.1") -> float | None:
    try:
        from observability import price_lookup
        c, priced = price_lookup(input_tokens, output_tokens, model)
        return round(c, 4) if priced else None
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------------------------
def cmd_freeze(a) -> int:
    au = json.loads(Path(a.au).read_text())
    au_items = au.get("Items", au) if isinstance(au, dict) else au
    doc = json.loads(Path(a.story_doc).read_text())
    case = freeze_case(au_items, doc, editorial_type=a.type, target_s=a.target, sound=a.sound)
    Path(a.out).write_text(json.dumps(case, ensure_ascii=False))
    print(json.dumps({"out": a.out, "moments": len(case["moments"]), "type": a.type, "target_s": a.target,
                      "guide_chars": len(json.dumps(case["story_guide"])), "coverage_chars": len(json.dumps(case["story_coverage"]))}, indent=2))
    return 0


def cmd_breakdown(a) -> int:
    case = json.loads(Path(a.case).read_text())
    rows = [breakdown(case, v) for v in a.versions]
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    keys = sorted({k for r in rows for k in r["components"]}, key=lambda k: -max(r["components"].get(k, 0) for r in rows))
    print(f"token method: {rows[0]['token_method']}; images are an ESTIMATE ({rows[0]['images']} sheets)")
    print("component".ljust(34) + "".join(r["version"].rjust(9) for r in rows))
    for k in keys:
        print(k.ljust(34) + "".join(str(r["components"].get(k, 0)).rjust(9) for r in rows))
    for name in ("system_words", "text_tokens", "image_tokens_estimate", "input_tokens_estimate"):
        print(name.ljust(34) + "".join(str(r[name]).rjust(9) for r in rows))
    return 0


def cmd_replay(a) -> int:
    case = json.loads(Path(a.case).read_text())
    plan = []
    for v in a.versions:
        b = breakdown(case, v)
        out_tok = a.assumed_output_tokens
        plan.append({"version": v, "input_tokens_estimate": b["input_tokens_estimate"], "assumed_output_tokens": out_tok,
                     "est_cost_usd_per_call": estimate_cost_usd(b["input_tokens_estimate"], out_tok), "calls": a.runs})
    print(json.dumps({"mode": "LIVE" if a.live else "DRY RUN (no model call)", "case": a.case, "plan": plan,
                      "est_total_cost_usd": round(sum((p["est_cost_usd_per_call"] or 0) * p["calls"] for p in plan), 4)}, indent=2))
    if not a.live:
        return 0
    print("--live is intentionally not wired in this milestone: the owner has not authorised a live run; "
          "use the real app on development with the version pinned, and compare with editorial_eval.py.", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--au", required=True); f.add_argument("--story-doc", required=True)
    f.add_argument("--type", choices=["highlights", "full_story"], required=True); f.add_argument("--target", type=float, required=True)
    f.add_argument("--sound", default="balanced"); f.add_argument("--out", required=True); f.set_defaults(fn=cmd_freeze)
    b = sub.add_parser("breakdown"); b.add_argument("--case", required=True); b.add_argument("--versions", nargs="+", default=["5.5", "5.6"])
    b.add_argument("--json", action="store_true"); b.set_defaults(fn=cmd_breakdown)
    r = sub.add_parser("replay"); r.add_argument("--case", required=True); r.add_argument("--versions", nargs="+", default=["5.5", "5.6"])
    r.add_argument("--runs", type=int, default=1); r.add_argument("--assumed-output-tokens", type=int, default=3000)
    r.add_argument("--live", action="store_true"); r.set_defaults(fn=cmd_replay)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
