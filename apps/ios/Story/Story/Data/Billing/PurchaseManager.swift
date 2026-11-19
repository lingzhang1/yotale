import Foundation
import StoreKit

/// Billing V1 / B3: StoreKit 2 wrapper. It loads the Plus product (the LOCALIZED price comes only from Apple), runs a purchase
/// that carries this account's `appAccountToken`, and hands Apple's signed transaction (JWS) to a handler. It never decides
/// entitlement: the handler (BillingStore) posts the JWS to the server, and a transaction is `finish()`ed only after the server
/// accepted it, so a purchase made while offline or while the server is down is re-delivered by StoreKit and cannot be lost.
enum PurchaseOutcome: Equatable {
    case purchased(jws: String)
    case pending                        // Ask to Buy / SCA: no transaction yet; Transaction.updates delivers it later
    case cancelled
    case failed
}

@MainActor
final class PurchaseManager {
    /// Permanent product id created in App Store Connect (subscription group 22593497).
    static let plusProductID = "com.lingzhang.story.plus.monthly"

    private var updatesTask: Task<Void, Never>?
    private var pendingFinish: [UInt64: Transaction] = [:]

    func loadPlus() async -> Product? {
        do { return try await Product.products(for: [Self.plusProductID]).first }
        catch { return nil }
    }

    /// Start a purchase for this YoTale account. `accountToken` MUST be the server-issued appAccountToken (UUID).
    func purchase(_ product: Product, accountToken: UUID) async -> PurchaseOutcome {
        do {
            let result = try await product.purchase(options: [.appAccountToken(accountToken)])
            switch result {
            case .success(let verification):
                guard case .verified(let txn) = verification else { return .failed }   // unverified on-device: never trust
                pendingFinish[txn.id] = txn
                return .purchased(jws: verification.jwsRepresentation)
            case .pending: return .pending
            case .userCancelled: return .cancelled
            @unknown default: return .failed
            }
        } catch {
            return .failed
        }
    }

    /// Call after the SERVER accepted the transaction(s) from `purchase` / `restoreJWS`. Safe to call twice.
    func finishPending() async {
        let batch = pendingFinish
        pendingFinish.removeAll()
        for (_, txn) in batch { await txn.finish() }
    }

    /// Restore Purchases: ask the App Store to sync, then return the JWS of every current Plus entitlement.
    func restoreJWS() async -> [String] {
        try? await AppStore.sync()
        var out: [String] = []
        for await result in Transaction.currentEntitlements {
            guard case .verified(let txn) = result, txn.productID == Self.plusProductID else { continue }
            pendingFinish[txn.id] = txn
            out.append(result.jwsRepresentation)
        }
        return out
    }

    /// Listen for transactions that arrive outside a purchase call (renewals, Ask to Buy approval, purchases made on another
    /// device, anything left unfinished by an earlier launch). `handler` returns true when the server accepted the transaction.
    func startListening(handler: @escaping @MainActor (String) async -> Bool) {
        updatesTask?.cancel()
        updatesTask = Task {
            for await result in Transaction.updates {
                guard case .verified(let txn) = result, txn.productID == Self.plusProductID else { continue }
                let accepted = await handler(result.jwsRepresentation)
                if accepted { await txn.finish() }
            }
        }
    }

    func stopListening() {
        updatesTask?.cancel()
        updatesTask = nil
    }
}
