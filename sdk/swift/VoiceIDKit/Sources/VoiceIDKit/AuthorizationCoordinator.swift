import Foundation

public enum AuthorizationResolution: Sendable, Equatable {
  case granted(authorization: ActionAuthorization, grant: AuthorizationGrant)
  case denied(ActionAuthorization)
  case stepUpRequired(ActionAuthorization)
}

public enum AuthorizationEvent: Sendable, Equatable {
  case captureStarted
  case requestSubmitted(action: ProtectedAction)
  case allowed(authorizationID: String)
  case denied(authorizationID: String, reasons: [String])
  case stepUpRequired(authorizationID: String, reasons: [String])
}

public typealias AuthorizationEventHandler = @Sendable (AuthorizationEvent) async -> Void

public struct AuthorizationCoordinator: Sendable {
  private let client: any VoiceIDGrantClient
  private let onEvent: AuthorizationEventHandler

  public init(
    client: any VoiceIDGrantClient,
    onEvent: @escaping AuthorizationEventHandler = { _ in }
  ) {
    self.client = client
    self.onEvent = onEvent
  }

  public func authorize(
    identityID: String,
    action: ProtectedAction,
    pcmWave: Data
  ) async throws -> AuthorizationResolution {
    await onEvent(.requestSubmitted(action: action))
    let issue = try await client.issueGrant(
      identityID: identityID,
      action: action,
      pcmWave: pcmWave
    )
    switch issue.authorization.decision {
    case .allow:
      guard
        let grant = issue.grant,
        grant.authorizationID == issue.authorization.authorizationID,
        grant.identityID == issue.authorization.identityID,
        grant.action == issue.authorization.action
      else {
        throw VoiceIDClientError.malformedResponse
      }
      await onEvent(.allowed(authorizationID: issue.authorization.authorizationID))
      return .granted(authorization: issue.authorization, grant: grant)
    case .deny:
      await onEvent(
        .denied(
          authorizationID: issue.authorization.authorizationID,
          reasons: issue.authorization.reasons
        )
      )
      return .denied(issue.authorization)
    case .stepUp:
      await onEvent(
        .stepUpRequired(
          authorizationID: issue.authorization.authorizationID,
          reasons: issue.authorization.reasons
        )
      )
      return .stepUpRequired(issue.authorization)
    }
  }

  public func consume(_ grant: AuthorizationGrant) async throws -> ConsumedAuthorizationGrant {
    let consumed = try await client.consume(grant: grant)
    guard
      consumed.grantID == grant.grantID,
      consumed.authorizationID == grant.authorizationID,
      consumed.identityID == grant.identityID,
      consumed.deviceID == grant.deviceID,
      consumed.action == grant.action
    else {
      throw VoiceIDClientError.malformedResponse
    }
    return consumed
  }
}
