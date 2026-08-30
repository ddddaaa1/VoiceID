@preconcurrency import AVFAudio
import Foundation
import SwiftUI
import VoiceIDCompanionCore
import VoiceIDKit

@MainActor
final class CompanionViewModel: ObservableObject {
  @Published var baseURL = "http://127.0.0.1:8000"
  @Published var identityID = "demo-user"
  @Published var deviceID = "wearable-demo"
  @Published var credential = ""
  @Published var selectedAction: ProtectedAction = .playMedia
  @Published private(set) var isBusy = false
  @Published private(set) var captureStatus = "Ready"
  @Published private(set) var routeName = "No route captured"
  @Published private(set) var credentialStatus = "Not saved in this session"
  @Published private(set) var result: CompanionResult?

  func saveCredential() async {
    let candidate = credential.trimmingCharacters(in: .whitespacesAndNewlines)
    guard isValidCredential(candidate) else {
      credentialStatus = "Use 1–128 visible ASCII characters without spaces."
      return
    }
    guard isValidIdentifier(deviceID) else {
      credentialStatus = "Enter a valid device ID before saving."
      return
    }

    do {
      let store = KeychainDeviceCredentialStore(account: deviceID)
      try await store.store(candidate)
      credential = ""
      credentialStatus = "Saved to the device-only Keychain"
    } catch {
      credentialStatus = "Keychain save failed: \(Self.describe(error))"
    }
  }

  func authorize() async {
    guard !isBusy else { return }
    result = nil

    do {
      let configuration = try makeConfiguration()
      guard await AVAudioApplication.requestRecordPermission() else {
        result = CompanionResult(
          kind: .denied,
          title: "Microphone access denied",
          message: "Enable microphone access in Settings before recording a voice command."
        )
        return
      }

      isBusy = true
      defer { isBusy = false }

      let credentials = KeychainDeviceCredentialStore(account: configuration.deviceID)
      let client = VoiceIDHTTPClient(configuration: configuration, credentials: credentials)
      let capture = AVAudioEngineVoiceCommandCapture { [weak self] status in
        await self?.renderCaptureStatus(status)
      }
      let workflow = CompanionAuthorizationWorkflow(
        capture: capture,
        client: client,
        authenticator: LocalDeviceAuthenticator()
      )

      let outcome = try await workflow.run(
        identityID: identityID,
        action: selectedAction,
        durationSeconds: 3
      )
      render(outcome)
    } catch {
      captureStatus = "Ready"
      result = CompanionResult(
        kind: .error,
        title: "Request failed safely",
        message: Self.describe(error)
      )
    }
  }

  private func makeConfiguration() throws -> VoiceIDConfiguration {
    guard let url = URL(string: baseURL), url.host != nil else {
      throw CompanionConfigurationError.invalidBaseURL
    }
    return try VoiceIDConfiguration(baseURL: url, deviceID: deviceID)
  }

  private func renderCaptureStatus(_ status: AudioCaptureStatus) {
    switch status {
    case .inactive:
      captureStatus = "Ready"
    case .recording(let route):
      routeName = route
      captureStatus = "Recording for 3 seconds"
    case .processing:
      captureStatus = "Processing and requesting policy"
    case .failed:
      captureStatus = "Capture failed"
    }
  }

  private func render(_ outcome: CompanionAuthorizationOutcome) {
    captureStatus = "Ready"
    switch outcome {
    case .authorized(let authorization, let consumed):
      result = CompanionResult(
        kind: .allowed,
        title: "Authorized and consumed",
        message: "The server grant was bound to this device and consumed once.",
        authorization: authorization,
        grantID: consumed.grantID
      )
    case .denied(let authorization):
      result = CompanionResult(
        kind: .denied,
        title: "Action denied",
        message: "The requested action remains blocked by server policy.",
        authorization: authorization
      )
    case .stepUpLocallyAuthenticated(let authorization):
      result = CompanionResult(
        kind: .stepUp,
        title: "Device owner confirmed locally",
        message:
          "The action is still blocked. Server-verifiable passkey completion is the next security increment.",
        authorization: authorization
      )
    }
  }

  private func isValidIdentifier(_ value: String) -> Bool {
    !value.isEmpty && value.count <= 128
      && value.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || "._:-".contains($0)) }
  }

  private func isValidCredential(_ value: String) -> Bool {
    !value.isEmpty && value.count <= 128
      && value.allSatisfy { $0.isASCII && !$0.isWhitespace && !$0.isNewline }
  }

  private static func describe(_ error: Error) -> String {
    switch error {
    case CompanionConfigurationError.invalidBaseURL:
      return "Enter a valid server URL. HTTPS is required outside localhost."
    case VoiceIDClientError.insecureBaseURL:
      return "HTTPS is required outside localhost. Use 127.0.0.1 only in the simulator."
    case VoiceIDClientError.invalidDeviceID:
      return "The device ID contains unsupported characters."
    case VoiceIDClientError.invalidIdentityID:
      return "The identity ID contains unsupported characters."
    case VoiceIDClientError.invalidCredential:
      return "The saved device credential is invalid."
    case CredentialStoreError.unavailable:
      return "No credential is stored for this device ID."
    case VoiceIDClientError.server(let status, let code, let message):
      return "Server \(status) · \(code): \(message)"
    case DeviceAuthenticationError.unavailable:
      return "Face ID, Touch ID, or the device passcode is unavailable."
    case DeviceAuthenticationError.rejected:
      return "Device-owner authentication was not completed."
    case AudioCaptureError.inputUnavailable:
      return "No microphone input is available."
    case AudioCaptureError.noAudioCaptured:
      return "No usable audio was captured."
    default:
      return String(describing: error)
    }
  }
}

private enum CompanionConfigurationError: Error {
  case invalidBaseURL
}

struct CompanionResult: Equatable {
  enum Kind: Equatable {
    case allowed
    case denied
    case stepUp
    case error
  }

  let kind: Kind
  let title: String
  let message: String
  var authorization: ActionAuthorization? = nil
  var grantID: String? = nil

  var tint: Color {
    switch kind {
    case .allowed: .green
    case .denied, .error: .red
    case .stepUp: .orange
    }
  }

  var symbol: String {
    switch kind {
    case .allowed: "checkmark.shield.fill"
    case .denied: "xmark.shield.fill"
    case .stepUp: "person.badge.key.fill"
    case .error: "exclamationmark.triangle.fill"
    }
  }
}
