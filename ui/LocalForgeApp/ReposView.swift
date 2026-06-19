import SwiftUI

struct ReposView: View {
    @StateObject private var vm = ReposViewModel()

    var body: some View {
        VStack(spacing: 0) {
            headerBar
            Divider()
            if vm.repos.isEmpty {
                emptyState
            } else {
                repoList
            }
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

    // ── Repo list ─────────────────────────────────────────────────────────────

    private var repoList: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 1) {
                ForEach(vm.repos) { repo in
                    RepoRow(repo: repo) {
                        vm.revealInFinder(repo)
                    } onRemove: {
                        vm.removeRepo(repo)
                    }
                    Divider().opacity(0.2)
                }
            }
            .padding(.vertical, 4)
        }
        .background(Color.black)
    }

    // ── Empty state ───────────────────────────────────────────────────────────

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "shield.slash")
                .font(.system(size: 36))
                .foregroundColor(.gray.opacity(0.4))
            Text("No repos protected yet")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.gray)
            Text("Run  localforge --install /path/to/repo  to protect a repo")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.gray.opacity(0.6))
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
}

// ── Repo row ──────────────────────────────────────────────────────────────────

struct RepoRow: View {
    let repo:     ManagedRepo
    let onReveal: () -> Void
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Status dot
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .overlay(
                    statusColor == .green
                        ? Circle().stroke(statusColor.opacity(0.35), lineWidth: 3)
                        : nil
                )

            // Repo info
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

            // Status pill
            Text(repo.status.label)
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundColor(statusColor)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(statusColor.opacity(0.12))
                .cornerRadius(4)

            // Action buttons
            Button {
                onReveal()
            } label: {
                Image(systemName: "folder")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.gray)
            .help("Reveal in Finder")

            Button {
                onRemove()
            } label: {
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
