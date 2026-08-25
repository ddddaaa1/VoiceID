import Foundation

public enum ProtectedAction: String, Codable, CaseIterable, Sendable {
  case playMedia = "play_media"
  case personalizeAssistant = "personalize_assistant"
  case switchProfile = "switch_profile"
  case readPrivateContent = "read_private_content"
  case sendMessage = "send_message"
  case makePurchase = "make_purchase"
  case unlockPhysicalAccess = "unlock_physical_access"
}

public enum ActionRisk: String, Codable, Sendable {
  case low
  case moderate
  case high
}

public enum AuthorizationDecision: String, Codable, Sendable {
  case allow
  case deny
  case stepUp = "step_up"
}

public enum VerificationDecision: String, Codable, Sendable {
  case accept
  case reject
  case review
}

public struct VerificationEvidence: Codable, Equatable, Sendable {
  public let attemptID: String
  public let createdAt: String
  public let identityID: String
  public let templateID: String
  public let templateVersion: Int
  public let modelID: String
  public let spoofModelID: String?
  public let pipelineID: String
  public let policyID: String
  public let decision: VerificationDecision
  public let speakerScore: Double?
  public let spoofProbability: Double?
  public let reasons: [String]

  enum CodingKeys: String, CodingKey {
    case attemptID = "attempt_id"
    case createdAt = "created_at"
    case identityID = "identity_id"
    case templateID = "template_id"
    case templateVersion = "template_version"
    case modelID = "model_id"
    case spoofModelID = "spoof_model_id"
    case pipelineID = "pipeline_id"
    case policyID = "policy_id"
    case decision
    case speakerScore = "speaker_score"
    case spoofProbability = "spoof_probability"
    case reasons
  }
}

public struct ActionAuthorization: Codable, Equatable, Sendable {
  public let authorizationID: String
  public let createdAt: String
  public let identityID: String
  public let action: ProtectedAction
  public let risk: ActionRisk
  public let decision: AuthorizationDecision
  public let authorizationPolicyID: String
  public let reasons: [String]
  public let verification: VerificationEvidence

  enum CodingKeys: String, CodingKey {
    case authorizationID = "authorization_id"
    case createdAt = "created_at"
    case identityID = "identity_id"
    case action
    case risk
    case decision
    case authorizationPolicyID = "authorization_policy_id"
    case reasons
    case verification
  }
}

public struct AuthorizationGrant: Codable, Equatable, Sendable {
  public let grantID: String
  public let authorizationID: String
  public let identityID: String
  public let deviceID: String
  public let action: ProtectedAction
  public let issuedAt: String
  public let expiresAt: String
  public let token: String

  enum CodingKeys: String, CodingKey {
    case grantID = "grant_id"
    case authorizationID = "authorization_id"
    case identityID = "identity_id"
    case deviceID = "device_id"
    case action
    case issuedAt = "issued_at"
    case expiresAt = "expires_at"
    case token
  }
}

public struct AuthorizationGrantIssue: Codable, Equatable, Sendable {
  public let authorization: ActionAuthorization
  public let grant: AuthorizationGrant?
}

public struct ConsumedAuthorizationGrant: Codable, Equatable, Sendable {
  public let grantID: String
  public let authorizationID: String
  public let identityID: String
  public let deviceID: String
  public let action: ProtectedAction
  public let consumedAt: String

  enum CodingKeys: String, CodingKey {
    case grantID = "grant_id"
    case authorizationID = "authorization_id"
    case identityID = "identity_id"
    case deviceID = "device_id"
    case action
    case consumedAt = "consumed_at"
  }
}

struct ErrorEnvelope: Decodable {
  let error: APIErrorDetail
}

struct APIErrorDetail: Decodable {
  let code: String
  let message: String
}
