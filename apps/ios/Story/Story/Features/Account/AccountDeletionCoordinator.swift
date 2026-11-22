import Foundation
import SwiftUI

/// Where the in-app "Delete Account" entry is offered: the environments whose backend has the deletion routes
/// (design 7.5). Development only until the beta rollout is approved; adding `.beta` here is part of that change.
/// The lock screen, wipe and other-device handling run in every build, so a build never strands a request.
enum AccountDeletionAvailability {
    static let environments: Set<StoryEnvironmentKind> = [.development]
    static var offered: Bool { environments.contains(StoryEnvironment.current.kind) }
}

/// The app-wide account-deletion state machine on the device (design 5.7). Owns the acceptance boundary, the
/// lost-response recovery, the lock screen, the cold-start wipe result, completion confirmation and the
/// other-device prompt.
@MainActor
@Observable
final class AccountDeletionCoordinator {
    enum Phase: Equatable {
        case none
        /// The POST outcome is unknown (503, timeout, app killed). Blocking: no new content until resolved.
        case checking
        /// The server said the request was never committed. Nothing was deleted.
        case notCommitted
        /// Accepted. The rest of this process shows only the lock screen; the wipe runs at the next launch.
        case locked
        /// The cold-start wipe failed. The app runs on an in-memory store; disk untouched until a retry works.
        case wipeFailed(String)
    }

    private(set) var phase: Phase = .none
    /// Server state shown on the lock screen ("accepted", "in progress", "deleted").
    private(set) var serverStatus: AccountDeletionService.Status?
    /// Set once when the server reports completion after the wipe; the root view shows it once.
    var showCompletion = false
    private(set) var completedAt: Date?
    /// Set when another device's deletion is confirmed by an authenticated 403 code (decision 8.19: ask).
    var otherDevicePrompt = false
    /// Shown on the lock and completion screens for an Apple-linked account (TN3194 fallback, design 6).
    private(set) var showAppleRevocationStep = false

    @ObservationIgnored var service = AccountDeletionService()
    @ObservationIgnored private var resolving = false
    @ObservationIgnored private var polling = false

    static let shared = AccountDeletionCoordinator()

    var blocksApp: Bool {
        switch phase {
        case .none: return false
        default: return true
        }
    }

    // ---- launch ----------------------------------------------------------------------------------------------
    /// Called from StoryApp.init with the result of the cold-start wipe, before any view exists.
    func bootstrap(wipe: LocalWipe.Result) {
        let pending = AccountDeletionFiles.pendingRequest()
        showAppleRevocationStep = pending?.federatedProvider == StoryAuthConfig.appleProviderName
        switch wipe {
        case .failed(let why):
            phase = .wipeFailed(why)
        case .wiped, .nothingPending:
            if let p = pending, p.stage == .submitting { phase = .checking }
        }
    }

    /// Called from the root view's task: resolves an unknown outcome, or checks for completion after the wipe.
    func resume() async {
        if phase == .checking { await resolveUnknownOutcome() }
        else if phase == .none, let p = AccountDeletionFiles.pendingRequest(), p.stage == .accepted {
            await checkCompletion(p)
        }
    }

    // ---- submission (design 5.3 acceptance boundary) -----------------------------------------------------
    enum SubmitResult: Equatable { case locked, checking, reauthRequired, failed(String) }

    /// Persist request.json, POST, and establish acceptance. `freshAccessToken` comes from the re-auth step.
    func submit(freshAccessToken: String, federatedProvider: String?, auth: AuthStore, billing: BillingStore) async -> SubmitResult {
        let pending = AccountDeletionFiles.PendingRequest(
            requestId: UUID().uuidString.lowercased(), receiptSecret: AccountDeletionFiles.newReceiptSecret(),
            createdAt: .now, stage: .submitting, federatedProvider: federatedProvider)
        do { try AccountDeletionFiles.savePendingRequest(pending) }
        catch { return .failed(L10n.t("Couldn't prepare the request on this iPhone. Please try again.")) }
        showAppleRevocationStep = federatedProvider == StoryAuthConfig.appleProviderName

        switch await service.submit(accessToken: freshAccessToken, requestId: pending.requestId,
                                    receiptSecret: pending.receiptSecret) {
        case .accepted, .alreadyRequested:
            return establishAcceptance(pending, auth: auth, billing: billing) ? .locked
                : .failed(L10n.t("Your account deletion started, but this iPhone couldn't save that. Reopen YoTale."))
        case .reauthRequired:
            AccountDeletionFiles.clearPendingRequest()
            return .reauthRequired
        case .rejected(let code):
            AccountDeletionFiles.clearPendingRequest()
            return .failed(Self.message(forRejection: code))
        case .unknown:
            phase = .checking
            Task { await resolveUnknownOutcome(auth: auth, billing: billing) }
            return .checking
        }
    }

    /// The only place `wipe-intent` is written for this device's own request.
    @discardableResult
    private func establishAcceptance(_ p: AccountDeletionFiles.PendingRequest, auth: AuthStore?,
                                     billing: BillingStore?) -> Bool {
        var accepted = p
        accepted.stage = .accepted
        do {
            try AccountDeletionFiles.saveWipeIntent(.init(requestId: p.requestId, createdAt: .now))
            try AccountDeletionFiles.savePendingRequest(accepted)
        } catch {
            return false
        }
        phase = .locked
        billing?.reset()
        auth?.signOut()          // stops every cloud writer (they need a token); local content stays until the wipe
        startPolling()
        return true
    }

    /// Lost 202, 503, timeout or app kill: ask the public status route with the receipt (no token needed).
    func resolveUnknownOutcome(auth: AuthStore? = nil, billing: BillingStore? = nil) async {
        guard !resolving, let p = AccountDeletionFiles.pendingRequest() else {
            if AccountDeletionFiles.pendingRequest() == nil, phase == .checking { phase = .none }
            return
        }
        resolving = true
        defer { resolving = false }
        var delay: UInt64 = 2
        while phase == .checking {
            switch await service.status(requestId: p.requestId, receiptSecret: p.receiptSecret) {
            case .accepted, .inProgress, .completed:
                establishAcceptance(p, auth: auth ?? AuthStore.shared, billing: billing)
                return
            case .notFound:
                AccountDeletionFiles.clearPendingRequest()
                phase = .notCommitted
                return
            case .unreachable:
                try? await Task.sleep(nanoseconds: delay * 1_000_000_000)
                delay = min(delay * 2, 60)
            }
        }
    }

    func acknowledgeNotCommitted() { if phase == .notCommitted { phase = .none } }

    // ---- lock screen polling and completion ------------------------------------------------------------------
    private func startPolling() {
        guard !polling else { return }
        polling = true
        Task {
            defer { polling = false }
            while phase == .locked, let p = AccountDeletionFiles.pendingRequest() {
                let s = await service.status(requestId: p.requestId, receiptSecret: p.receiptSecret)
                if s != .unreachable { serverStatus = s }
                try? await Task.sleep(nanoseconds: 30 * 1_000_000_000)
            }
        }
    }

    func refreshStatusNow() async {
        guard let p = AccountDeletionFiles.pendingRequest() else { return }
        let s = await service.status(requestId: p.requestId, receiptSecret: p.receiptSecret)
        if s != .unreachable { serverStatus = s }
    }

    /// After the wipe (normal app running): show "deleted" once when the server completes, then forget the request.
    private func checkCompletion(_ p: AccountDeletionFiles.PendingRequest) async {
        switch await service.status(requestId: p.requestId, receiptSecret: p.receiptSecret) {
        case .completed(let at):
            completedAt = at
            showCompletion = true
        case .notFound:
            AccountDeletionFiles.clearPendingRequest()   // nothing to confirm (should not happen once accepted)
        default:
            break                                       // still running or offline: ask again next foreground
        }
    }

    func acknowledgeCompletion() {
        showCompletion = false
        AccountDeletionFiles.clearPendingRequest()
        showAppleRevocationStep = false
    }

    /// Foreground hook: completion check after the wipe; no-op otherwise.
    func onForeground() async {
        if phase == .none, !showCompletion, let p = AccountDeletionFiles.pendingRequest(), p.stage == .accepted {
            await checkCompletion(p)
        }
    }

    // ---- wipe failure retry (in-memory container, so no store file is open) ---------------------------------
    func retryWipe() {
        switch LocalWipe.runIfPending() {
        case .failed(let why): phase = .wipeFailed(why)
        case .wiped, .nothingPending: phase = .locked   // done; the user closes and reopens to get a fresh store
        }
    }

    // ---- other devices (decision 8.19: ask) --------------------------------------------------------------
    /// Signed-in foreground/launch probe. Only an authenticated 403 with the deletion code triggers the prompt.
    func probeOtherDevice(auth: AuthStore) async {
        guard phase == .none, auth.isSignedIn, AccountDeletionFiles.pendingRequest() == nil,
              let token = await auth.validAccessToken() else { return }
        switch await service.probe(accessToken: token) {
        case .deletionInProgress, .deleted: otherDevicePrompt = true
        case .active, .unknown: break
        }
    }

    /// "Remove from this iPhone": same lifecycle as the requesting device, from the wipe-intent step.
    func otherDeviceRemove(auth: AuthStore, billing: BillingStore) {
        otherDevicePrompt = false
        do { try AccountDeletionFiles.saveWipeIntent(.init(requestId: nil, createdAt: .now)) }
        catch { auth.signOut(); return }
        phase = .locked
        billing.reset()
        auth.signOut()
    }

    /// "Keep on this iPhone": sign out only, as Sign Out does today.
    func otherDeviceKeep(auth: AuthStore, billing: BillingStore) {
        otherDevicePrompt = false
        billing.reset()
        auth.signOut()
    }

    static func message(forRejection code: String) -> String {
        switch code {
        case "deletion_unavailable": return L10n.t("Account deletion isn't available on this server yet. Nothing was deleted.")
        case "account_not_active": return L10n.t("This account can't be deleted from the app. Contact privacy@yotale.ai.")
        case "deletion_already_requested": return L10n.t("Deletion was already requested for this account.")
        default: return L10n.t("Couldn't request deletion. Nothing was deleted. Please try again.")
        }
    }
}
