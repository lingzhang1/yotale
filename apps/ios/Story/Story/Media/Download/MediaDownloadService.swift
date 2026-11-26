import Foundation
import CryptoKit

// R6 — iOS client for cloud media DOWNLOAD & restoration (/v1/media/{id}/download).
// Flow: ask the backend for a short-lived presigned GET + the SERVER-AUTHORITATIVE expectation
// (size_bytes + full-file content_sha256), then DOWNLOAD the object to a temp file with a native download task,
// and verify size + full-file sha256 (read back in chunks) before the caller atomically installs it.
//
// AUTH: every request carries the OWNER account's bearer token, passed EXPLICITLY (same rule as upload —
// never use another account's token). The backend scopes the presign to principal.story_user_id, so an
// object that is not the caller's returns 404 and no cross-account bytes are ever fetched.
//
// NEVER loads a large video into memory (safeguard #2 / req #2): URLSession writes the body to disk and the
// hash is computed from the file 1 MiB at a time.

enum MediaDownloadError: Error, LocalizedError {
    case transport(Error)
    case unauthorized           // 401
    case notFound               // 404 — not the caller's object (or gone)
    case notVerified            // 409 — cloud object not yet cloud_verified
    case badStatus(Int)
    case decoding
    case s3GetFailed(Int)       // presigned GET to S3 failed
    case sizeMismatch(expected: Int, got: Int)
    case checksumMismatch       // downloaded bytes != server-authoritative full-file sha256
    case missingExpectation     // server did not return size/checksum to verify against

    var errorDescription: String? {
        switch self {
        case .transport: return L10n.t("Network error during download.")
        case .unauthorized: return L10n.t("Download session expired.")
        case .notFound: return L10n.t("Cloud media not found for this account.")
        case .notVerified: return L10n.t("Cloud media not yet verified.")
        case .badStatus(let c): return L10n.t("Unexpected download response (\(c)).")
        case .decoding: return L10n.t("Unexpected download response shape.")
        case .s3GetFailed(let c): return L10n.t("Download from storage failed (\(c)).")
        case .sizeMismatch(let e, let g): return L10n.t("Downloaded size \(g) != expected \(e).")
        case .checksumMismatch: return L10n.t("Downloaded file failed integrity check.")
        case .missingExpectation: return L10n.t("Server did not provide size/checksum to verify the download.")
        }
    }
}

/// The server-authoritative download target: a short-lived presigned GET plus the expectation the download
/// is verified against (safeguard #7 — comes from the cloud record, NOT a local upload job).
struct MediaDownloadTarget {
    let url: URL
    let expiresIn: Int
    let expectedSize: Int
    let expectedSha256Hex: String   // full-file sha256 (hex)
    let contentType: String
}

/// Seam so MediaResolver can be driven by a fake in tests (no network/S3).
protocol MediaDownloading {
    /// GET /v1/media/{id}/download — returns the presigned URL + server-authoritative size/checksum.
    func presignDownload(accessToken: String, cloudMediaId: String) async throws -> MediaDownloadTarget
    /// Stream `target.url` to `destURL`, verifying size + full-file sha256. Writes a WHOLE file atomically
    /// into `destURL` only after verification passes; on any failure `destURL` is left absent.
    func download(target: MediaDownloadTarget, to destURL: URL,
                  progress: ((Double) -> Void)?) async throws
    /// GET /v1/media — the caller's own cloud media records (account-scoped). Used to RECONCILE local Moment
    /// cloud-state after a store migration / reinstall / on a new device (R6/R7): the server is authoritative
    /// about what is backed up, and `source_moment_id` links a record back to a local Moment.
    func listMedia(accessToken: String) async throws -> [CloudMediaRecord]
}

/// One server-side media record (the fields /v1/media returns). `sourceMomentId` links it to a local Moment.
struct CloudMediaRecord {
    let cloudMediaId: String
    let state: String                 // "cloud_verified" | "uploading" | ...
    let sizeBytes: Int
    let sourceMomentId: String        // local Moment UUID string (empty if the upload carried none)
    // P1-E — `mediaKind` ("moment" | "generated" | "ai_artifact" | "music") lets a reconcile pass pick out the
    // caller's backed-up My Music imports; `deviceAssetId` carries the local MyMusicAssetModel UUID for a music
    // record (the same slot a moment upload uses for its local AssetModel id), so restore re-links bytes to the
    // right library row.
    var mediaKind: String = "moment"
    var deviceAssetId: String = ""
    var isVerified: Bool { state == "cloud_verified" }
}

struct MediaDownloadService: MediaDownloading {
    var baseURL: URL = StoryBackend.baseURL
    var session: URLSession = StoryBackend.mediaDownloadSession

    func presignDownload(accessToken: String, cloudMediaId: String) async throws -> MediaDownloadTarget {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/media/\(cloudMediaId)/download"))
        req.httpMethod = "GET"
        req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.data(for: req) }
        catch { throw MediaDownloadError.transport(error) }
        let http = resp as! HTTPURLResponse
        switch http.statusCode {
        case 200: break
        case 401: throw MediaDownloadError.unauthorized
        case 404: throw MediaDownloadError.notFound
        case 409: throw MediaDownloadError.notVerified
        default: throw MediaDownloadError.badStatus(http.statusCode)
        }
        guard let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let urlStr = obj["url"] as? String, let url = URL(string: urlStr) else {
            throw MediaDownloadError.decoding
        }
        // Server-authoritative expectation (safeguard #7). A record missing either is not verifiable.
        guard let size = (obj["size_bytes"] as? Int) ?? (obj["size_bytes"] as? NSNumber)?.intValue,
              let sha = obj["content_sha256"] as? String, !sha.isEmpty else {
            throw MediaDownloadError.missingExpectation
        }
        return MediaDownloadTarget(
            url: url,
            expiresIn: (obj["expires_in"] as? Int) ?? 0,
            expectedSize: size,
            expectedSha256Hex: sha,
            contentType: (obj["content_type"] as? String) ?? "application/octet-stream")
    }

    func listMedia(accessToken: String) async throws -> [CloudMediaRecord] {
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/media"))
        req.httpMethod = "GET"
        req.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let (data, resp): (Data, URLResponse)
        do { (data, resp) = try await session.data(for: req) }
        catch { throw MediaDownloadError.transport(error) }
        let http = resp as! HTTPURLResponse
        if http.statusCode == 401 { throw MediaDownloadError.unauthorized }
        guard http.statusCode == 200 else { throw MediaDownloadError.badStatus(http.statusCode) }
        guard let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let arr = obj["media"] as? [[String: Any]] else { throw MediaDownloadError.decoding }
        return arr.compactMap { r in
            guard let cmid = r["cloud_media_id"] as? String else { return nil }
            let size = (r["size_bytes"] as? Int) ?? (r["size_bytes"] as? NSNumber)?.intValue ?? 0
            return CloudMediaRecord(
                cloudMediaId: cmid,
                state: (r["state"] as? String) ?? "",
                sizeBytes: size,
                sourceMomentId: (r["source_moment_id"] as? String) ?? "",
                mediaKind: (r["media_kind"] as? String) ?? "moment",
                deviceAssetId: (r["device_asset_id"] as? String) ?? "")
        }
    }

    func download(target: MediaDownloadTarget, to destURL: URL,
                  progress: ((Double) -> Void)? = nil) async throws {
        // URLSession writes the body straight to a file (a download task: native speed, nothing held in memory).
        // It replaces a byte-by-byte AsyncBytes loop that restored originals at about 1 MB/s on device
        // (dev 2026-11-26, 1.9 GB of originals for one Create).
        let partURL = destURL.appendingPathExtension("part")
        let fm = FileManager.default
        try? fm.removeItem(at: partURL)
        try? fm.removeItem(at: destURL)
        let http = try await Self.downloadFile(session: session, from: target.url, to: partURL, progress: progress)
        guard (200...299).contains(http.statusCode) else {
            try? fm.removeItem(at: partURL)
            throw MediaDownloadError.s3GetFailed(http.statusCode)
        }

        // VERIFY before exposing anything as a valid original (safeguard #1/#2): size, then the full-file sha256
        // read back from disk 1 MiB at a time (never the whole video in memory).
        let written = ((try? fm.attributesOfItem(atPath: partURL.path)[.size]) as? NSNumber)?.intValue ?? -1
        if written != target.expectedSize {
            try? fm.removeItem(at: partURL)
            throw MediaDownloadError.sizeMismatch(expected: target.expectedSize, got: written)
        }
        let gotSha: String
        do { gotSha = try Self.sha256Hex(of: partURL) }
        catch { try? fm.removeItem(at: partURL); throw MediaDownloadError.transport(error) }
        if gotSha.lowercased() != target.expectedSha256Hex.lowercased() {
            try? fm.removeItem(at: partURL)
            throw MediaDownloadError.checksumMismatch
        }
        // Verified → promote the .part to the real temp destination (the CALLER then atomically installs it
        // into the Moment's relativePath). Promotion is a rename on the same volume.
        try? fm.removeItem(at: destURL)
        try fm.moveItem(at: partURL, to: destURL)
        if let progress { await MainActor.run { progress(1.0) } }
    }

    /// One download task to `partURL`, with progress from the task's own Progress object and cooperative
    /// cancellation. The system temp file is moved inside the completion handler (it is deleted after it returns).
    static func downloadFile(session: URLSession, from url: URL, to partURL: URL,
                             progress: ((Double) -> Void)?) async throws -> HTTPURLResponse {
        final class Box: @unchecked Sendable { var task: URLSessionDownloadTask?; var observation: NSKeyValueObservation? }
        let box = Box()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (cont: CheckedContinuation<HTTPURLResponse, Error>) in
                let task = session.downloadTask(with: url) { tmp, resp, error in
                    box.observation?.invalidate()
                    if let error { cont.resume(throwing: MediaDownloadError.transport(error)); return }
                    guard let tmp, let http = resp as? HTTPURLResponse else {
                        cont.resume(throwing: MediaDownloadError.transport(URLError(.badServerResponse))); return
                    }
                    do {
                        try? FileManager.default.removeItem(at: partURL)
                        try FileManager.default.moveItem(at: tmp, to: partURL)
                        cont.resume(returning: http)
                    } catch { cont.resume(throwing: MediaDownloadError.transport(error)) }
                }
                if let progress {
                    // Callers write the value into SwiftData models, so deliver on the main queue, and only on a
                    // whole-percent change so a large file does not flood it.
                    var lastPct = -1
                    box.observation = task.progress.observe(\.fractionCompleted) { p, _ in
                        let v = min(1.0, max(0.0, p.fractionCompleted))
                        let pct = Int(v * 100)
                        guard pct != lastPct else { return }
                        lastPct = pct
                        DispatchQueue.main.async { progress(v) }
                    }
                }
                box.task = task
                task.resume()
            }
        } onCancel: {
            box.task?.cancel()
        }
    }

    /// Full-file sha256 (hex), streamed from disk in 1 MiB chunks.
    static func sha256Hex(of url: URL) throws -> String {
        let h = try FileHandle(forReadingFrom: url)
        defer { try? h.close() }
        var hasher = SHA256()
        while let chunk = try h.read(upToCount: 1 << 20), !chunk.isEmpty { hasher.update(data: chunk) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
