# Plan: Story Guide — persistent "what moments make this Story work"

## Context

During setup, the Story Blueprint screen (`ScreenStoryBlueprint`, "Here's what I'll look for.") shows Story's creative understanding — but that guidance disappears once the Story starts. Before or during an experience (e.g. before reaching a Tour du Mont Blanc location), users want to review the *kinds* of moments worth capturing.

This adds a persistent feature, **Story Guide**, reachable from Story Home. Story Guide answers: *"What kinds of moments would make this particular Story work?"* — it does **not** need to know the user's current physical scene (that's what "Shoot a moment" / "Show me" already do).

Hard constraints from the brief:
- Story Guide is **not a checklist**. No checkboxes, percentages, required shot counts, "shots remaining", or daily assignments.
- Categories are **Story-specific**, not universal — the TMB categories must not be reused verbatim for weddings, concerts, road trips, etc. (Data is defined as this-Story data; a comment notes it would be generated per Story.)
- Advisory qualitative states ("Looking strong", "Could use more", "You've got this covered") are allowed but **advisory only**.

Per user decisions: **per-category detail screens** (not inline accordion), **include advisory states**, and the entry is a **row directly below the Shoot / Create actions** on Story Home.

All work is in `/workspaces/default/code/src/App.tsx` (single-file prototype, inline-style token system: bg `#0a0a0b`, cream `#f5f0e8`, muted `rgba(245,240,232,…)`, gold `#d4a853`; Fraunces 300 for headings/quotes, DM Sans for body/labels; pill buttons; `ScreenWrap` mount/active fade).

## Architecture recap
- Screens are a `Screen` string-union (line ~46) rendered via `screenMap` in `App()` (line ~3720). Navigation = single `screen` key + `go(s)`; no params, no back-stack.
- `TMB_CHAPTERS` (line 24) is the existing 6-beat arc the Blueprint renders; Story Guide's categories are its persistent, richer counterpart.
- `ScreenTMB` (line 3105) is Story Home; actions block (Shoot a moment / Create my Story) is at lines ~3213–3227.

## Changes

### 1. New data constant `TMB_STORY_GUIDE` (near `TMB_CHAPTERS`, ~line 31)
Array of 6 categories, each `{ id, title, intent, state, tone, examples: string[] }`, adapted for this Story (comment: generated per Story, not universal):
- **Opening** — "Establish where the journey begins." · examples: packing / boots / backpack; leaving the hotel; first reveal of the mountains.
- **Journey** — "Show movement through the Alps." · walking away from camera; side profile on the trail; boots moving through terrain.
- **Scale** — "Make the mountains feel enormous." · a person beneath huge mountains; wide landscape with a person entering frame.
- **Human moments** — "Natural moments of both travelers." · candid laughter at a rest stop; sharing a view; a hand passing a water bottle.
- **Challenge** — "Show that this was a real journey." · a steep uphill effort; catching your breath; crossing a rough section.
- **Ending** — "Give the Story closure." · the final ridge; looking back at the route; arriving where it ends.

Advisory `state`/`tone` (mid-trip snapshot, illustrative, non-numeric): Opening `You've got this covered` (calm cream), Journey/Scale `Looking strong` (calm cream), Human moments/Challenge `Could use more` (gentle gold nudge), Ending `Comes near the end` (muted). Rendered as small text with a tiny dot — never a checkbox, bar, or count.

### 2. `Screen` union — add `'storyguide'` and `'storyguidecat'` (in the TMB group, ~line 77).

### 3. New `ScreenStoryGuide` overview component
Model layout on `ScreenTMB`/`ScreenStoryBlueprint` conventions. Contents:
- Header: back arrow (→ Home), "Tour du Mont Blanc" eyebrow, Fraunces 300 title **"Story Guide"**, DM Sans sub: "What kinds of moments would make this Story work." Plus a one-line reassurance that it adapts and isn't a checklist (e.g. "A guide, not a checklist — capture what feels right.").
- A vertical list of the 6 categories. Each row: category title (Fraunces 300, ~19px), intent line (DM Sans muted), the advisory `state` (tiny dot + small label, toned per `tone`), and a **"See shot ideas →"** affordance that calls `onOpen(index)`.
- Staggered `readIn` entrance (reuse existing keyframe pattern).
- Scrollable (`overflowY: 'auto'`).

Props: `{ onBack, onOpen }` where `onOpen: (index: number) => void`.

### 4. New `ScreenStoryGuideCategory` detail component
Reads the selected category. Contents:
- Back arrow → Story Guide overview.
- Eyebrow "Story Guide", Fraunces title = category `title`, intent line, advisory `state`.
- **Examples as calm shot ideas** — each example as a quiet card/row (Fraunces or DM Sans, generous spacing), presented as ideas/inspiration, no numbering, no capture requirement. Optionally a soft "These are ideas, not requirements." footnote.
- No primary CTA that implies mandatory capture; keep it reference-only. (A subtle "Shoot a moment" affordance is out of scope unless trivial — omit to preserve the "not a checklist / doesn't need current scene" intent.)

Props: `{ category, onBack }` (category = the selected `TMB_STORY_GUIDE` entry).

### 5. Story Home entry (`ScreenTMB`)
- Add prop `onStoryGuide: () => void`.
- Insert a **"Story Guide →"** row directly **below** the actions block (after "Create my Story", before the Story Idea divider at ~line 3229). Style it as a quiet full-width tappable row consistent with the "Later in the trip" rows (`padding:'11px 14px', borderRadius:10, border:'1px solid rgba(245,240,232,0.06)'`, label left, `→` right) — calm, secondary weight, not competing with the primary Shoot button. Optionally a tiny sub-label "Moments worth capturing".

### 6. `App()` wiring
- Add state `const [guideCategory, setGuideCategory] = useState(0)`.
- `ScreenTMB`: pass `onStoryGuide={() => go('storyguide')}`.
- `screenMap`:
  - `storyguide: <ScreenStoryGuide onBack={() => go('tmb')} onOpen={(i) => { setGuideCategory(i); go('storyguidecat') }} />`
  - `storyguidecat: <ScreenStoryGuideCategory category={TMB_STORY_GUIDE[guideCategory]} onBack={() => go('storyguide')} />`
- Leave `ScreenStoryBlueprint` (setup-time "Here's what I'll look for") untouched — Story Guide is its persistent counterpart, not a replacement.

## Verification
- Run `pnpm tsc --noEmit` (sandbox permitting) to confirm the new components, props, and `Screen` union members typecheck; the new `guideCategory` indexing and `onOpen` signature are the main risks.
- In the preview: Home → Start a Story (or the existing Story) → Story Home → tap **Story Guide →** → confirm the overview lists all 6 categories with intent lines and advisory states (no checkboxes/percentages/counts) → tap **See shot ideas →** on a category → confirm the detail screen shows that category's shot ideas → back returns to the overview → back returns to Story Home.
- Confirm the "Story Guide →" row sits below Shoot a moment / Create my Story and doesn't disrupt the mosaic → actions → Story Idea hierarchy.
