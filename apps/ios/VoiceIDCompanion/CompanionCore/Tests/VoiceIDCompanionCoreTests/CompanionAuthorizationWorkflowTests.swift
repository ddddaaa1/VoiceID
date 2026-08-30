import Foundation
import VoiceIDKit
import XCTest

@testable import VoiceIDCompanionCore

final class CompanionAuthorizationWorkflowTests: XCTestCase {
  func testAllowConsumesTheBoundGrantExactlyOnce() async throws {
    let recorder = Recorder()
    let workflow = CompanionAuthorizationWorkflow(
      capture: StubCapture(recorder: recorder),
      client: StubClient(issue: fixture(decision: .allow), recorder: recorder),
      authenticator: StubAuthenticator(recorder: recorder)
    )

    let outcome = try await workflow.run(identityID: "demo-user", action: .playMedia)

    guard case .authorized(let authorization, let consumed) = outcome else {
      return XCTFail("An allowed action must consume its server grant")
    }
    XCTAssertEqual(authorization.verification.speakerScore, 0.91)
    XCTAssertEqual(consumed.action, .playMedia)
    let snapshot = await recorder.snapshot()
    XCTAssertEqual(snapshot.captureCount, 1)
    XCTAssertEqual(snapshot.consumeCount, 1)
    XCTAssertEqual(snapshot.authenticationCount, 0)
  }

  func testDenyNeverConsumesOrAuthenticates() async throws {
    let recorder = Recorder()
    let workflow = CompanionAuthorizationWorkflow(
      capture: StubCapture(recorder: recorder),
      client: StubClient(issue: fixture(decision: .deny), recorder: recorder),
      authenticator: StubAuthenticator(recorder: recorder)
    )

    let outcome = try await workflow.run(identityID: "demo-user", action: .playMedia)

    guard case .denied(let authorization) = outcome else {
      return XCTFail("A server denial must remain denied")
    }
    XCTAssertEqual(authorization.decision, .deny)
    let snapshot = await recorder.snapshot()
    XCTAssertEqual(snapshot.consumeCount, 0)
    XCTAssertEqual(snapshot.authenticationCount, 0)
  }

  func testStepUpAuthenticatesLocallyButRemainsWithoutGrant() async throws {
    let recorder = Recorder()
    let workflow = CompanionAuthorizationWorkflow(
      capture: StubCapture(recorder: recorder),
      client: StubClient(issue: fixture(decision: .stepUp), recorder: recorder),
      authenticator: StubAuthenticator(recorder: recorder)
    )

    let outcome = try await workflow.run(
      identityID: "demo-user",
      action: .readPrivateContent
    )

    guard case .stepUpLocallyAuthenticated(let authorization) = outcome else {
      return XCTFail("Local authentication must not be represented as a server grant")
    }
    XCTAssertEqual(authorization.decision, .stepUp)
    let snapshot = await recorder.snapshot()
    XCTAssertEqual(snapshot.consumeCount, 0)
    XCTAssertEqual(snapshot.authenticationCount, 1)
  }

  private func fixture(decision: AuthorizationDecision) -> AuthorizationGrantIssue {
    let action: ProtectedAction = decision == .stepUp ? .readPrivateContent : .playMedia
    let authorization = ActionAuthorization(
      authorizationID: "authorization-1",
      createdAt: "2026-08-31T00:00:00Z",
      identityID: "demo-user",
      action: action,
      risk: decision == .stepUp ? .moderate : .low,
      decision: decision,
      authorizationPolicyID: "wearable-action-risk-v1",
      reasons: decision == .deny ? ["speaker_verification_failed"] : [],
      verification: VerificationEvidence(
        attemptID: "attempt-1",
        createdAt: "2026-08-31T00:00:00Z",
        identityID: "demo-user",
        templateID: "template-1",
        templateVersion: 1,
        modelID: "ecapa",
        spoofModelID: nil,
        pipelineID: "pcm16-v1",
        policyID: "provisional-cosine-v1",
        decision: decision == .deny ? .reject : .accept,
        speakerScore: 0.91,
        spoofProbability: nil,
        reasons: []
      )
    )
    let grant =
      decision == .allow
      ? AuthorizationGrant(
        grantID: "grant-1",
        authorizationID: authorization.authorizationID,
        identityID: authorization.identityID,
        deviceID: "wearable-demo",
        action: action,
        issuedAt: "2026-08-31T00:00:00Z",
        expiresAt: "2026-08-31T00:00:30Z",
        token: "never-log-this-token"
      )
      : nil
    return AuthorizationGrantIssue(authorization: authorization, grant: grant)
  }
}

private actor Recorder {
  private var captureCount = 0
  private var consumeCount = 0
  private var authenticationCount = 0

  func captured() { captureCount += 1 }
  func consumed() { consumeCount += 1 }
  func authenticated() { authenticationCount += 1 }

  func snapshot() -> (captureCount: Int, consumeCount: Int, authenticationCount: Int) {
    (captureCount, consumeCount, authenticationCount)
  }
}

private struct StubCapture: VoiceCommandCapturing {
  let recorder: Recorder

  func capture(durationSeconds: Double) async throws -> CapturedVoiceCommand {
    await recorder.captured()
    return CapturedVoiceCommand(
      pcmWave: PCM16WaveEncoder.encode(samples: [0, 0.1, -0.1], sampleRate: 16_000),
      durationSeconds: durationSeconds,
      sourceSampleRate: 48_000,
      routeName: "test-input"
    )
  }
}

private struct StubClient: VoiceIDGrantClient {
  let issue: AuthorizationGrantIssue
  let recorder: Recorder

  func issueGrant(
    identityID: String,
    action: ProtectedAction,
    pcmWave: Data
  ) async throws -> AuthorizationGrantIssue {
    issue
  }

  func consume(grant: AuthorizationGrant) async throws -> ConsumedAuthorizationGrant {
    await recorder.consumed()
    return ConsumedAuthorizationGrant(
      grantID: grant.grantID,
      authorizationID: grant.authorizationID,
      identityID: grant.identityID,
      deviceID: grant.deviceID,
      action: grant.action,
      consumedAt: "2026-08-31T00:00:01Z"
    )
  }
}

private struct StubAuthenticator: DeviceOwnerAuthenticating {
  let recorder: Recorder

  func authenticate(localizedReason: String) async throws {
    await recorder.authenticated()
  }
}
