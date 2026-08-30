import SwiftUI
import VoiceIDKit

struct CompanionView: View {
  @EnvironmentObject private var model: CompanionViewModel
  @State private var showCredential = false

  var body: some View {
    NavigationStack {
      ZStack {
        LinearGradient(
          colors: [Color.indigo.opacity(0.22), Color(uiColor: .systemBackground)],
          startPoint: .topLeading,
          endPoint: .center
        )
        .ignoresSafeArea()

        ScrollView {
          VStack(spacing: 18) {
            hero
            captureCard
            configurationCard
            actionCard
            if let result = model.result {
              ResultCard(result: result)
            }
            safetyNotice
          }
          .padding()
        }
      }
      .navigationTitle("VoiceID Companion")
      .navigationBarTitleDisplayMode(.inline)
    }
  }

  private var hero: some View {
    VStack(spacing: 10) {
      Image(systemName: "waveform.badge.shield")
        .font(.system(size: 52, weight: .semibold))
        .foregroundStyle(.indigo)
        .accessibilityHidden(true)
      Text("Voice-bound action authorization")
        .font(.title2.bold())
        .multilineTextAlignment(.center)
      Text("Capture a short command, request the server policy, and consume an allowed grant once.")
        .font(.subheadline)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.center)
    }
    .padding(.vertical, 8)
  }

  private var captureCard: some View {
    Card {
      HStack(spacing: 14) {
        ZStack {
          Circle()
            .fill(model.isBusy ? Color.red.opacity(0.15) : Color.indigo.opacity(0.12))
            .frame(width: 52, height: 52)
          Image(systemName: model.isBusy ? "waveform" : "mic.fill")
            .font(.title2)
            .foregroundStyle(model.isBusy ? .red : .indigo)
            .symbolEffect(.variableColor.iterative, isActive: model.isBusy)
        }
        VStack(alignment: .leading, spacing: 4) {
          Text(model.captureStatus)
            .font(.headline)
          Label(model.routeName, systemImage: "airpodspro")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        Spacer()
      }
    }
  }

  private var configurationCard: some View {
    Card(title: "Connection") {
      VStack(spacing: 14) {
        LabeledTextField(label: "Server URL", text: $model.baseURL)
          .textInputAutocapitalization(.never)
          .keyboardType(.URL)
        LabeledTextField(label: "Identity ID", text: $model.identityID)
          .textInputAutocapitalization(.never)
        LabeledTextField(label: "Device ID", text: $model.deviceID)
          .textInputAutocapitalization(.never)

        VStack(alignment: .leading, spacing: 6) {
          Text("Device credential")
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
          HStack {
            Group {
              if showCredential {
                TextField("Paste the configured credential", text: $model.credential)
              } else {
                SecureField("Paste the configured credential", text: $model.credential)
              }
            }
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()

            Button {
              showCredential.toggle()
            } label: {
              Image(systemName: showCredential ? "eye.slash" : "eye")
            }
            .accessibilityLabel(showCredential ? "Hide credential" : "Show credential")
          }
          .padding(12)
          .background(
            Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))

          HStack {
            Text(model.credentialStatus)
              .font(.caption)
              .foregroundStyle(.secondary)
            Spacer()
            Button("Save securely") {
              Task { await model.saveCredential() }
            }
            .buttonStyle(.bordered)
          }
        }

        Text(
          "127.0.0.1 targets the Mac-hosted API from the simulator. A physical iPhone requires an HTTPS endpoint reachable from the phone."
        )
        .font(.caption)
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
  }

  private var actionCard: some View {
    Card(title: "Protected action") {
      VStack(spacing: 14) {
        Picker("Action", selection: $model.selectedAction) {
          ForEach(ProtectedAction.allCases, id: \.self) { action in
            Label(action.displayName, systemImage: action.symbol).tag(action)
          }
        }
        .pickerStyle(.menu)
        .frame(maxWidth: .infinity, alignment: .leading)

        HStack {
          Label(model.selectedAction.displayName, systemImage: model.selectedAction.symbol)
          Spacer()
          Text(model.selectedAction.expectedRiskLabel)
            .font(.caption.bold())
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(model.selectedAction.riskTint.opacity(0.14), in: Capsule())
            .foregroundStyle(model.selectedAction.riskTint)
        }

        Button {
          Task { await model.authorize() }
        } label: {
          HStack {
            if model.isBusy {
              ProgressView().tint(.white)
            } else {
              Image(systemName: "mic.badge.plus")
            }
            Text(model.isBusy ? "Authorizing…" : "Record and authorize")
              .fontWeight(.semibold)
          }
          .frame(maxWidth: .infinity)
          .padding(.vertical, 6)
        }
        .buttonStyle(.borderedProminent)
        .tint(.indigo)
        .disabled(model.isBusy)
      }
    }
  }

  private var safetyNotice: some View {
    Label(
      "Experimental portfolio system. A voice match is not proof of identity or liveness.",
      systemImage: "exclamationmark.shield"
    )
    .font(.footnote)
    .foregroundStyle(.secondary)
    .padding(.bottom, 12)
  }
}

private struct Card<Content: View>: View {
  var title: String?
  let content: Content

  init(title: String? = nil, @ViewBuilder content: () -> Content) {
    self.title = title
    self.content = content()
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      if let title {
        Text(title)
          .font(.headline)
      }
      content
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 20))
    .overlay {
      RoundedRectangle(cornerRadius: 20)
        .stroke(Color.primary.opacity(0.06), lineWidth: 1)
    }
  }
}

private struct LabeledTextField: View {
  let label: String
  @Binding var text: String

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(label)
        .font(.caption.weight(.semibold))
        .foregroundStyle(.secondary)
      TextField(label, text: $text)
        .autocorrectionDisabled()
        .padding(12)
        .background(
          Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
    }
  }
}

private struct ResultCard: View {
  let result: CompanionResult

  var body: some View {
    Card(title: "Policy result") {
      VStack(alignment: .leading, spacing: 12) {
        Label(result.title, systemImage: result.symbol)
          .font(.title3.bold())
          .foregroundStyle(result.tint)
        Text(result.message)
          .font(.subheadline)

        if let authorization = result.authorization {
          Divider()
          DetailRow(label: "Decision", value: authorization.decision.rawValue.uppercased())
          DetailRow(label: "Server risk", value: authorization.risk.rawValue.capitalized)
          DetailRow(label: "Policy", value: authorization.authorizationPolicyID)
          if let score = authorization.verification.speakerScore {
            DetailRow(
              label: "Speaker score", value: score.formatted(.number.precision(.fractionLength(3))))
          }
          DetailRow(
            label: "Reasons",
            value: authorization.reasons.isEmpty
              ? "None returned" : authorization.reasons.joined(separator: ", ")
          )
        }
        if let grantID = result.grantID {
          DetailRow(label: "Consumed grant", value: String(grantID.prefix(12)) + "…")
        }
      }
    }
  }
}

private struct DetailRow: View {
  let label: String
  let value: String

  var body: some View {
    HStack(alignment: .top) {
      Text(label)
        .foregroundStyle(.secondary)
      Spacer(minLength: 20)
      Text(value)
        .multilineTextAlignment(.trailing)
        .textSelection(.enabled)
    }
    .font(.caption)
  }
}

extension ProtectedAction {
  fileprivate var displayName: String {
    switch self {
    case .playMedia: "Play media"
    case .personalizeAssistant: "Personalize assistant"
    case .switchProfile: "Switch profile"
    case .readPrivateContent: "Read private content"
    case .sendMessage: "Send message"
    case .makePurchase: "Make purchase"
    case .unlockPhysicalAccess: "Unlock physical access"
    }
  }

  fileprivate var symbol: String {
    switch self {
    case .playMedia: "play.fill"
    case .personalizeAssistant: "person.wave.2.fill"
    case .switchProfile: "person.2.fill"
    case .readPrivateContent: "envelope.badge.shield.half.filled.fill"
    case .sendMessage: "message.fill"
    case .makePurchase: "cart.fill"
    case .unlockPhysicalAccess: "lock.open.fill"
    }
  }

  fileprivate var expectedRiskLabel: String {
    switch self {
    case .playMedia, .personalizeAssistant, .switchProfile: "Expected low risk"
    case .readPrivateContent: "Expected moderate risk"
    case .sendMessage, .makePurchase, .unlockPhysicalAccess: "Expected high risk"
    }
  }

  fileprivate var riskTint: Color {
    switch self {
    case .playMedia, .personalizeAssistant, .switchProfile: .green
    case .readPrivateContent: .orange
    case .sendMessage, .makePurchase, .unlockPhysicalAccess: .red
    }
  }
}
