# R-d.6 — Music free-text search + pagination (picker) · Render-test removal

Status: 🟢 built + deployed (backend) / iOS wired, awaiting device build. Internal-testing provider only.
Date: 2026-10-11. App commits (local, NOT pushed): see below. No frozen-contract change.

## 1. Render Test (dev) removed
Removed the DEBUG-only "▶ Render Test (dev) · Media Engine V1" surface:
- deleted `apps/ios/.../Features/Debug/RenderTestHarnessView.swift`;
- removed its button, `showRenderHarness` state, and sheet from `CreateStoryPreviewView.swift`;
- the separate `showsDiagnostics` mock-output dev block was preserved (re-wrapped in its own `#if DEBUG`).
Consumer builds unaffected (it was already `#if DEBUG`). Parse-clean, `#if/#endif` balanced.

## 2. Music search + pagination
A user-driven free-text catalog search with load-more, added to the existing picker. Distinct from
`/v1/music/candidates` (MusicPlan-driven ranked recommendation) — this is a browse surface.

### Backend — `POST /v1/music/search`
- Request: `{query, page_size (1–20, default 10), cursor?}`. Response: `{candidates[], next_cursor}`.
- Candidate rows reuse the candidates shape (incl. `preview_url`); `score=0.0` (unranked); no top analysis.
- Provider-agnostic via a new `search_page(term, page_size, cursor) -> (tracks, next_cursor)`:
  - **MCP**: `SearchRecordings` with `first`+`after`; cursor = opaque `pageInfo.endCursor`; `next_cursor` None
    when `hasNextPage` false. Caches lqmp3/waveform urls for browsed tracks (preview + energy_curve work).
  - **REST**: offset-based; cursor = stringified integer offset; `next_cursor` None on a short page.
- Flag-gated 404 when `STORY_EPIDEMIC_MODE != prototyping`.

### iOS — picker search bar + load-more (`MusicPickerView`)
- Search bar below the subtitle; debounced (350 ms) typing + submit; clear button.
- Non-empty query swaps the recommended list for paginated results; empty query restores recommendations.
- "Load more" row while `next_cursor` present; selecting a search result flows through the same
  `.track(id)` → analysis/soundtrack path as a recommended pick.
- New `MusicCandidatesService.searchPage(query, pageSize, cursor)` + `MusicSearchResponseDTO`.

## 3. Verification
- Full backend suite **221 passed** (+7: MCP/REST `search_page`, endpoint page1/page2/404). iOS parse-clean.
- Live (deployed MCP): page1 → 3 tracks w/ previews + cursor; page2 → 3 DIFFERENT tracks; `has_more` honored.
- Backend deployed via CodeBuild → ECR → App Runner (env unchanged: mcp + prototyping).

## 4. Constraints
Business MCP internal-testing only; no frozen-contract change; no production music-selection/render change.
Not pushed.
