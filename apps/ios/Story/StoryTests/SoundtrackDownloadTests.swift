import XCTest
@testable import Story

/// MusicCandidatesService.downloadSoundtrack: the link comes from our API, the audio from the provider CDN, written to a
/// file by a download task. Driven by a URLProtocol stub (no network).
final class SoundtrackRouteStub: URLProtocol {
    nonisolated(unsafe) static var audio = Data()
    nonisolated(unsafe) static var audioStatus = 200
    nonisolated(unsafe) static var linkCalls = 0

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let url = request.url!
        if url.path.hasSuffix("/v1/music/soundtrack") {
            Self.linkCalls += 1
            let body = Data(#"{"track_id":"t1","download_url":"https://cdn.example.invalid/t1.mp3","usage":"prototyping","commercial_export_enabled":false}"#.utf8)
            reply(200, body)
        } else {
            reply(Self.audioStatus, Self.audio)
        }
    }
    private func reply(_ code: Int, _ body: Data) {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1",
                                                              headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class SoundtrackDownloadTests: XCTestCase {
    private func service() -> MusicCandidatesService {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [SoundtrackRouteStub.self]
        let s = URLSession(configuration: cfg)
        return MusicCandidatesService(baseURL: URL(string: "https://api.example.invalid")!, session: s, downloadSession: s)
    }

    override func setUp() { SoundtrackRouteStub.linkCalls = 0; SoundtrackRouteStub.audioStatus = 200 }

    func test_downloads_audio_to_a_file() async throws {
        SoundtrackRouteStub.audio = Data((0..<700_000).map { UInt8(truncatingIfNeeded: $0) })
        let url = try await service().downloadSoundtrack(trackId: "t1")
        XCTAssertEqual(try Data(contentsOf: url), SoundtrackRouteStub.audio)
        XCTAssertEqual(SoundtrackRouteStub.linkCalls, 1)
    }

    func test_provider_error_status_fails_without_retry() async {
        SoundtrackRouteStub.audioStatus = 403
        do { _ = try await service().downloadSoundtrack(trackId: "t1"); XCTFail("expected badStatus") }
        catch MusicServiceError.badStatus(let code) { XCTAssertEqual(code, 403) }
        catch { XCTFail("unexpected \(error)") }
        XCTAssertEqual(SoundtrackRouteStub.linkCalls, 1)
    }
}
