// TestHelpers.swift
// MarceditUITests
//
// XCUIApplication extensions and test-time helpers that drive the Marcedit UI.
//
// Accessibility identifiers used in this file:
//   PDFViewer              — InteractivePDFView / PDFView container
//   EditTextInput          — TextEditor / NSTextView in EditLineView
//   SaveButton             — "Save" button in EditLineView
//   CancelButton           — "Cancel" button in EditLineView
//   PreviewToggle          — preview on/off checkbox / button
//   SmartQuotesToggle      — smart quotes checkbox
//   LoadingIndicator       — spinner shown while Python is working
//   FontSearchCancelButton — cancel font search button
//   FontSearchProgress     — font search progress bar
//   FontSearchResults      — font results scroll view
//   DetectedFontLabel      — original font text in dialog header
//   CurrentFontLabel       — current font text in dialog header
//   FileList               — sidebar scroll view
//   AddPDFButton           — add PDF drop zone button
//   FileRow_<uuid>         — individual file row
//   FileRow_Revert_<uuid>  — revert button in selected file row
//   FileRow_Save_<uuid>    — save button in selected file row
//   FileRow_SaveAs_<uuid>  — save-as button in selected file row
//   FileRow_Close_<uuid>   — close button in selected file row
//   ZoomOutButton          — zoom out button
//   ZoomInButton           — zoom in button
//   ZoomFitButton          — fit to window button
//   NudgeButtonUp/Down/Left/Right — nudge arrow buttons
//   SizeUp / SizeDown      — size adjustment buttons
//   KernUp / KernDown      — kerning adjustment buttons
//   VectorFlattenButton    — vector flatten button in DocumentControlsView
//   SecureEraseButton      — secure erase button in DocumentControlsView
//   ViewMetadataButton     — view metadata button in DocumentControlsView
//   ScrubMetadataButton    — scrub metadata button in DocumentControlsView
//   MD5ChecksumLabel       — MD5 checksum text in DocumentControlsView
//   SidebarToggleButton    — sidebar collapse toggle button
//   OpenPDFButton          — "Open PDF File" button in empty state
//   ProcessingOverlay      — overlay shown during Python operations
//   CancelProcessingButton — cancel button in processing overlay
//   ToastMessage           — error/success toast container
//   HelpButton             — help & shortcuts button
//   EditDialogHeader       — draggable header of edit dialog
//   DialogResizeHandle     — resize handle of edit dialog

import XCTest
import Foundation

// MARK: - XCUIApplication helpers

extension XCUIApplication {

    // ---------------------------------------------------------------------------
    // MARK: App Launch
    // ---------------------------------------------------------------------------

    /// Copies the corpus input PDF to a unique writable test-artifact location,
    /// then launches the app with `--run-ui-tests`, `--test-pdf-path=`, and
    /// `--test-output-dir=`. Returns the output dir path so tests can run
    /// PDFVerifier against it.
    @discardableResult
    func launchWithCorpusCase(_ corpusCase: CorpusCase, autoOpenEdit: Bool = false) -> String {
        let fm = FileManager.default
        let tmpDir = stableUITestTempRoot()
            + "marcedit_uitest_\(corpusCase.id)_\(Int(Date().timeIntervalSince1970 * 1000))/"
        let tmpPDF = tmpDir + "input.pdf"
        let outputDir = tmpDir + "output/"
        do {
            try fm.createDirectory(atPath: tmpDir,
                                   withIntermediateDirectories: true,
                                   attributes: nil)
            try? fm.removeItem(atPath: tmpPDF)
            try fm.copyItem(atPath: corpusCase.pdfPath, toPath: tmpPDF)
            try fm.createDirectory(atPath: outputDir,
                                   withIntermediateDirectories: true,
                                   attributes: nil)
            print("[XCUICaseResult] prepared \(tmpDir)")
        } catch {
            XCTFail("Failed to prepare UI-test case directory \(tmpDir): \(error)")
        }

        resetMarceditTestLaunchArguments()
        var args = [
            "--run-ui-tests",
            "--test-pdf-path=\(tmpPDF)",
            "--test-output-dir=\(outputDir)"
        ]
        if autoOpenEdit {
            args += [
                "--test-open-edit-text=\(corpusCase.targetText)",
                "--test-open-edit-page=\(corpusCase.pageIndex)"
            ]
        }
        launchArguments += args
        launch()
        return outputDir
    }

    /// Launches the app with a specific PDF file path (no corpus required).
    /// Returns the output directory path.
    @discardableResult
    func launchWithPDFPath(_ pdfPath: String) -> String {
        let fm = FileManager.default
        let stamp = Int(Date().timeIntervalSince1970 * 1000)
        let tmpDir = stableUITestTempRoot() + "marcedit_uitest_direct_\(stamp)/"
        let tmpPDF = tmpDir + "input.pdf"
        let outputDir = tmpDir + "output/"
        do {
            try fm.createDirectory(atPath: tmpDir, withIntermediateDirectories: true)
            try? fm.removeItem(atPath: tmpPDF)
            try fm.copyItem(atPath: pdfPath, toPath: tmpPDF)
            try fm.createDirectory(atPath: outputDir, withIntermediateDirectories: true)
        } catch {
            XCTFail("Failed to prepare UI-test PDF directory \(tmpDir): \(error)")
        }

        resetMarceditTestLaunchArguments()
        launchArguments += [
            "--run-ui-tests",
            "--test-pdf-path=\(tmpPDF)",
            "--test-output-dir=\(outputDir)"
        ]
        launch()
        return outputDir
    }

    private func stableUITestTempRoot() -> String {
        let envRoot = ProcessInfo.processInfo.environment["MARCEDIT_XCUI_CASE_ROOT"]
        if let envRoot, !envRoot.isEmpty, canCreateChild(in: envRoot) {
            return envRoot.hasSuffix("/") ? envRoot : envRoot + "/"
        }

        let cacheBase = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)
            .first ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        let cacheRoot = cacheBase.appendingPathComponent("MarceditUITests", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: cacheRoot, withIntermediateDirectories: true)
        } catch {
            XCTFail("Failed to create UI-test cache root \(cacheRoot.path): \(error)")
        }
        return cacheRoot.path.hasSuffix("/") ? cacheRoot.path : cacheRoot.path + "/"
    }

    private func canCreateChild(in root: String) -> Bool {
        let normalizedRoot = root.hasSuffix("/") ? root : root + "/"
        let probe = normalizedRoot + ".marcedit_probe_\(UUID().uuidString)"
        do {
            try FileManager.default.createDirectory(atPath: probe, withIntermediateDirectories: true)
            try? FileManager.default.removeItem(atPath: probe)
            return true
        } catch {
            return false
        }
    }

    private func resetMarceditTestLaunchArguments() {
        launchArguments = launchArguments.filter { arg in
            !arg.hasPrefix("--run-ui-tests")
            && !arg.hasPrefix("--test-pdf-path=")
            && !arg.hasPrefix("--test-output-dir=")
            && !arg.hasPrefix("--test-open-edit-text=")
            && !arg.hasPrefix("--test-open-edit-page=")
        }
    }

    // ---------------------------------------------------------------------------
    // MARK: App Readiness
    // ---------------------------------------------------------------------------

    /// Waits until PDFViewer exists and any loading spinner is gone.
    @discardableResult
    func waitForPDFReady(timeout: TimeInterval = 90) -> Bool {
        let viewer = descendants(matching: .any)
            .matching(identifier: "PDFViewer")
            .firstMatch
        let exists = viewer.waitForExistence(timeout: timeout)

        // Also wait for any spinner to disappear
        let spinner = descendants(matching: .progressIndicator)
            .matching(identifier: "LoadingIndicator")
            .firstMatch
        if spinner.exists {
            let start = Date()
            while spinner.exists && Date().timeIntervalSince(start) < timeout {
                Thread.sleep(forTimeInterval: 0.2)
            }
        }
        return exists
    }

    /// Waits for the app window to appear (does not require a PDF to be loaded).
    @discardableResult
    func waitForAppWindow(timeout: TimeInterval = 15) -> Bool {
        windows.firstMatch.waitForExistence(timeout: timeout)
    }

    // ---------------------------------------------------------------------------
    // MARK: PDF Viewer Interaction
    // ---------------------------------------------------------------------------

    /// Double-clicks at the given fraction of PDFViewer's frame to open the edit dialog.
    func openEditDialogAt(normalizedX nx: Double, normalizedY ny: Double) {
        let viewer = descendants(matching: .any)
            .matching(identifier: "PDFViewer")
            .firstMatch

        XCTAssertTrue(viewer.waitForExistence(timeout: 10),
                      "PDFViewer not found — cannot click")

        let frame  = viewer.frame
        let target = CGPoint(
            x: frame.origin.x + frame.width  * CGFloat(nx),
            y: frame.origin.y + frame.height * CGFloat(ny)
        )

        let event = viewer.coordinate(withNormalizedOffset: CGVector(dx: nx, dy: ny))
        event.doubleClick()

        Thread.sleep(forTimeInterval: 0.4)
        _ = target
    }

    /// Opens the edit dialog for a corpus case. It first exercises the UI click path,
    /// then falls back to the test bridge when PDFKit accessibility geometry makes
    /// normalized page coordinates land outside the rendered page.
    func openEditDialog(for corpusCase: CorpusCase) {
        openEditDialogAt(normalizedX: corpusCase.clickNormX,
                         normalizedY: corpusCase.clickNormY)
        if waitForEditDialog(timeout: 3) { return }

        let textPredicate = NSPredicate(
            format: "label CONTAINS[c] %@ OR value CONTAINS[c] %@",
            corpusCase.targetText,
            corpusCase.targetText
        )
        let textElement = descendants(matching: .staticText)
            .matching(textPredicate)
            .firstMatch
        if textElement.waitForExistence(timeout: 3) {
            textElement.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.85))
                .doubleClick()
        }
        Thread.sleep(forTimeInterval: 0.4)
    }

    /// Single-click used for selection-accuracy tests.
    func singleClickAt(normalizedX nx: Double, normalizedY ny: Double) {
        let viewer = descendants(matching: .any)
            .matching(identifier: "PDFViewer")
            .firstMatch
        XCTAssertTrue(viewer.waitForExistence(timeout: 10))
        let coord = viewer.coordinate(withNormalizedOffset: CGVector(dx: nx, dy: ny))
        coord.click()
        Thread.sleep(forTimeInterval: 0.3)
    }

    // ---------------------------------------------------------------------------
    // MARK: Edit Dialog
    // ---------------------------------------------------------------------------

    /// Returns true when the EditTextInput field appears (sheet opened).
    @discardableResult
    func waitForEditDialog(timeout: TimeInterval = 15) -> Bool {
        let textField = descendants(matching: .textField)
            .matching(identifier: "EditTextInput")
            .firstMatch
        let textView = descendants(matching: .textView)
            .matching(identifier: "EditTextInput")
            .firstMatch
        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            if textField.exists || textView.exists { return true }
            Thread.sleep(forTimeInterval: 0.2)
        }
        return textField.exists || textView.exists
    }

    /// Returns true when the edit dialog is gone (sheet closed).
    @discardableResult
    func waitForEditDialogClosed(timeout: TimeInterval = 10) -> Bool {
        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            let tfExists = descendants(matching: .textField)
                .matching(identifier: "EditTextInput").firstMatch.exists
            let tvExists = descendants(matching: .textView)
                .matching(identifier: "EditTextInput").firstMatch.exists
            if !tfExists && !tvExists { return true }
            Thread.sleep(forTimeInterval: 0.15)
        }
        return false
    }

    /// Reads the current value from EditTextInput.
    func readSelectedText() -> String {
        let tf = descendants(matching: .textField)
            .matching(identifier: "EditTextInput")
            .firstMatch
        if tf.exists { return tf.value as? String ?? "" }

        let tv = descendants(matching: .textView)
            .matching(identifier: "EditTextInput")
            .firstMatch
        return tv.value as? String ?? ""
    }

    /// Selects all text in EditTextInput then types the replacement.
    func typeReplacement(_ text: String) {
        let tf = descendants(matching: .textField)
            .matching(identifier: "EditTextInput")
            .firstMatch
        let tv = descendants(matching: .textView)
            .matching(identifier: "EditTextInput")
            .firstMatch

        let field: XCUIElement = tf.exists ? tf : tv
        field.click()
        field.typeKey("a", modifierFlags: .command)
        field.typeText(text)
    }

    /// Clicks SaveButton and waits for the edit sheet to close.
    func saveEdit(timeout: TimeInterval = 10) {
        let btn = descendants(matching: .button)
            .matching(identifier: "SaveButton")
            .firstMatch
        XCTAssertTrue(btn.waitForExistence(timeout: 5), "SaveButton not found")
        btn.click()

        let sheet = descendants(matching: .sheet).firstMatch
        let start = Date()
        while sheet.exists && Date().timeIntervalSince(start) < timeout {
            Thread.sleep(forTimeInterval: 0.2)
        }
    }

    /// Clicks CancelButton and waits briefly.
    func cancelEdit() {
        let btn = descendants(matching: .button)
            .matching(identifier: "CancelButton")
            .firstMatch
        XCTAssertTrue(btn.waitForExistence(timeout: 5), "CancelButton not found")
        btn.click()
        Thread.sleep(forTimeInterval: 0.3)
    }

    /// Toggles the Preview checkbox (tries checkbox first, then button fallback).
    func togglePreview() {
        let toggle = descendants(matching: .checkBox)
            .matching(identifier: "PreviewToggle")
            .firstMatch
        if toggle.exists {
            toggle.click()
            return
        }
        let btn = descendants(matching: .button)
            .matching(identifier: "PreviewToggle")
            .firstMatch
        if btn.exists { btn.click() }
    }

    // ---------------------------------------------------------------------------
    // MARK: Sidebar
    // ---------------------------------------------------------------------------

    /// Selects a file in the sidebar by matching a FileRow whose label contains `name`.
    /// Returns true if the row was found and tapped.
    @discardableResult
    func selectFileInSidebar(name: String) -> Bool {
        let rows = descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_' AND NOT (identifier CONTAINS 'Revert') AND NOT (identifier CONTAINS 'Save') AND NOT (identifier CONTAINS 'Close')"))
        for i in 0..<rows.count {
            let row = rows.element(boundBy: i)
            if row.label.localizedCaseInsensitiveContains(name) {
                row.click()
                Thread.sleep(forTimeInterval: 0.3)
                return true
            }
        }
        return false
    }

    /// Returns all FileRow elements currently in the sidebar (base rows only, not action buttons).
    func sidebarFileRows() -> [XCUIElement] {
        let query = descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_' AND NOT (identifier CONTAINS '_Revert_') AND NOT (identifier CONTAINS '_Save_') AND NOT (identifier CONTAINS '_SaveAs_') AND NOT (identifier CONTAINS '_Close_')"))
        var result: [XCUIElement] = []
        for i in 0..<query.count {
            result.append(query.element(boundBy: i))
        }
        return result
    }

    /// Clicks the Add PDF button to open the file importer.
    func clickAddPDFButton() {
        let btn = descendants(matching: .button)
            .matching(identifier: "AddPDFButton")
            .firstMatch
        XCTAssertTrue(btn.waitForExistence(timeout: 5), "AddPDFButton not found")
        btn.click()
        Thread.sleep(forTimeInterval: 0.5)
    }

    // ---------------------------------------------------------------------------
    // MARK: Document Controls
    // ---------------------------------------------------------------------------

    /// Clicks a document control button identified by `identifier`.
    @discardableResult
    func clickDocumentControl(identifier: String) -> Bool {
        let btn = descendants(matching: .button)
            .matching(NSPredicate(format: "identifier == %@", identifier))
            .firstMatch
        guard btn.waitForExistence(timeout: 5) else { return false }
        btn.click()
        Thread.sleep(forTimeInterval: 0.4)
        return true
    }

    /// Reads the MD5 checksum value from the MD5ChecksumLabel, if present.
    func readMD5Checksum() -> String? {
        let label = descendants(matching: .staticText)
            .matching(identifier: "MD5ChecksumLabel")
            .firstMatch
        if label.waitForExistence(timeout: 5) {
            return label.value as? String
        }
        return nil
    }

    // ---------------------------------------------------------------------------
    // MARK: Alert Handling
    // ---------------------------------------------------------------------------

    /// Waits for an alert with the given title to appear and clicks the specified button.
    /// Returns true if the alert was found and the button clicked.
    @discardableResult
    func waitForAlert(title: String, clickButton buttonLabel: String, timeout: TimeInterval = 10) -> Bool {
        let alert = alerts[title]
        guard alert.waitForExistence(timeout: timeout) else { return false }
        let btn = alert.buttons[buttonLabel]
        guard btn.exists else { return false }
        btn.click()
        Thread.sleep(forTimeInterval: 0.3)
        return true
    }

    /// Returns true if any alert matching the title exists.
    func alertExists(title: String, timeout: TimeInterval = 5) -> Bool {
        alerts[title].waitForExistence(timeout: timeout)
    }

    // ---------------------------------------------------------------------------
    // MARK: Zoom Controls
    // ---------------------------------------------------------------------------

    /// Clicks the zoom in button.
    func clickZoomIn() {
        let btn = descendants(matching: .button)
            .matching(identifier: "ZoomInButton")
            .firstMatch
        if btn.waitForExistence(timeout: 5) { btn.click() }
    }

    /// Clicks the zoom out button.
    func clickZoomOut() {
        let btn = descendants(matching: .button)
            .matching(identifier: "ZoomOutButton")
            .firstMatch
        if btn.waitForExistence(timeout: 5) { btn.click() }
    }

    /// Clicks the fit-to-window zoom button.
    func clickZoomFit() {
        let btn = descendants(matching: .button)
            .matching(identifier: "ZoomFitButton")
            .firstMatch
        if btn.waitForExistence(timeout: 5) { btn.click() }
    }

    // ---------------------------------------------------------------------------
    // MARK: Font Controls
    // ---------------------------------------------------------------------------

    /// Clicks a nudge button `times` times. Direction: "up", "down", "left", "right".
    func clickNudge(direction: String, times: Int = 1) {
        let identifiers: [String: String] = [
            "up": "NudgeButtonUp",
            "down": "NudgeButtonDown",
            "left": "NudgeButtonLeft",
            "right": "NudgeButtonRight"
        ]
        guard let identifier = identifiers[direction.lowercased()] else { return }
        let btn = descendants(matching: .button)
            .matching(identifier: identifier)
            .firstMatch
        guard btn.waitForExistence(timeout: 5) else { return }
        for _ in 0..<times { btn.click(); Thread.sleep(forTimeInterval: 0.05) }
    }

    /// Clicks SizeUp or SizeDown button `times` times.
    func clickSize(up: Bool, times: Int = 1) {
        let identifier = up ? "SizeUp" : "SizeDown"
        let btn = descendants(matching: .button)
            .matching(identifier: identifier)
            .firstMatch
        guard btn.waitForExistence(timeout: 5) else { return }
        for _ in 0..<times { btn.click(); Thread.sleep(forTimeInterval: 0.05) }
    }

    /// Clicks KernUp or KernDown button `times` times.
    func clickKern(up: Bool, times: Int = 1) {
        let identifier = up ? "KernUp" : "KernDown"
        let btn = descendants(matching: .button)
            .matching(identifier: identifier)
            .firstMatch
        guard btn.waitForExistence(timeout: 5) else { return }
        for _ in 0..<times { btn.click(); Thread.sleep(forTimeInterval: 0.05) }
    }

    // ---------------------------------------------------------------------------
    // MARK: Sidebar Toggle & Help
    // ---------------------------------------------------------------------------

    /// Toggles the sidebar via the SidebarToggleButton.
    func toggleSidebar() {
        let btn = descendants(matching: .button)
            .matching(identifier: "SidebarToggleButton")
            .firstMatch
        if btn.waitForExistence(timeout: 5) {
            btn.click()
            Thread.sleep(forTimeInterval: 0.4)
        }
    }

    /// Returns true if the sidebar FileList is visible.
    var isSidebarVisible: Bool {
        descendants(matching: .any)
            .matching(identifier: "FileList")
            .firstMatch
            .exists
    }

    /// Clicks HelpButton to open the help sheet.
    func openHelpSheet() {
        let btn = descendants(matching: .button)
            .matching(identifier: "HelpButton")
            .firstMatch
        if btn.waitForExistence(timeout: 5) {
            btn.click()
            Thread.sleep(forTimeInterval: 0.4)
        } else {
            // Fallback: keyboard shortcut (Cmd+?)
            typeKey("/", modifierFlags: [.command, .shift])
            Thread.sleep(forTimeInterval: 0.4)
        }
    }

    // ---------------------------------------------------------------------------
    // MARK: Processing Overlay
    // ---------------------------------------------------------------------------

    /// Returns true if the processing overlay is currently visible.
    var isProcessingOverlayVisible: Bool {
        descendants(matching: .any)
            .matching(identifier: "ProcessingOverlay")
            .firstMatch
            .exists
    }

    /// Waits for the processing overlay to appear (up to `timeout` seconds).
    @discardableResult
    func waitForProcessingOverlay(timeout: TimeInterval = 10) -> Bool {
        descendants(matching: .any)
            .matching(identifier: "ProcessingOverlay")
            .firstMatch
            .waitForExistence(timeout: timeout)
    }

    /// Waits for the processing overlay to disappear.
    @discardableResult
    func waitForProcessingOverlayToDisappear(timeout: TimeInterval = 60) -> Bool {
        let overlay = descendants(matching: .any)
            .matching(identifier: "ProcessingOverlay")
            .firstMatch
        let start = Date()
        while overlay.exists && Date().timeIntervalSince(start) < timeout {
            Thread.sleep(forTimeInterval: 0.25)
        }
        return !overlay.exists
    }

    // ---------------------------------------------------------------------------
    // MARK: Toast
    // ---------------------------------------------------------------------------

    /// Waits for a toast message whose value contains `text`.
    @discardableResult
    func waitForToast(containing text: String, timeout: TimeInterval = 5) -> Bool {
        let toast = descendants(matching: .any)
            .matching(identifier: "ToastMessage")
            .firstMatch
        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            if toast.exists {
                let value = toast.value as? String ?? toast.label
                if value.localizedCaseInsensitiveContains(text) { return true }
            }
            Thread.sleep(forTimeInterval: 0.15)
        }
        return false
    }

    // ---------------------------------------------------------------------------
    // MARK: Test Automation (Distributed Notifications)
    // ---------------------------------------------------------------------------

    /// Posts a DistributedNotification from the test process.
    /// This reaches the app via TestBridge.
    func postDistributed(_ name: String, userInfo: [AnyHashable: Any]? = nil) {
        DistributedNotificationCenter.default().postNotificationName(
            NSNotification.Name(name),
            object: nil,
            userInfo: userInfo,
            deliverImmediately: true
        )
    }

    // ---------------------------------------------------------------------------
    // MARK: Output File Polling
    // ---------------------------------------------------------------------------

    /// Polls the outputDir for a saved PDF file. Returns the path or nil.
    func waitForOutputFile(in dir: String, timeout: TimeInterval = 15) -> String? {
        let fm = FileManager.default
        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            if let files = try? fm.contentsOfDirectory(atPath: dir),
               let pdf = files.first(where: { $0.hasSuffix(".pdf") }) {
                return (dir as NSString).appendingPathComponent(pdf)
            }
            Thread.sleep(forTimeInterval: 0.4)
        }
        return nil
    }

    // ---------------------------------------------------------------------------
    // MARK: Polling Utility
    // ---------------------------------------------------------------------------

    /// Polls `condition` every `pollInterval` until it returns true or `timeout` elapses.
    func waitUntil(timeout: TimeInterval, pollInterval: TimeInterval = 0.2, condition: () -> Bool) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            Thread.sleep(forTimeInterval: pollInterval)
        }
        return condition()
    }
}
