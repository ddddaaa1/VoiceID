import SwiftUI

@main
struct VoiceIDCompanionApp: App {
  @StateObject private var model = CompanionViewModel()

  var body: some Scene {
    WindowGroup {
      CompanionView()
        .environmentObject(model)
    }
  }
}
