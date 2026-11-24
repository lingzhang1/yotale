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

    /// Billing V2 recovery: every verified Plus transaction StoreKit still holds UNFINISHED (a purchase whose server post failed with
    /// a 401, a network error or a 503) plus the current entitlement, so it can be posted again on sign-in and on foreground. The
    /// server is idempotent per original transaction, so a replay is safe. Returned transactions are remembered for `finish(id:)`.
    func recoverableJWS(includeCurrent: Bool) async -> [(id: UInt64, jws: String)] {
        var out: [(id: UInt64, jws: String)] = []
        var seen = Set<UInt64>()
        for await result in Transaction.unfinished {
            guard case .verified(let txn) = result, txn.productID == Self.plusProductID, seen.insert(txn.id).inserted else { continue }
            pendingFinish[txn.id] = txn
            out.append((txn.id, result.jwsRepresentation))
        }
        guard includeCurrent else { return out }
        for await result in Transaction.currentEntitlements {
            guard case .verified(let txn) = result, txn.productID == Self.plusProductID, seen.insert(txn.id).inserted else { continue }
            out.append((txn.id, result.jwsRepresentation))
        }
        return out
    }

    /// The appAccountToken of this Apple ID's ACTIVE Plus subscription, if StoreKit has one (nil = none active, or no token).
    /// A different token than the signed-in account's means the subscription belongs to another YoTale account: a purchase
    /// would only hand back that subscription, which the server correctly refuses (dev 2026-11-22, 403 token mismatch).
    func activePlusAccountToken() async -> UUID? {
        for await result in Transaction.currentEntitlements {
            guard case .verified(let txn) = result, txn.productID == Self.plusProductID, txn.revocationDate == nil else { continue }
            if let exp = txn.expirationDate, exp < Date() { continue }
            return txn.appAccountToken
        }
        return nil
    }

    /// Whether the Plus subscription on this Apple ID will auto-renew (false = canceled but still active until the period end).
    /// Display wording only; nil when StoreKit has no verified status.
    func willAutoRenew(_ product: Product?) async -> Bool? {
        guard let statuses = try? await product?.subscription?.status else { return nil }
        for s in statuses {
            if case .verified(let info) = s.renewalInfo, info.currentProductID == Self.plusProductID { return info.willAutoRenew }
        }
        return nil
    }

    /// Finish one remembered transaction after the server accepted it. No-op for an id that is not pending.
    func finish(id: UInt64) async {
        guard let txn = pendingFinish.removeValue(forKey: id) else { return }
        await txn.finish()
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
