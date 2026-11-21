import Foundation
import Observation
import StoreKit

/// Billing V1 / B3 (V2 fixes): the app's view of the server's entitlement plus the StoreKit purchase flow.
///
/// Rules this type keeps:
///  • Server-authoritative: `entitlement` is only ever a decoded `GET /v1/billing/entitlement` response. After the server accepts a
///    transaction the app re-reads that endpoint; it never trusts (or depends on decoding) the purchase response.
///  • A purchase is sent to the server as Apple's signed JWS; the StoreKit transaction is `finish()`ed ONLY after the server accepted it.
///  • A network failure is never "signed out": only a 401 that survives one token refresh is.
///  • One submission per transaction at a time (the listener, the purchase call and recovery can all see the same transaction).
///  • No SwiftData: billing state is not persisted on the device (a reinstall or second device just asks the server).
@MainActor
@Observable
final class BillingStore {
    enum Phase: Equatable { case idle, loading, purchasing, restoring }

    enum Notice: Equatable {
        case purchased
        case pending            // Ask to Buy / SCA approval outstanding
        case restored
        case nothingToRestore
        case needsSignIn
        case unavailable        // server or App Store not reachable / not configured; try again later
        case failed
    }

    private(set) var entitlement: BillingEntitlement?
    private(set) var product: Product?
    private(set) var phase: Phase = .idle
    /// True while a verified Apple purchase is waiting for the server (posted and in flight, or its post failed with a RETRYABLE
    /// error: network, 503, session). The screen then shows "Confirming your subscription" instead of Subscribe, so a paying user is
    /// never asked to buy again. Cleared when the server confirms Plus or REJECTS the transaction (e.g. another account's purchase).
    private(set) var verifying = false
    var notice: Notice?

    @ObservationIgnored private let service: BillingService
    @ObservationIgnored private let purchases = PurchaseManager()
    @ObservationIgnored private var started = false
    @ObservationIgnored private var inFlight = Set<String>()
    @ObservationIgnored private var recovering = false

    init(service: BillingService = BillingService()) {
        self.service = service
    }

    // MARK: derived (display only)
    var isPlus: Bool { entitlement?.isPlus == true }
    /// The paywall and credit chips only make sense when an offer exists; credit counters only when the server enforces them.
    var offer: BillingOfferPlan? { entitlement?.offer?.plus }
    var localizedPrice: String? { product?.displayPrice }

    // MARK: lifecycle
    /// Idempotent. Begins listening for transactions (renewals, Ask to Buy approvals, a purchase made on another device).
    func start() {
        guard !started else { return }
        started = true
        purchases.startListening { [weak self] jws in
            guard let self else { return false }
            return await self.forward(jws: jws)
        }
        Task { await self.loadProduct() }
    }

    func stop() {
        purchases.stopListening()
        started = false
    }

    func refresh() async {
        guard phase == .idle else { return }
        phase = .loading
        defer { phase = .idle }
        await reloadEntitlement()
    }

    /// Read the server's entitlement directly (works inside a purchase/restore phase, unlike `refresh()`).
    private func reloadEntitlement() async {
        do {
            let e = try await service.entitlement()
            entitlement = e
            if e.isPlus { verifying = false; clearFailureNotice() }
        } catch BillingServiceError.notSignedIn {
            entitlement = nil
        } catch {
            // Keep whatever we last knew; the server stays the authority and the next refresh corrects it.
        }
    }

    /// Forget account-bound state (sign out / account switch). A different account must never see the previous entitlement.
    func reset() {
        entitlement = nil
        notice = nil
        verifying = false
    }

    /// Billing V2: on sign-in and on foreground, post any Plus transaction StoreKit still holds (a purchase whose earlier post failed
    /// with a 401 or a network error), then re-read the entitlement. Safe to call often: the server is idempotent per transaction.
    func recoverPendingTransactions() async {
        guard !recovering, phase == .idle else { return }
        recovering = true
        defer { recovering = false }
        await reloadEntitlement()
        let notice0 = notice
        // Current entitlements are only replayed while the server does not show Plus (a confirmed subscriber is not re-posted on
        // every foreground); unfinished transactions are always replayed.
        for (id, jws) in await purchases.recoverableJWS(includeCurrent: !isPlus) {
            if await forward(jws: jws, reload: false) { await purchases.finish(id: id) }
        }
        if notice == .failed { notice = notice0 }    // a background replay of another account's purchase is not this screen's error
        await reloadEntitlement()
    }

    private func loadProduct() async {
        if product == nil { product = await purchases.loadPlus() }
    }

    private func clearFailureNotice() {
        if let n = notice, n == .needsSignIn || n == .unavailable || n == .failed { notice = nil }
    }

    // MARK: purchase / restore
    func purchasePlus() async {
        guard phase == .idle else { return }
        notice = nil
        await loadProduct()
        guard let product else { notice = .unavailable; return }
        phase = .purchasing
        defer { phase = .idle }

        // The token binds the purchase to THIS YoTale account on the server. Always take it from the server, never invent one.
        if entitlement?.appleAppAccountToken == nil {
            do { entitlement = try await service.entitlement() }
            catch BillingServiceError.notSignedIn { notice = .needsSignIn; return }
            catch { notice = .unavailable; return }
        }
        guard let tokenString = entitlement?.appleAppAccountToken, let token = UUID(uuidString: tokenString) else {
            notice = .unavailable
            return
        }

        switch await purchases.purchase(product, accountToken: token) {
        case .purchased(let jws):
            verifying = true
            if await forward(jws: jws) {
                await purchases.finishPending()
                notice = .purchased
            } else if notice == nil {
                notice = .unavailable      // not finished: StoreKit re-delivers it and recovery re-posts it, so it is not lost
            }
        case .pending: notice = .pending
        case .cancelled: break
        case .failed: notice = .failed
        }
    }

    func restore() async {
        guard phase == .idle else { return }
        notice = nil
        phase = .restoring
        defer { phase = .idle }
        let all = await purchases.restoreJWS()
        guard !all.isEmpty else {
            await reloadEntitlement()
            notice = isPlus ? .restored : .nothingToRestore
            return
        }
        var accepted = false
        for jws in all {
            if await forward(jws: jws, reload: false) { accepted = true }
        }
        if accepted { await purchases.finishPending() }
        await reloadEntitlement()
        if isPlus || accepted { notice = .restored }
        else if notice == nil { notice = .nothingToRestore }
    }

    /// Post one signed transaction. True = the server accepted it (the caller may then finish the StoreKit transaction).
    /// A rejection is NOT finished and NOT retried in a loop: a foreign-account or invalid transaction would only be rejected again.
    /// The same JWS is never posted twice concurrently (listener + purchase + recovery can all see one transaction).
    private func forward(jws: String, reload: Bool = true) async -> Bool {
        guard inFlight.insert(jws).inserted else { return false }
        defer { inFlight.remove(jws) }
        do {
            _ = try await service.submit(signedTransaction: jws)
            clearFailureNotice()
            if reload { await reloadEntitlement() }
            return true
        } catch BillingServiceError.notSignedIn {
            notice = .needsSignIn
            verifying = true
            return false
        } catch BillingServiceError.rejected {
            notice = .failed
            verifying = false
            return false
        } catch {
            notice = .unavailable
            verifying = true
            return false
        }
    }
}
