import SwiftUI

struct ContentView: View {
    @StateObject private var vm = LogViewModel()
    @State private var selectedTab: AppTab = .monitor

    enum AppTab { case monitor, repos }

    var body: some View {
        VStack(spacing: 0) {
            tabBar
            Divider()
            switch selectedTab {
            case .monitor:
                VStack(spacing: 0) {
                    headerBar
                    Divider()
                    logPane
                    Divider()
                    statsBar
                }
                .onAppear { vm.start() }
            case .repos:
                ReposView()
            }
        }
        .background(Color(nsColor: .black))
        .onDisappear { vm.stop() }
        .onReceive(NotificationCenter.default.publisher(for: .clearLog)) { _ in vm.clear() }
    }

    // ── Tab bar ───────────────────────────────────────────────────────────────

    private var tabBar: some View {
        HStack(spacing: 0) {
            tabButton("Monitor", icon: "terminal", tab: .monitor)
            tabButton("Repos", icon: "folder.badge.gearshape", tab: .repos)
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.top, 6)
        .padding(.bottom, 0)
        .background(Color(nsColor: NSColor(red: 0.08, green: 0.08, blue: 0.10, alpha: 1)))
    }

    private func tabButton(_ label: String, icon: String, tab: AppTab) -> some View {
        let active = selectedTab == tab
        return Button {
            selectedTab = tab
        } label: {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(label)
                    .font(.system(size: 11, weight: .medium))
            }
            .foregroundColor(active ? .white : .gray)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(active ? Color.white.opacity(0.08) : Color.clear)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    // ── Header ────────────────────────────────────────────────────────────────

    private var headerBar: some View {
        HStack(spacing: 10) {
            Image("LocalForgeLogo")
                .resizable()
                .renderingMode(.original)
                .frame(width: 28, height: 28)

            VStack(alignment: .leading, spacing: 1) {
                Text("LocalForge Security Shield")
                    .font(.headline)
                    .foregroundColor(.white)
                Text("v2.0  ·  3-Layer Hybrid Pipeline")
                    .font(.caption)
                    .foregroundColor(.gray)
            }

            Spacer()

            // Layer status pills
            layerPill("L1", subtitle: "AST",    color: .cyan)
            layerPill("L2", subtitle: "ANE",    color: .blue)
            layerPill("L3", subtitle: "Qwen",   color: vm.codeReviewEnabled ? .purple : .gray)

            Divider().frame(height: 28)

            // Code review toggle
            Toggle(isOn: $vm.codeReviewEnabled) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Code Review")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(vm.codeReviewEnabled ? .purple : .gray)
                    Text(vm.codeReviewEnabled ? "ON" : "OFF")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundColor(vm.codeReviewEnabled ? .purple.opacity(0.8) : .gray.opacity(0.6))
                }
            }
            .toggleStyle(.switch)
            .controlSize(.mini)
            .tint(.purple)
            .help("Toggle Qwen L3 code quality assessment on every commit")

            Divider().frame(height: 28)

            StatusDot(isRunning: vm.isRunning)

            Button(vm.isRunning ? "Stop" : "Start") {
                vm.isRunning ? vm.stop() : vm.start()
            }
            .buttonStyle(.borderedProminent)
            .tint(vm.isRunning ? .red : .blue)
            .controlSize(.small)

            Button("Clear") { vm.clear() }
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(nsColor: NSColor(red: 0.08, green: 0.08, blue: 0.10, alpha: 1)))
    }

    // ── Log pane ──────────────────────────────────────────────────────────────

    private var logPane: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical) {
                LazyVStack(alignment: .leading, spacing: 1) {
                    ForEach(vm.lines) { line in
                        LogLineRow(line: line)
                            .id(line.id)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
            }
            .background(Color.black)
            .onChange(of: vm.lines.count) { _ in
                if let last = vm.lines.last {
                    withAnimation(.none) { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    // ── Stats bar ─────────────────────────────────────────────────────────────

    private var statsBar: some View {
        HStack(spacing: 16) {
            statChip(label: "Scanned", value: "\(vm.scannedCount)", color: .cyan)
            statChip(label: "Blocked", value: "\(vm.blockedCount)", color: .red)
            Spacer()
            Text("Assessment reports → ~/.localforge/reports/")
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.gray)
            Button {
                let url = URL(fileURLWithPath: NSString("~/.localforge/reports").expandingTildeInPath)
                try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
                NSWorkspace.shared.activateFileViewerSelecting([url])
            } label: {
                Image(systemName: "folder.badge.magnifyingglass")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundColor(.gray)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(Color(nsColor: NSColor(red: 0.06, green: 0.06, blue: 0.08, alpha: 1)))
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private func layerPill(_ name: String, subtitle: String, color: Color) -> some View {
        VStack(spacing: 1) {
            Text(name)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(color)
            Text(subtitle)
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(color.opacity(0.7))
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(color.opacity(0.12))
        .cornerRadius(4)
    }

    private func statChip(label: String, value: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(.gray)
            Text(value)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(color)
        }
    }
}

// ── Log line row ──────────────────────────────────────────────────────────────

struct LogLineRow: View {
    let line: LogLine

    private var tagColor: Color {
        switch line.level {
        case .info:     return .gray
        case .success:  return .green
        case .warn:     return .yellow
        case .error:    return .red
        case .advisory: return .purple
        case .layer1:   return .cyan
        case .layer2:   return .blue
        case .layer3:   return Color(red: 0.8, green: 0.4, blue: 1.0)
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Text(line.level.tag)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundColor(tagColor)
                .frame(width: 48, alignment: .leading)

            Text(line.text)
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(line.level == .error ? .red.opacity(0.9) : .white.opacity(0.88))
                .textSelection(.enabled)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 1)
        .padding(.horizontal, 4)
        .background(
            line.level == .error
                ? Color.red.opacity(0.07)
                : Color.clear
        )
        .cornerRadius(3)
    }
}

// ── Status dot ────────────────────────────────────────────────────────────────

struct StatusDot: View {
    let isRunning: Bool

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(isRunning ? Color.green : Color.gray)
                .frame(width: 7, height: 7)
                .overlay(
                    isRunning
                        ? Circle().stroke(Color.green.opacity(0.4), lineWidth: 3)
                        : nil
                )
            Text(isRunning ? "Active" : "Stopped")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(isRunning ? .green : .gray)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            (isRunning ? Color.green : Color.gray).opacity(0.1)
        )
        .cornerRadius(6)
    }
}
