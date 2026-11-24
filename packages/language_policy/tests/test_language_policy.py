"""Pure unit tests for packages/language_policy (no model, no network)."""
from __future__ import annotations

import pytest

from language_policy import (
    apply_language_suffix,
    contains_cjk_or_fullwidth,
    contains_han,
    content_language_instruction,
    detect_instruction_language,
    normalize_content_language,
    reply_language_instruction,
)


@pytest.mark.parametrize("raw,expected", [
    ("en", "en"), ("EN", "en"), ("en-US", "en"), ("en_GB", "en"), (" en ", "en"),
    ("zh", "zh-Hans"), ("zh-Hans", "zh-Hans"), ("zh_Hans", "zh-Hans"), ("zh-CN", "zh-Hans"),
    ("zh-Hans-CN", "zh-Hans"), ("ZH-hans", "zh-Hans"), ("zh_CN", "zh-Hans"), ("cmn", "zh-Hans"),
    # NOT Simplified Chinese / unsupported -> None (today's behaviour, never an error)
    ("zh-Hant", "x"), ("zh-TW", "x"), ("zh-HK", "x"), ("fr", "x"), ("de-DE", "x"), ("", "x"), ("   ", "x"),
    (None, "x"), (123, "x"), (["en"], "x"), ("english", "x"),
])
def test_normalization_table(raw, expected):
    assert normalize_content_language(raw) == (None if expected == "x" else expected)


@pytest.mark.parametrize("text,expected", [
    ("Use Moment 3 first and drop Moment 7", "en"),
    ("从片段3开始，不要使用片段7", "zh-Hans"),
    ("把 Moment 3 放在最前面", "zh-Hans"),                 # Chinese quoting an English token stays Chinese
    ("第3个片段放最前，use a cinematic style please", "mixed"),
    ("Use the 吉他 clip first, then the other one", "mixed"),
    ("", None), ("   ", None), (None, None), ("123 456 !!!", None),
    ("3b1c2f7e-1111-2222-3333-444455556666 12", None),     # ids / digits are ignored
    ("https://example.com/a 12", None),
])
def test_detect_instruction_language(text, expected):
    assert detect_instruction_language(text) == expected


def test_detection_is_deterministic():
    t = "第2个镜头放在片段5后面 and make it faster"
    assert len({detect_instruction_language(t) for _ in range(20)}) == 1


def test_script_helpers():
    assert contains_han("片段3") and not contains_han("Moment 3")
    assert contains_cjk_or_fullwidth("moment ３")            # full-width digit
    assert contains_cjk_or_fullwidth("use 3，then 4")         # full-width comma
    assert not contains_cjk_or_fullwidth("use 3, then 4")


def test_instruction_none_for_missing_or_unknown():
    for v in (None, "", "fr", "zh-Hant", 5):
        assert content_language_instruction(v) is None


def test_instruction_text_zh_and_en():
    zh = content_language_instruction("zh_CN")
    assert "Simplified Chinese" in zh and "简体中文" in zh
    # keys/ids/enums/directives stay; search-query fields stay English
    assert "JSON key" in zh and "enum" in zh and "directive name" in zh
    assert "visual_reference_query" in zh and "SEARCH QUERY" in zh and "English keywords" in zh
    en = content_language_instruction("en-US")
    assert "in English" in en and "visual_reference_query" in en


def test_apply_suffix_byte_identical_when_none():
    base = "SYSTEM PROMPT BODY\nline2\n"
    assert apply_language_suffix(base, None) == base
    assert apply_language_suffix(base, "klingon") == base
    out = apply_language_suffix(base, "zh-Hans")
    assert out.startswith(base) and out != base and out.endswith(content_language_instruction("zh-Hans"))


def test_reply_instruction_mentions_user_language():
    r = reply_language_instruction()
    assert "same language as the user's instruction" in r and "explicitly asks" in r
