import Foundation

// SceneImageService — POST /v1/scene-image (Unsplash reference image via the backend proxy).
//
// COMPLIANT + FAIL-SOFT by contract:
//   * Sends ONLY the scene's GENERIC visual_reference_query (no user media, no personal event details).
//     The backend re-sanitizes/bounds it; this client never sends a free-form user string.
//   * Returns METADATA ONLY — a hotlinked Unsplash CDN URL the UI loads via AsyncImage (never re-hosted).
//   * ANY failure (404 gated off, 503, transport, timeout, decode, no-match) resolves to nil => the scene
//     card renders text-only. An image request NEVER blocks Guide generation or the UI.
//   * Caches the per-query result in-memory so repeated Guide renders / re-opens don't re-hit the proxy.
//   * Fires the Unsplash download-tracking endpoint (/v1/scene-image/track) ONLY when a photo is actually
//     USED/selected as a reference (per Unsplash's rule) — never on mere display.
//
// Scene images are standard behavior (no feature switch); failures are soft (nil -> text-only card).
protocol SceneImageFetching {
    func fetch(query: String, storyId: UUID, sceneId: String) async -> SceneImageDTO?
    /// Query-only reference lookup with NO Guide provenance (story_id/scene_id omitted). Used by the
    /// live-camera Shooting Idea card, which has a generic composition query but no Guide scene. The
    /// backend treats story_id/scene_id as optional provenance; the compliance contract is identical.
    func fetch(query: String) async -> SceneImageDTO?
    func track(downloadLocation: String) async
}

actor SceneImageService: SceneImageFetching {
    private let baseURL: URL
    private let session: URLSession
    // In-memory metadata cache keyed by the exact query string; stores an optional (nil = cached 'no image').
    private var cache: [String: SceneImageDTO?] = [:]

    init(baseURL: URL = StoryBackend.baseURL, session: URLSession = StoryBackend.longSession) {
        self.baseURL = baseURL
        self.session = session
    }

    func fetch(query: String, storyId: UUID, sceneId: String) async -> SceneImageDTO? {
        await fetchCore(query: query, storyId: storyId, sceneId: sceneId)
    }

    /// Query-only lookup (no Guide provenance) for the live-camera Shooting Idea card.
    func fetch(query: String) async -> SceneImageDTO? {
        await fetchCore(query: query, storyId: nil, sceneId: nil)
    }

    private func fetchCore(query: String, storyId: UUID?, sceneId: String?) async -> SceneImageDTO? {
        let key = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else { return nil }
        if let cached = cache[key] { return cached }   // includes a cached nil (no-image) result

        var req = URLRequest(url: baseURL.appendingPathComponent("v1/scene-image"))
        StoryBackend.authorize(&req)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 6
        // story_id/scene_id are OPTIONAL provenance (never sent to the provider). Omit them for the
        // camera flow so the proxy contract is identical whether a Guide scene exists or not.
        var payload: [String: Any] = ["query": key]
        if let storyId { payload["story_id"] = storyId.uuidString }
        if let sceneId { payload["scene_id"] = sceneId }
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return nil }
        req.httpBody = body

        do {
            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else {
                return cacheAndReturn(key, nil)   // 404/503/anything -> text-only, cache the miss briefly
            }
            let decoded = try StoryContractCoding.decoder().decode(SceneImageResponseDTO.self, from: data)
            return cacheAndReturn(key, decoded.image)
        } catch {
            // Transport/timeout/decode: text-only fallback. Do NOT cache a transport failure as a permanent
            // miss (a transient network blip should be retryable) — only cache definitive server answers.
            return nil
        }
    }

    private func cacheAndReturn(_ key: String, _ value: SceneImageDTO?) -> SceneImageDTO? {
        cache[key] = value
        return value
    }

    /// Fire-and-forget Unsplash download tracking when a reference is actually used. Best-effort; errors ignored.
    func track(downloadLocation: String) async {
        guard downloadLocation.hasPrefix("https://api.unsplash.com/") else { return }
        var req = URLRequest(url: baseURL.appendingPathComponent("v1/scene-image/track"))
        StoryBackend.authorize(&req)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 4
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["download_location": downloadLocation])
        _ = try? await session.data(for: req)
    }
}
