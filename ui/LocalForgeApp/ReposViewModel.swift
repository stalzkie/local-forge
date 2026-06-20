import Foundation
import Combine
import AppKit

// ── Model ─────────────────────────────────────────────────────────────────────

struct DiscoveredRepo: Identifiable {
    let id   = UUID()
    let path : String
    var status: HookStatus
    var name : String { URL(fileURLWithPath: path).lastPathComponent }
}

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
    @Published var repos:           [ManagedRepo]    = []
    @Published var discoveredRepos: [DiscoveredRepo] = []
    @Published var isLoading:       Bool             = false
    @Published var isScanning:      Bool             = false
    @Published var scannedFolder:   String?          = nil

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

    func revealDiscoveredInFinder(_ repo: DiscoveredRepo) {
        NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: repo.path)
    }

    func scanFolder(_ folderURL: URL) {
        isScanning    = true
        scannedFolder = folderURL.path
        let fm        = FileManager.default
        let registeredPaths = Set(repos.map { $0.path })

        Task.detached(priority: .userInitiated) {
            var found: [DiscoveredRepo] = []

            // Walk one level deep — enough for ~/Developer or ~/Desktop
            let contents = (try? fm.contentsOfDirectory(
                at: folderURL,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            )) ?? []

            for url in contents {
                guard (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
                else { continue }

                // Check for .git directory — confirms it's a repo
                let gitDir = url.appendingPathComponent(".git")
                guard fm.fileExists(atPath: gitDir.path) else { continue }

                // Skip repos already registered
                let absPath = (try? fm.destinationOfSymbolicLink(atPath: url.path)) ?? url.path
                let canonical = URL(fileURLWithPath: absPath).standardized.path
                guard !registeredPaths.contains(canonical),
                      !registeredPaths.contains(url.path)
                else { continue }

                let status = ReposViewModel.hookStatus(for: url.path)
                found.append(DiscoveredRepo(path: url.path, status: status))
            }

            // Sort: repos with hooks first, then alphabetically
            found.sort {
                if $0.status.isHealthy != $1.status.isHealthy { return $0.status.isHealthy }
                return $0.name < $1.name
            }

            await MainActor.run {
                self.discoveredRepos = found
                self.isScanning      = false
            }
        }
    }

    func installDiscovered(_ repo: DiscoveredRepo) {
        guard let binary = binaryURL else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: binary)
        p.arguments     = ["--install", repo.path]
        try? p.run()
        p.waitUntilExit()
        // Re-scan folder and refresh registered list
        if let folder = scannedFolder {
            scanFolder(URL(fileURLWithPath: folder))
        }
        refresh()
    }

    func clearDiscovered() {
        discoveredRepos = []
        scannedFolder   = nil
    }

    // ── Private ───────────────────────────────────────────────────────────────

    nonisolated private static func loadRepos() -> [ManagedRepo] {
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

    nonisolated static func hookStatus(for path: String) -> HookStatus {
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

    nonisolated private static func parseHookVersion(_ content: String) -> Int? {
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
