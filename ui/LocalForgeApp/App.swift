import SwiftUI

@main
struct LocalForgeApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 860, minHeight: 540)
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("LocalForge") {
                Button("Clear Log") {
                    NotificationCenter.default.post(name: .clearLog, object: nil)
                }
                .keyboardShortcut("k", modifiers: .command)

                Divider()

                Button("Reveal Advisory Log in Finder") {
                    let url = URL(fileURLWithPath: NSString("~/.localforge/advisory_log").expandingTildeInPath)
                    NSWorkspace.shared.activateFileViewerSelecting([url])
                }
            }
        }
    }
}

extension Notification.Name {
    static let clearLog = Notification.Name("com.stalwrites.localforge.clearLog")
}
