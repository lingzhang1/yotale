import Foundation

// SceneVideoService — POST /v1/scene-video (Pixabay reference video via the backend proxy). Phase 1B.
//
// COMPLIANT + FAIL-SOFT by contract (mirrors SceneImageService):
//   * Sends ONLY a generic reference query + generic technique text (no user media, no personal details).
//     The backend normalizes/bounds it; this client never sends a free-form user string.
//   * Returns METADATA ONLY. The app STREAMS previewURL directly from cdn.pixabay.com in AVPlayer (Pixabay
//     permits video embedding). The posterURL is NOT hotlinked — it is loaded through the backend poster
//     endpoint (posterRequestURL below), because Pixabay forbids image hotlinking.
//   * ANY failure (404 gated to image mode, 503, transport, timeout, decode, no-match) resolves to nil =>
//     the caller falls back to the Unsplash image, then text. A video request NEVER blocks the UI.
//   * Caches the per-query result in-memory so re-opens / re-renders don't re-hit the proxy.
//
// Gated by StoryGuideFeatures.referenceVideoEnabled: in image mode fetch() short-circuits to nil with ZERO
// network, so image mode makes no video calls at all (owner §4).
protocol SceneVideoFetching {
    /// Fetch one reference video. `technique` is the shot's generic framing/camera-motion/instruction text
    /// (used server-side ONLY to classify the requested camera technique — no new model call, no PII).
    func fetch(query: String, technique: String?) async -> SceneVideoDTO?
    /// The backend URL the app loads a Pixabay poster image from (compliance: no client hotlinking).
    func posterRequestURL() -> URL
    func posterBody(for posterURL: String) -> Data?
}

actor SceneVideoService: SceneVideoFetching {
    private let baseURL: URL
    private let session: URLSession
    private var cache: [String: SceneVideoDTO?] = [:]

    init(baseURL: URL = StoryBackend.baseURL, session: URLSession = StoryBackend.longSession) {
        self.baseURL = baseURL
        self.session = session
    }

    nonisolated func posterRequestURL() -> URL {
        baseURL.appendingPathComponent("v1/scene-video/poster")
    }

    nonisolated func posterBody(for posterURL: String) -> Data? {
        try? JSONSerialization.data(withJSONObject: ["poster_url": posterURL])
    }

    func fetch(query: String, technique: String?) async -> SceneVideoDTO? {
        guard StoryGuideFeatures.referenceVideoEnabled else { return nil }
        let key = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return nil }
        let cacheKey = "\(key)::\(technique ?? "-")"
        if let cached = cache[cacheKey] { return cached }   // includes a cached nil (no-video) result

        var req = URLRequest(url: baseURL.appendingPathComponent("v1/scene-video"))
        StoryBackend.authorize(&req)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 6
        var payload: [String: Any] = ["query": key]
        if let technique, !technique.isEmpty { payload["technique_text"] = technique }
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return nil }
        req.httpBody = body

        do {
            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else {
                return cacheAndReturn(cacheKey, nil)   // 404 (image mode) / 503 / anything -> fallback
            }
            let decoded = try StoryContractCoding.decoder().decode(SceneVideoResponseDTO.self, from: data)
            return cacheAndReturn(cacheKey, decoded.video)
        } catch {
            // Transport/timeout/decode: fallback, but do NOT cache a transient failure as a permanent miss.
            return nil
        }
    }

    private func cacheAndReturn(_ key: String, _ value: SceneVideoDTO?) -> SceneVideoDTO? {
        cache[key] = value
        return value
    }
}
