#!/usr/bin/env python3
"""Merge per-area translation fragments into the iOS String Catalog.

    build_catalog.py --out apps/ios/Story/Story/Resources/Localizable.xcstrings frag_G1.json frag_G2.json ...

Fragment format: {"<english key>": {"zh-Hans": "...", "comment": "...", "en_one": "%lld moment"}}
  * `en_one` marks a plural key (single-number plural). English `other` is the key itself.
Existing catalog entries are preserved unless a fragment provides the key (fragments win). Conflicting translations
for the same key across fragments are reported and the FIRST fragment wins.
"""
import argparse
import json
import sys
from collections import OrderedDict


def entry(key, frag):
    zh = frag["zh-Hans"]
    e = OrderedDict()
    e["extractionState"] = "manual"
    if frag.get("comment"):
        e["comment"] = frag["comment"]
    loc = OrderedDict()
    if "en_one" in frag:
        loc["en"] = {"variations": {"plural": OrderedDict([
            ("one", {"stringUnit": {"state": "translated", "value": frag["en_one"]}}),
            ("other", {"stringUnit": {"state": "translated", "value": key}}),
        ])}}
        loc["zh-Hans"] = {"variations": {"plural": {
            "other": {"stringUnit": {"state": "translated", "value": zh}}}}}
    else:
        loc["zh-Hans"] = {"stringUnit": {"state": "translated", "value": zh}}
    e["localizations"] = loc
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("fragments", nargs="+")
    a = ap.parse_args()
    try:
        cat = json.load(open(a.out, encoding="utf8"))
    except FileNotFoundError:
        cat = {"sourceLanguage": "en", "strings": {}, "version": "1.0"}
    seen = {}
    conflicts = []
    for fp in a.fragments:
        frag = json.load(open(fp, encoding="utf8"))
        for k, v in frag.items():
            if "zh-Hans" not in v or not v["zh-Hans"].strip():
                print(f"SKIP (no zh-Hans) {k!r} in {fp}", file=sys.stderr)
                continue
            if k in seen:
                if seen[k]["zh-Hans"] != v["zh-Hans"]:
                    conflicts.append((k, seen[k]["zh-Hans"], v["zh-Hans"], fp))
                continue
            seen[k] = v
    for k, v in seen.items():
        cat["strings"][k] = entry(k, v)
    cat["strings"] = OrderedDict(sorted(cat["strings"].items(), key=lambda kv: kv[0].lower()))
    json.dump(cat, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=2)
    open(a.out, "a").write("\n")
    print(f"wrote {len(cat['strings'])} keys to {a.out}")
    for k, z1, z2, fp in conflicts:
        print(f"CONFLICT {k!r}: kept {z1!r}, ignored {z2!r} ({fp})", file=sys.stderr)


if __name__ == "__main__":
    main()
