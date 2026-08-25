import Foundation
import LocalAuthentication

public protocol DeviceOwnerAuthenticating: Sendable {
  func authenticate(localizedReason: String) async throws
}

public enum DeviceAuthenticationError: Error, Sendable {
  case unavailable
  case rejected
}

public struct LocalDeviceAuthenticator: DeviceOwnerAuthenticating {
  public init() {}

  public func authenticate(localizedReason: String) async throws {
    let context = LAContext()
    var error: NSError?
    guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
      throw DeviceAuthenticationError.unavailable
    }
    guard
      try await context.evaluatePolicy(
        .deviceOwnerAuthentication,
        localizedReason: localizedReason
      )
    else {
      throw DeviceAuthenticationError.rejected
    }
  }
}

/// The host app supplies an AuthenticationServices adapter after receiving a server challenge.
/// VoiceIDKit deliberately does not treat a local success boolean as server-verifiable proof.
public protocol PasskeyAssertionProviding: Sendable {
  func assertion(challenge: Data, relyingPartyID: String) async throws -> Data
}
