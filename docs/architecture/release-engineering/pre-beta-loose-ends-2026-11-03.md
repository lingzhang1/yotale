# Pre-Beta Loose Ends & Roadmap Status — 2026-11-03

Snapshot of open items with explicit disposition, so none becomes a forgotten branch. Audits below are
READ-ONLY findings; no iOS functionality, AWS trust policy, or branch merge was changed in producing this.

## 1. Quota-ledger P0 — ✅ CLOSED
Merged `ac4ab8a` (PR #82), dev + beta deployed, beta-verified (202 submit, worker completed, 0 false 429,
markers self-pruning). See `quota-ledger-bounded-runbook.md` closeout. No manual cleanup needed.

## 2. iOS branch `fix/ios-create-submit-audio-starvation` — AUDIT (disposition: selective, after diagnostic strip)
3 commits, NONE on master; the audio work is NOT the backend quota fix (that shipped separately in #82).

| Commit | Content | Classification |
|---|---|---|
| `2c14be6` | Move `AVAudioSession.setActive/setCategory` off the main actor via a new `AudioSessionCoordinator` actor; rewire `MusicPickerView` + `StoryResultView`; add `AudioSessionCoordinatorTests`. | **Valid audio-responsiveness improvement** — worth retaining. Fixes a real main-thread-block warning; not the root cause of the Create failure (that was the backend 429). |
| `84b72df` | `CREATE_TIMING` boundary `print()`s + `CancellationError` bracket in the submit path. | **Temporary diagnostic** — strip before merge. |
| `3dfbfe0` | `#if DEBUG deinit` probe + `WeakSelfSuspensionLifetimeTests` (rejecting the weak-self dealloc hypothesis). | **Diagnostic / superseded** — the lifetime test is a harmless correctness demo; the `deinit` print + `CREATE_TIMING` lines should be stripped. The weak-self and navigation theories were disproven; no lifecycle/nav code was changed (correctly). |

File-change audit: `AudioSessionCoordinator.swift` (new, keep), `MusicPickerView.swift`/`StoryResultView.swift`
(off-main rewire, keep), `EditPlanJobClient.swift`/`StoryCreationCoordinator.swift` (contain `CREATE_TIMING`
diagnostics — **14 lines** — strip), `AudioSessionCoordinatorTests.swift` (keep), `WeakSelfSuspensionLifetimeTests.swift`
(keep or drop; harmless).

**Recommendation:** retain the AudioSessionCoordinator + its two call-site rewires + `AudioSessionCoordinatorTests`
as a focused "iOS audio responsiveness" PR **after stripping the `CREATE_TIMING`/`deinit` diagnostics**. Discard
the pure-diagnostic additions. Requires an owner Xcode device build to verify (SwiftUI/audio; no macro/SwiftData).
**Owner:** Ling. **Not merged in this task.**

## 3. gamma/prod (and durable dev/beta) OIDC trust — AUDIT (disposition: one small CDK PR)
- There are **no gamma/prod deploy workflows** yet (`deploy-dev.yml`, `deploy-beta.yml` only) — so gamma/prod
  are not CI-deployable today.
- **Systemic issue:** the CDK source `infrastructure/cdk/lib/story-api-stack.ts:644-645` generates EVERY stage's
  deploy-role trust with `repo:lingzhang1*/story*:environment:${environment}`. After the `story → yotale`
  rename + public (immutable OIDC subjects → `repo:lingzhang1@<ownerid>/yotale@<repoid>:environment:<env>`),
  `story*` cannot match `yotale@<id>`. The in-code comment claiming it "already tolerates the numeric id" is
  stale/incorrect — this is exactly what failed dev and beta deploys this session.
- The live **dev and beta** roles were hand-patched to `repo:lingzhang1@*/yotale@*:environment:<env>` to unblock
  deploys — but a plain `cdk deploy` will REVERT those patches to the stale CDK value (the known
  master-deploy-reverts-live-patch trap).
- **Minimal durable fix:** change that one CDK line to `repo:lingzhang1@*/yotale@*:environment:${environment}`,
  PR → deploy per env. This makes the dev/beta patches permanent and pre-fixes gamma/prod.
- **Owner:** follow-up CDK PR (not done here; no live trust policy changed in this task beyond the earlier
  deploy-unblocking patches).

## 4. Roadmap status
- **P1-F reusable-AU-evidence:** Gate 1 + Gate 2 accepted.
- **Quota-ledger P0:** ✅ closed (this doc + runbook).
- **iOS audio branch:** audit complete (§2) — selective retain pending diagnostic strip + device build.
- **P1-G0 config/deployment gates:** pending — includes the CDK OIDC fix (§3) and the broader config-inventory
  surfacing (reusable_evidence across service+worker+device).
- **P1-G Gemini AU reliability:** pending (post-beta AI improvement — not started).
- **P1-H TestFlight readiness:** pending.
- Post-beta AI improvements tracked separately; none started in this task.

## 5. Confirmation
No beta data or runtime configuration was modified while producing this audit/closeout. (The quota deploys and
the earlier dev/beta OIDC patches were the authorized actions of prior steps; this step is docs-only.)
