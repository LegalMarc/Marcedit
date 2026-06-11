import SwiftUI
import AppKit

@main
struct MarceditApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @Environment(\.openWindow) private var openWindow
    @AppStorage("appAppearance") private var appAppearance: String = "auto"

    var body: some Scene {
        WindowGroup("Marcedit") {
            ContentView()
                .preferredColorScheme(colorScheme)
        }
        .windowResizability(.contentMinSize) // Allow user resizing beyond minimum content size
        .commands {
            CommandGroup(replacing: .appInfo) {
                Button("About Marcedit") {
                    // This opens the custom AboutView in a new window.
                    openWindow(id: "about")
                }
            }
            
            // Override Quit command (Cmd+Q) to check for unsaved changes
            CommandGroup(replacing: .appTermination) {
                Button("Quit Marcedit") {
                    // Trigger termination through AppDelegate
                    NSApplication.shared.terminate(nil)
                }
                .keyboardShortcut("q", modifiers: .command)
            }
            
            // Settings command (Cmd+,)
            CommandGroup(after: .appSettings) {
                Button("Settings...") {
                    openWindow(id: "settings")
                }
                .keyboardShortcut(",", modifiers: .command)
            }
            
            SidebarCommands()

            // File menu additions
            CommandGroup(replacing: .newItem) {
                Button("Open PDF...") {
                    NotificationCenter.default.post(name: .menuOpenPDF, object: nil)
                }
                .keyboardShortcut("o", modifiers: .command)
            }

            // View menu: zoom controls
            CommandMenu("View") {
                Button("Zoom In") {
                    NotificationCenter.default.post(name: .zoomIn, object: nil)
                }
                .keyboardShortcut("+", modifiers: .command)

                Button("Zoom Out") {
                    NotificationCenter.default.post(name: .zoomOut, object: nil)
                }
                .keyboardShortcut("-", modifiers: .command)

                Button("Fit to Window") {
                    NotificationCenter.default.post(name: .zoomFit, object: nil)
                }
                .keyboardShortcut("0", modifiers: .command)

                Divider()

                Button("Help & Shortcuts") {
                    NotificationCenter.default.post(name: .menuToggleHelp, object: nil)
                }
                .keyboardShortcut("/", modifiers: .command)
            }

            // Document menu: document-level operations
            CommandMenu("Document") {
                Button("Vector Flatten...") {
                    NotificationCenter.default.post(name: .menuVectorFlatten, object: nil)
                }

                Button("View Metadata") {
                    NotificationCenter.default.post(name: .menuViewMetadata, object: nil)
                }

                Button("Scrub Metadata...") {
                    NotificationCenter.default.post(name: .menuScrubMetadata, object: nil)
                }

                Divider()

                Button("Secure Erase...") {
                    NotificationCenter.default.post(name: .menuSecureErase, object: nil)
                }
            }
        }
        
        // Define the window for the About view.
        Window("About Marcedit", id: "about") {
            AboutView()
        }
        .windowResizability(.contentSize) // Makes the About window non-resizable
        
        // Define the window for Settings.
        Window("Settings", id: "settings") {
            SettingsView()
                .preferredColorScheme(colorScheme)
        }
        .windowResizability(.contentSize)
    }
    
    /// Compute the preferred color scheme based on user setting.
    private var colorScheme: ColorScheme? {
        switch appAppearance {
        case "light": return .light
        case "dark": return .dark
        default: return nil // Follow system
        }
    }
}
