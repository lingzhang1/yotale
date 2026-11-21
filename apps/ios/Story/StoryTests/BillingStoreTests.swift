import XCTest
@testable import Story

// Billing V2 review N9 (+ B1, S2, S3): BillingStore behaviour that does not need StoreKit. The store is driven through
// `forward(jws:)` and `refresh()` against a scripted URLProtocol, with only non-Plus entitlements (a Plus reload would touch StoreKit).
final class BillingStoreTests: XCTestCase {
    override func tearDown() {
        ScriptedURLProtocol.reset()
        super.tearDown()
    }

    private let freeJSON = Data(#"{"contract_version":2,"billing_mode":"enforce","enforced":true,"plan":"free_starter","status":"free_starter"}"#.utf8)
    private let applied = Data(#"{"result":"not_active"}"#.utf8)

    @MainActor
    private func store() -> BillingStore {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [ScriptedURLProtocol.self]
        let svc = BillingService(baseURL: URL(string: "https://example.test")!, session: URLSession(configuration: cfg), token: { _ in .token("t") })
        return BillingStore(service: svc)
    }

    @MainActor
    func testARetryableFailureKeepsVerifyingAndTheLaterSuccessThatIsNotPlusClearsIt() async {
        let s = store()
        ScriptedURLProtocol.responses = [(503, Data())]
        let r1 = await s.forward(jws: "jws-1")
        XCTAssertEqual(r1, .failed)
        XCTAssertTrue(s.verifying)                          // a paying user is never shown Subscribe on a retryable failure
        XCTAssertEqual(s.notice, .unavailable)

        ScriptedURLProtocol.responses = [(200, applied), (200, freeJSON)]      // accepted, but the account is not Plus (S2)
        let r2 = await s.forward(jws: "jws-1")
        XCTAssertEqual(r2, .accepted)
        XCTAssertFalse(s.verifying)                         // no stuck "Confirming your subscription"
        XCTAssertNil(s.notice)                              // the stale failure notice is gone
        XCTAssertFalse(s.isPlus)
    }

    @MainActor
    func testAcceptedButTheEntitlementReadFailingKeepsVerifying() async {
        let s = store()
        ScriptedURLProtocol.responses = [(200, applied), (503, Data())]
        let r = await s.forward(jws: "jws-1")
        XCTAssertEqual(r, .accepted)
        XCTAssertTrue(s.entitlementLoadFailed)
        XCTAssertNil(s.entitlement)
    }

    @MainActor
    func testARejectedTransactionClearsVerifyingAndShowsFailed() async {
        let s = store()
        ScriptedURLProtocol.responses = [(503, Data())]
        _ = await s.forward(jws: "a")
        XCTAssertTrue(s.verifying)
        ScriptedURLProtocol.responses = [(403, Data(#"{"error":"bound_elsewhere"}"#.utf8))]
        let r = await s.forward(jws: "b")
        XCTAssertEqual(r, .failed)
        XCTAssertFalse(s.verifying)
        XCTAssertEqual(s.notice, .failed)
    }

    @MainActor
    func testTheSameTransactionIsPostedOnceAndTheLoserIsADuplicateNotAFailure() async {
        let s = store()
        ScriptedURLProtocol.responses = [(200, applied), (200, freeJSON)]
        async let first = s.forward(jws: "same")
        async let second = s.forward(jws: "same")
        let results = await [first, second]
        XCTAssertEqual(results.filter { $0 == .accepted }.count, 1)
        XCTAssertEqual(results.filter { $0 == .duplicate }.count, 1)
        XCTAssertEqual(results.filter { $0 == .failed }.count, 0)
        XCTAssertNil(s.notice)                              // the duplicate raised no error
        // one submit + one entitlement read, not two submits
        XCTAssertEqual(ScriptedURLProtocol.authHeaders.count, 2)
    }

    @MainActor
    func testASuccessfulPostClearsStaleFailureNoticesButNotInformationalOnes() async {
        let s = store()
        for stale in [BillingStore.Notice.unavailable, .failed, .needsSignIn] {
            s.notice = stale
            ScriptedURLProtocol.responses = [(200, applied), (200, freeJSON)]
            _ = await s.forward(jws: "x")
            XCTAssertNil(s.notice, "\(stale) should be cleared")
        }
        s.notice = .pending
        ScriptedURLProtocol.responses = [(200, applied), (200, freeJSON)]
        _ = await s.forward(jws: "x")
        XCTAssertEqual(s.notice, .pending)
    }

    @MainActor
    func testAFailedFirstLoadIsAnErrorStateNotAnEmptyEntitlementAndRecoversOnRetry() async {
        let s = store()
        XCTAssertNil(s.entitlement)
        XCTAssertFalse(s.entitlementLoadFailed)             // before the first read: the view shows "loading"
        ScriptedURLProtocol.responses = [(503, Data())]
        await s.refresh()
        XCTAssertNil(s.entitlement)                         // B1: the view must show "couldn't load", never Subscribe
        XCTAssertTrue(s.entitlementLoadFailed)
        ScriptedURLProtocol.responses = [(200, freeJSON)]
        await s.refresh()
        XCTAssertEqual(s.entitlement?.plan, "free_starter")
        XCTAssertFalse(s.entitlementLoadFailed)
    }

    @MainActor
    func testResetForgetsEverythingAccountBound() async {
        let s = store()
        ScriptedURLProtocol.responses = [(503, Data())]
        _ = await s.forward(jws: "a")
        s.reset()
        XCTAssertFalse(s.verifying)
        XCTAssertNil(s.notice)
        XCTAssertNil(s.entitlement)
        XCTAssertFalse(s.entitlementLoadFailed)
    }
}
