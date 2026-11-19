import SwiftUI
import StoreKit

/// Billing V1 / B3: the one billing screen. It is the paywall for a Free starter and the subscription status screen for a Plus
/// subscriber. Everything shown comes from the server (allowances, status, renewal date) or from StoreKit (the localized price);
/// no price or number is hard-coded here.
struct PlusSubscriptionView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AuthStore.self) private var auth
    @Environment(BillingStore.self) private var billing

    /// Why the screen opened, so a denial can explain itself. Nil when opened from the account menu.
    var denial: BillingDenial?

    @State private var showManage = false

    var body: some View {
        NavigationStack {
            Form {
                if let denial {
                    Section { Text(denial.message).font(StoryTheme.body(15)) }
                }
                if !auth.isSignedIn {
                    Section { Text("Sign in to subscribe or to restore a purchase.") }
                } else if billing.isPlus {
                    activeSections
                } else {
                    offerSections
                }
                if auth.isSignedIn { restoreSection }
                noticeSection
            }
            .navigationTitle("YoTale Plus")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task {
                billing.start()
                await billing.refresh()
            }
            .manageSubscriptionsSheet(isPresented: $showManage)
        }
    }

    // MARK: Free starter -> offer
    @ViewBuilder private var offerSections: some View {
        Section {
            if let plus = billing.offer {
                benefitRow("film.stack", L10n.t("\(plus.videos) videos every month"))
                benefitRow("sparkles", L10n.t("\(plus.moments) new Moments analyzed every month"))
                benefitRow("arrow.triangle.2.circlepath", L10n.t("Create, make another version, or revise: each uses one video"))
                benefitRow("photo.on.rectangle", L10n.t("Footage you already analyzed is free to reuse"))
            }
        } header: {
            Text("What you get")
        } footer: {
            Text("Your videos stay yours if you cancel. Unused credits don't roll over.")
        }

        if billing.entitlement?.showsAllowances == true, let v = billing.entitlement?.videos, let m = billing.entitlement?.moments {
            Section("Your free starter") {
                LabeledContent("Video credits left", value: "\(v.remaining)")
                LabeledContent("New Moments you can analyze", value: "\(m.remaining)")
            }
        }

        Section {
            Button {
                Task { await billing.purchasePlus() }
            } label: {
                HStack {
                    Text("Subscribe").bold()
                    Spacer()
                    if billing.phase == .purchasing { ProgressView() }
                    else if let price = billing.localizedPrice { Text(priceLine(price)) }
                }
            }
            .disabled(billing.phase != .idle || billing.product == nil)
            .foregroundStyle(StoryTheme.gold)
        } footer: {
            Text("Payment is charged to your Apple ID. The subscription renews every month until you cancel it at least 24 hours before the renewal date. Manage or cancel any time in your Apple ID settings.")
        }
    }

    // MARK: Plus -> status
    @ViewBuilder private var activeSections: some View {
        Section {
            LabeledContent("Status", value: billing.entitlement?.isGrace == true
                           ? L10n.t("Payment issue. Update your payment method")
                           : L10n.t("Active"))
            if let end = billing.entitlement?.period?.end {
                LabeledContent("Renews or ends", value: L10nFormat.shortDate(Date(timeIntervalSince1970: TimeInterval(end))))
            }
            if let v = billing.entitlement?.videos, let m = billing.entitlement?.moments {
                LabeledContent("Video credits left", value: "\(v.remaining) / \(v.total)")
                LabeledContent("New Moments you can analyze", value: "\(m.remaining) / \(m.total)")
            }
        } footer: {
            Text("Your credits reset when your subscription renews.")
        }
        Section {
            Button("Manage Subscription") { showManage = true }
                .foregroundStyle(StoryTheme.gold)
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

    @ViewBuilder private var noticeSection: some View {
        if let notice = billing.notice {
            Section { Text(message(for: notice)).font(StoryTheme.body(14)) }
        }
    }

    // MARK: helpers
    private func benefitRow(_ symbol: String, _ text: String) -> some View {
        Label { Text(text) } icon: { Image(systemName: symbol).foregroundStyle(StoryTheme.gold) }
    }

    /// "$9.99 / month", using StoreKit's localized price and the product's real period.
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
        return p.value == 1 ? "\(price) / \(unit)" : "\(price) / \(p.value) \(unit)"
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
        }
    }
}
