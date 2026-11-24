import XCTest
@testable import Story

// Perf milestone (2026-11-18): EditPlan job polling notices a finished plan within ~5 s while the user waits in
// the foreground, and keeps the previous 2 -> 4 -> 8 -> 15 s backoff when the app is not active.
@MainActor
final class EditPlanPollingTests: XCTestCase {

    func test_foreground_schedule_grows_to_5s_and_stays() {
        var d = 2.0
        var seen: [Double] = [d]
        for _ in 0..<6 { d = EditPlanJobClient.nextPollDelay(after: d, foreground: true); seen.append(d) }
        XCTAssertEqual(seen, [2, 3, 4, 5, 5, 5, 5])
    }

    func test_background_schedule_is_the_previous_exponential_backoff() {
        var d = 2.0
        var seen: [Double] = [d]
        for _ in 0..<5 { d = EditPlanJobClient.nextPollDelay(after: d, foreground: false); seen.append(d) }
        XCTAssertEqual(seen, [2, 4, 8, 15, 15, 15])
    }

    func test_poll_reads_status_until_terminal_and_reports_each_state() async throws {
        StatusStub.responses = ["running", "completed"]
        StatusStub.reads = 0
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StatusStub.self]
        let client = EditPlanJobClient(baseURL: URL(string: "https://stub.invalid")!,
                                       session: URLSession(configuration: cfg), isForeground: { true })
        var states: [EditPlanJobStatus] = []
        let final = try await client.pollUntilTerminal(jobId: "job-1", maxSeconds: 30,
                                                       shouldCancel: { false },
                                                       onState: { states.append($0.status) })
        XCTAssertEqual(final.status, .completed)
        XCTAssertEqual(states, [.running, .completed])
        XCTAssertEqual(StatusStub.reads, 2, "no extra status reads after a terminal state")
    }
}

/// Answers GET /v1/edit-plan-jobs/<id> with the next queued status. No network.
final class StatusStub: URLProtocol {
    nonisolated(unsafe) static var responses: [String] = []
    nonisolated(unsafe) static var reads = 0

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let status = Self.responses.isEmpty ? "running" : Self.responses.removeFirst()
        Self.reads += 1
        let body = #"{"job_id":"job-1","status":"\#(status)"}"#.data(using: .utf8)!
        let resp = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
