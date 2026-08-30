// swift-tools-version: 6.0

import PackageDescription

let package = Package(
  name: "VoiceIDCompanionCore",
  platforms: [.iOS(.v17), .macOS(.v14)],
  products: [
    .library(name: "VoiceIDCompanionCore", targets: ["VoiceIDCompanionCore"])
  ],
  dependencies: [
    .package(path: "../../../../sdk/swift/VoiceIDKit")
  ],
  targets: [
    .target(
      name: "VoiceIDCompanionCore",
      dependencies: [.product(name: "VoiceIDKit", package: "VoiceIDKit")]
    ),
    .testTarget(
      name: "VoiceIDCompanionCoreTests",
      dependencies: ["VoiceIDCompanionCore", .product(name: "VoiceIDKit", package: "VoiceIDKit")]
    ),
  ],
  swiftLanguageModes: [.v6]
)
