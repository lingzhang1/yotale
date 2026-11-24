# Plan: Story App — Mobile Interactive Prototype

## Context

Story is an AI creative director for consumers. This prototype tests an 11-screen interaction flow: from expressing creative intent, scanning the environment, receiving a shot plan, capturing shots, to viewing the final video. The prototype must be fully clickable on mobile, feel cinematic and premium, and avoid any professional video-editor UI patterns.

## Aesthetic Decisions

- **Ground**: Near-black (`#0a0a0b`) — dark, cinematic, like a viewfinder
- **Accent**: Warm white (`#f5f0e8`) for primary text; amber/gold (`#d4a853`) for active/highlight states
- **Font pairing**: `Fraunces` (display, for "I have an idea" titles and hero text) + `DM Sans` (body, instructions, labels) — loaded via Google Fonts @import in `src/index.css`
- **Tone**: Minimal text, generous whitespace, one instruction at a time

## Architecture

Single-file implementation inside `src/App.tsx`. State: `currentScreen` (1–11) + minimal per-screen state (scan progress, countdown, recording state). No routing needed — it's a linear prototype flow.

Screen components are defined as functions within App.tsx (or split into `src/screens/` if file grows large). The outer shell renders an iPhone frame (390×844 logical px, centered on desktop) with overflow hidden so each screen fills it.

## Screen-by-Screen Plan

### Screen 1 — Creative Intent
- 4 visual style tiles (Cinematic, Energetic, Calm, Playful) as tappable cards with subtle selected state
- "Show me something I like" button (simulates reference upload)
- Textarea: "Describe what you want"
- "Cinematic" pre-selected by default
- Continue button → Screen 2

### Screen 2 — Reference
- Fake uploaded Reel: tall dark card with a gradient overlay, Times Square night photo from Unsplash, play icon
- "Got the vibe." heading
- "Anything you want to change?" subtext
- Pre-filled input: "Less influencer-like. Show more of Times Square."
- Continue → Screen 3

### Screen 3 — Scene Scan
- Full-screen dark UI styled like a camera viewfinder (corner brackets, subtle grid)
- "Show me where you are." + "Slowly show me the scene."
- Large circular scan button — tap to start 3-second animated progress ring
- Auto-advances to Screen 4 after scan completes

### Screen 4 — Thinking
- Full-screen dark, centered
- "Looking for an idea..." with a slow pulsing dot animation
- Auto-advances to Screen 5 after ~2 seconds

### Screen 5 — Story Idea
- "I have an idea." in Fraunces display
- Concept name: "Main Character"
- Description: "Move through the crowd, then reveal the city."
- 2-shot storyboard: two stacked image panels with shot numbers
- Metadata pill: "8 sec · 2 shots · ~20 sec to capture"
- Primary: "Let's shoot" → Screen 6
- Secondary: "Try another idea" (no-op in prototype, stays on screen)

### Screen 6 — Shot 1
- "1 of 2" label top
- Large looping visual area (Times Square walk video loop — use Unsplash image with subtle animation/parallax)
- "Walk toward the signs." — large, single instruction
- "I'll follow behind." — secondary, smaller
- "Ready" → Screen 7

### Screen 7 — Capture (Shot 1)
- Full-screen camera UI (dark, viewfinder corners)
- Countdown: 3 → 2 → 1 → GO (animated, 1 second each)
- Then: recording state with red pulsing dot + progress bar (simulated ~2s)
- Auto-advances to Screen 8

### Screen 8 — Validation
- "✓ Got it." centered, large checkmark
- Brief success animation (scale-in)
- "Next shot" → Screen 9

### Screen 9 — Shot 2
- Same structure as Screen 6
- "Stop and look toward the lights." instruction
- Different Unsplash image (upward city-lights perspective)
- "Ready" → Screen 7b (reuse Screen 7 logic, then → Screen 10)

### Screen 10 — Creating
- "Creating your Story..." centered
- Subtle progress bar or slow fade animation
- Auto-advances to Screen 11 after ~2.5 seconds

### Screen 11 — Result
- Large vertical video player area (tall card, Times Square night photo, play overlay)
- "Your Story" label
- "Save" button (primary)
- "Try another version" (secondary, ghost)

## Technical Notes

- **iPhone frame**: `w-[390px] h-[844px]` with `rounded-[50px]` border, notch cutout at top, centered in `min-h-screen bg-zinc-900` on desktop
- **Transitions**: `transition-all duration-300` fade or slide between screens via opacity/translate
- **Timers**: `useEffect` + `setTimeout` for auto-advancing screens (scan, countdown, thinking, creating)
- **Unsplash images**: Times Square night — use `photo-1534430480872-3498386e7856` and similar IDs
- **No external libraries** beyond what's already installed (React + Tailwind v4)

## Files to Modify

- `src/index.css` — add Google Fonts @imports (Fraunces, DM Sans) before `@import 'tailwindcss'`
- `src/App.tsx` — replace starter with full 11-screen prototype

## Verification

1. Open preview; app shows iPhone frame centered on dark desktop background
2. Tap through all 11 screens confirming correct advance logic
3. Verify auto-advance screens (3→4, 4→5, 7→8, 10→11) fire correctly
4. Check that fonts load (Fraunces for display, DM Sans for body)
5. Confirm no horizontal scroll or overflow on the iPhone frame
