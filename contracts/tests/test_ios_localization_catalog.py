"""Static guard: the iOS String Catalog covers every localized literal and is internally consistent.

Runs scripts/i18n/check_catalog.py (no Xcode needed). It cannot prove the app compiles or renders correctly; the
device build and the bilingual acceptance matrix remain the authoritative gate.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IOS = ROOT / "apps/ios/Story/Story"
CATALOG = IOS / "Resources/Localizable.xcstrings"


def test_catalog_covers_all_localized_literals():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/i18n/check_catalog.py"), "--ios", str(IOS)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-1000:]


def test_glossary_terms_are_consistent():
    s = json.loads(CATALOG.read_text(encoding="utf8"))["strings"]

    def zh(k):
        e = s[k]["localizations"]["zh-Hans"]
        return (e.get("stringUnit") or e["variations"]["plural"]["other"]["stringUnit"])["value"]

    assert zh("Moments") == "片段"
    assert zh("Story Guide") == "拍摄指南"
    assert zh("Highlights") == "精彩集锦"
    assert zh("Full Story") == "完整故事"
    assert zh("Customize") == "自定义" if "Customize" in s else True


def test_no_internal_terms_leak_into_chinese_ui():
    s = json.loads(CATALOG.read_text(encoding="utf8"))["strings"]
    banned = ["must_include", "order_after", "EditPlan", "Edit Planner", "contact sheet", "AU "]
    for k, v in s.items():
        loc = v["localizations"]["zh-Hans"]
        val = (loc.get("stringUnit") or loc["variations"]["plural"]["other"]["stringUnit"])["value"]
        for b in banned:
            assert b not in val, f"{k!r} -> {val!r} exposes {b!r}"


def test_info_plist_permissions_localized():
    d = json.loads((IOS / "Resources/InfoPlist.xcstrings").read_text(encoding="utf8"))["strings"]
    for k in ("NSCameraUsageDescription", "NSMicrophoneUsageDescription", "NSPhotoLibraryUsageDescription",
              "NSPhotoLibraryAddUsageDescription", "NSLocationWhenInUseUsageDescription"):
        assert d[k]["localizations"]["zh-Hans"]["stringUnit"]["value"].strip()
