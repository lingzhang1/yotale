import SwiftUI
import StoreKit

/// Billing V1 / B3 (V2 redesign): the one billing screen. It is the paywall for a Free starter and the subscription status screen
/// for a Plus subscriber. Everything shown comes from the server (plan, status, verified renewal/expiry date, the Free starter's
/// remaining allowance) or from StoreKit (the localized price, whether auto-renew is on); no price or number is hard-coded here.
/// Opening it never triggers an AI call: it only reads the billing endpoints and StoreKit.
struct PlusSubscriptionView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AuthStore.self) private var auth
    @Environment(BillingStore.self) private var billing

    /// Why the screen opened, so a denial can explain itself. Nil when opened from the account menu.
    var denial: BillingDenial?

    @State private var showManage = false
    @State private var anotherAccountAlertSeen = false

    /// The Free-starter offer (with the Subscribe button) is on screen.
    private var showsOfferInline: Bool {
        auth.isSignedIn && !billing.isPlus && !billing.verifying && billing.canOfferSubscribe
    }

    var body: some View {
        NavigationStack {
            Form {
                if let denial, !billing.isPlus {
                    Section { Text(denial.message).font(StoryTheme.body(15)) }
                }
                if !auth.isSignedIn {
                    heroSection
                    Section { Text("Sign in to subscribe or to restore a purchase.") }
                } else if billing.isPlus {
                    activeSections
                } else if billing.verifying {
                    verifyingSection
                } else if !billing.canOfferSubscribe {
                    // B1/R1: never Subscribe from unknown or stale state; Subscribe needs the LAST server read to have succeeded and said "not Plus".
                    heroSection
                    entitlementUnavailableSection
                } else {
                    heroSection
                    offerSections
                }
                if auth.isSignedIn { restoreSection }
                legalSection
                if !showsOfferInline { noticeSection }   // the offer section shows the notice beside Subscribe
            }
            .scrollContentBackground(.hidden)
            .background(StoryTheme.ink)
            .navigationTitle("YoTale Plus")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task {
                billing.start()
                await billing.refresh()
            }
            .manageSubscriptionsSheet(isPresented: $showManage)
            .alert("YoTale Plus", isPresented: Binding(
                get: { billing.notice == .ownedByAnotherAccount && showsOfferInline && !anotherAccountAlertSeen },
                set: { if !$0 && billing.notice == .ownedByAnotherAccount { anotherAccountAlertSeen = true } })) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(message(for: .ownedByAnotherAccount))
            }
        }
    }

    // MARK: Free starter -> paywall
    private var heroSection: some View {
        Section {
            VStack(alignment: .leading, spacing: 8) {
                Text("Create without overthinking.")
                    .font(StoryTheme.display(28))
                    .foregroundStyle(StoryTheme.cream)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Your AI director for capturing, creating, and refining beautiful video stories.")
                    .font(StoryTheme.body(15))
                    .foregroundStyle(StoryTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.vertical, 6)
            .listRowBackground(Color.clear)
        }
    }

    @ViewBuilder private var offerSections: some View {
        Section {
            benefitRow("camera.viewfinder", L10n.t("AI shooting guidance"))
            benefitRow("film.stack", L10n.t("Beautiful Highlights and Full Stories"))
            benefitRow("text.bubble", L10n.t("Natural-language video revisions"))
            benefitRow("square.on.square", L10n.t("Different versions from the same footage"))
            benefitRow("infinity", L10n.t("Unlimited AI video creation and editing with Plus"))
            benefitRow("sparkles", L10n.t("Unlimited AI shooting ideas while you film"))
        } footer: {
            Text("Unlimited means ordinary video creation and editing (Create, Create Another Version and Revise) while your subscription is active. Your videos stay yours if you cancel.")
        }

        if billing.entitlement?.showsAllowances == true, let v = billing.entitlement?.videos, let m = billing.entitlement?.moments {
            Section("Your free starter") {
                LabeledContent("Video credits left", value: "\(v.remaining)")
                LabeledContent("New Moments you can analyze", value: "\(m.remaining)")
                if billing.entitlement?.showsIdeaAllowance == true, let i = billing.entitlement?.ideas {
                    LabeledContent("AI shooting ideas left", value: "\(i.remaining)")
                }
            }
        }

        Section {
            if let price = billing.localizedPrice {
                Text(L10n.t("YoTale Plus — \(priceLine(price))"))
                    .font(StoryTheme.body(15, .medium))
                    .foregroundStyle(StoryTheme.cream)
            }
            Button {
                anotherAccountAlertSeen = false          // every tap explains again
                Task { await billing.purchasePlus() }
            } label: {
                HStack {
                    Text("Subscribe").bold()
                    Spacer()
                    if billing.phase == .purchasing { ProgressView() }
                }
            }
            .disabled(billing.phase != .idle || billing.product == nil)
            .foregroundStyle(StoryTheme.gold)
            // The result of a Subscribe tap shows HERE, next to the button (dev 2026-11-22: it was only in the last section, below
            // Terms and Privacy, so tapping Subscribe looked like nothing happened).
            if let n = billing.notice {
                Text(message(for: n)).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } footer: {
            Text("Payment is charged to your Apple ID. The subscription renews every month until you cancel it at least 24 hours before the renewal date. Manage or cancel any time in your Apple ID settings.")
        }
    }

    // MARK: Plus -> status (never a Subscribe button)
    @ViewBuilder private var activeSections: some View {
        Section {
            VStack(alignment: .leading, spacing: 6) {
                Text("YoTale Plus")
                    .font(StoryTheme.display(24))
                    .foregroundStyle(StoryTheme.cream)
                Text(billing.entitlement?.isGrace == true ? L10n.t("Payment issue. Update your payment method") : L10n.t("Active"))
                    .font(StoryTheme.body(15, .medium))
                    .foregroundStyle(billing.entitlement?.isGrace == true ? StoryTheme.danger : StoryTheme.gold)
                Text("Unlimited video creation and editing")
                    .font(StoryTheme.body(15))
                    .foregroundStyle(StoryTheme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.vertical, 6)
        }
        Section("Subscription details") {
            if let end = billing.entitlement?.subscriptionEndsAt {
                LabeledContent(dateLabel, value: L10nFormat.shortDate(end))
            }
            if let price = billing.localizedPrice {
                LabeledContent("Plan", value: L10n.t("YoTale Plus — \(priceLine(price))"))
            }
            Button("Manage Subscription") { showManage = true }
                .foregroundStyle(StoryTheme.gold)
        }
    }

    /// "Renews" while auto-renew is on, "Access until" once canceled (still active until the date), from StoreKit's renewal info;
    /// the DATE itself is always the server-verified one.
    private var dateLabel: String {
        switch billing.willAutoRenew {
        case .some(true): return L10n.t("Renews")
        case .some(false): return L10n.t("Access until")
        case .none: return L10n.t("Renews or ends")
        }
    }

    /// A verified Apple purchase the server has not confirmed yet: never show Subscribe to someone who has paid.
    private var verifyingSection: some View {
        Section {
            HStack(spacing: 12) {
                ProgressView()
                Text("Confirming your subscription…")
            }
            Button("Check again") { Task { await billing.recoverPendingTransactions() } }
                .foregroundStyle(StoryTheme.gold)
        } footer: {
            Text("Your purchase is safe. YoTale is confirming it with the App Store.")
        }
    }

    /// No server entitlement yet: loading, or the read failed (offline / server). Never offers Subscribe.
    @ViewBuilder private var entitlementUnavailableSection: some View {
        Section {
            if billing.entitlementLoadFailed && billing.phase != .loading {
                Text("Couldn't load your subscription. Check your connection and try again.")
                Button("Try again") { Task { await billing.refresh() } }
                    .foregroundStyle(StoryTheme.gold)
            } else {
                HStack(spacing: 12) {
                    ProgressView()
                    Text("Loading your subscription…")
                }
            }
        }
    }

    private var restoreSection: some View {
        Section {
            Button {
                Task { await billing.restore() }
            } label: {
                HStack {
                    Text("Restore Purchases")
                    Spacer()
                    if billing.phase == .restoring { ProgressView() }
                }
            }
            .disabled(billing.phase != .idle)
        }
    }

    /// Apple requires working Terms of Use and Privacy Policy links on a subscription screen.
    private var legalSection: some View {
        Section {
            Link("Terms of Use", destination: LegalLinks.termsOfUse)
            Link("Privacy Policy", destination: LegalLinks.privacyPolicy(for: L10n.current))
        }
        .foregroundStyle(StoryTheme.gold)
    }

    @ViewBuilder private var noticeSection: some View {
        if let notice = billing.notice {
            Section { Text(message(for: notice)).font(StoryTheme.body(14)) }
        }
    }

    // MARK: helpers
    private func benefitRow(_ symbol: String, _ text: String) -> some View {
        Label { Text(text).fixedSize(horizontal: false, vertical: true) } icon: {
            Image(systemName: symbol).foregroundStyle(StoryTheme.gold)
        }
    }

    /// "$9.99/month", using StoreKit's localized price and the product's real period.
    private func priceLine(_ price: String) -> String {
        guard let p = billing.product?.subscription?.subscriptionPeriod else { return price }
        let unit: String
        switch p.unit {
        case .day: unit = L10n.t("day")
        case .week: unit = L10n.t("week")
        case .month: unit = L10n.t("month")
        case .year: unit = L10n.t("year")
        @unknown default: unit = ""
        }
        return p.value == 1 ? "\(price)/\(unit)" : "\(price) / \(p.value) \(unit)"
    }

    private func message(for notice: BillingStore.Notice) -> String {
        switch notice {
        case .purchased: return L10n.t("You're subscribed to YoTale Plus. Thank you.")
        case .pending: return L10n.t("Your purchase is waiting for approval. It will activate automatically.")
        case .restored: return L10n.t("Your purchase was restored.")
        case .nothingToRestore: return L10n.t("No purchase to restore for this Apple ID.")
        case .needsSignIn: return L10n.t("Sign in to your YoTale account to finish this.")
        case .unavailable: return L10n.t("Couldn't reach the App Store or YoTale. Your purchase is safe. Please try again in a moment.")
        case .failed: return L10n.t("The purchase couldn't be completed.")
        case .notActive: return L10n.t("Your purchase was received, but your subscription is not active yet. If you were charged, tap Restore Purchases or try again in a moment.")
        case .ownedByAnotherAccount: return L10n.t("This Apple ID's YoTale Plus subscription belongs to a different YoTale account. Sign in to that account to use it, or subscribe with a different Apple ID.")
        }
    }
}
