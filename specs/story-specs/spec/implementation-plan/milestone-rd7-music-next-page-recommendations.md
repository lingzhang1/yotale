# R-d.7 — Next-page recommendations (music picker: different options per page)

Status: 🟢 built + deployed (backend) / iOS wired, device rebuild to see the pager. Internal-testing provider.
Date: 2026-10-11. App commit: see git. No frozen contract change.

## Goal
A "Next page" button in the music picker that REPLACES the recommended list with a DIFFERENT ranked set for
the same Story (not the typed-search Load-more from R-d.6 — this pages the recommendations themselves).

## Backend — `/v1/music/candidates` gains cursor paging
- Request: optional `cursor` (None = page 1). Response adds `next_cursor`.
- Page 1: ranked top set + `top_music_analysis` + `top_track_id` + `next_cursor` (unchanged for existing
  callers that omit cursor).
- Page N>1: pages the SAME MusicPlan search via `client.search_page(term, page_size, cursor)`, re-ranks that
  slice, returns different tracks. `top_music_analysis`/`top_track_id` are **page-1 only** (the Edit Planner
  consumes the page-1 pick; a chosen non-top/later-page track resolves its own analysis via /v1/music/analysis).
- Provider-agnostic (MCP cursor / REST offset, both already implement search_page). Flag-gated 404 as before.

## iOS — picker pager
- `MusicCandidatesService.candidates(..., cursor:)` + `MusicCandidatesResponseDTO.nextCursor`.
- `MusicSelectionResolver.Recommendation.nextCursor` + `nextPage(from:targetDurationSeconds:)` fetching the
  next page with the same MusicPlan.
- `MusicPickerView` holds `pages: [Recommendation]` + `pageIndex`; a **"Next page ›" / "‹ Back"** pager REPLACES
  the list. Already-fetched pages are cached (Back/Next just move the index). Selection is PRESERVED across
  pages; the AI "Story's pick" badge shows only on page 1 (later pages have no top pick).
- Picker constructed with `resolver:` + `targetDurationSeconds:` so it can fetch pages.

## Verification
- 224 backend tests (+1: candidates page1 has next_cursor + top_analysis; page2 different tracks, no analysis).
- iOS parse-clean. Live (deployed MCP): page1 → 4 ranked + cursor + analysis; page2 → 4 ALL-DIFFERENT tracks,
  no analysis.
- Deployed via CodeBuild → ECR → App Runner (env unchanged: mcp + prototyping).

## Constraints
Business MCP internal-testing only; no frozen contract/prompt change; existing single-page callers unaffected
(cursor optional). Not pushed.
