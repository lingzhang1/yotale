import Foundation

// Billing V1 / B3 wire models (contract 2 since Billing V2). The SERVER is authoritative: these types only DECODE what
// `/v1/billing/entitlement` and the 402 error bodies say. The app never computes plan, allowance or expiry, and never sends them.
// Everything is optional/defaulted because `STORY_BILLING_MODE=off` returns only the base fields (no plan, no allowances).
// Billing V2: YoTale Plus is unlimited. The server sends `videos`/`moments` = null for unlimited accounts and a `capabilities`
// object; every field added in V2 is optional so this build also decodes a contract-1 server.

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
    let unlimited: Bool?
    let videos: Int?            // contract-1 decode field only; not a Plus limit (Plus is unlimited)
    let moments: Int?
}

/// Billing V2 `capabilities`: what this account can do now, and its Apple-verified subscription state.
struct BillingCapabilities: Decodable, Equatable {
    struct Subscription: Decodable, Equatable {
        let status: String      // active | grace | expired | none
        let endsAt: Int?        // server-verified renewal or expiry (or grace end) date
    }
    let version: Int?
    let videoGeneration: String?    // unlimited | metered
    let momentAnalysis: String?
    let subscription: Subscription?
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
    let capabilities: BillingCapabilities?

    /// An active (or grace) YoTale Plus subscription, including one bought by a grandfathered tester (Billing V2, S8).
    var isPlus: Bool {
        if plan == "plus" && (status == "plus_active" || status == "plus_grace") { return true }
        let s = capabilities?.subscription?.status
        return s == "active" || s == "grace"
    }
    var isGrace: Bool { status == "plus_grace" || capabilities?.subscription?.status == "grace" }
    var isUnlimited: Bool {
        unlimited == true || plan == "beta_grandfathered" || capabilities?.videoGeneration == "unlimited" || isPlus
    }
    /// The server-verified renewal or expiry date of the subscription (nil when there is none).
    var subscriptionEndsAt: Date? {
        (capabilities?.subscription?.endsAt ?? (plan == "plus" ? period?.end : nil))
            .map { Date(timeIntervalSince1970: TimeInterval($0)) }
    }
    /// Counters only for accounts that really have a finite allowance (Free starter, admin_granted) and only once the server
    /// enforces it. Never for Plus or grandfathered accounts (S6).
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
            // Plus is unlimited (Billing V2): this code only reaches the Free starter (subscribe) or an admin grant (contact support).
            return action == "subscribe"
                ? L10n.t("You've used your free video credits. Upgrade to YoTale Plus to create more.")
                : L10n.t("You've used the videos included in your grant. Contact support to extend it.")
        case .momentAllowanceExhausted:
            return action == "subscribe"
                ? L10n.t("You've used your free Moment analysis. Your footage is still saved. Upgrade to YoTale Plus to analyze more.")
                : L10n.t("You've used the Moment analysis included in your grant. Your footage is still saved. Contact support to extend it.")
        case .subscriptionRequired, .unknown:
            return L10n.t("This needs a YoTale Plus subscription.")
        }
    }

    var canUpgrade: Bool { action == "subscribe" }
}
