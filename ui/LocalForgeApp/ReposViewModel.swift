import Foundation
import Combine
import AppKit

// ── Model ─────────────────────────────────────────────────────────────────────

enum HookStatus {
    case active(version: Int?)
    case outdated(installed: Int, expected: Int)
    case missing
    case replaced
    case pathMissing

    var label: String {
        switch self {
        case .active(let v):
            return v.map { "Active  (v\($0))" } ?? "Active"
        case .outdated(let i, let e):
            return "Outdated  (v\(i) → v\(e))"
        case .missing:
            return "Hook missing"
        case .replaced:
            return "Replaced by another tool"
        case .pathMissing:
            return "Path not found"
        }
    }

    var isHealthy: Bool {
        if case .active = self { return true }
        return false
    }
}

struct ManagedRepo: Identifiable {
    let id   = UUID()
    let path : String
    var status: HookStatus
    var name : String { URL(fileURLWithPath: path).lastPathComponent }
}

// ── ViewModel ─────────────────────────────────────────────────────────────────

@MainActor
final class ReposViewModel: ObservableObject {
    @Published var repos:     [ManagedRepo] = []
    @Published var isLoading: Bool          = false

    private static let reposFile = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".localforge/repos")

    private static let expectedHookVersion = 4   // keep in sync with EXPECTED_HOOK_VERSION in main.rs

    func refresh() {
        isLoading = true
        let loaded = Self.loadRepos()
        repos     = loaded
        isLoading = false
    }

    func upgradeAll() {
        guard let binary = binaryURL else { return }
        for repo in repos {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: binary)
            p.arguments     = ["--install", repo.path]
            try? p.run()
            p.waitUntilExit()
        }
        refresh()
    }

    func removeRepo(_ repo: ManagedRepo) {
        guard let binary = binaryURL else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: binary)
        p.arguments     = ["--uninstall", repo.path]
        try? p.run()
        p.waitUntilExit()
        refresh()
    }

    func revealInFinder(_ repo: ManagedRepo) {
        NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: repo.path)
    }

    // ── Private ───────────────────────────────────────────────────────────────

    private static func loadRepos() -> [ManagedRepo] {
        guard let content = try? String(contentsOf: reposFile, encoding: .utf8) else {
            return []
        }
        return content
            .components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .map { path in
                ManagedRepo(path: path, status: hookStatus(for: path))
            }
    }

    private static func hookStatus(for path: String) -> HookStatus {
        let fm      = FileManager.default
        let repoURL = URL(fileURLWithPath: path)

        guard fm.fileExists(atPath: path) else { return .pathMissing }

        let hookURL = repoURL.appendingPathComponent(".git/hooks/pre-commit")
        guard fm.fileExists(atPath: hookURL.path) else { return .missing }

        guard let content = try? String(contentsOf: hookURL, encoding: .utf8) else {
            return .missing
        }
        guard content.contains("LocalForge") else { return .replaced }

        let version = parseHookVersion(content)
        if let v = version {
            if v < expectedHookVersion { return .outdated(installed: v, expected: expectedHookVersion) }
            if v > expectedHookVersion { return .outdated(installed: v, expected: expectedHookVersion) }
        }
        return .active(version: version)
    }

    private static func parseHookVersion(_ content: String) -> Int? {
        for line in content.components(separatedBy: "\n").prefix(10) {
            let prefix = "# LOCALFORGE_HOOK_VERSION="
            if line.hasPrefix(prefix) {
                return Int(line.dropFirst(prefix.count).trimmingCharacters(in: .whitespaces))
            }
        }
        return nil
    }

    private var binaryURL: String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let installed = "\(home)/.localforge/bin/localforge"
        if FileManager.default.fileExists(atPath: installed) { return installed }
        return nil
    }
}
