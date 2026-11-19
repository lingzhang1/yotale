import XCTest
@testable import Story

// Billing V1 / B3: the app only DECODES what the server says. These tests pin the wire contract (contract_version 1) so a server
// change that breaks the app is caught here, and pin the rules that keep the UI honest (counters only when enforced, a 402
// always yields a typed denial, the AU 402 reuses the existing park-pending path and never loses footage).
final class BillingModelsTests: XCTestCase {
    private func decode(_ json: String) throws -> BillingEntitlement {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(BillingEntitlement.self, from: Data(json.utf8))
    }

    func testOffModePayloadDecodesWithNoPlanAndNoCounters() throws {
        let e = try decode("""
        {"contract_version":1,"billing_mode":"off","enforced":false,
         "offer":{"plus":{"product_id":"com.lingzhang.story.plus.monthly","videos":12,"moments":100}},
         "apple_app_account_token":"3b3f1f3e-8f4b-4f6e-9a55-0a1b2c3d4e5f"}
        """)
        XCTAssertEqual(e.billingMode, "off")
        XCTAssertNil(e.plan)
        XCTAssertFalse(e.showsAllowances)                     // never show counters before the server enforces
        XCTAssertEqual(e.offer?.plus.videos, 12)
        XCTAssertEqual(e.offer?.plus.productId, "com.lingzhang.story.plus.monthly")
        XCTAssertNotNil(UUID(uuidString: e.appleAppAccountToken ?? ""))   // a purchase needs a real UUID
    }

    func testEnforcedFreeStarterShowsAllowances() throws {
        let e = try decode("""
        {"contract_version":1,"billing_mode":"enforce","enforced":true,"plan":"free_starter","status":"free_starter","unlimited":false,
         "videos":{"total":2,"used":1,"reserved":0,"remaining":1},"moments":{"total":30,"used":10,"reserved":0,"remaining":20},
         "upgrade":{"eligible":true,"suggest":true,"blocking":false}}
        """)
        XCTAssertTrue(e.showsAllowances)
        XCTAssertEqual(e.videos?.remaining, 1)
        XCTAssertEqual(e.upgrade?.suggest, true)
        XCTAssertFalse(e.isPlus)
    }

    func testGrandfatheredAndUnlimitedNeverShowCounters() throws {
        let e = try decode("""
        {"contract_version":1,"billing_mode":"enforce","enforced":true,"plan":"beta_grandfathered","status":"beta_grandfathered",
         "unlimited":true,"videos":{"total":0,"used":0,"reserved":0,"remaining":0}}
        """)
        XCTAssertTrue(e.isUnlimited)
        XCTAssertFalse(e.showsAllowances)
    }

    func testPlusActiveAndGrace() throws {
        let active = try decode(#"{"contract_version":1,"billing_mode":"off","enforced":false,"plan":"plus","status":"plus_active"}"#)
        let grace = try decode(#"{"contract_version":1,"billing_mode":"off","enforced":false,"plan":"plus","status":"plus_grace"}"#)
        let expired = try decode(#"{"contract_version":1,"billing_mode":"off","enforced":false,"plan":"plus","status":"plus_expired"}"#)
        XCTAssertTrue(active.isPlus)
        XCTAssertTrue(grace.isPlus && grace.isGrace)          // grace keeps access
        XCTAssertFalse(expired.isPlus)
    }

    func testDenialParsesTypedCodeActionAndAllowances() {
        let body = """
        {"error":"video_credits_exhausted","action":"wait_for_renewal","contract_version":1,
         "entitlement":{"videos":{"total":12,"used":12,"reserved":0,"remaining":0},"moments":{"total":100,"used":3,"reserved":0,"remaining":97}}}
        """
        let d = BillingDenial.parse(Data(body.utf8))
        XCTAssertEqual(d.code, .videoCreditsExhausted)
        XCTAssertEqual(d.action, "wait_for_renewal")
        XCTAssertFalse(d.canUpgrade)                          // a Plus subscriber waits for renewal; no upsell
        XCTAssertEqual(d.videosRemaining, 0)
        XCTAssertEqual(d.momentsRemaining, 97)
    }

    func testEveryServerDenialCodeIsKnown() {
        for code in ["trial_expired", "video_credits_exhausted", "moment_allowance_exhausted", "subscription_required"] {
            XCTAssertNotEqual(BillingDenialCode(rawValue: code), .unknown, code)
        }
    }

    func testUnreadableBodyStillYieldsADenialThatOffersSubscribe() {
        let d = BillingDenial.parse(Data("not json".utf8))
        XCTAssertEqual(d.code, .unknown)
        XCTAssertTrue(d.canUpgrade)
        XCTAssertFalse(d.message.isEmpty)
    }

    func testServiceErrorMapping() {
        XCTAssertEqual(BillingService.map(401, Data()), .notSignedIn)
        XCTAssertEqual(BillingService.map(503, Data()), .unavailable)
        XCTAssertEqual(BillingService.map(403, Data(#"{"error":"app_account_token_mismatch"}"#.utf8)),
                       .rejected(code: "app_account_token_mismatch"))
        XCTAssertEqual(BillingService.map(409, Data(#"{"error":"transaction_bound_elsewhere"}"#.utf8)),
                       .rejected(code: "transaction_bound_elsewhere"))
        XCTAssertEqual(BillingService.map(500, Data()), .badStatus(500))
    }

    func testAnalysisDenialParksTheJobInsteadOfLosingFootage() {
        // The AU 402 maps onto the existing allowance path (`quotaExhausted`), which parks the job PENDING without burning an attempt.
        let err = AssetUnderstandingServiceError.quotaExhausted(scope: "billing_moment_allowance_exhausted")
        XCTAssertEqual(AUDisposition.classify(err, isOnline: true), .quotaPark)
        XCTAssertFalse(err.isRetryable)
    }
}
