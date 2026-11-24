import AVFoundation
import XCTest
@testable import Story

/// The audio mix must never put two gain changes on one track on top of each other: AVFoundation answers that
/// with an uncatchable exception (`_setRamp:`), which on beta (2026-11-12) crashed every render of a Story whose
/// fitted final shot was 0.79 s — and every relaunch that resumed it.
final class AudioGainScheduleTests: XCTestCase {

    // MARK: - the schedule itself

    private func assertNoOverlap(_ s: AudioGainSchedule, file: StaticString = #filePath, line: UInt = #line) {
        let cs = s.ordered
        for (i, a) in cs.enumerated() {
            for b in cs[(i + 1)...] {
                switch (a, b) {
                case (.point(let t1, _), .point(let t2, _)):
                    XCTAssertNotEqual(t1, t2, "two points at one time", file: file, line: line)
                case (.ramp(let s, let e, _, _), .point(let t, _)), (.point(let t, _), .ramp(let s, let e, _, _)):
                    XCTAssertFalse(t >= s && t <= e, "point \(t) on ramp \(s)-\(e)", file: file, line: line)
                case (.ramp(let s1, let e1, _, _), .ramp(let s2, let e2, _, _)):
                    XCTAssertFalse(s1 < e2 && s2 < e1, "ramps \(s1)-\(e1) and \(s2)-\(e2) overlap",
                                   file: file, line: line)
                }
            }
        }
    }

    func testPointInsideAnAcceptedRampIsSkipped() {
        var s = AudioGainSchedule()
        XCTAssertTrue(s.ramp(from: 0.8, to: 0, start: 9.0, end: 10.0))   // end fade
        XCTAssertFalse(s.point(0.6, at: 9.21))                            // the beta crash: shot start in the fade
        XCTAssertFalse(s.point(0.6, at: 9.0))                             // on the ramp's start
        XCTAssertTrue(s.point(0.6, at: 8.0))
        XCTAssertEqual(s.ordered.count, 2)
        assertNoOverlap(s)
    }

    func testOverlappingRampIsSkippedButTouchingRampsAreKept() {
        var s = AudioGainSchedule()
        XCTAssertTrue(s.ramp(from: 1, to: 0, start: 2.0, end: 3.0))
        XCTAssertFalse(s.ramp(from: 0, to: 1, start: 2.6, end: 3.4))     // overlaps
        XCTAssertTrue(s.ramp(from: 0, to: 1, start: 3.0, end: 3.4))      // touches end-to-start
        XCTAssertTrue(s.ramp(from: 0, to: 1, start: 1.0, end: 2.0))      // touches start-to-end
        assertNoOverlap(s)
    }

    func testEmptyBackwardsAndNonFiniteChangesAreSkipped() {
        var s = AudioGainSchedule()
        XCTAssertFalse(s.ramp(from: 0, to: 1, start: 1.0, end: 1.0))
        XCTAssertFalse(s.ramp(from: 0, to: 1, start: 2.0, end: 1.0))
        XCTAssertFalse(s.ramp(from: 0, to: 1, start: .nan, end: 1.0))
        XCTAssertFalse(s.point(1, at: .infinity))
        XCTAssertTrue(s.ordered.isEmpty)
    }

    func testLevelPointInsideASeamMovesToJustAfterIt() {
        var s = AudioGainSchedule()
        s.ramp(from: 0, to: 0.7, start: 4.6, end: 5.0)                   // incoming seam crossfade
        XCTAssertTrue(s.pointOrAfterRamp(0.5, at: 4.8))
        XCTAssertEqual(s.ordered.last, .point(at: AudioGainSchedule.ticks(5.0)! + 1, volume: 0.5))
        assertNoOverlap(s)
    }

    func testLevelPointInsideTheEndFadeIsDroppedNotMoved() {
        var s = AudioGainSchedule()
        s.ramp(from: 0.8, to: 0, start: 9.0, end: 10.0)
        s.ramp(from: 0, to: 0.8, start: 8.7, end: 9.0)                   // seam touching the fade
        XCTAssertFalse(s.pointOrAfterRamp(0.6, at: 9.5, before: 9.0))    // inside the fade: dropped
        XCTAssertFalse(s.pointOrAfterRamp(0.6, at: 8.8, before: 9.0))    // in the seam; after it = the fade
        XCTAssertTrue(s.ordered.allSatisfy { if case .ramp = $0 { return true } else { return false } })
    }

    // MARK: - buildAudioMix end to end (the crash path)

    private func seg(_ order: Int, _ dur: Double, audio: String) -> EditSegmentV2 {
        EditSegmentV2(order: order, assetId: "m\(order)", sourceStartSeconds: 0, sourceEndSeconds: dur,
                      outputDurationSeconds: dur, speed: 1.0, nativeAudio: audio, musicAlignment: nil)
    }

    private func range(_ start: Double, _ dur: Double) -> CMTimeRange {
        CMTimeRange(start: CMTime(seconds: start, preferredTimescale: 600),
                    duration: CMTime(seconds: dur, preferredTimescale: 600))
    }

    /// Builds the mix for a timeline of (start, duration) shots with music loop seams; the build itself is the
    /// assertion (an overlap aborts the test process), then every track's changes are re-checked.
    private func buildMix(_ shots: [(Double, Double)], seams: [Double]) -> AVMutableAudioMix {
        let segments = shots.enumerated().map { i, _ in seg(i, shots[i].1, audio: i % 3 == 0 ? "keep" : "duck") }
        let plan = EditPlanV2(schemaVersion: "edit_plan/2", targetDurationSeconds: 10, outputFormat: "vertical",
                              musicAssetId: "music", feasible: true, segments: segments)
        let inputs = MediaEngineInputs(plan: plan, resolveMomentURL: { _ in nil }, soundtrackURL: nil,
                                       musicAnalysis: nil, soundtrackRole: "supportive", nativeAudioPriority: "selective")
        let comp = AVMutableComposition()
        _ = comp.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
        _ = comp.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
        let musicA = comp.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
        let musicB = comp.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid)
        let ranges = zip(segments, shots).map { (segment: $0, range: range($1.0, $1.1)) }
        let end = shots.map { $0.0 + $0.1 }.max() ?? 0
        return MediaEngineV1().buildAudioMix(inputs, composition: comp, segmentRanges: ranges,
                                             soundtrackTrack: musicA, soundtrackTrackB: musicB,
                                             loopSeams: seams.map { CMTime(seconds: $0, preferredTimescale: 600) },
                                             totalDuration: CMTime(seconds: end, preferredTimescale: 600))
    }

    func testBetaCrashShapeShortFinalShotBuildsTheMix() {
        // ...4.0 s, 3.21 s, then the fitter-trimmed 0.79 s ending inside the 1 s fade window, with a loop seam.
        let mix = buildMix([(0, 4.0), (4.0, 3.21), (7.21, 0.79)], seams: [6.0])
        XCTAssertEqual(mix.inputParameters.count, 4)
        var trimmed = false
        // the end fade is clamped to the 0.79 s final shot (starts at its start, not 1 s before the end)
        for p in mix.inputParameters.suffix(2) {
            var a: Float = 0, b: Float = 0, r = CMTimeRange.zero
            if p.getVolumeRamp(for: CMTime(seconds: 7.9, preferredTimescale: 600),
                               startVolume: &a, endVolume: &b, timeRange: &r) {
                XCTAssertEqual(r.start.seconds, 7.21, accuracy: 0.002)
                XCTAssertEqual(b, 0)
                trimmed = true
            }
        }
        XCTAssertTrue(trimmed, "the soundtrack end fade must exist inside the last shot")
    }

    func testVeryShortShotsCrossfadeOverlapsAndDenseSeamsBuildTheMix() {
        // 0.1 s middle shots, a zero-length shot, crossfade overlaps (next starts before previous ends),
        // a 0.5 s final shot, seams closer together than the 0.4 s crossfade and one inside the end fade.
        let shots: [(Double, Double)] = [(0, 2.0), (1.8, 0.1), (1.9, 0.1), (2.0, 0.0), (2.0, 0.12),
                                         (2.05, 1.5), (3.4, 0.05), (3.45, 0.5)]
        let mix = buildMix(shots, seams: [1.0, 1.2, 1.3, 3.2, 3.8])
        XCTAssertEqual(mix.inputParameters.count, 4)
    }

    func testShortVideoUnderOneSecondStillFadesOut() {
        let mix = buildMix([(0, 0.6)], seams: [])
        var a: Float = 0, b: Float = 0, r = CMTimeRange.zero
        XCTAssertTrue(mix.inputParameters[2].getVolumeRamp(for: CMTime(seconds: 0.3, preferredTimescale: 600),
                                                           startVolume: &a, endVolume: &b, timeRange: &r))
        XCTAssertEqual(r.duration.seconds, 0.6, accuracy: 0.002)
    }
}
