@preconcurrency import AVFAudio
import Foundation

public enum AudioCaptureStatus: Sendable, Equatable {
  case inactive
  case recording(route: String)
  case processing
  case failed
}

public typealias AudioCaptureStatusHandler = @Sendable (AudioCaptureStatus) async -> Void

public struct CapturedVoiceCommand: Sendable, Equatable {
  public let pcmWave: Data
  public let durationSeconds: Double
  public let sourceSampleRate: Double
  public let routeName: String

  public init(
    pcmWave: Data,
    durationSeconds: Double,
    sourceSampleRate: Double,
    routeName: String
  ) {
    self.pcmWave = pcmWave
    self.durationSeconds = durationSeconds
    self.sourceSampleRate = sourceSampleRate
    self.routeName = routeName
  }
}

public enum AudioCaptureError: Error, Sendable {
  case invalidDuration
  case inputUnavailable
  case unsupportedInputFormat
  case noAudioCaptured
}

public protocol VoiceCommandCapturing: Sendable {
  func capture(durationSeconds: Double) async throws -> CapturedVoiceCommand
}

/// Bounded, user-initiated capture. The host should render every status transition as a visible
/// consent indicator and must include `NSMicrophoneUsageDescription` in its app configuration.
public actor AVAudioEngineVoiceCommandCapture: VoiceCommandCapturing {
  private let engine: AVAudioEngine
  private let onStatus: AudioCaptureStatusHandler

  public init(onStatus: @escaping AudioCaptureStatusHandler = { _ in }) {
    engine = AVAudioEngine()
    self.onStatus = onStatus
  }

  public func capture(durationSeconds: Double = 3.0) async throws -> CapturedVoiceCommand {
    guard (0.5...10.0).contains(durationSeconds) else {
      throw AudioCaptureError.invalidDuration
    }
    #if os(iOS)
      let session = AVAudioSession.sharedInstance()
      #if compiler(>=6.3)
        let bluetoothInput: AVAudioSession.CategoryOptions = .allowBluetoothHFP
      #else
        let bluetoothInput: AVAudioSession.CategoryOptions = .allowBluetooth
      #endif
      try session.setCategory(.record, mode: .measurement, options: [bluetoothInput])
      try session.setActive(true)
      let routeName = session.currentRoute.inputs.first?.portName ?? "unknown-input"
    #else
      let routeName = "system-default-input"
    #endif

    let input = engine.inputNode
    let format = input.inputFormat(forBus: 0)
    guard format.sampleRate > 0, format.channelCount > 0 else {
      await onStatus(.failed)
      throw AudioCaptureError.inputUnavailable
    }
    guard format.commonFormat == .pcmFormatFloat32, !format.isInterleaved else {
      await onStatus(.failed)
      throw AudioCaptureError.unsupportedInputFormat
    }

    let store = CaptureBufferStore(channelCount: Int(format.channelCount))
    input.installTap(onBus: 0, bufferSize: 1_024, format: format) { buffer, _ in
      store.append(buffer)
    }
    defer {
      engine.stop()
      input.removeTap(onBus: 0)
      #if os(iOS)
        try? AVAudioSession.sharedInstance().setActive(
          false, options: [.notifyOthersOnDeactivation])
      #endif
    }

    engine.prepare()
    try engine.start()
    await onStatus(.recording(route: routeName))
    do {
      try await Task.sleep(for: .seconds(durationSeconds))
    } catch {
      await onStatus(.failed)
      throw error
    }
    engine.stop()
    await onStatus(.processing)
    let source = store.snapshot()
    guard !source.isEmpty else {
      await onStatus(.failed)
      throw AudioCaptureError.noAudioCaptured
    }
    let target = PCM16WaveEncoder.linearResample(
      source,
      sourceRate: format.sampleRate,
      targetRate: 16_000
    )
    let wave = PCM16WaveEncoder.encode(samples: target, sampleRate: 16_000)
    await onStatus(.inactive)
    return CapturedVoiceCommand(
      pcmWave: wave,
      durationSeconds: Double(target.count) / 16_000.0,
      sourceSampleRate: format.sampleRate,
      routeName: routeName
    )
  }
}

public enum PCM16WaveEncoder {
  public static func encode(samples: [Float], sampleRate: Int) -> Data {
    precondition(sampleRate > 0)
    let dataBytes = samples.count * 2
    var output = Data()
    output.append(contentsOf: "RIFF".utf8)
    output.appendLittleEndian(UInt32(36 + dataBytes))
    output.append(contentsOf: "WAVEfmt ".utf8)
    output.appendLittleEndian(UInt32(16))
    output.appendLittleEndian(UInt16(1))
    output.appendLittleEndian(UInt16(1))
    output.appendLittleEndian(UInt32(sampleRate))
    output.appendLittleEndian(UInt32(sampleRate * 2))
    output.appendLittleEndian(UInt16(2))
    output.appendLittleEndian(UInt16(16))
    output.append(contentsOf: "data".utf8)
    output.appendLittleEndian(UInt32(dataBytes))
    for sample in samples {
      let bounded = max(-1.0, min(1.0, sample))
      let value = Int16(max(-32_768, min(32_767, Int((bounded * 32_767).rounded()))))
      output.appendLittleEndian(UInt16(bitPattern: value))
    }
    return output
  }

  static func linearResample(
    _ samples: [Float],
    sourceRate: Double,
    targetRate: Double
  ) -> [Float] {
    guard !samples.isEmpty, sourceRate != targetRate else { return samples }
    let outputCount = max(1, Int((Double(samples.count) * targetRate / sourceRate).rounded()))
    let ratio = sourceRate / targetRate
    return (0..<outputCount).map { outputIndex in
      let position = min(Double(outputIndex) * ratio, Double(samples.count - 1))
      let left = Int(position)
      let right = min(left + 1, samples.count - 1)
      let fraction = Float(position - Double(left))
      return samples[left] * (1 - fraction) + samples[right] * fraction
    }
  }
}

private final class CaptureBufferStore: @unchecked Sendable {
  private let lock = NSLock()
  private let channelCount: Int
  private var samples: [Float] = []

  init(channelCount: Int) {
    self.channelCount = channelCount
  }

  func append(_ buffer: AVAudioPCMBuffer) {
    guard let channels = buffer.floatChannelData else { return }
    let frameCount = Int(buffer.frameLength)
    lock.lock()
    defer { lock.unlock() }
    samples.reserveCapacity(samples.count + frameCount)
    for frame in 0..<frameCount {
      var mono: Float = 0
      for channel in 0..<channelCount {
        mono += channels[channel][frame]
      }
      samples.append(mono / Float(channelCount))
    }
  }

  func snapshot() -> [Float] {
    lock.lock()
    defer { lock.unlock() }
    return samples
  }
}

extension Data {
  fileprivate mutating func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
    var littleEndian = value.littleEndian
    Swift.withUnsafeBytes(of: &littleEndian) { append(contentsOf: $0) }
  }
}
