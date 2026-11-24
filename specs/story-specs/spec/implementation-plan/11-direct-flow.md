# 11 — DIRECT Flow

## Overview

End-to-end user journey for "help me shoot something good here." Composes specs 03–08 + 09–10 into a coherent experience. Build this after EDIT flow is working.

---

## Requirements

- At most two creative decisions: (1) intent input, (2) optionally try a different concept
- One concept shown by default — "Try another idea" is secondary, not primary
- Concept preview shown before any shooting begins (title, description, shot count, estimated time)
- Scene scan is optional — skippable without degrading the experience
- Every state (loading, concept card, capture, validation, processing, result) must work on a physical iPhone in a real outdoor environment
- Result screen: save to camera roll, share, start over — no editing controls in MVP
- Any AI step failure shows human-readable error with retry — never a blank screen or crash

---

## Design

**Full screen sequence:**
```
Home
  ↓
Intent Screen
  Template + optional text + optional reference
  ↓
"Show me where you are"
  [Hold to scan]  or  [Skip scan]
  ↓
"I have an idea…" (loading state)
  ↓
Concept Card
  Title · brief description · N shots · ~X sec
  [Let's shoot]   Try another idea
  ↓
Shot 1: guidance → capture → validation
  ↓
Shot 2: guidance → capture → validation
  ↓
"Creating your Story…"
  ↓
Result Screen
  Video plays on loop
  [Save]  [Share]  [Start over]
```

**Concept Card:**
```
┌─────────────────────────────┐
│  Main Character             │
│  Move through the crowd     │
│  before the city reveals    │
│                             │
│  2 shots · ~20 sec          │
│                             │
│  [Let's shoot]              │
│  Try another idea           │
└─────────────────────────────┘
```
Visual-first. No shot plan shown here. No filmmaking terms.

**"Try another idea":** Story Director called again with a variation hint. Returns one alternative concept. Supported once only — no infinite carousel.

**Loading states:**
- Scan analyzing: "Got it, I'm thinking…"
- Concept generating: "I have an idea…"
- Processing: "Creating your Story…"

Never a blank screen.

---

## Alpha 0.1 milestone

Walk outside. Open Story. Reference + description → 5-second scan → "I have an idea" → 2 shots → guided capture → finished video in ~30 seconds.

The only question that matters at this milestone:

> **"I genuinely wouldn't have thought to shoot it that way."**

If yes: push forward. If no: improve Story Director before adding features.

---

## Tasks

**Phase 1 (full fake end-to-end):**
- [ ] Wire together: Intent → fake scan → fake concept card → camera capture → fake validation → fake processing → result screen
- [ ] Run complete DIRECT flow on physical iPhone in a real outdoor environment
- [ ] Log every friction point and confusion during the run

**Integration (Phases 3–9):**
- [ ] Replace fake CreativeIntent with real AI (spec 03)
- [ ] Replace fake scan with real SceneUnderstanding (spec 04)
- [ ] Replace fake concept with real Story Director (spec 05)
- [ ] Replace fake validation with real shot validation (spec 08)
- [ ] Replace fake processing with real EditPlan + media engine (specs 09–10)

**Alpha 0.1 gate:**
- [ ] Walk outside, run full DIRECT flow, watch finished video
- [ ] Team verdict: "I wouldn't have thought to shoot it that way"
- [ ] If not: improve Director, do not add features

**Field testing:**
- [ ] Test in 5+ real environments (street, restaurant, park, landmark, beach)
- [ ] Log all "why is it asking me this" moments
- [ ] Log all "I'd just use Camera" moments
