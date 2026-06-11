import SwiftUI

/// Settings View for Marcedit
/// Styled to match Marcut appearance with grouped cards.
struct SettingsView: View {
    @ObservedObject private var logManager = LogManager.shared
    @AppStorage("appAppearance") private var appAppearance: String = "auto"
    @AppStorage("pdfAppearance") private var pdfAppearance: String = "auto"
    @AppStorage("preserveMetadata") private var preserveMetadata: Bool = false
    @AppStorage("exhaustiveFontSearch") private var exhaustiveFontSearch: Bool = false
    @Environment(\.dismiss) private var dismiss
    
    // Blue accent to match Marcut
    private let accentBlue = Color(red: 0.42, green: 0.55, blue: 0.82)
    
    var body: some View {
        VStack(spacing: 0) {
            // MARK: - Header
            VStack(spacing: 8) {
                Text("Settings")
                    .font(.title2)
                    .fontWeight(.semibold)
                
                Text("Configure editor behavior and appearance")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            .padding(.top, 24)
            .padding(.bottom, 20)
            
            // MARK: - Settings Content
            ScrollView {
                VStack(spacing: 16) {
                    // === Appearance Section ===
                    SettingsCard {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Appearance")
                                .font(.headline)
                            
                            VStack(alignment: .leading, spacing: 8) {
                                Picker("", selection: $appAppearance) {
                                    Text("Follow System").tag("auto")
                                    Text("Light").tag("light")
                                    Text("Dark").tag("dark")
                                }
                                .pickerStyle(.segmented)
                                .labelsHidden()
                                
                                Text("Choose light, dark, or follow system appearance.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            
                            Divider()
                            
                            // PDF Appearance
                            VStack(alignment: .leading, spacing: 8) {
                                Text("PDF Appearance")
                                    .font(.body)
                                
                                Picker("", selection: $pdfAppearance) {
                                    Text("Follow System").tag("auto")
                                    Text("Light").tag("light")
                                    Text("Dark").tag("dark")
                                }
                                .pickerStyle(.segmented)
                                .labelsHidden()
                                
                                Text("Independent of app theme. Inverts document colors in dark mode.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    
                    // === File Handling Section ===
                    SettingsCard {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("File Handling")
                                .font(.headline)
                            
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Preserve All Metadata")
                                        .font(.body)
                                    Text("Keeps original creation date and attributes when saving.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                Toggle("", isOn: $preserveMetadata)
                                    .labelsHidden()
                                    .toggleStyle(.switch)
                                    .tint(accentBlue)
                            }
                        }
                    }
                    
                    // === Font Replacement Section ===
                    SettingsCard {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Font Replacement")
                                .font(.headline)
                            
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Exhaustive Font Search")
                                        .font(.body)
                                    Text("Enable to scan all system fonts. Disable for faster common font search.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                Toggle("", isOn: $exhaustiveFontSearch)
                                    .labelsHidden()
                                    .toggleStyle(.switch)
                                    .tint(accentBlue)
                            }
                        }
                    }
                    
                    // === Debug Section (Bottom) ===
                    SettingsCard {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Debug")
                                .font(.headline)
                            
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Enable Debug Logging")
                                        .font(.body)
                                    Text("Writes verbose diagnostics for troubleshooting.")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                                Spacer()
                                Toggle("", isOn: $logManager.isLoggingEnabled)
                                    .labelsHidden()
                                    .toggleStyle(.switch)
                                    .tint(accentBlue)
                            }
                            
                            HStack(spacing: 12) {
                                Button("Open App Log") {
                                    logManager.openLog()
                                }
                                .buttonStyle(.bordered)
                                
                                Button("Clear Logs") {
                                    logManager.clearLog()
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)
            }
            
            Spacer()
            
            // MARK: - Footer Buttons
            HStack(spacing: 16) {
                Button("Cancel") {
                    dismiss()
                }
                .buttonStyle(.bordered)
                .keyboardShortcut(.escape, modifiers: [])
                
                Button("Save Settings") {
                    // Settings are auto-saved via @AppStorage
                    dismiss()
                }
                .buttonStyle(.borderedProminent)
                .tint(accentBlue)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.vertical, 20)
        }
        .frame(width: 480, height: 520)
        .background(Theme.backgroundColor)
    }
}

/// Card wrapper for settings sections
struct SettingsCard<Content: View>: View {
    let content: Content
    
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    
    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.cardColor)
            .cornerRadius(12)
    }
}

#Preview {
    SettingsView()
}
