import XCTest
import CryptoKit
@testable import Story

/// The REAL MediaDownloadService.download path (download task + chunked verification), driven by a URLProtocol stub
/// so no network or S3 is touched. MediaDownloadTests covers the resolver with a fake service.
final class MediaDownloadStub: URLProtocol {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var body = Data()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let resp = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: "HTTP/1.1",
                                   headerFields: ["Content-Length": "\(Self.body.count)"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        // Deliver in several chunks, like a real transfer.
        var i = 0
        while i < Self.body.count {
            let end = min(i + 300_000, Self.body.count)
            client?.urlProtocol(self, didLoad: Self.body.subdata(in: i..<end))
            i = end
        }
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class MediaDownloadServiceTests: XCTestCase {
    private func service() -> MediaDownloadService {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [MediaDownloadStub.self]
        var s = MediaDownloadService()
        s.session = URLSession(configuration: cfg)
        return s
    }

    private func payload(_ n: Int) -> Data { Data((0..<n).map { UInt8(truncatingIfNeeded: $0 &* 31 &+ 7) }) }
    private func hex(_ d: Data) -> String { SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined() }
    private func dest() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".mov")
    }
    private func target(_ d: Data, size: Int? = nil, sha: String? = nil) -> MediaDownloadTarget {
        MediaDownloadTarget(url: URL(string: "https://example.invalid/original")!, expiresIn: 300,
                            expectedSize: size ?? d.count, expectedSha256Hex: sha ?? hex(d), contentType: "video/quicktime")
    }

    func test_download_verifies_and_writes_the_file_with_progress() async throws {
        let d = payload(2_500_000)
        MediaDownloadStub.status = 200; MediaDownloadStub.body = d
        let out = dest()
        var last = 0.0
        try await service().download(target: target(d), to: out, progress: { last = $0 })
        XCTAssertEqual(try Data(contentsOf: out), d)
        XCTAssertEqual(last, 1.0, accuracy: 0.0001)
        XCTAssertFalse(FileManager.default.fileExists(atPath: out.appendingPathExtension("part").path))
    }

    func test_checksum_mismatch_leaves_no_file() async throws {
        let d = payload(1_000_000)
        MediaDownloadStub.status = 200; MediaDownloadStub.body = d
        let out = dest()
        do {
            try await service().download(target: target(d, sha: String(repeating: "0", count: 64)), to: out, progress: nil)
            XCTFail("expected checksumMismatch")
        } catch MediaDownloadError.checksumMismatch {}
        XCTAssertFalse(FileManager.default.fileExists(atPath: out.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: out.appendingPathExtension("part").path))
    }

    func test_size_mismatch_leaves_no_file() async throws {
        let d = payload(800_000)
        MediaDownloadStub.status = 200; MediaDownloadStub.body = d
        let out = dest()
        do {
            try await service().download(target: target(d, size: d.count + 1), to: out, progress: nil)
            XCTFail("expected sizeMismatch")
        } catch MediaDownloadError.sizeMismatch(let e, let g) {
            XCTAssertEqual(e, d.count + 1); XCTAssertEqual(g, d.count)
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: out.path))
    }

    func test_storage_error_status_is_reported() async throws {
        MediaDownloadStub.status = 403; MediaDownloadStub.body = Data("denied".utf8)
        let out = dest()
        do {
            try await service().download(target: target(Data("x".utf8)), to: out, progress: nil)
            XCTFail("expected s3GetFailed")
        } catch MediaDownloadError.s3GetFailed(let code) { XCTAssertEqual(code, 403) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: out.path))
    }

    func test_sha256_of_file_matches_in_memory_hash() throws {
        let d = payload(3_100_000)
        let u = dest(); try d.write(to: u)
        XCTAssertEqual(try MediaDownloadService.sha256Hex(of: u), hex(d))
    }

    func test_media_download_session_has_no_five_minute_cap() {
        let c = StoryBackend.mediaDownloadSession.configuration
        XCTAssertGreaterThanOrEqual(c.timeoutIntervalForResource, 3600)
        XCTAssertEqual(c.timeoutIntervalForRequest, 60)
    }
}
