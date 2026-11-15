"""Content-language policy (i18n en / zh-Hans) — PURE, deterministic, no model, no network.

The iOS client sends an OPTIONAL `content_language` on endpoints that generate Story-specific human-readable
text. This module is the single backend place that:

  * normalizes the raw value  -> 'en' | 'zh-Hans' | None            (never raises; unknown -> None)
  * detects an instruction's  -> 'en' | 'zh-Hans' | 'mixed' | None  (Han-vs-Latin ratio, deterministic)
  * builds the RUNTIME system-prompt SUFFIX that asks the model to write human-readable strings in that language
    while keeping every JSON key / id / enum / directive name and every image/music/video SEARCH QUERY field
    exactly as specified (search queries stay short English keywords).

Backwards-compat contract: a `None` language yields `None` / the UNCHANGED prompt, so English behaviour with no
new field is byte-identical. Prompt files are never edited and prompt_version strings are never bumped — the
suffix is appended at request-build time only.
"""
from __future__ import annotations

import re
from typing import Final

EN: Final = "en"
ZH_HANS: Final = "zh-Hans"
SUPPORTED: Final = (EN, ZH_HANS)

# ---------------------------------------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------------------------------------

def normalize_content_language(raw) -> str | None:
    """Canonicalize a client-supplied language tag. 'zh', 'zh-CN', 'zh_Hans', 'zh-Hans-CN', 'ZH-hans', 'EN',
    'en-US', 'en_GB' ... -> 'zh-Hans' / 'en'. Anything else (None, '', 'fr', 'zh-Hant', 'zh-TW', non-string)
    -> None (== today's behaviour). Never raises; callers must NEVER turn a bad value into a 4xx."""
    if not isinstance(raw, str):
        return None
    tag = raw.strip().replace("_", "-").lower()
    if not tag:
        return None
    parts = tag.split("-")
    primary = parts[0]
    if primary == "en":
        return EN
    if primary in ("zh", "cmn"):
        rest = set(parts[1:])
        # Traditional-script / Traditional-region tags are NOT Simplified Chinese.
        if rest & {"hant", "tw", "hk", "mo"}:
            return None
        return ZH_HANS
    return None


# ---------------------------------------------------------------------------------------------------------
# Script detection
# ---------------------------------------------------------------------------------------------------------

def is_han_char(ch: str) -> bool:
    """CJK ideograph (unified, ext A-F, compatibility). Excludes CJK punctuation/kana/hangul."""
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF
            or 0x20000 <= o <= 0x2FA1F or 0x2E80 <= o <= 0x2FDF or o == 0x3007)


def contains_han(text) -> bool:
    return isinstance(text, str) and any(is_han_char(c) for c in text)


def contains_cjk_or_fullwidth(text) -> bool:
    """Han ideographs, CJK punctuation (U+3000-303F) or full-width forms (U+FF00-FFEF, e.g. '３', '，').
    Used to decide whether an instruction needs the Chinese interpretation guidance."""
    if not isinstance(text, str):
        return False
    for c in text:
        o = ord(c)
        if is_han_char(c) or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
            return True
    return False


_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F]+")
_URL_RE = re.compile(r"(https?://\S+|www\.\S+|\S+@\S+)", re.IGNORECASE)
_ID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def detect_instruction_language(text) -> str | None:
    """Deterministic language of an instruction by Han-character count vs Latin WORD count.

    Digits, punctuation, URLs, e-mails and UUID-like ids are ignored. A Han character carries roughly a word of
    meaning, so Chinese text that quotes an English token ('把 Moment 3 放在最前面') still reads as Chinese.
    Returns 'zh-Hans' (Han share >= 0.6), 'en' (Han share <= 0.1, including zero), 'mixed' otherwise, and None
    when there are no letters at all (empty / digits / punctuation only). No model, no randomness."""
    if not isinstance(text, str) or not text.strip():
        return None
    cleaned = _ID_RE.sub(" ", _URL_RE.sub(" ", text))
    han = sum(1 for c in cleaned if is_han_char(c))
    latin_words = len(_WORD_RE.findall(cleaned))
    total = han + latin_words
    if total == 0:
        return None
    share = han / total
    if share >= 0.6:
        return ZH_HANS
    if share <= 0.1:
        return EN
    return "mixed"


# ---------------------------------------------------------------------------------------------------------
# Prompt suffixes
# ---------------------------------------------------------------------------------------------------------

_KEEP_CLAUSE = (
    "Keep every JSON key, id, enum value, directive name and schema field EXACTLY as specified — never "
    "translate, rename or localize them. Quote the user's own words unchanged (do not translate them). "
    "EXCEPTION: the field `visual_reference_query`, and any other field documented as an image, video or "
    "music SEARCH QUERY, must ALWAYS remain short English keywords (never Chinese)."
)

_SUFFIX: Final = {
    ZH_HANS: (
        "OUTPUT LANGUAGE (runtime directive): write every human-readable string value you produce — titles, "
        "labels, descriptions, tips, summaries, notes, rationales and reasons — in Simplified Chinese "
        "(简体中文). " + _KEEP_CLAUSE
    ),
    EN: (
        "OUTPUT LANGUAGE (runtime directive): write every human-readable string value you produce — titles, "
        "labels, descriptions, tips, summaries, notes, rationales and reasons — in English, even if the "
        "Story's own text is in another language. " + _KEEP_CLAUSE
    ),
}


def content_language_instruction(lang) -> str | None:
    """System-prompt suffix for a (normalized or raw) content language, or None => leave the prompt UNCHANGED.
    Accepts a raw tag too (normalized here), so a caller can pass the request field straight through."""
    norm = normalize_content_language(lang)
    if norm is None:
        return None
    return _SUFFIX[norm]


def reply_language_instruction() -> str:
    """For INTERACTIVE replies (revise / explore / update-guide chat): reply in the language of the user's
    instruction unless they explicitly ask for another language."""
    return (
        "REPLY LANGUAGE (runtime directive): write any free-text reply in the same language as the user's "
        "instruction, unless the user explicitly asks for a different language. Never translate the user's own "
        "words, and keep all JSON keys, ids, enum values and directive names exactly as specified."
    )


def apply_language_suffix(system: str, lang) -> str:
    """`system` + the content-language suffix; EXACTLY `system` when lang is None/unknown (byte-identical)."""
    suffix = content_language_instruction(lang)
    if suffix is None:
        return system
    return system + "\n\n" + suffix


def effective_language_key(lang) -> str | None:
    """Normalized language for CACHE / FINGERPRINT keys: None when absent so today's key is unchanged."""
    return normalize_content_language(lang)


__all__ = [
    "EN", "ZH_HANS", "SUPPORTED", "normalize_content_language", "detect_instruction_language",
    "content_language_instruction", "reply_language_instruction", "apply_language_suffix",
    "effective_language_key", "is_han_char", "contains_han", "contains_cjk_or_fullwidth",
]
