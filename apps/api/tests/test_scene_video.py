"""scene-video (Pixabay reference-video provider) — backend tests. Phase 1B.

Covers owner §5/§10: technique-conflict rejection (movement is the #1 criterion), candidate selection,
query normalization + broadening reuse, 24h caching, fail-soft provider/auth errors, SSRF-bounded poster
host, the shared media-mode flag, and compliant metadata mapping (direct preview MP4, backend-served poster,
attribution + utm). No network, no real key: the Pixabay client is a fake.
"""
from __future__ import annotations

import pytest

import scene_image as si
import scene_video as sv


def _hit(id_="1", tags="hiking, trail, mountain, people", *, w=1280, h=720,
         ai=False, low=False, grated=True, dur=12, user="alice"):
    return {
        "id": id_, "pageURL": f"https://pixabay.com/videos/id-{id_}/", "type": "film",
        "tags": tags, "duration": dur, "user": user,
        "isAiGenerated": ai, "isLowQuality": low, "isGRated": grated, "noAiTraining": False,
        "videos": {
            "tiny": {"url": f"https://cdn.pixabay.com/video/x/{id_}_tiny.mp4", "width": w, "height": h,
                     "size": 1, "thumbnail": f"https://cdn.pixabay.com/video/x/{id_}_tiny.jpg"},
            "small": {"url": f"https://cdn.pixabay.com/video/x/{id_}_small.mp4", "width": 1920, "height": 1080,
                      "size": 2, "thumbnail": f"https://cdn.pixabay.com/video/x/{id_}_small.jpg"},
        },
    }


class _FakeClient:
    """Returns a fixed hit list for every search; records queries. raise_exc to simulate provider failure."""

    def __init__(self, hits=None, raise_exc=None):
        self._hits = hits if hits is not None else [_hit()]
        self.raise_exc = raise_exc
        self.queries = []

    def search(self, query, *, per_page=sv.PIXABAY_PER_PAGE):
        self.queries.append(query)
        if self.raise_exc:
            raise self.raise_exc
        return list(self._hits)


# ---- media-mode flag ---------------------------------------------------------------------------------

@pytest.mark.parametrize("val,mode,enabled", [
    ("video", "video", True), ("image", "image", False), ("", "image", False),
    ("VIDEO", "video", True), ("bogus", "image", False), (None, "image", False),
])
def test_media_mode_flag(monkeypatch, val, mode, enabled):
    if val is None:
        monkeypatch.delenv(sv.FLAG_ENV, raising=False)
    else:
        monkeypatch.setenv(sv.FLAG_ENV, val)
    assert sv.media_mode() == mode
    assert sv.enabled() is enabled


# ---- technique classification + conflict gate (owner §5) ---------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Hold the camera steady and keep it still", "static"),
    ("Slowly pan across the valley", "pan"),
    ("Film hikers walking away, follow them up the trail", "tracking"),
    ("A slow reveal of the room", "reveal"),
    ("Drone flyover of the peaks", "aerial"),
    ("Move closer, push in on the guitar", "push_in"),
    ("Frame your desk", None),
])
def test_requested_technique(text, expected):
    assert sv.requested_technique(text) == expected


def test_static_request_rejects_aerial_candidate():
    assert sv.technique_conflicts("static", ["drone", "aerial", "mountains"]) is True
    assert sv.technique_conflicts("static", ["office", "walking", "person"]) is False


def test_pan_request_rejects_drone():
    assert sv.technique_conflicts("pan", ["aerial", "drone", "forest"]) is True
    assert sv.technique_conflicts("pan", ["pan", "forest", "move"]) is False


def test_no_requested_technique_never_conflicts():
    assert sv.technique_conflicts(None, ["aerial", "drone"]) is False


# ---- selection ---------------------------------------------------------------------------------------

def test_select_rejects_low_quality_and_non_g():
    assert sv.select([_hit(low=True)], None, "hiking trail") is None
    assert sv.select([_hit(grated=False)], None, "hiking trail") is None


def test_select_rejects_technique_conflict_even_with_subject_overlap():
    # Requested a STATIC mountain shot; the only candidate is a drone flyover that shares "mountain".
    hits = [_hit("d", tags="mountain, aerial, drone, flyover")]
    assert sv.select(hits, "static", "mountain hikers") is None


def test_select_prefers_candidate_that_shows_requested_movement():
    pan = _hit("pan1", tags="pan, forest, move, nature")
    plain = _hit("plain", tags="forest, nature, trees")
    chosen = sv.select([plain, pan], "pan", "forest pan")
    assert chosen["id"] == "pan1"


def test_select_prefers_landscape_and_non_ai_when_movement_equal():
    ai_land = _hit("ai", tags="desk, laptop", ai=True, w=1280, h=720)
    real_land = _hit("real", tags="desk, laptop", ai=False, w=1280, h=720)
    assert sv.select([ai_land, real_land], None, "desk laptop")["id"] == "real"


def test_select_rejects_candidate_with_no_subject_overlap():
    # The §5 trap: 'person sofa living room' must NOT accept a clip tagged only 'walking sneakers shoes'.
    off = _hit("off", tags="walking, sneakers, nike, shoes, path, outdoors")
    assert sv.select([off], None, "person sofa living room") is None


def test_select_prefers_higher_subject_overlap():
    weak = _hit("weak", tags="people, mall, shop, busy, walking")          # 1 overlap: people
    strong = _hit("strong", tags="hiking, trail, mountain, people, walk")  # 3 overlap
    chosen = sv.select([weak, strong], None, "hikers mountain trail people")
    assert chosen["id"] == "strong"


def test_subject_overlap_ignores_camera_and_stop_words():
    # 'wide' / 'shot' / 'the' must not count as subject overlap.
    assert sv.subject_overlap(_hit("x", tags="wide, shot, the"), "wide shot the office aisle") == 0
    assert sv.subject_overlap(_hit("y", tags="office, aisle, person"), "wide shot office aisle person") == 2


# ---- mapping / compliance ----------------------------------------------------------------------------

def test_map_builds_compliant_metadata():
    v = sv._map(_hit("42", user="bob"), matched_query="hiking trail", matched_technique="tracking")
    assert v.provider == "pixabay" and v.video_id == "42"
    assert v.preview_url == "https://cdn.pixabay.com/video/x/42_tiny.mp4"          # tiny preview, direct stream
    assert v.poster_url == "https://cdn.pixabay.com/video/x/42_tiny.jpg"           # poster served via backend
    assert v.attribution_text == "Video by bob on Pixabay"
    assert "utm_source=yotale" in v.source_url and v.source_url.startswith("https://pixabay.com/videos/")
    assert v.aspect_ratio == "16:9"
    d = v.to_wire()
    assert d["matched_technique"] == "tracking" and d["matched_query"] == "hiking trail"


def test_poster_host_ssrf_guard():
    assert sv.poster_is_allowed_host("https://cdn.pixabay.com/video/x/1_tiny.jpg") is True
    assert sv.poster_is_allowed_host("http://cdn.pixabay.com/x.jpg") is False       # must be https
    assert sv.poster_is_allowed_host("https://evil.example/x.jpg") is False
    assert sv.poster_is_allowed_host("https://cdn.pixabay.com.evil.com/x.jpg") is False


# ---- end-to-end find_reference_video -----------------------------------------------------------------

def test_find_returns_video_and_caches_24h():
    cache = si.MetadataCache(ttl_seconds=86_400)
    client = _FakeClient([_hit("7", tags="hiking, trail, people, walking")])
    v = sv.find_reference_video(client, query="hikers walking away mountain trail",
                                technique_text="stand still and film hikers walking away", cache=cache)
    assert v is not None and v.video_id == "7"
    # second call is served from cache — no further provider search
    before = len(client.queries)
    v2 = sv.find_reference_video(client, query="hikers walking away mountain trail",
                                 technique_text="stand still and film hikers walking away", cache=cache)
    assert v2.video_id == "7" and len(client.queries) == before


def test_find_no_acceptable_candidate_caches_miss_and_returns_none():
    cache = si.MetadataCache()
    # requested static, only a drone candidate -> rejected -> None (image/text fallback)
    client = _FakeClient([_hit("d", tags="mountain, aerial, drone")])
    v = sv.find_reference_video(client, query="mountain", technique_text="hold still, static wide shot", cache=cache)
    assert v is None
    before = len(client.queries)
    sv.find_reference_video(client, query="mountain", technique_text="hold still, static wide shot", cache=cache)
    assert len(client.queries) == before, "a cached miss must not re-search"


def test_find_empty_query_is_none_without_search():
    client = _FakeClient()
    assert sv.find_reference_video(client, query="!!! 42 http://x", technique_text=None) is None
    assert client.queries == []


def test_find_broadens_when_first_attempt_has_no_acceptable_hit():
    # First (full) query returns only a conflicting drone; a broadened query would return a good clip.
    class Broadening:
        def __init__(self):
            self.queries = []

        def search(self, q, *, per_page=sv.PIXABAY_PER_PAGE):
            self.queries.append(q)
            if q == "hiking trail mountain":
                return [_hit("d", tags="aerial, drone, mountain")]
            return [_hit("good", tags="hiking, trail, walking, people")]
    c = Broadening()
    v = sv.find_reference_video(c, query="hiking trail mountain",
                                technique_text="static shot of hikers", cache=None)
    assert v is not None and v.video_id == "good"
    assert len(c.queries) >= 2


# ---- provider fail-soft ------------------------------------------------------------------------------

def test_provider_error_propagates_for_endpoint_to_failsoft():
    client = _FakeClient(raise_exc=sv.SceneVideoProviderError("pixabay rate limited (429)"))
    with pytest.raises(sv.SceneVideoProviderError):
        sv.find_reference_video(client, query="city street", technique_text=None)


def test_auth_error_propagates():
    client = _FakeClient(raise_exc=sv.SceneVideoAuthError("pixabay auth rejected (401)"))
    with pytest.raises(sv.SceneVideoAuthError):
        sv.find_reference_video(client, query="city street", technique_text=None)


# ===== Endpoint tests (POST /v1/scene-video, /v1/scene-video/poster) ==================================

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_mod  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_video(monkeypatch):
    monkeypatch.setenv("STORY_REFERENCE_MEDIA_MODE", "video")
    main_mod._SCENE_VIDEO_CACHE = None
    main_mod._SCENE_VIDEO_CLIENT = None
    main_mod._SCENE_VIDEO_CLIENT_FACTORY = None
    yield
    main_mod._SCENE_VIDEO_CLIENT_FACTORY = None


def _client(fake=None):
    if fake is not None:
        main_mod._SCENE_VIDEO_CLIENT_FACTORY = lambda: fake
    return TestClient(create_app())


def test_endpoint_404_in_image_mode_makes_no_video_call(monkeypatch):
    monkeypatch.setenv("STORY_REFERENCE_MEDIA_MODE", "image")
    fake = _FakeClient()
    c = _client(fake)
    r = c.post("/v1/scene-video", json={"query": "hiking trail"})
    assert r.status_code == 404
    assert fake.queries == []


def test_endpoint_returns_video_ok():
    fake = _FakeClient([_hit("7", tags="hiking, trail, walking, people")])
    r = _client(fake).post("/v1/scene-video",
                           json={"query": "hikers walking away mountain trail",
                                 "technique_text": "stand still and film hikers walking away"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    v = body["video"]
    assert v["provider"] == "pixabay" and v["video_id"] == "7"
    assert v["preview_url"].startswith("https://cdn.pixabay.com/") and v["preview_url"].endswith(".mp4")
    assert "Pixabay" in v["attribution_text"]


def test_endpoint_no_match_is_text_only_fallback():
    # requested static, only a drone candidate -> rejected
    fake = _FakeClient([_hit("d", tags="mountain, aerial, drone")])
    r = _client(fake).post("/v1/scene-video",
                           json={"query": "mountain", "technique_text": "hold still, static wide"})
    assert r.status_code == 200 and r.json()["status"] == "no_match" and r.json()["video"] is None


def test_endpoint_provider_error_is_graceful():
    fake = _FakeClient(raise_exc=sv.SceneVideoProviderError("pixabay rate limited (429)"))
    r = _client(fake).post("/v1/scene-video", json={"query": "city street"})
    assert r.status_code == 200 and r.json()["status"] == "provider_error" and r.json()["video"] is None


def test_endpoint_empty_query_text_only_no_call():
    fake = _FakeClient()
    r = _client(fake).post("/v1/scene-video", json={"query": "!!! 42"})
    assert r.status_code == 200 and r.json()["status"] == "invalid_query"
    assert fake.queries == []


def test_endpoint_caches_24h_across_requests():
    fake = _FakeClient([_hit("7", tags="hiking, trail, walking")])
    c = _client(fake)
    j = {"query": "hiking trail", "technique_text": "walk with them"}
    c.post("/v1/scene-video", json=j)
    n = len(fake.queries)
    c.post("/v1/scene-video", json=j)
    assert len(fake.queries) == n, "second identical request must be served from the 24h cache"


# ---- poster endpoint ----

class _FakePosterResp:
    def __init__(self, data=b"\xff\xd8\xffJPEGBYTES", ctype="image/jpeg"):
        self._data = data
        self.headers = {"Content-Type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._data


def test_poster_rejects_non_pixabay_host():
    r = _client().post("/v1/scene-video/poster", json={"poster_url": "https://evil.example/x.jpg"})
    assert r.status_code == 400


def test_poster_fetches_allowed_host(monkeypatch):
    monkeypatch.setattr(sv.urllib.request, "urlopen", lambda req, timeout=0: _FakePosterResp())
    r = _client().post("/v1/scene-video/poster",
                       json={"poster_url": "https://cdn.pixabay.com/video/x/1_tiny.jpg"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")
    assert r.content == b"\xff\xd8\xffJPEGBYTES"


def test_poster_404_in_image_mode(monkeypatch):
    monkeypatch.setenv("STORY_REFERENCE_MEDIA_MODE", "image")
    r = _client().post("/v1/scene-video/poster",
                       json={"poster_url": "https://cdn.pixabay.com/video/x/1_tiny.jpg"})
    assert r.status_code == 404


def test_fetch_poster_rejects_non_image(monkeypatch):
    monkeypatch.setattr(sv.urllib.request, "urlopen",
                        lambda req, timeout=0: _FakePosterResp(data=b"<html>", ctype="text/html"))
    with pytest.raises(sv.SceneVideoProviderError):
        sv.fetch_poster("https://cdn.pixabay.com/video/x/1_tiny.jpg")
