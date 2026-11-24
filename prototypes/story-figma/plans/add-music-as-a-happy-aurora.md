# Add Music to Story's creative direction & final edit flow

## Context
Music should shape the Story edit (pacing, selection, arc), inferred automatically from Creative Direction, chosen concretely only at "Create my Story", and changeable from the final result — triggering a re-edit, not an audio swap. Story Home stays untouched.

All work is in `src/App.tsx` (single-file app, inline styles, Fraunces + DM Sans, `#0a0a0b` bg, cream `rgba(245,240,232,…)` text, gold `#d4a853` accent). Reuse `ScreenWrap`, existing typography/button styles.

## Changes

1. **State (App, ~L4013)**
   - Extend `CreativeDirection` (L2814) with `music: { feel: string[]; description: string; auto: boolean }`.
   - Add `inferMusicDirection(direction)` → label like "Emotional cinematic · gradual build" (maps vibe/tags; fallback when `auto`).
   - Add `MUSIC_TRACKS` const (Alpine Journey, Into the Mountains, Somewhere Far Away, Moving Forward) with `mood`, `shape`, `duration`, `pacing`, plus App state `selectedTrackId`, `importedTrack`, `musicReturnTo`, `reEditing` flag.

2. **ScreenStoryContext (L2972)** — add a subtle "Music" row under tags: label + inferred direction + `Change →`. Tapping opens an inline bottom sheet (not a new screen): "How should the music feel?" chips (Cinematic, Emotional, Epic, Dreamy, Energetic, Chill, multi-select), "Describe it…" textarea, "Let Story choose" link. Done updates direction.

3. **Story Guide influence** — small helper that reorders/rewords a couple of `TMB_STORY_GUIDE` notes based on music feel (epic/cinematic → establishing, scale, climax; chill/dreamy/emotional → quiet moments, laughter, emotional ending). Applied where guide is rendered in `ScreenTMB` (~L3375). No music UI on Home.

4. **ScreenTMBPreview (L3787)** — add a MUSIC section between mosaic and CTA: "♫ Story's pick", track title (Fraunces), mood + shape · duration, `▶ Preview` (toggles animated equalizer bars + progress, simulated), `Change music →`.

5. **New screen `tmbmusic` (ChooseMusic)** — "Choose music / Recommended for your Story", 4 track rows with ▶ preview, meta, "Selected ✓" in gold; `+ Import music` row (hidden file input `accept="audio/*"` → adds "Your track" as an option). Footnote: "Different music changes the edit — Story will re-cut moments, pacing and build to fit." Back/confirm returns to `musicReturnTo`.

6. **Screen10Creating (L2324)** — accept optional `trackName` + `reEdit` props; cycle status lines ("Reading your moments…", "Listening to Alpine Journey…", "Shaping the story around the music…", "Timing cuts to the beat…"); when `reEdit`, headline "Re-editing to fit {track}…". Direct-flow callers unchanged (defaults).

7. **Screen11Result (L2358)** — add optional `trackName`, `onChangeMusic`: subtle "♫ Alpine Journey" line under title; actions "Looks good" (existing) and "Change music". Picking a new track from result shows toast "Story may adjust the edit to fit this music." then routes to `creating` with `reEdit`, then back to `result`.

8. Register `tmbmusic` in `Screen` union and screen map; wire routes.

## Verification
Walk the preview: Start a Story → context shows inferred music, Change → chips/describe/Let Story choose → Home has no music → Create my Story shows pick + preview → Change music selects/imports → Create → progress mentions music → Result shows ♫ track → Change music → re-edit progress → result with new track.
