import Foundation

/// Billing V1 / B3: thin client for the two authenticated billing endpoints. The server decides everything; this only
/// fetches the entitlement and forwards Apple-signed transactions (a JWS the server verifies itself). No plan, price,
/// credit count or expiry is ever sent.
enum BillingServiceError: Error, Equatable {
    case notSignedIn                    // 401 after one refresh-and-retry, or no session at all
    case transport                      // network (including "could not reach the auth server"): safe to retry, NOT signed out
    case unavailable                    // 503: billing store / Apple verification not configured; retry later
    case rejected(code: String)         // 4xx the server will not accept (invalid signature, token mismatch, bound elsewhere...)
    case badStatus(Int)
    case decoding
}

struct BillingService {
    var baseURL: URL = StoryBackend.baseURL
    var session: URLSession = .shared
    /// Billing V2: a REFRESHING token source (the cached seam token can be expired). `forceRefresh` is used once after a 401.
    /// `.offline` (auth server unreachable) is a transport error, never "signed out".
    var token: @MainActor (_ forceRefresh: Bool) async -> AccessTokenFetch = { force in
        await AuthStore.shared?.fetchAccessToken(forceRefresh: force) ?? .signedOut
    }

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    func entitlement() async throws -> BillingEntitlement {
        let data = try await call("v1/billing/entitlement", method: "GET", body: nil)
        do { return try Self.decoder().decode(BillingEntitlement.self, from: data) }
        catch { throw BillingServiceError.decoding }
    }

    /// Forward a StoreKit 2 transaction (`VerificationResult.jwsRepresentation`). The server verifies Apple's signature, the
    /// bundle/environment/product, and that the transaction's appAccountToken is THIS account's. Returns the server's result
    /// (`applied` | `not_active`). The caller re-reads `GET /v1/billing/entitlement` for what to display (server-authoritative),
    /// so a purchase response this build cannot decode can never leave the app showing Subscribe to a paying user.
    func submit(signedTransaction jws: String) async throws -> String {
        let body = try? JSONSerialization.data(withJSONObject: ["signed_transaction": jws])
        let data = try await call("v1/billing/transactions", method: "POST", body: body)
        struct R: Decodable { let result: String? }
        return (try? Self.decoder().decode(R.self, from: data))?.result ?? "applied"   // a 200 IS acceptance; `result` is informational
    }

    /// One authenticated request with ONE refresh-and-retry on 401 (never a loop).
    private func call(_ path: String, method: String, body: Data?) async throws -> Data {
        for attempt in 0..<2 {
            var req = URLRequest(url: baseURL.appendingPathComponent(path))
            req.httpMethod = method
            if let body {
                req.httpBody = body
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            }
            switch await token(attempt > 0) {
            case .token(let t): req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
            case .offline: throw BillingServiceError.transport
            case .signedOut:
                if attempt > 0 { throw BillingServiceError.notSignedIn }
                // dev optional-auth: send without a bearer; prod answers 401 -> notSignedIn below
            }
            let (data, http) = try await send(req)
            if http.statusCode == 200 { return data }
            if http.statusCode == 401 && attempt == 0 { continue }
            throw Self.map(http.statusCode, data)
        }
        throw BillingServiceError.notSignedIn
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
