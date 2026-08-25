import Foundation
import Security

public enum CredentialStoreError: Error, Sendable {
  case unavailable
  case unexpectedStatus(OSStatus)
}

public actor KeychainDeviceCredentialStore: DeviceCredentialProviding {
  private let service: String
  private let account: String

  public init(service: String = "dev.voiceid.device-credential", account: String) {
    self.service = service
    self.account = account
  }

  public func store(_ credential: String) throws {
    let base: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
    SecItemDelete(base as CFDictionary)
    var insert = base
    insert[kSecValueData as String] = Data(credential.utf8)
    insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    let status = SecItemAdd(insert as CFDictionary, nil)
    guard status == errSecSuccess else {
      throw CredentialStoreError.unexpectedStatus(status)
    }
  }

  public func credential() async throws -> String {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound {
      throw CredentialStoreError.unavailable
    }
    guard status == errSecSuccess else {
      throw CredentialStoreError.unexpectedStatus(status)
    }
    guard let data = result as? Data, let value = String(data: data, encoding: .utf8) else {
      throw CredentialStoreError.unavailable
    }
    return value
  }
}
