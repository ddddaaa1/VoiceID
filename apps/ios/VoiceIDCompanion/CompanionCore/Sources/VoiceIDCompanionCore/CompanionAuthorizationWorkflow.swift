import Foundation
import VoiceIDKit

public enum CompanionAuthorizationOutcome: Equatable, Sendable {
  case authorized(
    authorization: ActionAuthorization,
    consumedGrant: ConsumedAuthorizationGrant
  )
  case denied(authorization: ActionAuthorization)
  case stepUpLocallyAuthenticated(authorization: ActionAuthorization)
}

/// Runs the complete bounded companion flow while preserving the server-owned policy decision.
/// A local device-authentication success is intentionally not converted into an authorization grant.
public struct CompanionAuthorizationWorkflow: Sendable {
  private let capture: any VoiceCommandCapturing
  private let coordinator: AuthorizationCoordinator
  private let authenticator: any DeviceOwnerAuthenticating

  public init(
    capture: any VoiceCommandCapturing,
    client: any VoiceIDGrantClient,
    authenticator: any DeviceOwnerAuthenticating
  ) {
    self.capture = capture
    coordinator = AuthorizationCoordinator(client: client)
    self.authenticator = authenticator
  }

  public func run(
    identityID: String,
    action: ProtectedAction,
    durationSeconds: Double = 3
  ) async throws -> CompanionAuthorizationOutcome {
    let command = try await capture.capture(durationSeconds: durationSeconds)
    let resolution = try await coordinator.authorize(
      identityID: identityID,
      action: action,
      pcmWave: command.pcmWave
    )

    switch resolution {
    case .granted(let authorization, let grant):
      let consumed = try await coordinator.consume(grant)
      return .authorized(authorization: authorization, consumedGrant: consumed)
    case .denied(let authorization):
      return .denied(authorization: authorization)
    case .stepUpRequired(let authorization):
      try await authenticator.authenticate(
        localizedReason: "Confirm device ownership for this protected VoiceID action."
      )
      return .stepUpLocallyAuthenticated(authorization: authorization)
    }
  }
}
