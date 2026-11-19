import SwiftUI

/// Billing V1 / B3: "N video credits left" at the creation entry points (Create, Revise). Shown ONLY when the server enforces
/// limits and the account has finite allowances, so it stays invisible for grandfathered beta users and while billing is off.
/// The number is the server's `remaining`; the app never counts credits itself. Tapping opens YoTale Plus.
struct VideoCreditsLine: View {
    @Environment(BillingStore.self) private var billing
    @State private var showPlus = false

    var body: some View {
        Group {
            if billing.entitlement?.showsAllowances == true, let v = billing.entitlement?.videos {
                Button { showPlus = true } label: {
                    Label {
                        Text(v.remaining == 1 ? L10n.t("1 video credit left") : L10n.t("\(v.remaining) video credits left"))
                    } icon: {
                        Image(systemName: "film.stack")
                    }
                    .font(StoryTheme.body(13, .medium))
                    .foregroundStyle(v.remaining == 0 ? StoryTheme.danger : StoryTheme.gold)
                }
                .buttonStyle(.plain)
                .sheet(isPresented: $showPlus) { PlusSubscriptionView() }
            }
        }
        .task { await billing.refresh() }
    }
}
