import Foundation
import Combine

// ── Log level ─────────────────────────────────────────────────────────────────

enum LogLevel {
    case info, success, warn, error, advisory, layer1, layer2, layer3

    var tag: String {
        switch self {
        case .info:     return " INFO "
        case .success:  return "  OK  "
        case .warn:     return " WARN "
        case .error:    return " ERR  "
        case .advisory: return " ADV  "
        case .layer1:   return "  L1  "
        case .layer2:   return "  L2  "
        case .layer3:   return "  L3  "
        }
    }
}

// ── Log line ──────────────────────────────────────────────────────────────────

struct LogLine: Identifiable {
    let id    = UUID()
    let level : LogLevel
    let text  : String
    let date  : Date = .now
}

// ── ViewModel ─────────────────────────────────────────────────────────────────

@MainActor
final class LogViewModel: ObservableObject {

    @Published var lines:            [LogLine] = []
    @Published var isRunning:        Bool      = false
    @Published var blockedCount:     Int       = 0
    @Published var scannedCount:     Int       = 0
    @Published var codeReviewEnabled: Bool     = true {
        didSet {
            UserDefaults.standard.set(codeReviewEnabled, forKey: "codeReviewEnabled")
            writeReviewPref()
        }
    }

    private var process:    Process?
    private var outputPipe: Pipe?

    private static let prefFile: URL = {
        let home = FileManager.default.homeDirectoryForCurrentUser
        return home.appendingPathComponent(".localforge/prefs")
    }()

    init() {
        codeReviewEnabled = UserDefaults.standard.object(forKey: "codeReviewEnabled") as? Bool ?? true
    }

    private var binaryURL: URL {
        // 1. Production: binary bundled inside .app at Contents/MacOS/localforge-core
        let bundled = Bundle.main.bundleURL
            .appendingPathComponent("Contents/MacOS/localforge-core")
        if FileManager.default.fileExists(atPath: bundled.path) {
            return bundled
        }

        // 2. Development: SOURCE_ROOT baked into Info.plist by Xcode as LFSourceRoot
        //    Points to the project root (ui/../ = local-forge/)
        if let sourceRoot = Bundle.main.object(forInfoDictionaryKey: "LFSourceRoot") as? String {
            let devRelease = URL(fileURLWithPath: sourceRoot)
                .appendingPathComponent("target/release/localforge")
            if FileManager.default.fileExists(atPath: devRelease.path) {
                return devRelease
            }
            let devDebug = URL(fileURLWithPath: sourceRoot)
                .appendingPathComponent("target/debug/localforge")
            if FileManager.default.fileExists(atPath: devDebug.path) {
                return devDebug
            }
        }

        return bundled
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    func start() {
        guard !isRunning else { return }

        writeReviewPref()
        append("LocalForge v2.0 starting…", level: .info)
        append("Binary: \(binaryURL.path)", level: .info)
        append("Code review: \(codeReviewEnabled ? "enabled" : "disabled")", level: .info)

        let p = Process()
        p.executableURL = binaryURL
        p.arguments     = ["--monitor"]

        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError  = pipe
        outputPipe = pipe
        process    = p

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty {
                handle.readabilityHandler = nil
                return
            }
            guard let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor [weak self] in self?.ingest(text) }
        }

        let pipeHandle = pipe.fileHandleForReading
        p.terminationHandler = { [weak self] proc in
            pipeHandle.readabilityHandler = nil
            Task { @MainActor [weak self] in
                self?.isRunning = false
                self?.append("LocalForge process exited (code \(proc.terminationStatus)).", level: .warn)
            }
        }

        do {
            try p.run()
            isRunning = true
            append("Engine started (PID \(p.processIdentifier)).", level: .success)
            append("3-Layer pipeline: L1 AST  •  L2 CoreML/ANE  •  L3 Qwen/MLX", level: .info)
        } catch {
            append("Failed to launch binary: \(error.localizedDescription)", level: .error)
            append("Build with:  cargo build --release", level: .warn)
        }
    }

    func stop() {
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        process?.terminate()
        process    = nil
        outputPipe = nil
        isRunning  = false
        append("Engine stopped.", level: .warn)
    }

    func clear() {
        lines        = []
        blockedCount = 0
        scannedCount = 0
    }

    // ── Parsing ───────────────────────────────────────────────────────────────

    private func ingest(_ raw: String) {
        raw.components(separatedBy: "\n")
           .map { $0.trimmingCharacters(in: .whitespaces) }
           .filter { !$0.isEmpty }
           .forEach { line in
               let (level, text) = classify(line)
               append(text, level: level)

               if level == .error && line.contains("BLOCKED") { blockedCount += 1 }
               if line.contains("Scan passed") || line.contains("BLOCKED") { scannedCount += 1 }
           }
    }

    private func classify(_ line: String) -> (LogLevel, String) {
        let l = line.lowercased()
        let text = line.hasPrefix("[LocalForge] ") ? String(line.dropFirst(13)) : line

        if l.contains("blocked") || l.contains("failed") { return (.error, text) }
        if l.contains("[security]")                       { return (.error, text) }
        if l.contains("[bug_risk]")                       { return (.warn,  text) }
        if l.contains("[quality]")                        { return (.advisory, text) }
        if l.contains("layer 1") || l.contains("  l1  ") || l.contains("ast") { return (.layer1, text) }
        if l.contains("layer 2") || l.contains("  l2  ") || l.contains("ane") || l.contains("coreml") { return (.layer2, text) }
        if l.contains("layer 3") || l.contains("  l3  ") || l.contains("qwen") || l.contains("advisory") { return (.layer3, text) }
        if l.contains("full report:")                     { return (.advisory, text) }
        if l.contains("passed") || l.contains("clean") || l.contains("  ok  ") { return (.success, text) }
        if l.contains("warn")                             { return (.warn, text) }
        if l.contains("err")                              { return (.error, text) }
        return (.info, text)
    }

    private func writeReviewPref() {
        let url = Self.prefFile
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let value = codeReviewEnabled ? "1" : "0"
        try? value.write(to: url, atomically: true, encoding: .utf8)
    }

    private func append(_ text: String, level: LogLevel) {
        lines.append(LogLine(level: level, text: text))
        if lines.count > 2000 { lines.removeFirst(lines.count - 2000) }
    }
}
