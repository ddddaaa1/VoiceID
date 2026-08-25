import Foundation
import Security

#if canImport(FoundationNetworking)
  import FoundationNetworking
#endif

public protocol DeviceCredentialProviding: Sendable {
  func credential() async throws -> String
}

public protocol NonceGenerating: Sendable {
  func nonce() throws -> String
}

public struct SecureNonceGenerator: NonceGenerating {
  public init() {}

  public func nonce() throws -> String {
    var bytes = [UInt8](repeating: 0, count: 24)
    guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
      throw VoiceIDClientError.secureRandomUnavailable
    }
    return Data(bytes).base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }
}

public struct VoiceIDConfiguration: Sendable {
  public let baseURL: URL
  public let deviceID: String

  public init(baseURL: URL, deviceID: String) throws {
    let isLoopback = baseURL.host == "127.0.0.1" || baseURL.host == "localhost"
    guard baseURL.scheme == "https" || (baseURL.scheme == "http" && isLoopback) else {
      throw VoiceIDClientError.insecureBaseURL
    }
    guard Self.isValidIdentifier(deviceID) else {
      throw VoiceIDClientError.invalidDeviceID
    }
    self.baseURL = baseURL
    self.deviceID = deviceID
  }

  private static func isValidIdentifier(_ value: String) -> Bool {
    guard !value.isEmpty, value.count <= 128, value.first?.isASCII == true else { return false }
    return value.allSatisfy {
      $0.isASCII && ($0.isLetter || $0.isNumber || "._:-".contains($0))
    }
  }
}

public enum VoiceIDClientError: Error, Equatable, Sendable {
  case insecureBaseURL
  case invalidDeviceID
  case invalidIdentityID
  case invalidCredential
  case invalidAudio
  case secureRandomUnavailable
  case invalidHTTPResponse
  case server(status: Int, code: String, message: String)
  case malformedResponse
}

public protocol VoiceIDGrantClient: Sendable {
  func issueGrant(
    identityID: String,
    action: ProtectedAction,
    pcmWave: Data
  ) async throws -> AuthorizationGrantIssue

  func consume(grant: AuthorizationGrant) async throws -> ConsumedAuthorizationGrant
}

public final class VoiceIDHTTPClient: VoiceIDGrantClient, @unchecked Sendable {
  private let configuration: VoiceIDConfiguration
  private let credentials: any DeviceCredentialProviding
  private let nonceGenerator: any NonceGenerating
  private let session: URLSession

  public init(
    configuration: VoiceIDConfiguration,
    credentials: any DeviceCredentialProviding,
    nonceGenerator: any NonceGenerating = SecureNonceGenerator(),
    session: URLSession = .shared
  ) {
    self.configuration = configuration
    self.credentials = credentials
    self.nonceGenerator = nonceGenerator
    self.session = session
  }

  public func issueGrant(
    identityID: String,
    action: ProtectedAction,
    pcmWave: Data
  ) async throws -> AuthorizationGrantIssue {
    guard
      pcmWave.count >= 44,
      pcmWave.count <= 10_000_000,
      pcmWave.starts(with: Data("RIFF".utf8)),
      pcmWave[8..<12] == Data("WAVE".utf8)
    else {
      throw VoiceIDClientError.invalidAudio
    }
    let boundary = "voiceid-\(try nonceGenerator.nonce())"
    var form = MultipartFormData(boundary: boundary)
    form.appendField(name: "action", value: action.rawValue)
    form.appendField(name: "request_nonce", value: try nonceGenerator.nonce())
    form.appendFile(
      name: "sample",
      filename: "voice-command.wav",
      contentType: "audio/wav",
      bytes: pcmWave
    )
    form.finish()
    let identity = try validatedPathIdentifier(identityID)
    let url = configuration.baseURL
      .appendingPathComponent("api")
      .appendingPathComponent("v1")
      .appendingPathComponent("identities")
      .appendingPathComponent(identity)
      .appendingPathComponent("authorization-grants")
    var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)
    request.httpMethod = "POST"
    request.httpBody = form.data
    request.setValue(
      "multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
    try await authenticate(&request)
    return try await send(request, as: AuthorizationGrantIssue.self)
  }

  public func consume(grant: AuthorizationGrant) async throws -> ConsumedAuthorizationGrant {
    let url = configuration.baseURL
      .appendingPathComponent("api")
      .appendingPathComponent("v1")
      .appendingPathComponent("authorization-grants")
      .appendingPathComponent("consume")
    var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)
    request.httpMethod = "POST"
    request.httpBody = try JSONEncoder().encode(
      ConsumptionBody(token: grant.token, action: grant.action)
    )
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    try await authenticate(&request)
    return try await send(request, as: ConsumedAuthorizationGrant.self)
  }

  private func authenticate(_ request: inout URLRequest) async throws {
    let credential = try await credentials.credential()
    guard
      !credential.isEmpty,
      credential.count <= 128,
      credential.allSatisfy({ $0.isASCII && !$0.isWhitespace && !$0.isNewline })
    else {
      throw VoiceIDClientError.invalidCredential
    }
    request.setValue(configuration.deviceID, forHTTPHeaderField: "X-VoiceID-Device-ID")
    request.setValue("Device \(credential)", forHTTPHeaderField: "Authorization")
  }

  private func send<Response: Decodable>(
    _ request: URLRequest,
    as type: Response.Type
  ) async throws -> Response {
    let (data, response) = try await session.data(for: request)
    guard let http = response as? HTTPURLResponse else {
      throw VoiceIDClientError.invalidHTTPResponse
    }
    guard (200..<300).contains(http.statusCode) else {
      if let envelope = try? JSONDecoder().decode(ErrorEnvelope.self, from: data) {
        throw VoiceIDClientError.server(
          status: http.statusCode,
          code: envelope.error.code,
          message: envelope.error.message
        )
      }
      throw VoiceIDClientError.server(
        status: http.statusCode,
        code: "unknown_error",
        message: "VoiceID request failed"
      )
    }
    do {
      return try JSONDecoder().decode(type, from: data)
    } catch {
      throw VoiceIDClientError.malformedResponse
    }
  }

  private func validatedPathIdentifier(_ value: String) throws -> String {
    guard
      !value.isEmpty,
      value.count <= 128,
      value.allSatisfy({ $0.isASCII && ($0.isLetter || $0.isNumber || "._:-".contains($0)) })
    else {
      throw VoiceIDClientError.invalidIdentityID
    }
    return value
  }
}

private struct ConsumptionBody: Encodable {
  let token: String
  let action: ProtectedAction
}
