#!/usr/bin/env python3
"""Editorial vNext — minimal FROZEN-REQUEST REPLAY (development evaluation only).

Purpose: compare two planner versions on byte-identical source evidence. The app's live request changes with Story
state, so two live jobs are never a controlled pair. This tool freezes ONE real request (the exact staged envelope and
contact-sheet JPEG bytes a development job just used) and replays it through the SAME planner code, provider gateway
and technical validator as the worker, changing only STORY_EDIT_PLAN_VERSION.

  capture  Watch the existing restricted dev staging bucket (read-only) for the next job(s) and copy body.json + sheets
           locally. The staging object is deleted by the worker at job end, so this must run while a job is in flight.
  verify   Recompute every component hash of a frozen case and compare with its manifest.
  run      Replay one arm (a child process pinned to --version); writes result.json + the prompt text it sent.
  report   Verify that arms of a pair share identical input hashes, then print a metric table.
  purge    Delete a frozen case / results directory.

No new endpoint, no AWS resource, no flag. Reads one dev S3 bucket; calls the provider only in `run`. Private text and
images live under a 0700 directory (default $KIROCREW_SCRATCH/replay) and are removed with `purge`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "packages", ROOT / "scripts"):
    sys.path.insert(0, str(p))

STAGING_BUCKET = "story-development-edit-plan-staging-989088054552-us-east-1"
# Worker env that selects the model (non-secret; read from the dev worker). The key itself is read in-process from
# Secrets Manager by the existing gateway and is never printed or stored.
DEV_MODEL_ENV = {"STORY_OPENAI_MODEL": "gpt-5.1", "STORY_GEMINI_MODEL": "gemini-3.8-flash", "STORY_ENVIRONMENT": "development"}


def _root() -> Path:
    d = Path(os.environ.get("EDITORIAL_REPLAY_DIR") or (Path(os.environ.get("KIROCREW_SCRATCH", "/tmp")) / "replay"))
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(d, 0o700)
    return d


def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _h(x) -> str:
    b = x if isinstance(x, (bytes, bytearray)) else _canon(x).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------------------------------------------
# component hashes (the "source evidence" of a request, independent of any prompt version)
# --------------------------------------------------------------------------------------------------------------
def component_hashes(body: dict, creative_brief, sheets: list[tuple[str, bytes]]) -> dict:
    ms = body.get("moments") or []
    return {
        "moment_ids_in_order": _h([str(m.get("id")) for m in ms]),
        "moments_payload": _h(ms),
        "story_guide": _h(body.get("story_guide")),
        "story_coverage": _h(body.get("story_coverage")),
        "creative_intent_and_target": _h(body.get("creative_intent")),
        "editorial_type": _h(body.get("editorial_type")),
        "editorial_mode": _h(body.get("editorial_mode")),
        "operation_and_instructions": _h(body.get("revision_context")),      # mode, directives, soft text, duration source
        "sound_preference": _h(body.get("sound_preference")),
        "music": _h([body.get("music_plan"), body.get("music_asset_id"), body.get("music_analysis")]),
        "output_format": _h(body.get("output_format")),
        "client_brief_text": _h(creative_brief),
        "sheet_order": _h([m for m, _ in sheets]),
        "sheet_bytes": _h([hashlib.sha256(d).hexdigest() for _, d in sheets]),
    }


def source_hash(comps: dict) -> str:
    return _h(comps)


# --------------------------------------------------------------------------------------------------------------
# capture / verify
# --------------------------------------------------------------------------------------------------------------
def _case_write(case_dir: Path, envelope_raw: str, sheets: list[tuple[str, bytes]], meta: dict) -> dict:
    case_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    (case_dir / "sheets").mkdir(exist_ok=True, mode=0o700)
    (case_dir / "envelope.json").write_text(envelope_raw)
    for mid, data in sheets:
        (case_dir / "sheets" / f"{mid}.jpg").write_bytes(data)
    env = json.loads(envelope_raw)
    body = json.loads(env["body"])
    comps = component_hashes(body, env.get("creative_brief"), sheets)
    man = {"components": comps, "source_hash": source_hash(comps), "sheet_order": [m for m, _ in sheets],
           "envelope_sha256": hashlib.sha256(envelope_raw.encode()).hexdigest(), "meta": meta}
    (case_dir / "manifest.json").write_text(json.dumps(man, indent=1))
    return man


def load_case(case_dir: Path) -> tuple[dict, dict, list[tuple[str, bytes]], dict]:
    """(envelope, body, sheets, manifest) exactly as frozen."""
    man = json.loads((case_dir / "manifest.json").read_text())
    raw = (case_dir / "envelope.json").read_text()
    env = json.loads(raw)
    sheets = [(m, (case_dir / "sheets" / f"{m}.jpg").read_bytes()) for m in man["sheet_order"]]
    return env, json.loads(env["body"]), sheets, man


def verify_case(case_dir: Path) -> dict:
    man = json.loads((case_dir / "manifest.json").read_text())
    raw = (case_dir / "envelope.json").read_text()
    if hashlib.sha256(raw.encode()).hexdigest() != man["envelope_sha256"]:
        return {"ok": False, "mismatched": ["envelope.json"], "envelope_intact": False, "source_hash": None}
    env, body, sheets, _ = load_case(case_dir)
    now = component_hashes(body, env.get("creative_brief"), sheets)
    bad = sorted(k for k in now if now[k] != man["components"].get(k))
    return {"ok": not bad and source_hash(now) == man["source_hash"], "mismatched": bad,
            "envelope_intact": True, "source_hash": source_hash(now)}


def cmd_capture(a) -> int:
    import boto3
    s3 = boto3.client("s3", region_name="us-east-1")

    def jobs() -> set[str]:
        out, tok = set(), None
        while True:
            kw = dict(Bucket=STAGING_BUCKET, Prefix="jobs/", Delimiter="/")
            if tok:
                kw["ContinuationToken"] = tok
            r = s3.list_objects_v2(**kw)
            out |= {p["Prefix"] for p in r.get("CommonPrefixes", [])}
            if not r.get("IsTruncated"):
                return out
            tok = r.get("NextContinuationToken")
    seen, got = jobs(), 0
    print(f"watching {STAGING_BUCKET} ({len(seen)} existing prefixes ignored). Start the Create in the app now.", flush=True)
    t0 = time.time()
    while got < a.count and time.time() - t0 < a.timeout:
        for pre in sorted(jobs() - seen):
            seen.add(pre)
            try:
                raw = s3.get_object(Bucket=STAGING_BUCKET, Key=pre + "body.json")["Body"].read().decode()
                env = json.loads(raw)
                order = env["sheet_order"]
                sheets = []
                for mid in order:                       # body.json is written first; sheets follow
                    for _ in range(60):
                        try:
                            sheets.append((mid, s3.get_object(Bucket=STAGING_BUCKET, Key=pre + f"sheets/{mid}.jpg")["Body"].read()))
                            break
                        except s3.exceptions.NoSuchKey:
                            time.sleep(1)
                    else:
                        raise RuntimeError(f"sheet {mid} never appeared")
            except Exception as e:                      # job already terminal/deleted, or partial: report, keep watching
                print(f"  skipped {pre}: {type(e).__name__}: {e}", flush=True)
                continue
            b = json.loads(env["body"])
            rc = b.get("revision_context") or {}
            label = f"{a.label_prefix}{got + 1}_{b.get('editorial_type')}_{int(float(b['creative_intent']['target_duration_seconds']))}s"
            man = _case_write(_root() / "cases" / label, raw, sheets,
                              {"captured_from": pre, "editorial_type": b.get("editorial_type"),
                               "operation": rc.get("mode") or "original", "target_s": b["creative_intent"]["target_duration_seconds"],
                               "duration_source": rc.get("duration_target_source"), "moments": len(b["moments"]),
                               "sheets": len(sheets), "critique_revision": bool(env.get("critique_revision")),
                               "has_soft_direction": bool(rc.get("soft_direction")), "has_directives": bool(rc.get("directives"))})
            print(json.dumps({"captured": label, "source_hash": man["source_hash"][:16], **man["meta"]}), flush=True)
            got += 1
        time.sleep(a.poll)
    return 0 if got else 2


def cmd_verify(a) -> int:
    r = verify_case(Path(a.case))
    print(json.dumps(r, indent=1))
    return 0 if r["ok"] else 1


# --------------------------------------------------------------------------------------------------------------
# run (one arm). The parent only sets the environment; the child imports the planner AFTER the version is set.
# --------------------------------------------------------------------------------------------------------------
def cmd_run(a) -> int:
    case = Path(a.case)
    v = verify_case(case)
    if not v["ok"]:
        print("REFUSING to run: frozen case does not match its manifest", v, file=sys.stderr)
        return 3
    meta = json.loads((case / "manifest.json").read_text())["meta"]
    if meta.get("critique_revision"):
        print("REFUSING: the frozen request asks for the critique pass (must be OFF).", file=sys.stderr)
        return 3
    if meta.get("operation") != "original" or meta.get("has_directives") or meta.get("has_soft_direction"):
        print("REFUSING: this evaluation is an undirected ORIGINAL (not Explore/Revise, no directives, no Customize text).", file=sys.stderr)
        return 3
    out = Path(a.out) if a.out else _root() / "results" / f"{case.name}__{a.arm}_{a.version}"
    if (out / "result.json").exists() and not a.force:
        print(f"REFUSING: {out}/result.json exists (one planned attempt per arm; use --force only with owner approval)", file=sys.stderr)
        return 4
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    if a.dry_run:
        print(json.dumps(_dry(case, a.version), indent=1))
        return 0
    env = dict(os.environ, **DEV_MODEL_ENV, STORY_EDIT_PLAN_VERSION=a.version, STORY_MODEL_PROVIDER="direct",
               PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "packages")]))
    env.pop("STORY_CRITIQUE_REVISION", None)
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_inner", "--case", str(case), "--out", str(out),
                        "--arm", a.arm, "--version", a.version], env=env)
    return r.returncode


def _inputs(env: dict, body: dict, sheets):
    """Mirror apps/api/app/worker.py::_run_edit_plan input construction field-for-field."""
    from edit_planner import EditPlanInputs
    from model_gateway import ImageInput
    images = [ImageInput(data=d, media_type="image/jpeg") for _m, d in sheets]
    order = [m for m, _ in sheets]
    return EditPlanInputs(
        story_id=str(body["story_id"]), creative_intent_id=str(body["creative_intent_id"]),
        creative_intent=body["creative_intent"], story_guide=body.get("story_guide", {}),
        story_coverage=body.get("story_coverage", {}), moments=body["moments"], music_plan=body.get("music_plan", {}),
        output_format=body.get("output_format", "vertical"), music_asset_id=body.get("music_asset_id"),
        music_plan_id=str(body["music_plan_id"]) if body.get("music_plan_id") else None,
        music_analysis=body.get("music_analysis"), sound_preference=body.get("sound_preference"),
        editorial_mode=body.get("editorial_mode"), editorial_type=body.get("editorial_type"),
        revision_context=body.get("revision_context"), images=images, creative_brief=env.get("creative_brief"),
        image_moment_order=order, critique_revision=bool(env.get("critique_revision")))


def _prompt_stats(inp, system: str, user: str) -> dict:
    import editorial_frozen as FZ
    head, _, rest = user.partition("\nINPUT:\n")
    return {"system_tokens": FZ.count_tokens(system), "user_text_tokens": FZ.count_tokens(user),
            "au_projection_tokens": FZ.count_tokens(rest), "user_directive_tokens": FZ.count_tokens(head),
            "image_count": len(inp.images), "image_bytes": sum(len(i.data) for i in inp.images),
            "image_tokens_estimate": FZ.image_tokens_estimate(len(inp.images)), "token_method": FZ.token_method()}


def _dry(case: Path, version: str) -> dict:
    env, body, sheets, man = load_case(case)
    os.environ["STORY_EDIT_PLAN_VERSION"] = version
    import edit_planner as ep
    inp = _inputs(env, body, sheets)
    system = Path(ep._PROMPT_PATH).read_text()
    return {"dry_run": True, "prompt_version": ep.PROMPT_VERSION, "source_hash": man["source_hash"][:16],
            **_prompt_stats(inp, system, ep._build_user(inp))}


def cmd_inner(a) -> int:
    case, out = Path(a.case), Path(a.out)
    import edit_planner as ep
    if ep.PROMPT_VERSION != f"edit_plan/{a.version}":
        print(f"version mismatch: planner resolved {ep.PROMPT_VERSION}, arm asked {a.version}", file=sys.stderr)
        return 5
    from edit_planner import RealEditPlannerEngine
    from model_gateway.provider import routed_gateway
    env, body, sheets, man = load_case(case)
    inp = _inputs(env, body, sheets)
    # hashes of what the planner is ACTUALLY about to receive (rebuilt from the objects, not the files)
    live = component_hashes({**body, "moments": inp.moments}, inp.creative_brief, [(m, i.data) for m, i in zip(inp.image_moment_order, inp.images)])
    assert live == man["components"], "in-process inputs differ from the frozen manifest"
    system = Path(ep._PROMPT_PATH).read_text()
    user = ep._build_user(inp)
    (out / "system.txt").write_text(system)
    (out / "user.txt").write_text(user)
    engine = RealEditPlannerEngine(routed_gateway("edit_plan", ep.MODEL_ID), executability_repair_attempts=2)
    t0 = time.time()
    err = None
    plan = None
    try:
        plan = engine.generate(inp)
    except Exception as e:   # a failed attempt is a result; never retried here
        err = f"{type(e).__name__}: {str(e)[:300]}"
    wall = round(time.time() - t0, 2)
    diag = getattr(engine, "last_diagnostics", {}) or {}
    plan_d = json.loads(plan.model_dump_json()) if plan is not None else None
    cost = None
    try:
        from observability import price_lookup
        c, priced = price_lookup(int(diag.get("input_tokens") or 0), int(diag.get("output_tokens") or 0), "gpt-5.1")
        cost = round(c, 4) if priced else None
    except Exception:
        pass
    keep = ("model_calls", "executability_repairs_used", "critique_attempted", "first_pass_executable", "first_pass_errors",
            "completion", "partial_disclosure", "material_unmet", "duration_fit", "selection", "input_tokens", "output_tokens",
            "used_fallback", "any_fallback", "calls")
    res = {"arm": a.arm, "version": a.version, "prompt_version": ep.PROMPT_VERSION, "case": case.name,
           "source_hash": man["source_hash"], "input_components": live, "planner_wall_s": wall, "error": err,
           "diagnostics": {k: diag.get(k) for k in keep}, "est_cost_usd": cost,
           "prompt": _prompt_stats(inp, system, user), "plan": plan_d, "meta": man["meta"]}
    (out / "result.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"arm": a.arm, "prompt_version": ep.PROMPT_VERSION, "wall_s": wall, "error": err,
                      "model_calls": diag.get("model_calls"), "tokens": [diag.get("input_tokens"), diag.get("output_tokens")]}))
    return 0 if err is None else 1


# --------------------------------------------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------------------------------------------
def metrics_row(res: dict, moments: list[dict]) -> dict:
    import edit_planner as ep
    d = res.get("diagnostics") or {}
    plan = res.get("plan") or {}
    segs = sorted(plan.get("segments") or [], key=lambda s: s.get("order", 0))
    outs = [float(s["output_duration_seconds"]) for s in segs]
    st = ep._shot_stats(outs)
    pc = ep._pacing_stats([{**s, "asset_id": str(s["asset_id"])} for s in segs], {str(m["id"]).lower(): m for m in moments})
    fit, sel = d.get("duration_fit") or {}, d.get("selection") or {}
    pre_total = (sel.get("budget") or {}).get("pre_fit_total_s")
    tgt = float(plan.get("target_duration_seconds") or res["meta"]["target_s"])
    return {"arm": res["arm"], "prompt_version": res["prompt_version"], "type": res["meta"]["editorial_type"],
            "target_s": tgt, "model_plan_s": pre_total, "fitted_s": round(sum(outs), 2) if outs else None,
            "segments": st.get("n"), "moments_used": len({str(s["asset_id"]).lower() for s in segs}),
            "mean_s": st.get("mean_s"), "median_s": st.get("median_s"), "p25_s": st.get("p25_s"), "p75_s": st.get("p75_s"),
            "share_le_2_5": pc["share_le_2_5"], "cuts": pc["cuts"], "buckets": pc["buckets"],
            "opening10_shots": pc["opening"]["shots"], "opening10_distinct_payoffs": pc["opening"]["distinct_payoffs"],
            "native_keep": sum(1 for s in segs if s.get("native_audio") == "keep"),
            "native_duck": sum(1 for s in segs if s.get("native_audio") == "duck"),
            "native_mute": sum(1 for s in segs if s.get("native_audio") == "mute"),
            "model_calls": d.get("model_calls"), "repair_calls": d.get("executability_repairs_used"),
            "critique": bool(d.get("critique_attempted")), "first_pass_executable": d.get("first_pass_executable"),
            "completion": d.get("completion"), "fit_applied": bool(fit.get("applied")),
            "input_tokens": d.get("input_tokens"), "output_tokens": d.get("output_tokens"),
            "system_tokens": res["prompt"]["system_tokens"], "user_text_tokens": res["prompt"]["user_text_tokens"],
            "au_projection_tokens": res["prompt"]["au_projection_tokens"],
            "image_tokens_est": res["prompt"]["image_tokens_estimate"], "wall_s": res["planner_wall_s"],
            "est_cost_usd": res.get("est_cost_usd"), "error": res.get("error")}


def cmd_report(a) -> int:
    results = [json.loads((Path(p) / "result.json").read_text()) for p in a.results]
    rows, problems = [], []
    by_case: dict[str, list[dict]] = {}
    for r in results:
        by_case.setdefault(r["case"], []).append(r)
    for case, rs in by_case.items():
        if len({r["source_hash"] for r in rs}) > 1 or len({_canon(r["input_components"]) for r in rs}) > 1:
            problems.append(f"NOT A CONTROLLED PAIR ({case}): arms differ in source evidence hashes")
        if len({r["prompt_version"] for r in rs}) < 2:
            problems.append(f"NOTE ({case}): arms share one prompt version")
    for r in results:
        _, body, _, _ = load_case(_root() / "cases" / r["case"])
        rows.append(metrics_row(r, body["moments"]))
    print(json.dumps({"controlled": not any(p.startswith("NOT A CONTROLLED") for p in problems), "problems": problems,
                      "rows": rows}, indent=1))
    return 0


def cmd_purge(a) -> int:
    import shutil
    for p in a.paths:
        shutil.rmtree(p, ignore_errors=True)
        print("removed", p)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture"); c.add_argument("--count", type=int, default=1); c.add_argument("--timeout", type=int, default=900)
    c.add_argument("--poll", type=float, default=2.0); c.add_argument("--label-prefix", default="c"); c.set_defaults(fn=cmd_capture)
    v = sub.add_parser("verify"); v.add_argument("--case", required=True); v.set_defaults(fn=cmd_verify)
    for name, fn in (("run", cmd_run), ("_inner", cmd_inner)):
        r = sub.add_parser(name); r.add_argument("--case", required=True); r.add_argument("--arm", required=True)
        r.add_argument("--version", required=True); r.add_argument("--out"); r.set_defaults(fn=fn)
        if name == "run":
            r.add_argument("--dry-run", action="store_true"); r.add_argument("--force", action="store_true")
    rp = sub.add_parser("report"); rp.add_argument("results", nargs="+"); rp.set_defaults(fn=cmd_report)
    pg = sub.add_parser("purge"); pg.add_argument("paths", nargs="+"); pg.set_defaults(fn=cmd_purge)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
