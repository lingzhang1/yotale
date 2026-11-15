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

    assert zh("Moments") == "瞬间"
    assert zh("Moment %lld") == "瞬间 %lld"
    assert zh("Your Shooting Script") == "拍摄指南"
    assert zh("Story Guide") == "拍摄指南"
    assert zh("Highlights") == "精彩集锦"
    assert zh("Full Story") == "完整故事"
    assert zh("Customize") == "自定义" if "Customize" in s else True


def test_no_internal_terms_leak_into_chinese_ui():
    s = json.loads(CATALOG.read_text(encoding="utf8"))["strings"]
    banned = ["must_include", "order_after", "EditPlan", "Edit Planner", "contact sheet", "AU "]
    for k, v in s.items():
        if v.get("shouldTranslate") is False:
            continue
        loc = v["localizations"]["zh-Hans"]
        val = (loc.get("stringUnit") or loc["variations"]["plural"]["other"]["stringUnit"])["value"]
        for b in banned:
            assert b not in val, f"{k!r} -> {val!r} exposes {b!r}"


def test_info_plist_permissions_localized():
    d = json.loads((IOS / "Resources/InfoPlist.xcstrings").read_text(encoding="utf8"))["strings"]
    for k in ("NSCameraUsageDescription", "NSMicrophoneUsageDescription", "NSPhotoLibraryUsageDescription",
              "NSPhotoLibraryAddUsageDescription", "NSLocationWhenInUseUsageDescription"):
        assert d[k]["localizations"]["zh-Hans"]["stringUnit"]["value"].strip()


def _zh_values():
    s = json.loads(CATALOG.read_text(encoding="utf8"))["strings"]
    out = {}
    for k, v in s.items():
        if v.get("shouldTranslate") is False:
            continue
        loc = v["localizations"]["zh-Hans"]
        out[k] = (loc.get("stringUnit") or loc["variations"]["plural"]["other"]["stringUnit"])["value"]
    return out


def test_moment_entity_is_shunjian_not_pianduan():
    """Copy pass v2: the product entity Moment is 瞬间. 片段 is allowed only where the English talks about an actual
    clip/excerpt, so any key mentioning "moment" must not render as 片段."""
    for k, z in _zh_values().items():
        if "moment" in k.lower() and "clip" not in k.lower():
            assert "片段" not in z, f"{k!r} -> {z!r}: Moment must be 瞬间"


def test_story_count_label_is_not_concatenated_awkwardly():
    z = _zh_values()
    assert z["%lld in %@"] == "%2$@ · %1$lld 个瞬间"   # was "%2$@ 中共 %1$lld 个" ("…女孩 中共 20 个")
    assert "中共" not in "".join(z.values())
    assert z["%lld in your library"] == "共 %lld 个"


def test_coverage_status_labels_match_semantics():
    z = _zh_values()
    assert z["Not captured"] == "尚未拍摄"
    assert z["Covered"] == "已拍摄"
    assert z["Looking strong"] == "已有相关素材"    # owner decision; was 看起来不错 (a generic positive)


def test_alias_keys_keep_english_identical():
    """Keys that differ from their English text (sentence-form Moment number, Arrange sheet title) must carry an
    explicit English value equal to the original English, so the English UI is unchanged."""
    s = json.loads(CATALOG.read_text(encoding="utf8"))["strings"]
    for key, english in {"Moment %lld (in a sentence)": "Moment %lld",
                         "Arrange Moments (sheet title)": "Arrange Moments"}.items():
        assert s[key]["localizations"]["en"]["stringUnit"]["value"] == english


def test_owner_numbering_and_arrange_decisions():
    z = _zh_values()
    assert z["Moment %lld"] == "瞬间 %lld"                       # compact labels / chips
    assert z["Moment %lld (in a sentence)"] == "第 %lld 个瞬间"   # inside sentences
    assert z["Moment %lld doesn't exist in this Story."] == "这个故事里没有第 %lld 个瞬间。"
    assert z["Arrange Moments (sheet title)"] == "调整顺序"
    assert z["Arrange"] == "调整顺序"
    assert z["Arrange Moments"] == "调整瞬间顺序"
    assert z["Revise"] == "调整影片"
