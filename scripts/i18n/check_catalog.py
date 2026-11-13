#!/usr/bin/env python3
"""Static localization coverage check for the iOS app (no Xcode needed).

    check_catalog.py [--ios apps/ios/Story/Story] [--catalog .../Localizable.xcstrings] [--strict]

Checks
  1. Every string literal used at a localization site (SwiftUI Text/Button/Label/Section/Toggle/TextField/
     navigationTitle/alert/confirmationDialog/accessibility*/Menu/Picker/LabeledContent/ProgressView and
     `L10n.t(`) has a catalog key with a non-empty zh-Hans value. Interpolations are matched structurally
     (any format specifier matches any interpolation), so a wrong *type* (%lld vs %@) is NOT detected here —
     Xcode's compiler extraction (SWIFT_EMIT_LOC_STRINGS) flags those as stale/new on the next build.
  2. zh-Hans values never use MORE format specifiers than the key (dropping a technical detail is allowed).
  3. Plural entries have english one/other and zh-Hans other.
  4. No catalog entry is left in state new / needs_review / stale.
Exit code 1 on problems (with --strict also on unused keys).
"""
import argparse
import json
import os
import re
import sys

SITES = (r"Text|Button|Label|Section|Toggle|TextField|SecureField|Picker|Menu|LabeledContent|ProgressView|Link|"
         r"\.navigationTitle|\.alert|\.confirmationDialog|\.accessibilityLabel|\.accessibilityHint|"
         r"\.accessibilityValue|\.help|L10n\.t|String\(localized:")
SITE_RE = re.compile(r"(?:%s)\(\s*$" % SITES)
SPEC_RE = re.compile(r"%(?:\d+\$)?(?:l?ld|lld|@|l?f|d|f|ld|lu|u)")


def scan_literals(src):
    """Yield (offset_of_open_quote, skeleton, has_interp, line_no). Skeleton: interpolation -> \\x00."""
    i, n = 0, len(src)
    line = 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += src.count("\n", i, j)
            i = j
            continue
        if src.startswith('"""', i):
            j = src.find('"""', i + 3)
            j = n if j < 0 else j + 3
            line += src.count("\n", i, j)
            i = j
            continue
        if c == '"':
            start, start_line = i, line
            i += 1
            out, interp = [], False
            while i < n and src[i] != '"':
                if src[i] == "\\":
                    if src.startswith("\\(", i):
                        depth, i = 1, i + 2
                        interp = True
                        while i < n and depth:
                            if src[i] == "(":
                                depth += 1
                            elif src[i] == ")":
                                depth -= 1
                            elif src[i] == '"':       # nested string inside interpolation
                                i += 1
                                while i < n and src[i] != '"':
                                    i += 2 if src[i] == "\\" else 1
                            i += 1
                        out.append("\x00")
                        continue
                    nxt = src[i + 1] if i + 1 < n else ""
                    out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\", "'": "'", "r": "\r"}.get(nxt, nxt))
                    i += 2
                    continue
                if src[i] == "\n":
                    break
                out.append(src[i])
                i += 1
            i += 1
            yield start, "".join(out), interp, start_line
            continue
        i += 1


def debug_ranges(src):
    """Line ranges inside `#if DEBUG` ... `#endif` (nesting aware); strings there are developer-only."""
    out, stack = [], []
    for i, l in enumerate(src.split("\n"), 1):
        t = l.strip()
        if t.startswith("#if"):
            stack.append((i, t.startswith("#if DEBUG")))
        elif t.startswith("#endif") and stack:
            st, dbg = stack.pop()
            if dbg:
                out.append((st, i))
    return out


def skeleton_of_key(key):
    return SPEC_RE.sub("\x00", key.replace("%%", "\x01")).replace("\x01", "%")


def specs(s):
    return sorted(SPEC_RE.findall(s.replace("%%", "")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ios", default="apps/ios/Story/Story")
    ap.add_argument("--catalog", default=None)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    cat_path = a.catalog or os.path.join(a.ios, "Resources", "Localizable.xcstrings")
    cat = json.load(open(cat_path, encoding="utf8"))["strings"]
    problems = []

    sk_to_key = {}
    for k, v in cat.items():
        sk_to_key.setdefault(skeleton_of_key(k), k)
        loc = v.get("localizations", {})
        zh = loc.get("zh-Hans")
        if not zh:
            problems.append(f"catalog: {k!r} has no zh-Hans")
            continue
        if "variations" in zh:
            pl = zh["variations"].get("plural", {})
            zv = pl.get("other", {}).get("stringUnit", {})
            en = loc.get("en", {}).get("variations", {}).get("plural", {})
            if not ("one" in en and "other" in en):
                problems.append(f"catalog: plural {k!r} lacks english one/other")
        else:
            zv = zh.get("stringUnit", {})
        val = zv.get("value", "")
        if not val.strip():
            problems.append(f"catalog: {k!r} empty zh-Hans")
        elif not any("$" in s for s in specs(val)) and any(specs(val).count(x) > specs(k).count(x) for x in set(specs(val))):
            problems.append(f"catalog: specifier mismatch {k!r} -> {val!r}")
        if zv.get("state") not in (None, "translated"):
            problems.append(f"catalog: {k!r} state={zv.get('state')}")

    used = set()
    missing = []
    for root, _, files in os.walk(a.ios):
        for f in files:
            if not f.endswith(".swift"):
                continue
            path = os.path.join(root, f)
            src = open(path, encoding="utf8").read()
            debug_lines = debug_ranges(src)
            for off, sk, interp, line in scan_literals(src):
                if any(a <= line <= b for a, b in debug_lines) or f == "DirectorDebugPanel.swift":
                    continue
                before = src[max(0, off - 60):off]
                # same-line call prefix, e.g. `Text(` `L10n.t(` `.navigationTitle(` `Button(role: .x, ` -> label arg
                m = re.search(r"(?:%s)\((?:[^()\"]*,\s*)?$" % SITES, before) or SITE_RE.search(before)
                if not m:
                    continue
                if sk.strip("\x00 ") == "" or not re.search(r"[A-Za-z]{2}", sk.replace("\x00", "")):
                    continue
                if "verbatim" in before[-12:]:
                    continue
                key = sk_to_key.get(sk)
                if key is None:
                    missing.append((os.path.relpath(path, a.ios), line, sk.replace("\x00", "\\(…)")))
                else:
                    used.add(key)

    for p, l, s in missing:
        problems.append(f"missing key: {p}:{l}  {s!r}")
    unused = sorted(set(cat) - used)
    print(f"catalog keys: {len(cat)}  used-by-scan: {len(used)}  missing: {len(missing)}  unused: {len(unused)}")
    for p in problems:
        print("PROBLEM", p)
    if unused and a.strict:
        for u in unused:
            print("UNUSED", repr(u))
    sys.exit(1 if problems or (a.strict and unused) else 0)


if __name__ == "__main__":
    main()
