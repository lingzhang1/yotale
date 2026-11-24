import XCTest
@testable import Story

// P1-F evaluation tooling — offline REPLAY of planning-time visual evidence from cached AU frames.
//
// Skipped unless the test process has P1F_REPLAY_DIR (pass `TEST_RUNNER_P1F_REPLAY_DIR=<dir>` to xcodebuild).
// The directory holds `manifest.json` (per Moment, in the runtime sheet order: id, planner duration,
// useful-segment count, AU guidance, cached frame files + tMs) and `frames/*.jpg` (the cached AU frames).
//
// Runs the REAL VisualEvidencePreparation + MultimodalVisualBudget + MomentContactSheetBuilder — the exact
// cache-hit code path a device run takes — for Highlights and Full Story, and writes each sheet plus a
// summary (frame timestamps, bytes, coverage) to `out_<type>/`. It also writes the pre-v2 comparison: the same
// cached frames sampled uniformly at the old duration-floor frame count (`out_uniform_floor/`), so a device
// run's server-side image_payload_bytes can be checked against both. No network, no SwiftData, no model call.
@MainActor
final class RuntimeEvidenceReplayTests: XCTestCase {

    private struct Cand: Decodable {
        let s: Double; let e: Double; let p: Double?; let c: Double?
        var candidate: EvidenceCandidate { EvidenceCandidate(start: s, end: e, peak: p, confidence: c) }
    }
    private struct Frame: Decodable { let file: String; let tMs: Int }
    private struct Moment: Decodable {
        let id: String; let duration: Double; let useful: Int
        let visual: [Cand]; let narrative: [Cand]; let events: [Cand]; let frames: [Frame]
    }
    private struct Manifest: Decodable { let moments: [Moment] }

    func test_replay_cached_evidence_sheets() async throws {
        guard let dir = ProcessInfo.processInfo.environment["P1F_REPLAY_DIR"], !dir.isEmpty else {
            throw XCTSkip("P1F_REPLAY_DIR not set — offline evaluation replay only")
        }
        let base = URL(fileURLWithPath: dir)
        let man = try JSONDecoder().decode(Manifest.self,
                                           from: Data(contentsOf: base.appendingPathComponent("manifest.json")))
        var frames: [UUID: [AUExtractedFrame]] = [:]
        for m in man.moments {
            let id = try XCTUnwrap(UUID(uuidString: m.id))
            frames[id] = try m.frames.map {
                AUExtractedFrame(jpeg: try Data(contentsOf: base.appendingPathComponent("frames/\($0.file)")),
                                 tMs: $0.tMs)
            }
        }

        for (label, type) in [("highlights", EvidenceVideoType.highlights), ("full_story", .fullStory)] {
            let refs = man.moments.map { m in
                EvidenceMomentRef(
                    momentId: UUID(uuidString: m.id)!, durationSeconds: m.duration, usefulSegmentCount: m.useful,
                    guidance: EditorialFrameGuidance(videoType: type, visual: m.visual.map(\.candidate),
                                                     narrative: m.narrative.map(\.candidate),
                                                     events: m.events.map(\.candidate)))
            }
            let r = await VisualEvidencePreparation.prepare(
                moments: refs, localURL: { _ in nil },
                fetchCachedFrames: { frames[$0.momentId] },
                restoreSources: { _ in ([:], []) })
            XCTAssertEqual(r.cacheHitCount, man.moments.count)
            try write(r.sheets, to: base.appendingPathComponent("out_\(label)"), extra: [
                "policy": EvidenceFrameMapper.policyVersion,
                "tier": r.budget.selectedTier,
                "applied_steps": r.budget.appliedSteps,
                "wire_bytes": r.wireBytes,
                "events_covered": "\(r.coverage.eventsCovered)/\(r.coverage.eventsTotal)",
                "visual_covered": "\(r.coverage.visualCovered)/\(r.coverage.visualTotal)",
                "narrative_covered": "\(r.coverage.narrativeCovered)/\(r.coverage.narrativeTotal)",
            ])
        }

        // Pre-v2 comparison: same cached frames, uniform selection at the old Tier-1 duration-floor count.
        var floorSheets: [MomentContactSheet] = []
        for m in man.moments {
            let id = UUID(uuidString: m.id)!
            let budget = ContactSheetBudget.tier1(forDuration: m.duration)
            let picked = EvidenceFrameMapper.selectExtracted(frames[id]!, guidance: nil,
                                                             count: budget.framesPerMoment)
            floorSheets.append(try MomentContactSheetBuilder.buildFromFrames(
                momentId: id, frames: picked, durationSeconds: m.duration, budget: budget))
        }
        try write(floorSheets, to: base.appendingPathComponent("out_uniform_floor"),
                  extra: ["policy": "uniform at ContactSheetBudget.tier1 count (pre-v2 frame count)"])
    }

    private func write(_ sheets: [MomentContactSheet], to out: URL, extra: [String: Any]) throws {
        try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
        var rows: [[String: Any]] = []
        for (i, s) in sheets.enumerated() {
            let name = String(format: "%02d_%@.jpg", i + 1, String(s.momentId.uuidString.prefix(8)).lowercased())
            try s.jpeg.write(to: out.appendingPathComponent(name))
            rows.append(["id": s.momentId.uuidString, "file": name, "frames": s.frameCount,
                         "frame_ms": s.frameMs, "bytes": s.jpeg.count])
        }
        var summary = extra
        summary["sheet_count"] = sheets.count
        summary["frame_total"] = sheets.reduce(0) { $0 + $1.frameCount }
        summary["total_jpeg_bytes"] = sheets.reduce(0) { $0 + $1.jpeg.count }
        summary["sheets"] = rows
        let json = try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys])
        try json.write(to: out.appendingPathComponent("summary.json"))
    }
}
