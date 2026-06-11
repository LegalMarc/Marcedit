// TestBridge.swift
// Marcedit
//
// Glue layer between XCUITest and the running app.
//
// Only active when launched with "--run-ui-tests" (set by XCUIApplication.launchArguments).
// Does two things:
//
//  1. Parses "--test-pdf-path=<path>" and "--test-output-dir=<dir>" launch args
//     and auto-opens the given PDF once Python has initialised.
//
//  2. Registers DistributedNotificationCenter observers that bridge cross-process
//     test commands into the in-process NotificationCenter that EditorViewModel
//     already observes. This lets XCUITest post commands without any UI interaction:
//
//       XCUITest posts DistributedNotification "com.marcedit.test.LoadTestPDF"
//           → TestBridge receives it
//               → posts local .LoadTestPDF notification
//                   → EditorViewModel.add(urls:) opens the PDF
//
// DistributedNotificationCenter only works within the same user session (same UID),
// so there are no cross-user security concerns. Names are reverse-DNS prefixed.

import Foundation
import AppKit

enum TestBridge {

    // MARK: - Distributed notification names (cross-process)

    private static let dnLoadTestPDF   = "com.marcedit.test.LoadTestPDF"
    private static let dnTriggerEdit   = "com.marcedit.test.TriggerEdit"
    private static let dnSetText       = "com.marcedit.test.SetText"
    private static let dnTogglePreview = "com.marcedit.test.TogglePreview"
    private static let dnQueryState    = "com.marcedit.test.QueryState"
    private static let dnSaveEdit      = "com.marcedit.test.SaveEdit"
    private static let dnCancelEdit    = "com.marcedit.test.CancelEdit"

    // MARK: - Setup (call once from AppDelegate)

    /// Must be called from the main thread after Python has been initialised.
    static func setup() {
        guard CommandLine.arguments.contains("--run-ui-tests") else { return }

        NSLog("[TestBridge] Test mode active")

        // 1. Parse launch args
        parseLaunchArgs()

        // 2. Register distributed-notification bridges
        registerDistributedBridges()
    }

    // MARK: - Launch argument parsing

    private static func parseLaunchArgs() {
        let args = CommandLine.arguments

        // --test-pdf-path=<path>
        if let pathArg = args.first(where: { $0.hasPrefix("--test-pdf-path=") }) {
            let path = String(pathArg.dropFirst("--test-pdf-path=".count))
            NSLog("[TestBridge] Will auto-open PDF: \(path)")
            // Delay slightly so Python runtime and EditorViewModel are ready
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                NotificationCenter.default.post(
                    name: .LoadTestPDF,
                    object: nil,
                    userInfo: ["path": path]
                )
            }
        }

        // --test-output-dir=<dir>
        if let dirArg = args.first(where: { $0.hasPrefix("--test-output-dir=") }) {
            let dir = String(dirArg.dropFirst("--test-output-dir=".count))
            UserDefaults.standard.set(dir, forKey: "uitest.outputDir")
            NSLog("[TestBridge] Test output dir: \(dir)")
        }

        if let editArg = args.first(where: { $0.hasPrefix("--test-open-edit-text=") }) {
            let text = String(editArg.dropFirst("--test-open-edit-text=".count))
            let pageIndex = args
                .first(where: { $0.hasPrefix("--test-open-edit-page=") })
                .flatMap { Int(String($0.dropFirst("--test-open-edit-page=".count))) } ?? 0
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.5) {
                NSLog("[TestBridge] Auto-opening edit dialog for text: \(text)")
                NotificationCenter.default.post(
                    name: .TriggerEditDialog,
                    object: nil,
                    userInfo: ["text": text, "pageIndex": pageIndex]
                )
            }
        }
    }

    // MARK: - Distributed notification bridges

    private static var observers: [Any] = []

    private static func registerDistributedBridges() {
        let dnc = DistributedNotificationCenter.default()
        let nc  = NotificationCenter.default

        // Bridge a distributed notification to a local one, forwarding userInfo.
        // Uses explicit `nc` capture to avoid naming conflicts with the `local` param.
        func bridge(distributed distName: String, localName: Notification.Name) {
            let obs = dnc.addObserver(
                forName: NSNotification.Name(distName),
                object: nil,
                queue: .main
            ) { notification in
                NSLog("[TestBridge] \(distName) → \(localName.rawValue)")
                nc.post(name: localName, object: nil, userInfo: notification.userInfo)
            }
            observers.append(obs)
        }

        bridge(distributed: dnLoadTestPDF,   localName: Notification.Name.LoadTestPDF)
        bridge(distributed: dnTriggerEdit,   localName: Notification.Name.TriggerEditDialog)
        bridge(distributed: dnSetText,       localName: Notification.Name.SetEditText)
        bridge(distributed: dnTogglePreview, localName: Notification.Name.TogglePreview)
        bridge(distributed: dnQueryState,    localName: Notification.Name.TestQueryState)

        // SaveEdit / CancelEdit bridge to internal notification names
        let saveObs = dnc.addObserver(
            forName: NSNotification.Name(dnSaveEdit),
            object: nil,
            queue: .main
        ) { _ in
            NSLog("[TestBridge] SaveEdit received")
            nc.post(name: .testSaveEdit, object: nil)
        }
        observers.append(saveObs)

        let cancelObs = dnc.addObserver(
            forName: NSNotification.Name(dnCancelEdit),
            object: nil,
            queue: .main
        ) { _ in
            NSLog("[TestBridge] CancelEdit received")
            nc.post(name: .testCancelEdit, object: nil)
        }
        observers.append(cancelObs)

        NSLog("[TestBridge] Registered \(observers.count) distributed notification bridges")
    }
}

// MARK: - Extra notification names for TestBridge

extension Notification.Name {
    static let testSaveEdit   = Notification.Name("com.marcedit.test.internal.SaveEdit")
    static let testCancelEdit = Notification.Name("com.marcedit.test.internal.CancelEdit")
}
