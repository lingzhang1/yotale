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
        {"error":"video_credits_exhausted","action":"contact_support","contract_version":2,
         "entitlement":{"videos":{"total":12,"used":12,"reserved":0,"remaining":0},"moments":{"total":100,"used":3,"reserved":0,"remaining":97}}}
        """
        let d = BillingDenial.parse(Data(body.utf8))
        XCTAssertEqual(d.code, .videoCreditsExhausted)
        XCTAssertEqual(d.action, "contact_support")
        XCTAssertFalse(d.canUpgrade)                          // an admin grant is extended by support; no upsell
        XCTAssertFalse(d.message.contains("Plus"))
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

// Billing V2: Plus is unlimited. The V2 payload must decode in THIS build and in the shipped contract-1 build (B5).
final class BillingV2ContractTests: XCTestCase {
    private static let plusV2 = """
    {"contract_version":2,"billing_mode":"enforce","enforced":true,
     "offer":{"plus":{"product_id":"com.lingzhang.story.plus.monthly","unlimited":true,"videos":12,"moments":100}},
     "capabilities":{"version":1,"video_generation":"unlimited","moment_analysis":"unlimited",
                     "subscription":{"status":"active","ends_at":1802592000}},
     "plan":"plus","status":"plus_active","unlimited":true,
     "trial":{"state":"not_applicable","started_at":null,"ends_at":null,"days":14},
     "period":{"id":"1000:1000","start":1800000000,"end":1802592000},
     "videos":null,"moments":null,"refunds":{"used":0,"allowed":0},
     "upgrade":{"eligible":false,"suggest":false,"blocking":false},
     "apple_app_account_token":"3b3f1f3e-8f4b-4f6e-9a55-0a1b2c3d4e5f"}
    """

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    func testPlusV2DecodesAsUnlimitedWithNoCountersAndAVerifiedDate() throws {
        let e = try decoder().decode(BillingEntitlement.self, from: Data(Self.plusV2.utf8))
        XCTAssertTrue(e.isPlus)
        XCTAssertTrue(e.isUnlimited)
        XCTAssertFalse(e.showsAllowances)                     // no counters for Plus (S6)
        XCTAssertNil(e.videos)
        XCTAssertEqual(e.offer?.plus.unlimited, true)
        XCTAssertEqual(e.subscriptionEndsAt, Date(timeIntervalSince1970: 1802592000))
    }

    func testAGrandfatheredTesterWhoBoughtPlusIsShownAsSubscribed() throws {
        let json = """
        {"contract_version":2,"billing_mode":"off","enforced":false,"plan":"beta_grandfathered","status":"beta_grandfathered",
         "unlimited":true,"capabilities":{"subscription":{"status":"active","ends_at":1802592000}}}
        """
        let e = try decoder().decode(BillingEntitlement.self, from: Data(json.utf8))
        XCTAssertTrue(e.isPlus)                               // the Active screen, never Subscribe (S8)
        XCTAssertFalse(e.showsAllowances)
    }

    func testFreeStarterKeepsItsCounters() throws {
        let json = """
        {"contract_version":2,"billing_mode":"enforce","enforced":true,"plan":"free_starter","status":"free_starter","unlimited":false,
         "capabilities":{"video_generation":"metered","moment_analysis":"metered","subscription":{"status":"none","ends_at":null}},
         "videos":{"total":2,"used":1,"reserved":0,"remaining":1},"moments":{"total":30,"used":0,"reserved":0,"remaining":30}}
        """
        let e = try decoder().decode(BillingEntitlement.self, from: Data(json.utf8))
        XCTAssertFalse(e.isPlus)
        XCTAssertTrue(e.showsAllowances)
        XCTAssertEqual(e.videos?.remaining, 1)
    }

    func testALapsedPlusAccountShowsNoStarterCountersEvenIfAnOlderServerSentThem() throws {
        let json = """
        {"contract_version":2,"billing_mode":"enforce","enforced":true,"plan":"plus","status":"plus_expired","unlimited":false,
         "capabilities":{"video_generation":"metered","moment_analysis":"metered","subscription":{"status":"expired","ends_at":1802592000}},
         "videos":{"total":2,"used":2,"reserved":0,"remaining":0},"moments":{"total":30,"used":0,"reserved":0,"remaining":30}}
        """
        let e = try decoder().decode(BillingEntitlement.self, from: Data(json.utf8))
        XCTAssertFalse(e.isPlus)
        XCTAssertFalse(e.showsAllowances)                     // S1: plan-gated on the client too
    }

    func testAContract1ServerStillDecodes() throws {
        let v1 = """
        {"contract_version":1,"billing_mode":"off","enforced":false,
         "offer":{"plus":{"product_id":"com.lingzhang.story.plus.monthly","videos":12,"moments":100}}}
        """
        let e = try decoder().decode(BillingEntitlement.self, from: Data(v1.utf8))
        XCTAssertNil(e.capabilities)
        XCTAssertFalse(e.isPlus)
    }

    // ---- copies of the SHIPPED contract-1 structs (BillingModels.swift at 40a77f5), so compatibility is proven, not assumed ----
    private struct OldAllowance: Decodable { let total: Int; let used: Int; let reserved: Int; let remaining: Int }
    private struct OldTrial: Decodable { let state: String; let startedAt: Int?; let endsAt: Int?; let days: Int? }
    private struct OldPeriod: Decodable { let id: String?; let start: Int?; let end: Int? }
    private struct OldUpgrade: Decodable { let eligible: Bool; let suggest: Bool; let blocking: Bool }
    private struct OldOfferPlan: Decodable { let productId: String; let videos: Int; let moments: Int }
    private struct OldOffer: Decodable { let plus: OldOfferPlan }
    private struct OldEntitlement: Decodable {
        let billingMode: String
        let enforced: Bool
        let offer: OldOffer?
        let error: String?
        let plan: String?
        let status: String?
        let unlimited: Bool?
        let trial: OldTrial?
        let period: OldPeriod?
        let videos: OldAllowance?
        let moments: OldAllowance?
        let upgrade: OldUpgrade?
        let appleAppAccountToken: String?
        var isPlus: Bool { plan == "plus" && (status == "plus_active" || status == "plus_grace") }
        var isUnlimited: Bool { unlimited == true || plan == "beta_grandfathered" }
        var showsAllowances: Bool { enforced && !isUnlimited && videos != nil }
    }

    func testTheShippedContract1ModelDecodesTheV2PlusPayload() throws {
        let old = try decoder().decode(OldEntitlement.self, from: Data(Self.plusV2.utf8))
        XCTAssertTrue(old.isPlus)                             // the old build shows its Active screen
        XCTAssertFalse(old.showsAllowances)
        XCTAssertNil(old.videos)                              // and prints no counters there (it shows them only when videos != nil)
        XCTAssertEqual(old.offer?.plus.videos, 12)            // required Int still present for the old paywall decode
    }
}

// Billing V2: temporary capacity is a retryable busy, never "you reached a limit".
final class BillingBusyTests: XCTestCase {
    override func tearDown() { ScriptedURLProtocol.reset(); super.tearDown() }

    func testEditPlanSubmitBusy429IsRetryable() async {
        ScriptedURLProtocol.responses = [(429, Data(#"{"error":"quota_exceeded","scope":"active_jobs","retry_after_seconds":30,"busy":true}"#.utf8))]
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [ScriptedURLProtocol.self]
        let client = EditPlanJobClient(baseURL: URL(string: "https://stub.invalid")!,
                                       session: URLSession(configuration: cfg), isForeground: { true })
        do {
            _ = try await client.submitPrepared(PreparedJobSubmit(body: Data(), boundary: "b"))
            XCTFail("expected busy")
        } catch EditPlanJobError.busy(let ra) {
            XCTAssertEqual(ra, 30)
        } catch {
            XCTFail("unexpected \(error)")
        }
    }

    func testCapacityBusyOffersTryAgainNotALimitScreen() {
        XCTAssertEqual(FailureRecovery.from(.capacityBusy), .technical)
        XCTAssertEqual(FailureRecovery.from(.quotaDenied("x")), .quotaReached)   // a real per-user cap is unchanged
    }
}

// Apple requires Terms of Use and Privacy Policy links next to a subscription purchase.
final class LegalLinksTests: XCTestCase {
    func testLinksAreHTTPSAndLanguageAware() {
        for url in [LegalLinks.termsOfUse, LegalLinks.privacyPolicyEnglish, LegalLinks.privacyPolicyChinese] {
            XCTAssertEqual(url.scheme, "https")
            XCTAssertNotNil(url.host)
        }
        XCTAssertEqual(LegalLinks.privacyPolicy(for: .en), LegalLinks.privacyPolicyEnglish)
        XCTAssertEqual(LegalLinks.privacyPolicy(for: .zhHans), LegalLinks.privacyPolicyChinese)
        XCTAssertEqual(LegalLinks.termsOfUse.host, "www.apple.com")
    }
}
