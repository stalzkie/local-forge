import SwiftUI
import AppKit

struct ReposView: View {
    @StateObject private var vm = ReposViewModel()

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            content
            Divider()
            footerBar
        }
        .background(Color.black)
        .onAppear { vm.refresh() }
    }

    // ── Header ────────────────────────────────────────────────────────────────

    private var headerBar: some View {
        HStack(spacing: 10) {
            Image(systemName: "folder.badge.gearshape")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.cyan)

            VStack(alignment: .leading, spacing: 1) {
                Text("Protected Repositories")
                    .font(.headline)
                    .foregroundColor(.white)
                Text("\(vm.repos.count) repo\(vm.repos.count == 1 ? "" : "s") registered")
                    .font(.caption)
                    .foregroundColor(.gray)
            }

            Spacer()

            // Scan folder button
            Button {
                pickFolder()
            } label: {
                Label("Scan Folder", systemImage: "folder.badge.plus")
                    .font(.system(size: 11))
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .tint(.cyan)
            .help("Scan a folder to discover git repos and install LocalForge into them")

            Button {
                vm.upgradeAll()
            } label: {
                Label("Upgrade All", systemImage: "arrow.triangle.2.circlepath")
                    .font(.system(size: 11))
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .tint(.cyan)
            .help("Re-install the latest hook into every registered repo")

            Button {
                vm.refresh()
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 12))
            }
            .buttonStyle(.plain)
            .foregroundColor(.gray)
            .help("Refresh repo status")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(nsColor: NSColor(red: 0.08, green: 0.08, blue: 0.10, alpha: 1)))
    }

    // ── Content ───────────────────────────────────────────────────────────────

    @ViewBuilder
    private var content: some View {
        let hasRegistered  = !vm.repos.isEmpty
        let hasDiscovered  = !vm.discoveredRepos.isEmpty

        if !hasRegistered && !hasDiscovered && vm.scannedFolder == nil {
            emptyState
        } else {
            ScrollView(.vertical) {
                LazyVStack(spacing: 1, pinnedViews: .sectionHeaders) {
                    // ── Registered repos ──────────────────────────────────────
                    if hasRegistered {
                        Section {
                            ForEach(vm.repos) { repo in
                                RepoRow(repo: repo) {
                                    vm.revealInFinder(repo)
                                } onRemove: {
                                    vm.removeRepo(repo)
                                }
                                Divider().opacity(0.2)
                            }
                        } header: {
                            sectionHeader(
                                title: "Protected  (\(vm.repos.count))",
                                icon: "checkmark.shield.fill",
                                color: .cyan
                            )
                        }
                    }

                    // ── Discovered repos ──────────────────────────────────────
                    if hasDiscovered || vm.scannedFolder != nil {
                        Section {
                            if vm.isScanning {
                                HStack(spacing: 8) {
                                    ProgressView()
                                        .controlSize(.small)
                                        .tint(.cyan)
                                    Text("Scanning…")
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundColor(.gray)
                                }
                                .padding(.vertical, 20)
                                .frame(maxWidth: .infinity)
                            } else if vm.discoveredRepos.isEmpty {
                                Text("No unprotected git repos found in this folder.")
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(.gray.opacity(0.6))
                                    .padding(.vertical, 20)
                                    .frame(maxWidth: .infinity)
                            } else {
                                ForEach(vm.discoveredRepos) { repo in
                                    DiscoveredRepoRow(repo: repo) {
                                        vm.revealDiscoveredInFinder(repo)
                                    } onInstall: {
                                        vm.installDiscovered(repo)
                                    }
                                    Divider().opacity(0.2)
                                }
                            }
                        } header: {
                            HStack {
                                sectionHeader(
                                    title: vm.scannedFolder.map { "Found in \(URL(fileURLWithPath: $0).lastPathComponent)  (\(vm.discoveredRepos.count))" } ?? "Discovered",
                                    icon: "magnifyingglass",
                                    color: .yellow
                                )
                                Spacer()
                                Button {
                                    vm.clearDiscovered()
                                } label: {
                                    Image(systemName: "xmark")
                                        .font(.system(size: 9))
                                        .foregroundColor(.gray.opacity(0.6))
                                }
                                .buttonStyle(.plain)
                                .padding(.trailing, 14)
                                .help("Clear discovered repos")
                            }
                        }
                    }

                    // ── Empty registered state (but has discovered) ────────────
                    if !hasRegistered && !hasDiscovered && vm.scannedFolder != nil && !vm.isScanning {
                        emptyState
                    }
                }
                .padding(.vertical, 4)
            }
            .background(Color.black)
        }
    }

    // ── Empty state ───────────────────────────────────────────────────────────

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "shield.slash")
                .font(.system(size: 36))
                .foregroundColor(.gray.opacity(0.4))
            Text("No repos protected yet")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.gray)
            Text("Run  localforge --install /path/to/repo  to protect a repo,")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray.opacity(0.6))
            Text("or click  Scan Folder  to discover repos on your machine.")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray.opacity(0.6))

            Button {
                pickFolder()
            } label: {
                Label("Scan Folder", systemImage: "folder.badge.plus")
                    .font(.system(size: 12))
            }
            .buttonStyle(.borderedProminent)
            .tint(.cyan)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
    }

    // ── Footer ────────────────────────────────────────────────────────────────

    private var footerBar: some View {
        HStack {
            let healthy = vm.repos.filter { $0.status.isHealthy }.count
            let total   = vm.repos.count
            Text("\(healthy)/\(total) hooks active")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(healthy == total && total > 0 ? .green : .yellow)
            Spacer()
            Text("~/.localforge/repos")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.gray.opacity(0.5))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(Color(nsColor: NSColor(red: 0.06, green: 0.06, blue: 0.08, alpha: 1)))
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private func sectionHeader(title: String, icon: String, color: Color) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(color)
            Text(title)
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundColor(color)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: NSColor(red: 0.06, green: 0.08, blue: 0.10, alpha: 1)))
    }

    private func pickFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories  = true
        panel.canChooseFiles        = false
        panel.allowsMultipleSelection = false
        panel.message   = "Select a folder to scan for git repos"
        panel.prompt    = "Scan"
        panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Developer")
            .exists
            ? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Developer")
            : FileManager.default.homeDirectoryForCurrentUser

        if panel.runModal() == .OK, let url = panel.url {
            vm.scanFolder(url)
        }
    }
}

// ── Registered repo row ───────────────────────────────────────────────────────

struct RepoRow: View {
    let repo:     ManagedRepo
    let onReveal: () -> Void
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .overlay(
                    statusColor == .green
                        ? Circle().stroke(statusColor.opacity(0.35), lineWidth: 3)
                        : nil
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(repo.name)
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundColor(.white)
                Text(repo.path)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.gray.opacity(0.6))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Spacer()

            Text(repo.status.label)
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundColor(statusColor)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(statusColor.opacity(0.12))
                .cornerRadius(4)

            Button { onReveal() } label: {
                Image(systemName: "folder")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.gray)
            .help("Reveal in Finder")

            Button { onRemove() } label: {
                Image(systemName: "minus.circle")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.gray.opacity(0.6))
            .help("Remove from LocalForge")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color.black)
    }

    private var statusColor: Color {
        switch repo.status {
        case .active:      return .green
        case .outdated:    return .yellow
        case .missing:     return .orange
        case .replaced:    return .orange
        case .pathMissing: return .red
        }
    }
}

// ── Discovered repo row ───────────────────────────────────────────────────────

struct DiscoveredRepoRow: View {
    let repo:      DiscoveredRepo
    let onReveal:  () -> Void
    let onInstall: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Unprotected indicator
            Circle()
                .strokeBorder(Color.yellow.opacity(0.6), lineWidth: 1.5)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(repo.name)
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .foregroundColor(.white.opacity(0.85))
                Text(repo.path)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.gray.opacity(0.5))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Spacer()

            // Hook status pill (missing/replaced/outdated)
            Text(hookBadgeLabel)
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundColor(hookBadgeColor)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(hookBadgeColor.opacity(0.12))
                .cornerRadius(4)

            Button { onReveal() } label: {
                Image(systemName: "folder")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.gray)
            .help("Reveal in Finder")

            // Install button
            Button {
                onInstall()
            } label: {
                Label("Protect", systemImage: "shield.lefthalf.filled")
                    .font(.system(size: 10, weight: .medium))
            }
            .buttonStyle(.borderedProminent)
            .tint(.cyan)
            .controlSize(.small)
            .help("Install LocalForge hook into this repo")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(nsColor: NSColor(red: 0.04, green: 0.06, blue: 0.08, alpha: 1)))
    }

    private var hookBadgeLabel: String {
        switch repo.status {
        case .missing:     return "No hook"
        case .replaced:    return "Other hook"
        case .outdated(let i, let e): return "Hook v\(i)→v\(e)"
        case .active:      return "Active"
        case .pathMissing: return "Not found"
        }
    }

    private var hookBadgeColor: Color {
        switch repo.status {
        case .active:      return .green
        case .outdated:    return .yellow
        case .missing:     return .gray
        case .replaced:    return .orange
        case .pathMissing: return .red
        }
    }
}

// ── URL helper ────────────────────────────────────────────────────────────────

private extension URL {
    var exists: Bool { FileManager.default.fileExists(atPath: path) }
}
