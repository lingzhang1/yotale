"""Scene-video provider — Pixabay stock-video references for YoTale Phase 1B (Shooting Idea + Story Guide).

Backend-only. The Pixabay API key is read from AWS Secrets Manager (secret id, default 'Pixabay_Video_API_KEY')
IN-PROCESS and NEVER logged, returned to callers, or embedded in the iOS app. This is a BOUNDED reference-video
lookup — NOT an unrestricted public video-search proxy. One video per shot/scene.

WHY VIDEO (owner Phase 1B): a photo shows a composition; a short clip shows the CAMERA MOVEMENT. The #1
acceptance criterion is that the clip matches the requested TECHNIQUE, not just the subject (the exact trap the
Unsplash photo work hit). So selection runs a technique-compatibility gate, not raw keyword overlap.

PROVIDER = Pixabay (owner decision 2026-11-05, after a 12-example Coverr-vs-Pixabay eval). Coverr stays an
evaluated alternative, not integrated. Pixabay chosen for deeper subject/technique coverage (real pan/reveal/
portrait clips) and an existing dev key.

COMPLIANCE (verified 2026-11-05 against pixabay.com/api/docs + service/license-summary):
  * Video EMBEDDING is permitted → iOS streams the preview MP4 (videos.tiny/small, ~720p/1080p) DIRECTLY from
    cdn.pixabay.com to AVPlayer. We do NOT proxy video bytes.
  * Image HOTLINKING is NOT permitted → the poster .jpg (videos.*.thumbnail) must NOT be hotlinked by the app;
    it is served through the backend poster endpoint (POST /v1/scene-video/poster) which fetches + returns the
    bytes. This module exposes poster_is_allowed_host() + the poster URL; the endpoint does the fetch.
  * Attribution: show where results come from — we return `attribution_text` ("Video by <user> on Pixabay") and
    `source_url` (the pageURL). The app must display them.
  * Caching: Pixabay requires responses cached 24h — MetadataCache ttl defaults to 24h here.
  * AI content: allowed by the owner for display. We surface `is_ai_generated` and PREFER non-AI in selection,
    but do not exclude. Sponsored/low-quality/non-G are excluded.
  * No ML/training use of Pixabay content or API data (noAiTraining respected: never used for training/eval).
  * Fail-soft: auth/provider/rate-limit/timeout → typed exceptions the endpoint maps to a graceful "no video"
    (image/text fallback). MUST NEVER block Director/Guide generation or the UI.

Reuses scene_image's query-normalization + broadening + cache + utm helpers (DRY; same "always show something
relevant, never a misleading one" rule).
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

import scene_image  # reuse normalize_query / broadening_candidates / MetadataCache / _utm / control regex

BASE = "https://pixabay.com/api/videos/"
SECRET_ENV = "PIXABAY_SECRET_ID"
DEFAULT_SECRET_ID = "Pixabay_Video_API_KEY"
FLAG_ENV = "STORY_REFERENCE_MEDIA_MODE"       # image|video; video enables this endpoint
APP_UTM = "yotale"
QUERY_MAX_LEN = 100                            # Pixabay q cap is 100 chars
PROVIDER_TIMEOUT_SECONDS = 5.0
PIXABAY_PER_PAGE = 20                          # one bounded candidate fetch (Pixabay requires per_page in [3,200])
POSTER_ALLOWED_HOSTS = ("cdn.pixabay.com",)    # SSRF guard: the poster endpoint fetches ONLY these hosts


class SceneVideoDisabledError(RuntimeError):
    """STORY_REFERENCE_MEDIA_MODE != 'video'."""


class SceneVideoAuthError(RuntimeError):
    """The Pixabay key could not be read, or the provider rejected it."""


class SceneVideoProviderError(RuntimeError):
    """The provider failed, timed out, or rate-limited (HTTP 429/5xx/transport)."""


def media_mode() -> str:
    """The shared reference-media mode. Defaults SAFELY to 'image' when missing/invalid (owner §2)."""
    v = (os.environ.get(FLAG_ENV) or "").strip().lower()
    return v if v in ("image", "video") else "image"


def enabled() -> bool:
    return media_mode() == "video"


def load_key(secret_id: str | None = None) -> str:
    """Read the Pixabay API key from Secrets Manager in-process (mirrors scene_image.load_key). Never logged."""
    import boto3  # noqa
    from botocore.exceptions import BotoCoreError, ClientError  # noqa
    sid = secret_id or os.environ.get(SECRET_ENV, DEFAULT_SECRET_ID)
    sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        s = (sm.get_secret_value(SecretId=sid).get("SecretString") or "").strip()
    except (ClientError, BotoCoreError) as e:
        raise SceneVideoAuthError(f"could not read Pixabay secret: {type(e).__name__}") from e
    if s.startswith("{"):
        try:
            d = json.loads(s)
        except Exception as e:
            raise SceneVideoAuthError("secret JSON malformed") from e

        def _norm(x: str) -> str:
            return "".join(ch for ch in x.lower() if ch.isalnum())
        for want in ("pixabayapikey", "apikey", "pixabaykey", "key", "value"):
            for k, v in d.items():
                if _norm(k) == want and str(v).strip():
                    return str(v).strip()
        if len(d) == 1:
            return str(next(iter(d.values()))).strip()
        raise SceneVideoAuthError("secret JSON has no recognizable Pixabay key field")
    if not s:
        raise SceneVideoAuthError("empty secret")
    return s


# ---- Technique matching (owner §5: movement is the #1 criterion) ---------------------------------------
# A clip is only shown when its tags are COMPATIBLE with the requested shot's camera technique — not merely
# when a subject word overlaps. We classify the requested technique from the Director/Guide text and the
# candidate from its Pixabay tags, then reject hard conflicts (e.g. a static shot vs a drone flyover).

# Requested-technique cues (from shot framing/camera_motion/instruction, already generic — reuses the Phase 1A
# ShotReferenceQuery spirit but server-side and video-aware).
_MOVEMENT_CUES = {
    "static": ("static", "still", "stationary", "hold steady", "steady", "locked"),
    "pan": ("pan", "panning", "panoramic sweep"),
    "tilt": ("tilt", "tilting"),
    "tracking": ("tracking", "follow", "following", "walk with", "move with"),
    "push_in": ("push in", "push-in", "dolly in", "zoom in", "move closer"),
    "reveal": ("reveal", "revealing", "reveals"),
    "aerial": ("aerial", "drone", "flyover", "fly over", "birds eye", "bird's eye", "overhead drone"),
    "handheld": ("handheld", "pov", "first person", "first-person"),
}
# Candidate-tag signals that indicate ACTUAL movement in the clip (Pixabay tags often name the motion).
_TAG_MOVEMENT = {
    "pan": ("pan", "panning"),
    "tilt": ("tilt",),
    "tracking": ("tracking", "follow", "following", "walking", "walk"),
    "push_in": ("zoom", "dolly", "push"),
    "reveal": ("reveal", "revealing"),
    "aerial": ("aerial", "drone", "flyover", "birds eye", "fly"),
    "handheld": ("handheld", "pov", "first person"),
}
# Technique pairs that CONFLICT: a requested key must not be served by a candidate carrying the conflicting tag.
_CONFLICTS = {
    "static": ("aerial", "handheld"),      # a locked-off shot must not be a drone or shaky POV
    "pan": ("aerial",),
    "tracking": ("aerial",),
    "reveal": ("aerial",),
    "aerial": ("static", "handheld"),
}


def requested_technique(text: str) -> str | None:
    """Classify the requested camera technique from generic shot text. None => no explicit technique."""
    t = (text or "").lower()
    # Order matters: aerial/reveal/tracking are more specific than static.
    for key in ("aerial", "reveal", "tracking", "push_in", "pan", "tilt", "handheld", "static"):
        if any(c in t for c in _MOVEMENT_CUES[key]):
            return key
    return None


def _candidate_movements(tags: list[str]) -> set[str]:
    blob = " ".join(tags).lower()
    return {k for k, needles in _TAG_MOVEMENT.items() if any(n in blob for n in needles)}


def technique_conflicts(requested: str | None, tags: list[str]) -> bool:
    """True when the candidate's tags imply a camera technique that CONFLICTS with the requested one."""
    if not requested:
        return False
    bad = _CONFLICTS.get(requested, ())
    return bool(set(bad) & _candidate_movements(tags))


@dataclass(frozen=True)
class SceneVideo:
    """Metadata-only reference-video result. NO video bytes re-hosted; the app streams preview_url directly.
    poster_url is served through the backend poster endpoint (Pixabay forbids image hotlinking)."""

    provider: str                 # "pixabay"
    video_id: str
    preview_url: str              # cdn.pixabay.com MP4 (tiny/small) — app streams directly (embedding allowed)
    poster_url: str               # cdn.pixabay.com .jpg — served via backend poster endpoint, NOT hotlinked
    source_url: str               # pageURL, utm-tagged (attribution)
    attribution_text: str         # "Video by <user> on Pixabay"
    contributor: str
    tags: list[str]
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    is_ai_generated: bool = False
    matched_query: str | None = None
    matched_technique: str | None = None

    def to_wire(self) -> dict:
        return {
            "provider": self.provider,
            "video_id": self.video_id,
            "preview_url": self.preview_url,
            "poster_url": self.poster_url,
            "source_url": self.source_url,
            "attribution_text": self.attribution_text,
            "contributor": self.contributor,
            "tags": self.tags,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "is_ai_generated": self.is_ai_generated,
            "matched_query": self.matched_query,
            "matched_technique": self.matched_technique,
        }


def _aspect(w: int | None, h: int | None) -> str | None:
    if not w or not h:
        return None
    from math import gcd
    g = gcd(w, h) or 1
    return f"{w // g}:{h // g}"


POSTER_MAX_BYTES = 3 * 1024 * 1024             # posters are small JPEGs; cap the backend fetch


def poster_is_allowed_host(url: str) -> bool:
    """SSRF guard for the poster endpoint: only Pixabay's CDN over HTTPS may be fetched."""
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    return p.scheme == "https" and p.hostname in POSTER_ALLOWED_HOSTS


def fetch_poster(url: str, *, opener=None, timeout: float = PROVIDER_TIMEOUT_SECONDS) -> tuple[bytes, str]:
    """Fetch ONE poster image's bytes from the allowed Pixabay CDN. SSRF-bounded + size-capped + image-only.
    Raises SceneVideoProviderError on anything unusable (the endpoint maps that to a graceful 404). `opener`
    is injectable for tests (no network in CI)."""
    if not poster_is_allowed_host(url):
        raise SceneVideoProviderError("poster host not allowed")
    _open = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": "YoTale/1.0 (reference-media)"})
    try:
        with _open(req, timeout=timeout) as r:
            ctype = (getattr(r, "headers", {}) or {}).get("Content-Type", "image/jpeg")
            data = r.read(POSTER_MAX_BYTES + 1)
    except Exception as e:
        raise SceneVideoProviderError(f"poster fetch failed: {type(e).__name__}") from e
    if not str(ctype).startswith("image/"):
        raise SceneVideoProviderError("poster not an image")
    if len(data) > POSTER_MAX_BYTES:
        raise SceneVideoProviderError("poster too large")
    return data, str(ctype)


class PixabayClient:
    """Thin Pixabay video REST client. Injectable for tests (no network in CI). Bounded timeout; typed errors."""

    def __init__(self, api_key: str, *, base: str = BASE, timeout: float = PROVIDER_TIMEOUT_SECONDS, opener=None):
        self._key = api_key
        self._base = base
        self._timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def search(self, query: str, *, per_page: int = PIXABAY_PER_PAGE) -> list[dict]:
        """Return raw Pixabay video hits for a keyword query (bounded). Raises typed errors on failure."""
        params = {
            "key": self._key,
            "q": query[:QUERY_MAX_LEN],
            "per_page": max(3, min(per_page, 200)),   # Pixabay requires per_page in [3,200]
            "safesearch": "true",
            "video_type": "film",                      # exclude animation; stock footage only
        }
        req = urllib.request.Request(
            f"{self._base}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": "YoTale/1.0 (reference-media)", "Accept": "application/json"},
        )
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            if e.code in (401, 403):
                raise SceneVideoAuthError(f"pixabay auth rejected ({e.code})") from e
            if e.code == 429:
                raise SceneVideoProviderError("pixabay rate limited (429)") from e
            raise SceneVideoProviderError(f"pixabay http {e.code}") from e
        except Exception as e:
            raise SceneVideoProviderError(f"pixabay transport: {type(e).__name__}") from e
        if status in (401, 403):
            raise SceneVideoAuthError(f"pixabay auth rejected ({status})")
        if status == 429:
            raise SceneVideoProviderError("pixabay rate limited (429)")
        if status >= 400:
            raise SceneVideoProviderError(f"pixabay http {status}")
        try:
            return (json.loads(body).get("hits") or [])
        except Exception as e:
            raise SceneVideoProviderError("pixabay returned non-JSON") from e


def _map(hit: dict, *, matched_query: str, matched_technique: str | None) -> SceneVideo | None:
    """Map a raw Pixabay hit to SceneVideo, choosing the preview (tiny) + poster. None if unusable."""
    files = hit.get("videos") or {}
    # Prefer 'tiny' (720p) for the preview stream; fall back up the ladder.
    chosen = None
    for sz in ("tiny", "small", "medium", "large"):
        f = files.get(sz)
        if isinstance(f, dict) and f.get("url"):
            chosen = f
            break
    if not chosen:
        return None
    tags = [t.strip() for t in (hit.get("tags") or "").split(",") if t.strip()]
    user = (hit.get("user") or "Pixabay").strip()
    w, h = chosen.get("width"), chosen.get("height")
    return SceneVideo(
        provider="pixabay",
        video_id=str(hit.get("id", "")),
        preview_url=chosen["url"],
        poster_url=chosen.get("thumbnail") or files.get("tiny", {}).get("thumbnail") or "",
        source_url=scene_image._utm(hit.get("pageURL") or "https://pixabay.com"),
        attribution_text=f"Video by {user} on Pixabay",
        contributor=user,
        tags=tags,
        duration=hit.get("duration"),
        width=w, height=h, aspect_ratio=_aspect(w, h),
        is_ai_generated=bool(hit.get("isAiGenerated")),
        matched_query=matched_query,
        matched_technique=matched_technique,
    )


# Words that carry NO subject meaning — excluded when checking query<->tag subject overlap, so a clip is
# never accepted purely because it shares a camera word ("wide", "shot") or a stop-word with the query.
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "on", "in", "at", "by", "to", "with", "and", "or", "for", "from", "into",
    "your", "their", "its", "shot", "film", "footage", "clip", "video", "scene", "view", "example",
    # framing / camera words — present in a query's intent but not a SUBJECT the clip is about
    "wide", "close", "closeup", "medium", "tight", "angle", "low", "high", "eye", "level", "detail",
    "composition", "frame", "framing", "steady", "slow", "slowly",
}) | {w for s in _MOVEMENT_CUES.values() for phrase in s for w in phrase.split()}


def _content_terms(text: str) -> set[str]:
    """Subject/environment words in a query — camera words and stop-words removed. These are what a clip
    must actually be ABOUT for it to be a relevant reference (owner §5: subject match, not keyword overlap)."""
    toks = re.sub(r"[^a-z ]+", " ", (text or "").lower()).split()
    return {t for t in toks if len(t) > 2 and t not in _STOPWORDS}


def _tag_words(hit: dict) -> set[str]:
    blob = " ".join(t.strip() for t in (hit.get("tags") or "").split(","))
    return set(re.sub(r"[^a-z ]+", " ", blob.lower()).split())


def subject_overlap(hit: dict, query: str) -> int:
    """How many of the query's content (subject) words appear in the candidate's tags."""
    return len(_content_terms(query) & _tag_words(hit))


def _acceptable(hit: dict, requested: str | None, query: str) -> bool:
    """Owner §5 gate. Reject: sponsored/low-quality/non-G footage, a hard technique conflict, OR a clip whose
    tags share NO subject word with the query (keyword search returns loosely-related clips — a confidently
    wrong video is worse than none). When the query has no usable subject words, fall back to no-conflict only."""
    if hit.get("isLowQuality"):
        return False
    if hit.get("isGRated") is False:          # non-G footage excluded from a reference shown in-app
        return False
    tags = [t.strip() for t in (hit.get("tags") or "").split(",") if t.strip()]
    if technique_conflicts(requested, tags):
        return False
    wanted = _content_terms(query)
    if wanted and subject_overlap(hit, query) == 0:
        return False                          # shares no subject with what was asked for
    return True


def select(hits: list[dict], requested: str | None, query: str = "") -> dict | None:
    """Pick the best acceptable candidate. Ranks by: (1) subject-word overlap with the query, (2) tags SHOW
    the requested movement, (3) landscape, (4) non-AI, (5) popularity. Returns None (→ fallback) when nothing
    is acceptable — fewer correct references beat many misleading ones (owner §5/§11)."""
    acceptable = [h for h in hits if _acceptable(h, requested, query)]
    if not acceptable:
        return None

    def score(h: dict) -> tuple:
        tags = [t.strip() for t in (h.get("tags") or "").split(",") if t.strip()]
        shows_move = requested in _candidate_movements(tags) if requested else False
        tiny = (h.get("videos") or {}).get("tiny") or {}
        landscape = (tiny.get("width") or 0) >= (tiny.get("height") or 0)
        non_ai = not h.get("isAiGenerated")
        return (subject_overlap(h, query), shows_move, landscape, non_ai, h.get("downloads") or 0)

    return max(acceptable, key=score)


def find_reference_video(client: PixabayClient, *, query: str, technique_text: str | None,
                         cache: "scene_image.MetadataCache | None" = None) -> SceneVideo | None:
    """End-to-end: normalize query, search (broadening on thin results), gate + select, map. Returns None for a
    graceful image/text fallback. `technique_text` is the shot's framing/motion text used to classify the
    requested camera technique (no new model call — reuses Director/Guide content)."""
    norm = scene_image.normalize_query(query)
    if norm is None:
        return None
    requested = requested_technique(technique_text or query)
    cache_key = f"video::{norm}::{requested or '-'}"
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return None if cached is scene_image.MetadataCache._MISS else cached

    chosen_hit = None
    matched_q = None
    for attempt in scene_image.broadening_candidates(norm):
        hits = client.search(attempt)
        pick = select(hits, requested, attempt)
        if pick is not None:
            chosen_hit, matched_q = pick, attempt
            break
    video = _map(chosen_hit, matched_query=matched_q, matched_technique=requested) if chosen_hit else None
    if cache is not None:
        cache.put(cache_key, video if video is not None else scene_image.MetadataCache._MISS)
    return video


__all__ = [
    "BASE", "SECRET_ENV", "DEFAULT_SECRET_ID", "FLAG_ENV", "APP_UTM", "QUERY_MAX_LEN",
    "PROVIDER_TIMEOUT_SECONDS", "PIXABAY_PER_PAGE", "POSTER_ALLOWED_HOSTS",
    "SceneVideoDisabledError", "SceneVideoAuthError", "SceneVideoProviderError",
    "media_mode", "enabled", "load_key", "requested_technique", "technique_conflicts",
    "poster_is_allowed_host", "fetch_poster", "POSTER_MAX_BYTES",
    "SceneVideo", "PixabayClient", "select", "find_reference_video",
]
