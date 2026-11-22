import XCTest
@testable import Story

/// Account deletion D5: the pure pieces (files, receipt hash, response mapping, defaults reset, directory
/// emptying). The full wipe and the lock lifecycle touch the app container and SwiftData; they are device tests
/// (design 7.4) and are deliberately not run against the test host's own store here.
final class AccountDeletionTests: XCTestCase {

    override func tearDown() {
        // Never leave a marker behind: a stray wipe-intent would wipe the simulator app at its next launch.
        try? AccountDeletionFiles.clearWipeIntent()
        AccountDeletionFiles.clearPendingRequest()
        StubProtocol.handler = nil
        super.tearDown()
    }

    // ---- files -------------------------------------------------------------------------------------------
    func test_pendingRequest_and_wipeIntent_roundTrip_and_are_separate() throws {
        XCTAssertNil(AccountDeletionFiles.pendingRequest())
        let p = AccountDeletionFiles.PendingRequest(requestId: "r1", receiptSecret: "s", createdAt: Date(timeIntervalSince1970: 1),
                                                    stage: .submitting, federatedProvider: "SignInWithApple")
        try AccountDeletionFiles.savePendingRequest(p)
        XCTAssertEqual(AccountDeletionFiles.pendingRequest(), p)
        XCTAssertNil(AccountDeletionFiles.wipeIntent(), "a pending request never implies a wipe")
        try AccountDeletionFiles.saveWipeIntent(.init(requestId: "r1", createdAt: Date(timeIntervalSince1970: 2)))
        XCTAssertEqual(AccountDeletionFiles.wipeIntent()?.requestId, "r1")
        try AccountDeletionFiles.clearWipeIntent()
        XCTAssertNil(AccountDeletionFiles.wipeIntent())
        XCTAssertNotNil(AccountDeletionFiles.pendingRequest(), "clearing the wipe keeps the request for completion")
    }

    @MainActor
    func test_files_live_outside_every_wiped_directory() {
        let dir = AccountDeletionFiles.directory.standardizedFileURL.path
        for wiped in LocalWipe.directoriesToEmpty(.default) {
            XCTAssertFalse(dir.hasPrefix(wiped.standardizedFileURL.path + "/"), "\(dir) is inside \(wiped.path)")
        }
    }

    func test_receiptSecret_is_256_bits_hex_and_hash_is_sha256() {
        let s = AccountDeletionFiles.newReceiptSecret()
        XCTAssertEqual(s.count, 64)
        XCTAssertTrue(s.allSatisfy { "0123456789abcdef".contains($0) })
        XCTAssertNotEqual(s, AccountDeletionFiles.newReceiptSecret())
        XCTAssertEqual(AccountDeletionService.receiptHash("abc"),
                       "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    }

    // ---- local wipe helpers --------------------------------------------------------------------------------
    @MainActor
    func test_resetDefaults_keeps_only_the_app_language() {
        let suite = "AccountDeletionTests.\(UUID().uuidString)"
        let d = UserDefaults(suiteName: suite)!
        d.set("zh-Hans", forKey: AppLanguageStore.defaultsKey)
        d.set(true, forKey: "story.location.explainerShown")
        LocalWipe.resetDefaults(d, bundleId: suite)
        XCTAssertEqual(d.string(forKey: AppLanguageStore.defaultsKey), "zh-Hans")
        XCTAssertNil(d.object(forKey: "story.location.explainerShown"))
        d.removePersistentDomain(forName: suite)
    }

    @MainActor
    func test_emptyDirectory_removes_children_and_keeps_the_directory() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("wipe-\(UUID().uuidString)")
        try fm.createDirectory(at: root.appendingPathComponent("media/x"), withIntermediateDirectories: true)
        try Data("a".utf8).write(to: root.appendingPathComponent("media/x/clip.mov"))
        try Data("b".utf8).write(to: root.appendingPathComponent("default.store-wal"))
        try LocalWipe.emptyDirectory(root, fileManager: fm)
        XCTAssertTrue(fm.fileExists(atPath: root.path))
        XCTAssertEqual(try fm.contentsOfDirectory(atPath: root.path), [])
        try fm.removeItem(at: root)
    }

    @MainActor
    func test_runIfPending_does_nothing_without_a_marker() {
        XCTAssertNil(AccountDeletionFiles.wipeIntent())
        XCTAssertEqual(LocalWipe.runIfPending(clearKeychain: { XCTFail("must not clear the Keychain") }), .nothingPending)
    }

    @MainActor
    func test_wipe_covers_both_stores_and_their_sidecar_files() {
        XCTAssertEqual(Set(LocalWipe.storeNames), ["default.store", "recovery-fallback.store"])
        XCTAssertEqual(LocalWipe.storeSuffixes, ["", "-shm", "-wal"])
    }

    // ---- API mapping ---------------------------------------------------------------------------------------
    private func service() -> AccountDeletionService {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubProtocol.self]
        return AccountDeletionService(baseURL: URL(string: "https://api.test")!, session: URLSession(configuration: cfg))
    }

    private func stub(_ status: Int, _ body: String) {
        StubProtocol.handler = { req in (status, Data(body.utf8), req) }
    }

    func test_submit_maps_every_outcome() async {
        let svc = service()
        let cases: [(Int, String, AccountDeletionService.SubmitOutcome)] = [
            (202, #"{"state":"accepted"}"#, .accepted),
            (409, #"{"error":"deletion_already_requested"}"#, .alreadyRequested),
            (401, #"{"error":"reauth_required"}"#, .reauthRequired),
            (503, #"{"error":"deletion_unavailable"}"#, .rejected("deletion_unavailable")),
            (403, #"{"error":"account_not_active"}"#, .rejected("account_not_active")),
            (503, #"{"error":"deletion_outcome_unknown"}"#, .unknown),
            (500, "oops", .unknown),
        ]
        for (status, body, want) in cases {
            stub(status, body)
            let got = await svc.submit(accessToken: "t", requestId: "r", receiptSecret: "s")
            XCTAssertEqual(got, want, "HTTP \(status) \(body)")
        }
        StubProtocol.handler = { _ in throw URLError(.timedOut) }
        let timedOut = await svc.submit(accessToken: "t", requestId: "r", receiptSecret: "s")
        XCTAssertEqual(timedOut, .unknown, "a timeout may have reached the server: never 'nothing happened'")
    }

    func test_submit_sends_only_the_receipt_hash() async {
        var sent: [String: Any] = [:]
        StubProtocol.handler = { req in
            sent = (try? JSONSerialization.jsonObject(with: StubProtocol.body(of: req))) as? [String: Any] ?? [:]
            return (202, Data(), req)
        }
        _ = await service().submit(accessToken: "t", requestId: "r1", receiptSecret: "abc")
        XCTAssertEqual(sent["confirm"] as? String, "DELETE")
        XCTAssertEqual(sent["request_id"] as? String, "r1")
        XCTAssertEqual(sent["receipt_hash"] as? String, AccountDeletionService.receiptHash("abc"))
        XCTAssertNil(sent["receipt_secret"])
    }

    func test_status_maps_states() async {
        let svc = service()
        stub(200, #"{"state":"accepted","completed_at":null}"#)
        var s = await svc.status(requestId: "r", receiptSecret: "s"); XCTAssertEqual(s, .accepted)
        stub(200, #"{"state":"in_progress"}"#)
        s = await svc.status(requestId: "r", receiptSecret: "s"); XCTAssertEqual(s, .inProgress)
        stub(200, #"{"state":"completed","completed_at":1800000000}"#)
        s = await svc.status(requestId: "r", receiptSecret: "s")
        XCTAssertEqual(s, .completed(Date(timeIntervalSince1970: 1_800_000_000)))
        stub(404, #"{"error":"not_found"}"#)
        s = await svc.status(requestId: "r", receiptSecret: "s"); XCTAssertEqual(s, .notFound)
        stub(503, "")
        s = await svc.status(requestId: "r", receiptSecret: "s"); XCTAssertEqual(s, .unreachable)
    }

    func test_only_the_deletion_codes_count_as_confirmation_on_another_device() async {
        let svc = service()
        stub(403, #"{"detail":"account deleting","error":"account_deletion_in_progress"}"#)
        var p = await svc.probe(accessToken: "t"); XCTAssertEqual(p, .deletionInProgress)
        stub(403, #"{"detail":"account deleted","error":"account_deleted"}"#)
        p = await svc.probe(accessToken: "t"); XCTAssertEqual(p, .deleted)
        for (status, body) in [(403, #"{"detail":"account suspended"}"#), (403, #"{"error":"app_account_token_mismatch"}"#),
                               (401, #"{"detail":"token expired"}"#), (500, "")] {
            stub(status, body)
            p = await svc.probe(accessToken: "t")
            XCTAssertEqual(p, .unknown, "generic \(status) must never wipe local data")
        }
        stub(200, #"{"story_user_id":"u"}"#)
        p = await svc.probe(accessToken: "t"); XCTAssertEqual(p, .active)
    }
}

/// URLProtocol stub: the handler returns (status, body) for a request.
final class StubProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (Int, Data, URLRequest))?

    static func body(of req: URLRequest) -> Data {
        if let b = req.httpBody { return b }
        guard let s = req.httpBodyStream else { return Data() }
        s.open(); defer { s.close() }
        var out = Data()
        var buf = [UInt8](repeating: 0, count: 4096)
        while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; out.append(buf, count: n) }
        return out
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let h = Self.handler else { client?.urlProtocol(self, didFailWithError: URLError(.unknown)); return }
        do {
            let (status, data, _) = try h(request)
            let resp = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }
    override func stopLoading() {}
}
