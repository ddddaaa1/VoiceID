// swift-tools-version: 6.0

import PackageDescription

let package = Package(
  name: "VoiceIDKit",
  platforms: [
    .iOS(.v17),
    .macOS(.v14),
  ],
  products: [
    .library(name: "VoiceIDKit", targets: ["VoiceIDKit"])
  ],
  targets: [
    .target(
      name: "VoiceIDKit",
      linkerSettings: [
        .linkedFramework("AVFAudio"),
        .linkedFramework("LocalAuthentication"),
        .linkedFramework("Security"),
      ]
    ),
    .testTarget(name: "VoiceIDKitTests", dependencies: ["VoiceIDKit"]),
  ],
  swiftLanguageModes: [.v6]
)
