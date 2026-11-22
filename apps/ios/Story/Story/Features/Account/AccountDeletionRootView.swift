import SwiftUI

/// Root switch (design 5.7): while a deletion's outcome is being checked, after it is accepted, or when the
/// cold-start wipe failed, the app shows ONLY these screens, so no new content or sign-in can happen before the
/// local wipe has finished.
struct AccountDeletionRootView<Content: View>: View {
    @Environment(AuthStore.self) private var auth
    @Environment(BillingStore.self) private var billing
    @Environment(\.scenePhase) private var scenePhase
    @State private var coordinator = AccountDeletionCoordinator.shared
    @ViewBuilder var content: () -> Content

    var body: some View {
        Group {
            if coordinator.blocksApp {
                AccountDeletionLockView(coordinator: coordinator)
            } else {
                content()
            }
        }
        .task { await coordinator.resume() }
        .task(id: auth.state) {
            if auth.state == .signedIn { await coordinator.probeOtherDevice(auth: auth) }
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            Task {
                await coordinator.onForeground()
                await coordinator.probeOtherDevice(auth: auth)
            }
        }
        .alert(L10n.t("Your YoTale account was deleted"), isPresented: $coordinator.showCompletion) {
            Button(L10n.t("OK")) { coordinator.acknowledgeCompletion() }
        } message: {
            Text(completionMessage)
        }
        .alert(L10n.t("This account was deleted from another device"), isPresented: $coordinator.otherDevicePrompt) {
            Button(L10n.t("Remove From This iPhone"), role: .destructive) {
                coordinator.otherDeviceRemove(auth: auth, billing: billing)
            }
            Button(L10n.t("Keep on This iPhone"), role: .cancel) {
                coordinator.otherDeviceKeep(auth: auth, billing: billing)
            }
        } message: {
            Text(L10n.t("You've been signed out. Remove this account's Stories, Moments and videos from this iPhone too?"))
        }
    }

    private var completionMessage: String {
        var parts: [String] = []
        if let at = coordinator.completedAt {
            parts.append(L10n.t("Your account and its cloud data were deleted on \(at.formatted(date: .abbreviated, time: .shortened))."))
        } else {
            parts.append(L10n.t("Your account and its cloud data were deleted."))
        }
        if coordinator.showAppleRevocationStep { parts.append(AccountDeletionLockView.appleStep) }
        return parts.joined(separator: "\n\n")
    }
}

struct AccountDeletionLockView: View {
    let coordinator: AccountDeletionCoordinator

    static var appleStep: String {
        L10n.t("You signed in with Apple. To also remove YoTale from your Apple Account, open Settings, tap your name, then Sign-In & Security, Sign in with Apple, YoTale, and choose Stop Using.")
    }

    var body: some View {
        VStack(spacing: 18) {
            Spacer()
            switch coordinator.phase {
            case .checking:
                ProgressView().controlSize(.large).tint(StoryTheme.gold)
                title(L10n.t("Checking your deletion request"))
                text(L10n.t("We couldn't confirm whether your request reached us. Keep YoTale open with a connection; this finishes on its own."))
            case .notCommitted:
                title(L10n.t("Your account wasn't deleted"))
                text(L10n.t("The request didn't reach us, so nothing was deleted. You can try again from the account menu."))
                Button(L10n.t("OK")) { coordinator.acknowledgeNotCommitted() }.buttonStyle(.borderedProminent)
            case .locked:
                Image(systemName: "checkmark.shield").font(.system(size: 44)).foregroundStyle(StoryTheme.gold)
                title(L10n.t("Your account is being deleted"))
                text(L10n.t("Close YoTale to finish removing your data from this iPhone. It's removed the next time YoTale opens."))
                text(statusLine)
                if coordinator.showAppleRevocationStep { text(Self.appleStep) }
            case .wipeFailed(let why):
                Image(systemName: "exclamationmark.triangle").font(.system(size: 40)).foregroundStyle(.orange)
                title(L10n.t("Couldn't finish removing data from this iPhone"))
                text(L10n.t("Nothing new is saved until this finishes. Try again, or close and reopen YoTale."))
                Text(verbatim: why).font(.caption2).foregroundStyle(StoryTheme.cream.opacity(0.35))
                Button(L10n.t("Try Again")) { coordinator.retryWipe() }.buttonStyle(.borderedProminent)
            case .none:
                EmptyView()
            }
            Spacer()
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .storyBackground()
        .tint(StoryTheme.gold)
        .task(id: coordinator.phase) {
            if coordinator.phase == .locked { await coordinator.refreshStatusNow() }
        }
    }

    private var statusLine: String {
        switch coordinator.serverStatus {
        case .completed: return L10n.t("Status: your account and its cloud data are deleted.")
        case .inProgress: return L10n.t("Status: deleting. This usually finishes within two hours.")
        default: return L10n.t("Status: request received. This usually finishes within two hours.")
        }
    }

    private func title(_ s: String) -> some View {
        Text(s).font(StoryTheme.display(22)).foregroundStyle(StoryTheme.cream).multilineTextAlignment(.center)
    }

    private func text(_ s: String) -> some View {
        Text(s).font(StoryTheme.body(14)).foregroundStyle(StoryTheme.cream.opacity(0.75))
            .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
    }
}
