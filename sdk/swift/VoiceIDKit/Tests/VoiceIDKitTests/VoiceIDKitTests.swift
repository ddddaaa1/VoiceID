import Foundation
import XCTest

@testable import VoiceIDKit

final class VoiceIDKitTests: XCTestCase {
  func testDecodesGrantIssueContract() throws {
    let issue = try JSONDecoder().decode(
      AuthorizationGrantIssue.self,
      from: Data(Self.allowResponse.utf8)
    )

    XCTAssertEqual(issue.authorization.decision, .allow)
    XCTAssertEqual(issue.authorization.verification.decision, .accept)
    XCTAssertEqual(issue.grant?.action, .playMedia)
    XCTAssertEqual(issue.grant?.deviceID, "wearable-demo")
  }

  func testCoordinatorPreservesAllowDenyAndStepUpPolicy() async throws {
    let allow = try Self.issue(decision: .allow, includeGrant: true)
    let allowed = try await AuthorizationCoordinator(client: StubClient(issue: allow)).authorize(
      identityID: "demo-user",
      action: .playMedia,
      pcmWave: Data("wave".utf8)
    )
    guard case .granted(let grant) = allowed else {
      return XCTFail("allow must return the server grant")
    }
    XCTAssertEqual(grant.action, .playMedia)

    let deniedIssue = try Self.issue(decision: .deny, includeGrant: false)
    let denied = try await AuthorizationCoordinator(client: StubClient(issue: deniedIssue))
      .authorize(
        identityID: "demo-user",
        action: .playMedia,
        pcmWave: Data("wave".utf8)
      )
    guard case .denied(let authorization) = denied else {
      return XCTFail("deny must remain denied")
    }
    XCTAssertEqual(authorization.decision, .deny)

    let stepUpIssue = try Self.issue(decision: .stepUp, includeGrant: false)
    let stepUp = try await AuthorizationCoordinator(client: StubClient(issue: stepUpIssue))
      .authorize(
        identityID: "demo-user",
        action: .readPrivateContent,
        pcmWave: Data("wave".utf8)
      )
    guard case .stepUpRequired(let authorization) = stepUp else {
      return XCTFail("step-up must never be converted into a local grant")
    }
    XCTAssertEqual(authorization.decision, .stepUp)
  }

  func testCoordinatorRejectsAllowWithoutGrant() async throws {
    let malformed = try Self.issue(decision: .allow, includeGrant: false)
    do {
      _ = try await AuthorizationCoordinator(client: StubClient(issue: malformed)).authorize(
        identityID: "demo-user",
        action: .playMedia,
        pcmWave: Data()
      )
      XCTFail("allow without a signed grant must fail closed")
    } catch let error as VoiceIDClientError {
      XCTAssertEqual(error, .malformedResponse)
    }
  }

  func testPCMEncoderProducesBoundedMono16kWave() {
    let output = PCM16WaveEncoder.encode(samples: [-2.0, 0.0, 2.0], sampleRate: 16_000)

    XCTAssertEqual(String(data: output.prefix(4), encoding: .ascii), "RIFF")
    XCTAssertEqual(String(data: output[8..<12], encoding: .ascii), "WAVE")
    XCTAssertEqual(output.count, 44 + 6)
    XCTAssertEqual(output.littleEndianUInt32(at: 24), 16_000)
    XCTAssertEqual(output.littleEndianUInt16(at: 34), 16)
  }

  func testConfigurationRequiresTLSOutsideLoopback() throws {
    XCTAssertThrowsError(
      try VoiceIDConfiguration(
        baseURL: URL(string: "http://voiceid.example")!,
        deviceID: "wearable-demo"
      )
    )
    XCTAssertNoThrow(
      try VoiceIDConfiguration(
        baseURL: URL(string: "http://127.0.0.1:8000")!,
        deviceID: "wearable-demo"
      )
    )
  }

  func testSecureNonceIsURLSafeAndUnique() throws {
    let generator = SecureNonceGenerator()
    let first = try generator.nonce()
    let second = try generator.nonce()

    XCTAssertGreaterThanOrEqual(first.count, 16)
    XCTAssertNotEqual(first, second)
    XCTAssertTrue(first.allSatisfy { $0.isLetter || $0.isNumber || $0 == "-" || $0 == "_" })
  }

  private static func issue(
    decision: AuthorizationDecision,
    includeGrant: Bool
  ) throws -> AuthorizationGrantIssue {
    let authorization = ActionAuthorization(
      authorizationID: "authorization-1",
      createdAt: "2026-08-25T12:00:00Z",
      identityID: "demo-user",
      action: decision == .stepUp ? .readPrivateContent : .playMedia,
      risk: decision == .stepUp ? .moderate : .low,
      decision: decision,
      authorizationPolicyID: "wearable-action-risk-v1",
      reasons: decision == .stepUp ? ["device_authentication_required"] : [],
      verification: VerificationEvidence(
        attemptID: "attempt-1",
        createdAt: "2026-08-25T12:00:00Z",
        identityID: "demo-user",
        templateID: "template-1",
        templateVersion: 1,
        modelID: "model-1",
        spoofModelID: nil,
        pipelineID: "pipeline-1",
        policyID: "policy-1",
        decision: decision == .deny ? .reject : .accept,
        speakerScore: 0.9,
        spoofProbability: nil,
        reasons: []
      )
    )
    let grant =
      includeGrant
      ? AuthorizationGrant(
        grantID: "grant-1",
        authorizationID: authorization.authorizationID,
        identityID: "demo-user",
        deviceID: "wearable-demo",
        action: .playMedia,
        issuedAt: "2026-08-25T12:00:00Z",
        expiresAt: "2026-08-25T12:00:30Z",
        token: "secret-token"
      )
      : nil
    return AuthorizationGrantIssue(authorization: authorization, grant: grant)
  }

  private static let allowResponse = """
    {
      "authorization": {
        "authorization_id": "authorization-1",
        "created_at": "2026-08-25T12:00:00Z",
        "identity_id": "demo-user",
        "action": "play_media",
        "risk": "low",
        "decision": "allow",
        "authorization_policy_id": "wearable-action-risk-v1",
        "reasons": ["voice_sufficient_for_low_risk_action"],
        "verification": {
          "attempt_id": "attempt-1",
          "created_at": "2026-08-25T12:00:00Z",
          "identity_id": "demo-user",
          "template_id": "template-1",
          "template_version": 1,
          "model_id": "model-1",
          "spoof_model_id": null,
          "pipeline_id": "pipeline-1",
          "policy_id": "policy-1",
          "decision": "accept",
          "speaker_score": 0.9,
          "spoof_probability": null,
          "reasons": ["speaker_match"]
        }
      },
      "grant": {
        "grant_id": "grant-1",
        "authorization_id": "authorization-1",
        "identity_id": "demo-user",
        "device_id": "wearable-demo",
        "action": "play_media",
        "issued_at": "2026-08-25T12:00:00Z",
        "expires_at": "2026-08-25T12:00:30Z",
        "token": "secret-token"
      }
    }
    """
}

private struct StubClient: VoiceIDGrantClient {
  let issue: AuthorizationGrantIssue

  func issueGrant(
    identityID: String,
    action: ProtectedAction,
    pcmWave: Data
  ) async throws -> AuthorizationGrantIssue {
    issue
  }

  func consume(grant: AuthorizationGrant) async throws -> ConsumedAuthorizationGrant {
    ConsumedAuthorizationGrant(
      grantID: grant.grantID,
      authorizationID: grant.authorizationID,
      identityID: grant.identityID,
      deviceID: grant.deviceID,
      action: grant.action,
      consumedAt: "2026-08-25T12:00:01Z"
    )
  }
}

extension Data {
  fileprivate func littleEndianUInt16(at offset: Int) -> UInt16 {
    UInt16(self[offset]) | UInt16(self[offset + 1]) << 8
  }

  fileprivate func littleEndianUInt32(at offset: Int) -> UInt32 {
    UInt32(self[offset])
      | UInt32(self[offset + 1]) << 8
      | UInt32(self[offset + 2]) << 16
      | UInt32(self[offset + 3]) << 24
  }
}
