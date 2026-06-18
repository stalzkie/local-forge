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

    @Published var lines:     [LogLine] = []
    @Published var isRunning: Bool      = false
    @Published var blockedCount: Int    = 0
    @Published var scannedCount: Int    = 0

    private var process:    Process?
    private var outputPipe: Pipe?

    private var binaryURL: URL {
        // When bundled: .app/Contents/MacOS/localforge-core
        // During development: project root target/release/localforge
        let bundled = Bundle.main.bundleURL
            .appendingPathComponent("Contents/MacOS/localforge-core")
        if FileManager.default.fileExists(atPath: bundled.path) {
            return bundled
        }
        // Dev fallback: walk up from the bundle to find the project root
        var url = Bundle.main.bundleURL
        for _ in 0..<6 {
            url = url.deletingLastPathComponent()
            let candidate = url.appendingPathComponent("target/release/localforge")
            if FileManager.default.fileExists(atPath: candidate.path) {
                return candidate
            }
        }
        return bundled
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    func start() {
        guard !isRunning else { return }

        append("LocalForge v2.0 starting…", level: .info)
        append("Binary: \(binaryURL.path)", level: .info)

        let p = Process()
        p.executableURL = binaryURL
        p.arguments     = []   // no args → TUI mode; stdout/stderr go to the pipe

        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError  = pipe
        outputPipe = pipe
        process    = p

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor [weak self] in self?.ingest(text) }
        }

        p.terminationHandler = { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.isRunning = false
                self?.append("LocalForge process exited.", level: .warn)
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
        process?.terminate()
        process    = nil
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
        // Strip the "[LocalForge] " prefix for cleaner display
        let text = line.hasPrefix("[LocalForge] ") ? String(line.dropFirst(13)) : line

        if l.contains("blocked") || l.contains("err") || l.contains("failed") {
            return (.error, text)
        }
        if l.contains("layer 1") || l.contains("l1") || l.contains("ast") {
            return (.layer1, text)
        }
        if l.contains("layer 2") || l.contains("l2") || l.contains("ane") || l.contains("coreml") {
            return (.layer2, text)
        }
        if l.contains("layer 3") || l.contains("l3") || l.contains("qwen") || l.contains("advisory") || l.contains("adv") {
            return (.layer3, text)
        }
        if l.contains("ok") || l.contains("passed") || l.contains("success") || l.contains("clean") {
            return (.success, text)
        }
        if l.contains("warn") {
            return (.warn, text)
        }
        return (.info, text)
    }

    private func append(_ text: String, level: LogLevel) {
        lines.append(LogLine(level: level, text: text))
        if lines.count > 2000 { lines.removeFirst(lines.count - 2000) }
    }
}
