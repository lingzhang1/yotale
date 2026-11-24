# YoTale

**An AI director for your personal videos.**

YoTale turns the everyday clips you shoot on your phone into a finished, watchable story — without you having to think like an editor. You point the camera, YoTale directs. It suggests what to shoot next, understands the footage you capture, and automatically edits your moments into a short film with pacing, structure, and music.

> Repository: https://github.com/lingzhang1/yotale

---

## What it does

Most of us have hundreds of video clips and no finished videos. Editing is slow, and knowing *what to shoot* in the first place is even harder. YoTale is built around a simple idea: **a good director makes a good video** — so YoTale plays the director for you.

- **Guides your shoot.** When you start a story, YoTale creates a creative plan and gives you live "shot ideas" on the camera screen — what to film, from where, and for how long.
- **Understands your footage.** As you capture moments, it analyzes each clip to know what's actually in it — the subject, the setting, the feeling.
- **Edits it for you.** It assembles your moments into a coherent short video with sensible pacing and structure.
- **Scores it with music.** It picks and plans music that fits the mood and timing of your story.

You shoot the moments. YoTale handles the direction and the edit.

---

## How a story comes together

```
  You start a story
         │
         ▼
  ┌──────────────┐   Creative plan: YoTale decides the kind of story
  │  Story Guide │   you're making and maps out how to shoot it.
  └──────────────┘
         │
         ▼
  ┌──────────────┐   On-camera "shot ideas" tell you what to film next.
  │  Director    │   You record real moments on your phone.
  └──────────────┘
         │
         ▼
  ┌──────────────┐   Each clip is analyzed so YoTale knows what's in it.
  │ Understanding│
  └──────────────┘
         │
         ▼
  ┌──────────────┐   An edit plan sequences your moments into a story,
  │  Edit Planner│   with pacing and a matching music track.
  └──────────────┘
         │
         ▼
   Your finished video
```

---

## What's in this repository

YoTale is a single monorepo containing the app, the backend that powers it, the infrastructure that runs it, and the product specs and design prototype.

| Area | Path | What it is |
|---|---|---|
| **iOS app** | `apps/ios/` | The native SwiftUI app you shoot and watch stories in. Open `apps/ios/Story/Story.xcodeproj` in Xcode. |
| **Backend API** | `apps/api/` | The Python service the app talks to — creates stories, runs the AI pipeline, serves results. |
| **AI engines** | `packages/` | The building blocks of the director: story guide, scene understanding, edit planner, music, and more. Each is an independent, well-scoped package. |
| **Infrastructure** | `infrastructure/` | AWS CDK definitions for deploying the backend (dev / beta / prod). |
| **Product specs** | `specs/` | The design docs and milestone plans behind each feature. |
| **Design prototype** | `prototypes/story-figma/` | The Figma-exported interactive UI prototype (React + Vite). |
| **Prompts** | `prompts/` | The versioned AI prompts that drive the engines. |
| **Contracts** | `contracts/` | The shared data contracts between the app and the backend. |

> The specs and the Figma prototype used to live in separate repositories (`yotale-specs`, `yotale-figma`). They are now consolidated here with their full history, so YoTale is the single source of truth.

### The AI engines, briefly

The `packages/` directory holds the pieces of the director. The most important ones:

- **`story_guide`** — builds the long-horizon creative plan for a story, once, up front.
- **`director_engine`** — answers "given what you want, what should you shoot right now?"
- **`scene_understanding`** — the multimodal analyzer that works out what each captured clip contains.
- **`edit_planner`** / **`edit_engine`** — turn your understood moments into a sequenced edit.
- **`music_direction`** / **`music_plan`** / **`music_engine`** — choose and time the music.
- **`model_gateway`** — the single doorway all engines use to call the underlying AI models.
- **`user_quota`**, **`observability`** — usage limits and operational metrics.

Each engine is self-contained and does not call the others directly — the application layer orchestrates them. That keeps every piece testable on its own.

---

## Running it

**iOS app:** open `apps/ios/Story/Story.xcodeproj` in Xcode and run on a device or simulator. See `apps/ios/README.md` for details.

**Backend:** the API is a Python service under `apps/api/` with its own `pyproject.toml`; the AI engines live in `packages/`. Infrastructure for deploying it is in `infrastructure/`.

---

## Status

YoTale is in active pre-beta development. The core loop — start a story, get directed, shoot moments, and generate an edited video with music — is working end to end on the dev and beta backends.

---

## Repository layout

```
yotale/
├── apps/
│   ├── ios/          Native iOS app (SwiftUI)
│   └── api/          Backend API (Python)
├── packages/         AI engines + shared services
├── prompts/          Versioned AI prompts
├── contracts/        App ↔ backend data contracts
├── infrastructure/   AWS CDK (dev / beta / prod)
├── specs/            Product specs & milestone plans
├── prototypes/
│   └── story-figma/  Figma-exported UI prototype
├── evals/            Evaluation harnesses
└── docs/             Architecture docs
```
