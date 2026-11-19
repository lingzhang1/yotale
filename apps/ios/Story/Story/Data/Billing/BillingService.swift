import Foundation

/// Billing V1 / B3: thin client for the two authenticated billing endpoints. The server decides everything; this only
/// fetches the entitlement and forwards Apple-signed transactions (a JWS the server verifies itself). No plan, price,
/// credit count or expiry is ever sent.
enum BillingServiceError: Error, Equatable {
    case notSignedIn                    // 401: the app has no valid session
    case transport                      // network: safe to retry
    case unavailable                    // 503: billing store / Apple verification not configured; retry later
    case rejected(code: String)         // 4xx the server will not accept (invalid signature, token mismatch, bound elsewhere...)
    case badStatus(Int)
    case decoding
}

struct BillingService {
    var baseURL: URL = StoryBackend.baseURL
    var session: URLSession = .shared

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    func entitlement() async throws -> BillingEntitlement {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/billing/entitlement"))
        StoryBackend.authorize(&req)
        req.httpMethod = "GET"
        let (data, http) = try await send(req)
        guard http.statusCode == 200 else { throw Self.map(http.statusCode, data) }
        do { return try Self.decoder().decode(BillingEntitlement.self, from: data) }
        catch { throw BillingServiceError.decoding }
    }

    /// Forward a StoreKit 2 transaction (`VerificationResult.jwsRepresentation`). The server verifies Apple's signature, the
    /// bundle/environment/product, and that the transaction's appAccountToken is THIS account's. Returns the new entitlement.
    func submit(signedTransaction jws: String) async throws -> BillingEntitlement? {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/billing/transactions"))
        StoryBackend.authorize(&req)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["signed_transaction": jws])
        let (data, http) = try await send(req)
        guard http.statusCode == 200 else { throw Self.map(http.statusCode, data) }
        struct R: Decodable { let entitlement: BillingEntitlement? }
        return (try? Self.decoder().decode(R.self, from: data))?.entitlement
    }

    private func send(_ req: URLRequest) async throws -> (Data, HTTPURLResponse) {
        do {
            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse else { throw BillingServiceError.badStatus(-1) }
            return (data, http)
        } catch let e as BillingServiceError {
            throw e
        } catch {
            throw BillingServiceError.transport
        }
    }

    static func map(_ status: Int, _ data: Data) -> BillingServiceError {
        switch status {
        case 401: return .notSignedIn
        case 503: return .unavailable
        case 403, 409, 422:
            struct E: Decodable { let error: String? }
            return .rejected(code: (try? JSONDecoder().decode(E.self, from: data))?.error ?? "rejected")
        default: return .badStatus(status)
        }
    }
}
