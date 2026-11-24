#!/usr/bin/env python3
"""Offline ffmpeg EDITORIAL PREVIEW of a saved EditPlan (evaluation only; NOT the product renderer).

Reads a replay result.json (scripts/editorial_replay.py) and a media map {moment_id: local file}, and concatenates
the plan's segments in order with straight cuts. Honest limits, also written beside every preview:
  - ffmpeg, not the iOS MediaEngine: no export parity (color, stabilisation, encoder, aspect handling differ);
  - no music track: native audio only (keep = as recorded, duck = a fixed -9 dB, mute = silent). Beat alignment and the
    real music/native mix are NOT represented;
  - frames are center-cropped to 1080x1920 (vertical); no transitions or effects are added; speed is applied as planned;
  - source windows are the plan's source_start/end seconds against the cloud copy of each Moment.
Private footage stays in the local 0700 evaluation directory; nothing is uploaded.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DUCK_DB = -9


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])


def _has_audio(path: str) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return "aac" in r.stdout or "mp4a" in r.stdout


def render(result: Path, media_map: dict[str, str], out: Path, label: str) -> dict:
    res = json.loads(result.read_text())
    segs = sorted(res["plan"]["segments"], key=lambda s: s["order"])
    tmp = out.parent / f".{out.stem}_parts"
    tmp.mkdir(parents=True, exist_ok=True)
    parts, rows, missing = [], [], []
    t = 0.0
    for i, s in enumerate(segs):
        mid = str(s["asset_id"]).lower()
        src = media_map.get(mid)
        a, b = float(s["source_start_seconds"]), float(s["source_end_seconds"])
        spd = float(s.get("speed") or 1.0)
        outd = (b - a) / spd
        if not src or not Path(src).exists():
            missing.append(mid)
            continue
        part = tmp / f"p{i:03d}.mp4"
        vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,setpts=PTS/{spd}"
        na = s.get("native_audio") or "keep"
        if na == "mute" or not _has_audio(src):
            af = "anullsrc=r=44100:cl=stereo"
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{a}", "-t", f"{b - a}", "-i", src, "-f", "lavfi", "-t", f"{outd}", "-i", af,
                   "-map", "0:v:0", "-map", "1:a:0", "-vf", vf]
        else:
            chain = f"atempo={spd}," if abs(spd - 1.0) > 1e-6 else ""
            vol = f"volume={DUCK_DB}dB," if na == "duck" else ""
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{a}", "-t", f"{b - a}", "-i", src, "-map", "0:v:0", "-map", "0:a:0",
                   "-vf", vf, "-af", f"{chain}{vol}aresample=44100,aformat=channel_layouts=stereo"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100",
                "-ac", "2", "-t", f"{outd}", str(part)]
        _run(cmd)
        parts.append(part)
        rows.append({"shot": i, "moment": mid[:8], "src": [round(a, 2), round(b, 2)], "speed": spd, "out_s": round(outd, 2),
                     "t_start": round(t, 2), "audio": na, "role": s.get("narrative_role")})
        t += outd
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    for p in parts:
        p.unlink()
    lst.unlink()
    tmp.rmdir()
    side = {"label": label, "prompt_version": res["prompt_version"], "preview_s": round(t, 2), "shots": rows,
            "missing_media": missing, "limitations": __doc__.strip().split("\n", 1)[1].strip()}
    out.with_suffix(".shots.json").write_text(json.dumps(side, indent=1))
    return side


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--result", required=True)
    ap.add_argument("--media-dir", required=True, help="directory of <moment_id>.mov files")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    a = ap.parse_args(argv)
    mm = {p.stem.lower(): str(p) for p in Path(a.media_dir).glob("*.mov")}
    side = render(Path(a.result), mm, Path(a.out), a.label)
    print(json.dumps({"out": a.out, "preview_s": side["preview_s"], "shots": len(side["shots"]), "missing": side["missing_media"]}))
    return 0 if not side["missing_media"] else 1


if __name__ == "__main__":
    sys.exit(main())
