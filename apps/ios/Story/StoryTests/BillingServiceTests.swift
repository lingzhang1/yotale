import XCTest
@testable import Story

// Billing V2 (commit A): the observed "paid but still Subscribe / Sign in" bug. Network-free via a scripted URLProtocol.
// Locks: a 401 gets exactly ONE refresh-and-retry; an unreachable auth server is a transport error (never signed out); a
// purchase response this build cannot decode still counts as accepted (the store re-reads GET /v1/billing/entitlement).
final class BillingServiceTests: XCTestCase {
    override func tearDown() {
        ScriptedURLProtocol.reset()
        super.tearDown()
    }

    private func service(token: @escaping @MainActor (Bool) async -> AccessTokenFetch) -> BillingService {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [ScriptedURLProtocol.self]
        return BillingService(baseURL: URL(string: "https://example.test")!, session: URLSession(configuration: cfg), token: token)
    }

    private let entitlementJSON = #"{"contract_version":1,"billing_mode":"off","enforced":false,"plan":"plus","status":"plus_active"}"#

    @MainActor
    func test401IsRetriedOnceWithAForcedRefresh() async throws {
        ScriptedURLProtocol.responses = [(401, Data()), (200, Data(entitlementJSON.utf8))]
        let forced = ForcedLog()
        let svc = service { force in forced.values.append(force); return .token(force ? "fresh" : "stale") }
        let e = try await svc.entitlement()
        XCTAssertTrue(e.isPlus)
        XCTAssertEqual(forced.values, [false, true])
        XCTAssertEqual(ScriptedURLProtocol.authHeaders, ["Bearer stale", "Bearer fresh"])
    }

    @MainActor
    func testA401AfterTheRetryIsNotSignedInAndDoesNotLoop() async {
        ScriptedURLProtocol.responses = [(401, Data()), (401, Data()), (200, Data(entitlementJSON.utf8))]
        let svc = service { _ in .token("t") }
        do { _ = try await svc.entitlement(); XCTFail("expected notSignedIn") }
        catch { XCTAssertEqual(error as? BillingServiceError, .notSignedIn) }
        XCTAssertEqual(ScriptedURLProtocol.authHeaders.count, 2)
    }

    @MainActor
    func testOfflineAuthServerIsTransportNotSignedOut() async {
        let svc = service { _ in .offline }
        do { _ = try await svc.entitlement(); XCTFail("expected transport") }
        catch { XCTAssertEqual(error as? BillingServiceError, .transport) }
        XCTAssertTrue(ScriptedURLProtocol.authHeaders.isEmpty)        // nothing was sent with a stale token
    }

    @MainActor
    func testSubmitAcceptsA200WhoseEntitlementThisBuildCannotDecode() async throws {
        // The pre-fix server returned a bare ledger view (no billing_mode/enforced). A 200 is still acceptance.
        ScriptedURLProtocol.responses = [(200, Data(#"{"result":"applied","entitlement":{"plan":"plus"}}"#.utf8))]
        let svc = service { _ in .token("t") }
        let r = try await svc.submit(signedTransaction: "jws")
        XCTAssertEqual(r, "applied")
    }

    @MainActor
    func testEntitlementDecodeFailureIsSurfacedNotSwallowed() async {
        ScriptedURLProtocol.responses = [(200, Data(#"{"plan":"plus"}"#.utf8))]
        let svc = service { _ in .token("t") }
        do { _ = try await svc.entitlement(); XCTFail("expected decoding") }
        catch { XCTAssertEqual(error as? BillingServiceError, .decoding) }
    }
}

@MainActor final class ForcedLog { var values: [Bool] = [] }

/// Serves a scripted sequence of (status, body) and records the Authorization header of every request.
final class ScriptedURLProtocol: URLProtocol {
    nonisolated(unsafe) static var responses: [(Int, Data)] = []
    nonisolated(unsafe) static var authHeaders: [String] = []
    static func reset() { responses = []; authHeaders = [] }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.authHeaders.append(request.value(forHTTPHeaderField: "Authorization") ?? "")
        let (status, body) = Self.responses.isEmpty ? (500, Data()) : Self.responses.removeFirst()
        let resp = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
