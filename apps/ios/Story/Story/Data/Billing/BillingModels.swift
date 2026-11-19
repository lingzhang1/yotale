import Foundation

// Billing V1 / B3 wire models. The SERVER is authoritative: these types only DECODE what `/v1/billing/entitlement` and the
// 402 error bodies say. The app never computes plan, allowance or expiry, and never sends them to the server.
// Everything is optional/defaulted because `STORY_BILLING_MODE=off` returns only the base fields (no plan, no allowances).

struct BillingAllowance: Decodable, Equatable {
    let total: Int
    let used: Int
    let reserved: Int
    let remaining: Int
}

struct BillingTrial: Decodable, Equatable {
    let state: String           // not_started | active | expired | not_applicable
    let startedAt: Int?
    let endsAt: Int?
    let days: Int?
}

struct BillingPeriod: Decodable, Equatable {
    let id: String?
    let start: Int?
    let end: Int?
}

struct BillingUpgrade: Decodable, Equatable {
    let eligible: Bool
    let suggest: Bool           // true after the first finished video (never a block)
    let blocking: Bool          // true only when the Free starter can no longer create or analyse
}

struct BillingOfferPlan: Decodable, Equatable {
    let productId: String
    let videos: Int
    let moments: Int
}

struct BillingOffer: Decodable, Equatable {
    let plus: BillingOfferPlan
}

struct BillingEntitlement: Decodable, Equatable {
    let billingMode: String             // off | observe | enforce
    let enforced: Bool
    let offer: BillingOffer?
    let error: String?                  // "billing_unavailable" when the server's billing store is down
    let plan: String?                   // free_starter | plus | beta_grandfathered | admin_granted
    let status: String?                 // free_starter | plus_active | plus_grace | plus_expired | beta_grandfathered | admin_granted
    let unlimited: Bool?
    let trial: BillingTrial?
    let period: BillingPeriod?
    let videos: BillingAllowance?
    let moments: BillingAllowance?
    let upgrade: BillingUpgrade?
    let appleAppAccountToken: String?   // the UUID the purchase must carry as `appAccountToken`

    var isPlus: Bool { plan == "plus" && (status == "plus_active" || status == "plus_grace") }
    var isGrace: Bool { status == "plus_grace" }
    var isUnlimited: Bool { unlimited == true || plan == "beta_grandfathered" }
    /// Limits are only real once the server enforces them; before that the app shows no allowance counters.
    var showsAllowances: Bool { enforced && !isUnlimited && videos != nil }
}

/// A 402 body: `{"error": <code>, "action": <action>, "contract_version": 1, "entitlement": {...}}`.
enum BillingDenialCode: String {
    case trialExpired = "trial_expired"
    case videoCreditsExhausted = "video_credits_exhausted"
    case momentAllowanceExhausted = "moment_allowance_exhausted"
    case subscriptionRequired = "subscription_required"
    case unknown
}

struct BillingDenial: Equatable {
    let code: BillingDenialCode
    let action: String                  // subscribe | wait_for_renewal | contact_support
    let videosRemaining: Int?
    let momentsRemaining: Int?

    /// Parse a 402 response body. Never throws: an unreadable body still yields an `unknown` denial, because a 402 always
    /// means "the entitlement does not permit this", whatever the details.
    static func parse(_ data: Data) -> BillingDenial {
        struct Body: Decodable {
            struct Ent: Decodable { let videos: BillingAllowance?; let moments: BillingAllowance? }
            let error: String?
            let action: String?
            let entitlement: Ent?
        }
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let b = try? dec.decode(Body.self, from: data)
        return BillingDenial(code: BillingDenialCode(rawValue: b?.error ?? "") ?? .unknown,
                             action: b?.action ?? "subscribe",
                             videosRemaining: b?.entitlement?.videos?.remaining,
                             momentsRemaining: b?.entitlement?.moments?.remaining)
    }

    /// Honest, specific copy. Never blames the user, never offers a plain retry (a retry cannot succeed until the allowance changes).
    var message: String {
        switch code {
        case .trialExpired:
            return L10n.t("Your free starter period has ended. Upgrade to YoTale Plus to keep creating videos.")
        case .videoCreditsExhausted:
            return action == "wait_for_renewal"
                ? L10n.t("You've used all your video credits for this period. They renew with your next billing period.")
                : L10n.t("You've used your free video credits. Upgrade to YoTale Plus to create more.")
        case .momentAllowanceExhausted:
            return action == "wait_for_renewal"
                ? L10n.t("You've used this period's new-Moment analysis. It renews with your next billing period. Your footage is still saved.")
                : L10n.t("You've used your free Moment analysis. Your footage is still saved. Upgrade to YoTale Plus to analyze more.")
        case .subscriptionRequired, .unknown:
            return L10n.t("This needs a YoTale Plus subscription.")
        }
    }

    var canUpgrade: Bool { action == "subscribe" }
}
