import CryptoKit
import Foundation

/// HTTP client for the account-deletion API (design 5.3; backend D3).
///
///   POST /v1/account/deletion         authenticated, fresh sign-in; 202 accepted / 409 already requested
///   POST /v1/account/deletion/status  PUBLIC; the receipt secret is the credential (works after Cognito disables
///                                     the user); 404 for an unknown id and a wrong secret alike
///   GET  /v1/me                       used as the account-status probe on other devices: an AUTHENTICATED 403
///                                     with error account_deletion_in_progress / account_deleted is the only
///                                     signal that counts as confirmed deletion (a generic 401/403 never does)
struct AccountDeletionService {
    var baseURL: URL = StoryBackend.baseURL
    var session: URLSession = StoryBackend.longSession

    enum SubmitOutcome: Equatable {
        case accepted                   // 202: acceptance established
        case alreadyRequested           // 409: another request for this account exists (also acceptance)
        case reauthRequired             // 401: no fresh sign-in; nothing was written
        case rejected(String)           // 400/403/422/429 or 503 deletion_unavailable: nothing was written
        case unknown                    // 503 outcome unknown, timeout, lost connection: ask the status route
    }

    enum Status: Equatable {
        case accepted, inProgress
        case completed(Date?)
        case notFound                   // definitive: the request was never committed (or the secret is wrong)
        case unreachable                // offline / server error: try again later
    }

    enum ProbeResult: Equatable { case active, deletionInProgress, deleted, unknown }

    static func receiptHash(_ secret: String) -> String {
        SHA256.hash(data: Data(secret.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    func submit(accessToken: String, requestId: String, receiptSecret: String) async -> SubmitOutcome {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/account/deletion"))
        req.httpMethod = "POST"
        req.timeoutInterval = 30
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "confirm": "DELETE", "request_id": requestId, "receipt_hash": Self.receiptHash(receiptSecret)])
        guard let (data, http) = await Self.send(req, session) else {
            return .unknown                                     // the request may have reached the server
        }
        let code = Self.errorCode(data)
        switch http.statusCode {
        case 202: return .accepted
        case 409 where code == "deletion_already_requested": return .alreadyRequested
        case 401 where code == "reauth_required": return .reauthRequired
        case 401: return .reauthRequired
        case 503 where code == "deletion_unavailable": return .rejected("deletion_unavailable")
        case 400, 403, 409, 413, 422, 429: return .rejected(code ?? "http_\(http.statusCode)")
        default: return .unknown                                // 5xx and anything else: outcome unknown
        }
    }

    func status(requestId: String, receiptSecret: String) async -> Status {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/account/deletion/status"))
        req.httpMethod = "POST"
        req.timeoutInterval = 20
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: [
            "request_id": requestId, "receipt_secret": receiptSecret])
        guard let (data, http) = await Self.send(req, session) else {
            return .unreachable
        }
        if http.statusCode == 404 { return .notFound }
        guard http.statusCode == 200,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return .unreachable }
        switch obj["state"] as? String {
        case "accepted": return .accepted
        case "in_progress": return .inProgress
        case "completed":
            let ts = (obj["completed_at"] as? NSNumber)?.doubleValue
            return .completed(ts.map { Date(timeIntervalSince1970: $0) })
        default: return .unreachable
        }
    }

    /// Other-device check. Only an authenticated response carrying the deletion error code is a confirmation.
    func probe(accessToken: String) async -> ProbeResult {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/me"))
        req.httpMethod = "GET"
        req.timeoutInterval = 20
        req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        guard let (data, http) = await Self.send(req, session) else {
            return .unknown
        }
        if http.statusCode == 200 { return .active }
        guard http.statusCode == 403 else { return .unknown }
        switch Self.errorCode(data) {
        case "account_deletion_in_progress": return .deletionInProgress
        case "account_deleted": return .deleted
        default: return .unknown
        }
    }

    /// One request; nil on a transport failure or a non-HTTP response.
    private static func send(_ req: URLRequest, _ session: URLSession) async -> (Data, HTTPURLResponse)? {
        do {
            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse else { return nil }
            return (data, http)
        } catch {
            return nil
        }
    }

    static func errorCode(_ data: Data) -> String? {
        (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
    }
}
