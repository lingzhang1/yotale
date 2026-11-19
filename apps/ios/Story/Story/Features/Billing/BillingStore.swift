import Foundation
import Observation
import StoreKit

/// Billing V1 / B3: the app's view of the server's entitlement plus the StoreKit purchase flow.
///
/// Rules this type keeps:
///  • Server-authoritative: `entitlement` is only ever a decoded server response. Nothing here derives plan, allowance or expiry.
///  • A purchase is sent to the server as Apple's signed JWS; the StoreKit transaction is `finish()`ed ONLY after the server accepted it.
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
    var notice: Notice?

    @ObservationIgnored private let service: BillingService
    @ObservationIgnored private let purchases = PurchaseManager()
    @ObservationIgnored private var started = false

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
        do {
            entitlement = try await service.entitlement()
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
    }

    private func loadProduct() async {
        if product == nil { product = await purchases.loadPlus() }
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
            if await forward(jws: jws) { await purchases.finishPending(); notice = .purchased }
            else { notice = .unavailable }      // not finished: StoreKit re-delivers it, so the purchase is not lost
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
        guard !all.isEmpty else { notice = .nothingToRestore; return }
        var accepted = false
        for jws in all {
            if await forward(jws: jws) { accepted = true }
        }
        if accepted { await purchases.finishPending() }
        await refreshAfterRestore()
        notice = (isPlus || accepted) ? .restored : .nothingToRestore
    }

    private func refreshAfterRestore() async {
        if let e = try? await service.entitlement() { entitlement = e }
    }

    /// Post one signed transaction. True = the server accepted it (the caller may then finish the StoreKit transaction).
    /// A rejection is NOT finished and NOT retried in a loop: a foreign-account or invalid transaction would only be rejected again.
    private func forward(jws: String) async -> Bool {
        do {
            if let e = try await service.submit(signedTransaction: jws) { entitlement = e }
            return true
        } catch BillingServiceError.notSignedIn {
            notice = .needsSignIn
            return false
        } catch BillingServiceError.rejected {
            notice = .failed
            return false
        } catch {
            notice = .unavailable
            return false
        }
    }
}
