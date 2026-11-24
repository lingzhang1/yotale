# 01 — Project Foundation

## Overview

Core iOS app shell, navigation, local persistence, and backend API skeleton. Everything else runs on top of this. Build first.

---

## Requirements

- iPhone-first, iOS 17+, vertical layout throughout
- Home screen with two entry points: DIRECT and EDIT
- Consistent back/cancel behavior; no tab bar in MVP
- `StoryProject` persists locally as JSON (CoreData or flat-file in Application Support)
- Projects survive app restart; assets stored as local file paths, no cloud sync in MVP
- Backend REST API with endpoints stubbed for all major operations; returns hard-coded fixture responses in Phase 1; designed so real AI layers slot in without client changes
- Every async operation has a loading state; every AI/network call has an error state with retry

---

## Design

**App architecture:** SwiftUI + MVVM. One `StoryProjectStore` singleton owns all project state.

**Navigation:**
```
RootView
├── HomeView
│   ├── DirectFlowView (modal full-screen)
│   └── EditFlowView (modal full-screen)
```

**Persistence:** Projects serialized as JSON at `Application Support/projects/<uuid>.json`. Media at `Application Support/assets/<uuid>.<ext>`.

**Backend:** Base URL configurable via environment. All endpoints return `{ "data": ..., "error": null }`. Phase 1 responses are fixtures.

**Dependencies:** System frameworks only in MVP — AVFoundation for camera/media, Vision for frame analysis.

---

## Tasks

- [ ] Create Xcode project, iOS 17+
- [ ] Implement `HomeView` with DIRECT / EDIT entry points
- [ ] Implement `StoryProjectStore` with JSON persistence
- [ ] Implement local asset file management (copy, reference, delete)
- [ ] Scaffold backend API with fixture responses
- [ ] Wire client networking layer (URLSession)
- [ ] Implement global loading and error state handling
- [ ] Run full DIRECT + EDIT flows end-to-end on a physical device with all AI faked
