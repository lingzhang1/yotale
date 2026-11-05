import XCTest
@testable import Story

// Phase 1B — SceneVideoDTO decoding + reference-media-mode flag. Pure logic; no network.
final class SceneVideoTests: XCTestCase {

    private let okEnvelope = """
    {"status":"ok","video":{
      "provider":"pixabay","video_id":"305660",
      "preview_url":"https://cdn.pixabay.com/video/x/305660_tiny.mp4",
      "poster_url":"https://cdn.pixabay.com/video/x/305660_tiny.jpg",
      "source_url":"https://pixabay.com/videos/id-305660/?utm_source=yotale&utm_medium=referral",
      "attribution_text":"Video by alice on Pixabay","contributor":"alice",
      "tags":["hiking","trail","mountain"],"duration":15,"width":1280,"height":720,
      "aspect_ratio":"16:9","is_ai_generated":false,
      "matched_query":"hiking trail","matched_technique":"tracking"}}
    """.data(using: .utf8)!

    func testDecodesVideoEnvelope() throws {
        let r = try StoryContractCoding.decoder().decode(SceneVideoResponseDTO.self, from: okEnvelope)
        XCTAssertEqual(r.status, "ok")
        let v = try XCTUnwrap(r.video)
        XCTAssertEqual(v.provider, "pixabay")
        XCTAssertEqual(v.videoId, "305660")
        XCTAssertTrue(v.previewURL.hasSuffix("_tiny.mp4"), "preview is the direct-stream MP4")
        XCTAssertTrue(v.posterURL.hasSuffix(".jpg"))
        XCTAssertEqual(v.contributor, "alice")
        XCTAssertEqual(v.matchedTechnique, "tracking")
        XCTAssertEqual(v.aspect, 1280.0 / 720.0, accuracy: 0.001)
    }

    func testNoMatchEnvelopeDecodesToNilVideo() throws {
        let data = #"{"status":"no_match","video":null}"#.data(using: .utf8)!
        let r = try StoryContractCoding.decoder().decode(SceneVideoResponseDTO.self, from: data)
        XCTAssertEqual(r.status, "no_match")
        XCTAssertNil(r.video)
    }

    func testAspectFallbackWhenDimensionsMissing() throws {
        let data = """
        {"status":"ok","video":{"provider":"pixabay","video_id":"1","preview_url":"https://cdn.pixabay.com/x.mp4",
         "poster_url":"https://cdn.pixabay.com/x.jpg","source_url":"https://pixabay.com/videos/id-1/",
         "attribution_text":"Video by bob on Pixabay","contributor":"bob","tags":[],
         "duration":null,"width":null,"height":null,"aspect_ratio":null,"is_ai_generated":null,
         "matched_query":null,"matched_technique":null}}
        """.data(using: .utf8)!
        let v = try XCTUnwrap(try StoryContractCoding.decoder().decode(SceneVideoResponseDTO.self, from: data).video)
        XCTAssertEqual(v.aspect, 16.0 / 9.0, accuracy: 0.001, "unknown dimensions -> 16:9 so the player never collapses")
    }

    // MARK: - Reference-media mode flag (owner §2/§4: one shared switch, safe default image)

    private func withEnv(_ value: String?, _ body: () -> Void) {
        let key = StoryGuideFeatures.referenceMediaKey
        let saved = ProcessInfo.processInfo.environment[key]
        if let value { setenv(key, value, 1) } else { unsetenv(key) }
        UserDefaults.standard.removeObject(forKey: key)
        body()
        if let saved { setenv(key, saved, 1) } else { unsetenv(key) }
    }

    func testModeDefaultsToImageWhenUnset() {
        withEnv(nil) {
            // With no env and no UserDefaults override, the compiled default is image.
            UserDefaults.standard.removeObject(forKey: StoryGuideFeatures.referenceMediaKey)
            XCTAssertEqual(StoryGuideFeatures.referenceMediaMode, .image)
        }
    }

    func testModeReadsVideoFromEnv() {
        withEnv("video") { XCTAssertEqual(StoryGuideFeatures.referenceMediaMode, .video) }
    }

    func testInvalidModeFallsBackToImage() {
        withEnv("bogus") { XCTAssertEqual(StoryGuideFeatures.referenceMediaMode, .image) }
    }

    func testReferenceVideoEnabledRequiresSceneImagesAndVideoMode() {
        withEnv("video") {
            // referenceVideoEnabled also gates on sceneImagesEnabled (the master kill-switch); when scene
            // images are on (default) and mode is video, video is enabled.
            XCTAssertEqual(StoryGuideFeatures.referenceVideoEnabled,
                           StoryGuideFeatures.sceneImagesEnabled)
        }
        withEnv("image") {
            XCTAssertFalse(StoryGuideFeatures.referenceVideoEnabled, "image mode never enables video")
        }
    }
}
