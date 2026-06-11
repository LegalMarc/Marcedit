//
//  FeatureFlags.swift
//  Marcedit
//
//  Feature flag system for gradual rollout of new architecture.
//  Allows A/B testing, gradual migration, and instant rollback.
//
//  Created: 2026-01-23
//

import Foundation

/// Feature flags for controlling new architecture rollout
enum FeatureFlags {

    // MARK: - Architecture V2 Flags

    /// Enable new font matching service (multi-factor scoring)
    static var useNewFontMatcher: Bool {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "FeatureFlag.UseNewFontMatcher")
        #else
        return UserDefaults.standard.object(forKey: "FeatureFlag.UseNewFontMatcher") as? Bool ?? false
        #endif
    }

    /// Enable atomic file operations
    static var useAtomicFileOps: Bool {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "FeatureFlag.UseAtomicFileOps")
        #else
        return UserDefaults.standard.object(forKey: "FeatureFlag.UseAtomicFileOps") as? Bool ?? false
        #endif
    }

    /// Enable command-based undo/redo (vs file-based)
    static var useCommandUndo: Bool {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "FeatureFlag.UseCommandUndo")
        #else
        return UserDefaults.standard.object(forKey: "FeatureFlag.UseCommandUndo") as? Bool ?? false
        #endif
    }

    /// Enable state machine for edit sessions
    static var useStateMachine: Bool {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "FeatureFlag.UseStateMachine")
        #else
        return UserDefaults.standard.object(forKey: "FeatureFlag.UseStateMachine") as? Bool ?? false
        #endif
    }

    // MARK: - Performance Flags

    /// Enable early exit in font search (fixes bug #1)
    static var useFontSearchEarlyExit: Bool {
        return true  // Always enabled - proven 20x speedup
    }

    /// Enable font search caching
    static var useFontSearchCache: Bool {
        return true  // Always enabled - no downsides
    }

    // MARK: - Experimental Flags

    /// Enable XPC Python service (Week 2)
    static var useXPCPythonService: Bool {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "FeatureFlag.UseXPCPythonService")
        #else
        return false  // Not ready for release yet
        #endif
    }

    /// Enable visual regression testing
    static var enableVisualTesting: Bool {
        #if DEBUG
        return UserDefaults.standard.bool(forKey: "FeatureFlag.EnableVisualTesting")
        #else
        return false
        #endif
    }

    // MARK: - Helper Methods

    #if DEBUG
    /// Enable all V2 architecture features (for testing)
    static func enableAllV2Features() {
        UserDefaults.standard.set(true, forKey: "FeatureFlag.UseNewFontMatcher")
        UserDefaults.standard.set(true, forKey: "FeatureFlag.UseAtomicFileOps")
        UserDefaults.standard.set(true, forKey: "FeatureFlag.UseCommandUndo")
        UserDefaults.standard.set(true, forKey: "FeatureFlag.UseStateMachine")
        UserDefaults.standard.set(true, forKey: "FeatureFlag.UseXPCPythonService")
    }

    /// Disable all V2 architecture features (rollback)
    static func disableAllV2Features() {
        UserDefaults.standard.set(false, forKey: "FeatureFlag.UseNewFontMatcher")
        UserDefaults.standard.set(false, forKey: "FeatureFlag.UseAtomicFileOps")
        UserDefaults.standard.set(false, forKey: "FeatureFlag.UseCommandUndo")
        UserDefaults.standard.set(false, forKey: "FeatureFlag.UseStateMachine")
        UserDefaults.standard.set(false, forKey: "FeatureFlag.UseXPCPythonService")
    }
    #endif

    /// Get status summary for debugging
    static func getStatusSummary() -> String {
        return """
        Feature Flags Status:
        - NewFontMatcher: \(useNewFontMatcher)
        - AtomicFileOps: \(useAtomicFileOps)
        - CommandUndo: \(useCommandUndo)
        - StateMachine: \(useStateMachine)
        - XPCPythonService: \(useXPCPythonService)
        - VisualTesting: \(enableVisualTesting)
        """
    }
}

// MARK: - Settings View Extension

#if DEBUG
extension FeatureFlags {
    /// View for toggling feature flags in debug builds
    struct DebugFlagsView: View {
        @State private var useFontMatcher = FeatureFlags.useNewFontMatcher
        @State private var useFileOps = FeatureFlags.useAtomicFileOps
        @State private var useUndo = FeatureFlags.useCommandUndo
        @State private var useStateMachine = FeatureFlags.useStateMachine
        @State private var useXPC = FeatureFlags.useXPCPythonService

        var body: some View {
            Form {
                Section("Architecture V2") {
                    Toggle("New Font Matcher", isOn: $useFontMatcher)
                        .onChange(of: useFontMatcher) { _, new in
                            UserDefaults.standard.set(new, forKey: "FeatureFlag.UseNewFontMatcher")
                        }

                    Toggle("Atomic File Operations", isOn: $useFileOps)
                        .onChange(of: useFileOps) { _, new in
                            UserDefaults.standard.set(new, forKey: "FeatureFlag.UseAtomicFileOps")
                        }

                    Toggle("Command-Based Undo", isOn: $useUndo)
                        .onChange(of: useUndo) { _, new in
                            UserDefaults.standard.set(new, forKey: "FeatureFlag.UseCommandUndo")
                        }

                    Toggle("State Machine", isOn: $useStateMachine)
                        .onChange(of: useStateMachine) { _, new in
                            UserDefaults.standard.set(new, forKey: "FeatureFlag.UseStateMachine")
                        }
                }

                Section("Experimental") {
                    Toggle("XPC Python Service", isOn: $useXPC)
                        .onChange(of: useXPC) { _, new in
                            UserDefaults.standard.set(new, forKey: "FeatureFlag.UseXPCPythonService")
                        }
                }

                Section("Quick Actions") {
                    Button("Enable All V2 Features") {
                        FeatureFlags.enableAllV2Features()
                        updateToggles()
                    }

                    Button("Disable All V2 Features (Rollback)") {
                        FeatureFlags.disableAllV2Features()
                        updateToggles()
                    }
                    .foregroundColor(.red)
                }

                Section("Status") {
                    Text(FeatureFlags.getStatusSummary())
                        .font(.system(.caption, design: .monospaced))
                }
            }
            .navigationTitle("Feature Flags")
        }

        private func updateToggles() {
            useFontMatcher = FeatureFlags.useNewFontMatcher
            useFileOps = FeatureFlags.useAtomicFileOps
            useUndo = FeatureFlags.useCommandUndo
            useStateMachine = FeatureFlags.useStateMachine
            useXPC = FeatureFlags.useXPCPythonService
        }
    }
}

import SwiftUI
#endif
