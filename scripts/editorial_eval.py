#!/usr/bin/env python3
"""Editorial vNext — OFFLINE evaluation harness (no model call, no AWS, no network, no media).

Compares the planner's baseline (edit_plan/5.3) and candidate (edit_plan/5.5) on identical source evidence, and turns
saved edit-plan job records into comparable metric rows. It never claims quality: it records what was asked, what the
model returned, and deterministic numbers about the result. Quality is judged by the owner on RENDERED videos.

  render   Render the system + user + repair prompts for one case under each prompt version, plus a unified diff.
           (Mock-free and model-free: shows exactly what each version would send. Proves nothing about quality.)
  metrics  One job record (+ optional AU dump) -> one metric row.
  compare  Several job records -> a markdown/JSON table, with guards against invalid comparisons
           (an Explore must not be compared with an Original; targets/types must match across a pair).

Inputs are local files the owner points at (job-item JSON as exported from the jobs table, an AU query dump, or a
case JSON). Nothing private is written into the repo; pass --out to a scratch or a git-ignored directory.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "packages"):
    sys.path.insert(0, str(p))

import edit_planner as ep                                                         # noqa: E402
from edit_planner import EditPlanInputs, selection_diagnostics, validate_plan     # noqa: E402

PROMPTS = ROOT / "prompts" / "edit_plan"


# ---------------------------------------------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------------------------------------------
from contextlib import contextmanager                                              # noqa: E402


@contextmanager
def _version(version: str):
    """Temporarily select a planner version in-process; always restores the real module state."""
    saved = (ep._EDIT_PLAN_VERSION, ep._v53_active, ep._v55_active)
    ep._EDIT_PLAN_VERSION = version
    ep._v53_active = lambda: float(version) >= 5.3                                  # type: ignore[assignment]
    ep._v55_active = lambda: float(version) >= 5.5                                  # type: ignore[assignment]
    try:
        yield
    finally:
        ep._EDIT_PLAN_VERSION, ep._v53_active, ep._v55_active = saved


def _system_text(version: str) -> str:
    t = (PROMPTS / version / "system.md").read_text()
    return (t.split("-->", 1)[1] if t.lstrip().startswith("<!--") else t).strip()


def _inputs_from_case(case: dict) -> EditPlanInputs:
    from model_gateway import ImageInput
    c = dict(case)
    n_img = int(c.pop("n_placeholder_images", 0) or 0)
    c.setdefault("story_id", "00000000-0000-4000-8000-000000000001")
    c.setdefault("creative_intent_id", "00000000-0000-4000-8000-000000000002")
    c.setdefault("story_guide", {}); c.setdefault("story_coverage", {}); c.setdefault("music_plan", {})
    if n_img:
        c["images"] = [ImageInput(b"\xff\xd8x") for _ in range(n_img)]
        c.setdefault("image_moment_order", [m["id"] for m in c["moments"]][:n_img])
    return EditPlanInputs(**c)


def cmd_render(a) -> int:
    case = json.loads(Path(a.case).read_text())
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    summary, user_texts = {}, {}
    for v in a.versions:
        with _version(v):
            inp = _inputs_from_case(case)
            sysx, user = _system_text(v), ep._build_user(inp)
            repair = ep._build_repair(inp, {"segments": []}, ["example validator error"])
            hint = ep.compute_budget_hint(inp) if float(v) >= 5.5 else None
        d = out / v; d.mkdir(exist_ok=True)
        (d / "system.txt").write_text(sysx); (d / "user.txt").write_text(user); (d / "repair.txt").write_text(repair)
        user_texts[v] = user
        summary[v] = {"prompt_version": f"edit_plan/{v}", "system_chars": len(sysx), "user_chars": len(user),
                      "approx_text_tokens": (len(sysx) + len(user)) // 4,
                      "editorial_type": inp.editorial_type, "moments": len(inp.moments), "images": len(inp.images),
                      "budget_hint": hint}
    if len(a.versions) >= 2:
        x, y = a.versions[0], a.versions[1]
        diff = difflib.unified_diff(user_texts[x].splitlines(), user_texts[y].splitlines(), f"user@{x}", f"user@{y}", lineterm="")
        (out / "user.diff").write_text("\n".join(diff))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


# ---------------------------------------------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------------------------------------------
def _deser(v):
    """Accept DynamoDB-JSON ({'S':..}) or already-plain values."""
    try:
        from boto3.dynamodb.types import TypeDeserializer
        if isinstance(v, dict) and len(v) == 1 and next(iter(v)) in ("S", "N", "M", "L", "BOOL", "NULL", "SS", "NS"):
            return TypeDeserializer().deserialize(v)
    except Exception:
        pass
    return v


def load_job(path: str) -> dict:
    raw = json.loads(Path(path).read_text())
    if "Item" in raw:
        raw = raw["Item"]
    return {k: _deser(v) for k, v in raw.items()}


def load_au_moments(path: str | None) -> list[dict]:
    """AU query dump -> planner Moment dicts (id, duration, useful segments, editorial, events)."""
    if not path:
        return []
    raw = json.loads(Path(path).read_text())
    items = raw.get("Items", raw) if isinstance(raw, dict) else raw
    out = []
    for it in items:
        r = {k: _deser(v) for k, v in it.items()}
        try:
            j = json.loads(r["understanding_json"]) if isinstance(r.get("understanding_json"), str) else r["understanding_json"]
        except Exception:
            continue
        obs = j.get("observed") or {}
        ms = j.get("sampled_frame_ms") or [0]
        n = max(2, len(ms))
        dur = round(ms[-1] / 1000.0 * n / (n - 1), 2)
        us = [[u.get("start_time"), u.get("end_time")] for u in (obs.get("useful_segments") or []) if isinstance(u, dict)]
        out.append({"id": str(r.get("moment_id") or j.get("moment_id")).lower(), "duration_seconds": dur,
                    "useful_segments": us or [[0, dur]], "editorial": j.get("editorial"), "events": obs.get("events")})
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


_PLAN_NUM = ("order", "source_start_seconds", "source_end_seconds", "output_duration_seconds", "speed")


def _coerce_plan(plan: dict) -> dict:
    """Job items round-trip numbers as Decimal/str; the planner's validator needs floats."""
    out = dict(plan or {})
    segs = []
    for sg in out.get("segments", []) or []:
        sg = dict(sg)
        for k in _PLAN_NUM:
            if sg.get(k) is not None and _num(sg.get(k)) is not None:
                sg[k] = int(float(sg[k])) if k == "order" else float(sg[k])
        segs.append(sg)
    out["segments"] = segs
    if _num(out.get("target_duration_seconds")) is not None:
        out["target_duration_seconds"] = float(out["target_duration_seconds"])
    return out


def job_metrics(job: dict, au_moments: list[dict] | None = None, label: str | None = None) -> dict:
    d = job.get("diagnostics") or {}
    plan = _coerce_plan(job.get("plan") or {})
    ed = d.get("editorial") or {}
    rd = d.get("rev_diag") or {}
    fit = d.get("duration_fit") or {}
    target = _num(plan.get("target_duration_seconds"))
    sel = d.get("selection") if isinstance(d.get("selection"), dict) else None
    order = (job.get("request_ref") or {}).get("sheet_order")
    sheet_ids = json.loads(order) if isinstance(order, str) else (order or [])
    mset = {m["id"] for m in (au_moments or [])}
    moments = [m for m in (au_moments or []) if (not sheet_ids) or m["id"] in {str(s).lower() for s in sheet_ids}]
    try:
        inp = EditPlanInputs(story_id="00000000-0000-4000-8000-000000000001", creative_intent_id="00000000-0000-4000-8000-000000000002",
                             creative_intent={"target_duration_seconds": target or 1.0}, story_guide={}, story_coverage={},
                             moments=moments, music_plan={}, editorial_type=ed.get("requested"))
    except Exception:
        inp = None
    if sel is None and inp is not None and moments:
        sel = selection_diagnostics(plan, inp, d, None)
    segs = sorted(plan.get("segments", []) or [], key=lambda s: _num(s.get("order")) or 0)
    outs = [_num(s.get("output_duration_seconds")) for s in segs if _num(s.get("output_duration_seconds")) is not None]
    stats = ep._shot_stats(outs)
    before, after = _num(fit.get("before_s")), _num(fit.get("after_s"))
    dropped = len(fit.get("dropped") or [])
    if isinstance(d.get("selection"), dict):          # recorded by the worker (v5.5-era jobs and later)
        pre_total = d["selection"]["budget"]["pre_fit_total_s"]
        pre_n = (d["selection"].get("pre_fit") or {}).get("n")
    else:                                             # baseline job recorded before M1: derive from the duration fit
        pre_total = before if before is not None else (sum(outs) if outs else None)
        pre_n = len(outs) + dropped
    valid = None
    if inp is not None and moments:
        try:
            valid = not validate_plan({"segments": plan.get("segments", []), "target_duration_seconds": target}, inp)
        except Exception:
            valid = None
    pay = [u for u in (sel or {}).get("used", []) if "p" in u]
    cost = None
    try:
        from observability import price_lookup
        c, priced = price_lookup(d.get("input_tokens") or 0, d.get("output_tokens") or 0, d.get("model_id") or "")
        cost = round(c, 4) if priced else None
    except Exception:
        cost = None
    created, updated = _num(job.get("created_at")), _num(job.get("updated_at"))
    return {
        "label": label or str(job.get("job_id", ""))[:8],
        "job": str(job.get("job_id", ""))[:8],
        "prompt_version": d.get("prompt_version") or ed.get("prompt_version"),
        "editorial_type": ed.get("requested") or (sel or {}).get("editorial_type"),
        "operation": (rd.get("mode") or "original"),
        "target_s": target, "target_source": d.get("duration_target_source") or "unrecorded",
        "moments": (sel or {}).get("n_moments") or len(sheet_ids) or None, "sheets": d.get("sheet_count"),
        "model_calls": d.get("model_calls"), "first_pass_executable": d.get("first_pass_executable"),
        "completion": d.get("completion"), "valid": valid,
        "pre_fit_total_s": round(pre_total, 1) if pre_total is not None else None,
        "pre_fit_overshoot_pct": round((pre_total / target - 1) * 100, 1) if (pre_total and target) else None,
        "delivered_s": round(sum(outs), 1) if outs else None,
        "delivered_overshoot_pct": round((sum(outs) / target - 1) * 100, 1) if (outs and target) else None,
        "shots": stats.get("n"), "distinct": len({str(s.get("asset_id")).lower() for s in segs}),
        "pre_fit_shots": pre_n, "pre_fit_mean_s": round(pre_total / pre_n, 2) if (pre_total and pre_n) else None,
        "mean_s": stats.get("mean_s"), "median_s": stats.get("median_s"), "p25_s": stats.get("p25_s"), "p75_s": stats.get("p75_s"),
        "fit_applied": bool(fit.get("applied")), "fit_adopted": fit.get("adopted"),
        "fit_changes": len(fit.get("changes") or []), "fit_dropped": dropped,
        "payoff_shots": sum(1 for u in pay if u.get("p")) if pay else None,
        "opening_is_payoff": ((sel or {}).get("opening") or {}).get("p") if sel else None,
        "unused_payoff_moments": len((sel or {}).get("unused_payoff") or []) if sel else None,
        "input_tokens": d.get("input_tokens"), "output_tokens": d.get("output_tokens"), "est_cost_usd": cost,
        "job_latency_s": round(updated - created, 1) if (created is not None and updated is not None) else None,
        "api_build": d.get("api_build_sha"), "worker_build": d.get("worker_build_sha"),
    }


def comparison_warnings(rows: list[dict]) -> list[str]:
    w = []
    by_type: dict = {}
    for r in rows:
        by_type.setdefault(r.get("editorial_type"), []).append(r)
    for t, rs in by_type.items():
        if len({r["operation"] for r in rs}) > 1:
            w.append(f"INVALID COMPARISON ({t}): mixes operations {sorted({r['operation'] for r in rs})}; "
                     "an Explore must not be compared with an Original to claim editorial superiority.")
        if len({r["target_s"] for r in rs}) > 1:
            w.append(f"NOT COMPARABLE ({t}): different target durations {sorted({r['target_s'] for r in rs if r['target_s']})}.")
        if len({r["moments"] for r in rs if r["moments"]}) > 1:
            w.append(f"NOT COMPARABLE ({t}): different Moment counts.")
        if len({r["prompt_version"] for r in rs}) < 2 and len(rs) > 1:
            w.append(f"NOTE ({t}): all rows share prompt_version {rs[0]['prompt_version']}; this is not a baseline/candidate pair.")
    return w


COLS = ["label", "prompt_version", "editorial_type", "operation", "target_s", "moments", "sheets", "model_calls",
        "pre_fit_total_s", "pre_fit_overshoot_pct", "delivered_s", "delivered_overshoot_pct", "shots", "distinct",
        "pre_fit_mean_s", "mean_s", "median_s", "fit_changes", "fit_dropped", "payoff_shots", "opening_is_payoff",
        "unused_payoff_moments", "valid", "completion", "input_tokens", "output_tokens", "est_cost_usd", "job_latency_s"]


def to_markdown(rows: list[dict], warnings: list[str]) -> str:
    head = "| " + " | ".join(COLS) + " |\n|" + "---|" * len(COLS) + "\n"
    body = "".join("| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in COLS) + " |\n" for r in rows)
    wl = "".join(f"- **{x}**\n" for x in warnings)
    return (wl + "\n" if wl else "") + head + body + (
        "\nQuality is NOT measured here. Judge rendered videos; these are deterministic descriptors only.\n")


def cmd_metrics(a) -> int:
    row = job_metrics(load_job(a.job), load_au_moments(a.au), a.label)
    print(json.dumps(row, indent=2))
    return 0


def cmd_compare(a) -> int:
    au = load_au_moments(a.au)
    labels = a.labels.split(",") if a.labels else [None] * len(a.jobs)
    rows = [job_metrics(load_job(j), au, labels[i] if i < len(labels) else None) for i, j in enumerate(a.jobs)]
    warns = comparison_warnings(rows)
    md = to_markdown(rows, warns)
    print(md)
    if a.out:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        (out / "compare.md").write_text(md); (out / "compare.json").write_text(json.dumps({"rows": rows, "warnings": warns}, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render"); r.add_argument("--case", required=True); r.add_argument("--out", required=True)
    r.add_argument("--versions", nargs="+", default=["5.3", "5.5"]); r.set_defaults(fn=cmd_render)
    m = sub.add_parser("metrics"); m.add_argument("--job", required=True); m.add_argument("--au"); m.add_argument("--label")
    m.set_defaults(fn=cmd_metrics)
    c = sub.add_parser("compare"); c.add_argument("jobs", nargs="+"); c.add_argument("--au"); c.add_argument("--labels")
    c.add_argument("--out"); c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
