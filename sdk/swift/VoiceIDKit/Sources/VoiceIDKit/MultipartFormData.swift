import Foundation

struct MultipartFormData: Sendable {
  let boundary: String
  private(set) var data = Data()

  init(boundary: String) {
    self.boundary = boundary
  }

  mutating func appendField(name: String, value: String) {
    append("--\(boundary)\r\n")
    append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
    append("\(value)\r\n")
  }

  mutating func appendFile(name: String, filename: String, contentType: String, bytes: Data) {
    append("--\(boundary)\r\n")
    append(
      "Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n"
    )
    append("Content-Type: \(contentType)\r\n\r\n")
    data.append(bytes)
    append("\r\n")
  }

  mutating func finish() {
    append("--\(boundary)--\r\n")
  }

  private mutating func append(_ value: String) {
    data.append(value.data(using: .utf8)!)
  }
}
