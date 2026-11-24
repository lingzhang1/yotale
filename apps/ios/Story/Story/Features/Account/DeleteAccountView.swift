import StoreKit
import SwiftUI

/// "Delete Account" flow (design 5.1): what is deleted, subscription warning, re-authentication bound to THIS
/// account, typed confirmation, submission. Presented as a sheet from the Home account menu.
struct DeleteAccountView: View {
    @Environment(AuthStore.self) private var auth
    @Environment(BillingStore.self) private var billing
    @Environment(\.dismiss) private var dismiss
    private let coordinator = AccountDeletionCoordinator.shared

    private enum Step { case intro, subscription, reauth, confirm }
    @State private var step: Step = .intro
    @State private var hasActiveSubscription = false
    @State private var showManage = false

    // re-auth
    @State private var challenge: OTPChallenge?
    @State private var code = ""
    @State private var freshToken: String?

    // confirm
    @State private var typed = ""
    @State private var busy = false
    @State private var error: String?

    private var hint: AuthStore.AccountHint? { auth.accountHint }
    private var confirmWord: String { L10n.t("DELETE") }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    switch step {
                    case .intro: intro
                    case .subscription: subscription
                    case .reauth: reauth
                    case .confirm: confirm
                    }
                    if let error {
                        Text(error).font(StoryTheme.body(13)).foregroundStyle(.red)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(20)
            }
            .storyBackground()
            .navigationTitle(Text(L10n.t("Delete Account")))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L10n.t("Cancel")) { dismiss() }.disabled(busy)
                }
            }
        }
        .tint(StoryTheme.gold)
        .interactiveDismissDisabled(busy)
        .manageSubscriptionsSheet(isPresented: $showManage)
        .task { hasActiveSubscription = await Self.activeSubscription(billing: billing) }
    }

    // ---- steps ---------------------------------------------------------------------------------------------
    private var intro: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading(L10n.t("Delete your YoTale account?"))
            paragraph(L10n.t("This permanently deletes:"))
            bullets([
                L10n.t("Your account and sign-in"),
                L10n.t("Your Stories, and the Moments and videos backed up to the cloud"),
                L10n.t("The AI analysis we saved for your Moments, and your music favorites"),
                L10n.t("Your Moments, Stories and videos on this iPhone"),
            ])
            paragraph(L10n.t("What stays:"))
            bullets([
                L10n.t("Copies you saved to your Photos library, and iCloud or computer backups of this iPhone"),
                L10n.t("Purchase records that Apple keeps"),
                L10n.t("Frames and text already sent to our AI, image and music providers, which we can't recall"),
                L10n.t("Copies on other iPhones signed in to this account, until you remove them there"),
            ])
            paragraph(L10n.t("Deletion usually finishes within two hours, and a final check runs a day later. It can't be undone."))
            primary(L10n.t("Continue")) { step = hasActiveSubscription ? .subscription : .reauth }
        }
    }

    private var subscription: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading(L10n.t("You have an active YoTale Plus subscription"))
            paragraph(L10n.t("Deleting your account doesn't cancel it. Apple keeps billing you until you cancel in your Apple Account settings. We can't cancel or refund it, and it can't be moved to a new account."))
            primary(L10n.t("Manage Subscription")) { showManage = true }
            secondary(L10n.t("Continue Without Cancelling")) { step = .reauth }
        }
    }

    @ViewBuilder private var reauth: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading(L10n.t("Confirm it's you"))
            if let provider = hint?.federatedProvider {
                paragraph(provider == StoryAuthConfig.appleProviderName
                          ? L10n.t("Sign in with Apple again to confirm.")
                          : L10n.t("Sign in with Google again to confirm."))
                primary(provider == StoryAuthConfig.appleProviderName ? L10n.t("Continue with Apple")
                        : L10n.t("Continue with Google")) { Task { await federatedReauth() } }
            } else if let email = hint?.email {
                if challenge == nil {
                    paragraph(L10n.t("We'll email a code to \(email)."))
                    primary(L10n.t("Send Code")) { Task { await sendCode() } }
                } else {
                    paragraph(L10n.t("Enter the code we sent to \(email)."))
                    TextField("123456", text: $code)
                        .keyboardType(.numberPad).textContentType(.oneTimeCode)
                        .font(StoryTheme.body(18)).padding(12)
                        .background(StoryTheme.cream.opacity(0.06)).clipShape(RoundedRectangle(cornerRadius: 10))
                    primary(L10n.t("Verify")) { Task { await verifyCode() } }
                        .disabled(code.trimmingCharacters(in: .whitespaces).count < 6)
                    secondary(L10n.t("Send a New Code")) { Task { await sendCode() } }
                }
            } else {
                paragraph(L10n.t("You're signed out. Sign in again to delete your account."))
            }
        }
        .disabled(busy)
    }

    private var confirm: some View {
        VStack(alignment: .leading, spacing: 14) {
            heading(L10n.t("Last step"))
            paragraph(L10n.t("Type \(confirmWord) to delete your account. Your local Moments and videos on this iPhone will be deleted too."))
            TextField(confirmWord, text: $typed)
                .textInputAutocapitalization(.characters).autocorrectionDisabled()
                .font(StoryTheme.body(18)).padding(12)
                .background(StoryTheme.cream.opacity(0.06)).clipShape(RoundedRectangle(cornerRadius: 10))
            Button(role: .destructive) { Task { await submit() } } label: {
                HStack {
                    if busy { ProgressView().padding(.trailing, 6) }
                    Text(L10n.t("Delete Account")).frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent).tint(.red)
            .disabled(busy || typed.trimmingCharacters(in: .whitespaces) != confirmWord)
        }
    }

    // ---- actions ---------------------------------------------------------------------------------------------
    private func sendCode() async {
        error = nil; busy = true; defer { busy = false }
        do { challenge = try await auth.reauthStartEmail(); code = "" }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Couldn't send a code.") }
    }

    private func verifyCode() async {
        guard let challenge else { return }
        error = nil; busy = true; defer { busy = false }
        do {
            freshToken = try await auth.reauthVerifyEmail(code: code.trimmingCharacters(in: .whitespaces),
                                                          challenge: challenge)
            step = .confirm
        } catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("That code didn't work.") }
    }

    private func federatedReauth() async {
        error = nil; busy = true; defer { busy = false }
        do { freshToken = try await auth.reauthFederated(); step = .confirm }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Sign-in was cancelled or failed.") }
    }

    private func submit() async {
        guard let token = freshToken else { step = .reauth; return }
        error = nil; busy = true; defer { busy = false }
        switch await coordinator.submit(freshAccessToken: token, federatedProvider: hint?.federatedProvider,
                                        auth: auth, billing: billing) {
        case .locked, .checking:
            dismiss()                       // the root view now shows the lock / checking screen
        case .reauthRequired:
            freshToken = nil; challenge = nil; typed = ""; step = .reauth
            error = L10n.t("Please confirm it's you again. Sign-in has to be within the last 5 minutes.")
        case .failed(let message):
            error = message
        }
    }

    /// StoreKit first (works in every billing mode and during a server outage), then the server's view.
    static func activeSubscription(billing: BillingStore) async -> Bool {
        for await result in Transaction.currentEntitlements {
            if case .verified(let t) = result, t.productType == .autoRenewable, t.revocationDate == nil {
                return true
            }
        }
        return billing.isPlus
    }

    // ---- styling helpers -------------------------------------------------------------------------------------
    private func heading(_ s: String) -> some View {
        Text(s).font(StoryTheme.display(22)).foregroundStyle(StoryTheme.cream)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func paragraph(_ s: String) -> some View {
        Text(s).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream.opacity(0.75))
            .fixedSize(horizontal: false, vertical: true)
    }

    private func bullets(_ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(items, id: \.self) { item in
                HStack(alignment: .top, spacing: 8) {
                    Text(verbatim: "•").foregroundStyle(StoryTheme.gold)
                    Text(item).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream.opacity(0.85))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func primary(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Text(title).frame(maxWidth: .infinity) }
            .buttonStyle(.borderedProminent)
    }

    private func secondary(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Text(title).frame(maxWidth: .infinity) }
            .buttonStyle(.bordered)
    }
}
