# Architecture & Implementation Documents — Canonical Location

**This directory (`docs/architecture/`) is the CANONICAL, version-controlled home** for approved architecture
and implementation-plan documents (owner decision 2026-10-25).

## Why this exists
The repository's `specs/` directory is **gitignored** in the parent repo, so documents written there live only
on a developer's disk and are not version-controlled. Approved, load-bearing design documents belong in tracked
source control — here.

## Rules
- **Canonical = the copy in this directory.** Edit documents HERE.
- Do **not** force-add or un-ignore `specs/`. The `specs/` copies (where they exist on disk) are **historical
  working drafts**, preserved as-is; they are not deleted or moved.
- **Do not maintain two independently edited copies.** When a document here supersedes a `specs/` draft, this
  tracked copy is authoritative; the `specs/` draft is frozen history.

## Editorial Pipeline v2 (`editorial-pipeline-v2/`)
| Document | Role |
|---|---|
| `milestone-editorial-pipeline-v2-highlights-fullstory-phase-a.md` | Phase A architecture audit & design (complete; reference) |
| `milestone-editorial-pipeline-v2-p0-evidence-reliability.md` | P0 — evidence reliability + never-block policy. Status: **DEV ACCEPTED** (merged `5a5e5e2`, dev-deployed) |
| `milestone-editorial-pipeline-v2-p1-implementation-design.md` | P1 implementation-ready design (approved; P1-A in progress) |

## Release Engineering (`release-engineering/`)
| Document | Role |
|---|---|
| `testflight-email-self-signup.md` | TestFlight self-signup milestone (Option A) |
| `p1g0-config-inventory.md` | P1-G0 running-config inventory (dev baseline) |
| `quota-ledger-bounded-runbook.md` | Quota phantom-429 fix + bounded-ledger + beta-cleanup runbook. Status: **CLOSED — ACCEPTED** (merged `ac4ab8a` / PR #82, dev+beta deployed, beta-verified) |
| `pre-beta-loose-ends-2026-11-03.md` | Open-item disposition: quota P0 closed; iOS audio branch audit; gamma/prod OIDC CDK fix; P1 roadmap status |
