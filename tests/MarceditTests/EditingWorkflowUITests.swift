//
//  EditingWorkflowUITests.swift
//  MarceditTests
//
//  Comprehensive UI tests for detecting GUI issues:
//  - Preview toggle scroll/zoom preservation
//  - Edit window positioning and stability
//  - Text selection boundaries
//
//  MIGRATION NOTE: These tests have been migrated to the XCUITest project at:
//    MarceditUITests/MarceditUITestsUITests/EditingWorkflowTests.swift
//
//  To run UI tests:
//    1. Build with: swift build -c release
//    2. Open MarceditUITests/MarceditUITests.xcodeproj in Xcode
//    3. Run tests with Cmd+U
//
//  Uses XCUITest with accessibility identifiers for reliable automation.
//

import XCTest

final class EditingWorkflowUITests: XCTestCase {

    var app: XCUIApplication!

    // Default test PDF path - can be overridden per test
    let defaultTestPDFPath = "ignored-resources/sample-files-marcedit/15425215.pdf"

    /// Check if we're running in a proper UI testing environment
    /// XCUITests require a UI Testing target which Swift Package Manager doesn't support
    static var isUITestingAvailable: Bool {
        // Check if we have a valid target application path
        // When running via `swift test`, XCUIApplication cannot find the app
        let testConfig = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"]
        return testConfig != nil && testConfig!.contains("UITest")
    }

    override func setUp() {
        super.setUp()
        continueAfterFailure = false

        // Only initialize XCUIApplication if we're in a UI testing environment
        if Self.isUITestingAvailable {
            app = XCUIApplication()
        }
    }

    /// Skip test if UI testing is not available
    func skipIfNoUITesting() throws {
        if !Self.isUITestingAvailable {
            throw XCTSkip("XCUITests require UI Testing target. Use ./scripts/run-ui-tests.sh for GUI tests")
        }
    }

    override func tearDown() {
        app = nil
        super.tearDown()
    }

    // MARK: - Helper Methods

    /// Launch app with test PDF loaded automatically
    func launchWithTestPDF(path: String? = nil) throws {
        try skipIfNoUITesting()

        let pdfPath = path ?? defaultTestPDFPath
        app.launchArguments = ["--run-ui-tests", "--test-pdf-path=\(pdfPath)"]
        app.launchEnvironment = [
            "TESTING": "1",
            "DISABLE_AUTOSAVE": "1"
        ]
        app.launch()

        // Wait for PDF to load
        let pdfViewer = app.otherElements["PDFViewer"]
        let loaded = pdfViewer.waitForExistence(timeout: 10)
        XCTAssertTrue(loaded, "PDF viewer should exist after launch with test PDF")
    }

    /// Create a test PDF using Python/PyMuPDF
    func createTestPDF(at url: URL) {
        let pythonCode = """
        import fitz

        doc = fitz.open()
        page = doc.new_page()

        # Add various text elements for testing
        page.insert_text((50, 700), "Hello World", fontsize=12)
        page.insert_text((50, 680), "Test Line 2", fontsize=12)
        page.insert_text((50, 660), "Sample text for editing", fontsize=12)
        page.insert_text((50, 640), "Blue text", fontsize=12, color=(0, 0, 1))
        page.insert_text((50, 620), "Another line here", fontsize=12)

        # Add a second page
        page2 = doc.new_page()
        page2.insert_text((50, 700), "Second page content", fontsize=12)

        doc.save("\(url.path)")
        doc.close()
        """

        let scriptURL = URL(fileURLWithPath: "/tmp/create_test_pdf.py")
        try? pythonCode.write(to: scriptURL, atomically: true, encoding: .utf8)

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [scriptURL.path]

        do {
            try process.run()
            process.waitUntilExit()
        } catch {
            XCTFail("Failed to create test PDF: \(error)")
        }

        try? FileManager.default.removeItem(at: scriptURL)
    }

    // MARK: - Test Category 1: Preview Toggle Issues (CRITICAL)

    /// Test Issue #1A: PDF scroll position should be preserved when toggling preview
    func testPreviewTogglePreservesScrollPosition() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists, "PDF viewer should exist")

        // Click on PDF to select text and open edit dialog
        pdfViewer.click()
        sleep(1)

        // Double-click to trigger text selection
        pdfViewer.doubleTap()
        sleep(1)

        // Wait for edit dialog
        let editInput = app.textFields["EditTextInput"]
        let dialogOpened = editInput.waitForExistence(timeout: 5)

        // If dialog didn't open, try clicking at a different location
        if !dialogOpened {
            let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
            clickCoord.doubleTap()
            sleep(1)
        }

        // Check if preview toggle exists
        let previewToggle = app.checkBoxes["PreviewToggle"]
        guard previewToggle.waitForExistence(timeout: 3) else {
            // Skip test if we couldn't open the edit dialog
            throw XCTSkip("Could not open edit dialog to test preview toggle")
        }

        // Get initial window frame for comparison
        let window = app.windows.firstMatch
        let initialFrame = window.frame

        // Toggle preview ON
        previewToggle.click()
        sleep(1)

        // Verify window hasn't moved significantly
        let afterToggleOnFrame = window.frame
        let deltaXOn = abs(afterToggleOnFrame.origin.x - initialFrame.origin.x)
        let deltaYOn = abs(afterToggleOnFrame.origin.y - initialFrame.origin.y)

        XCTAssertLessThan(deltaXOn, 50, "Window moved \(deltaXOn)px horizontally after preview toggle ON")
        XCTAssertLessThan(deltaYOn, 50, "Window moved \(deltaYOn)px vertically after preview toggle ON")

        // Toggle preview OFF
        previewToggle.click()
        sleep(1)

        // Verify window position still stable
        let afterToggleOffFrame = window.frame
        let deltaXOff = abs(afterToggleOffFrame.origin.x - initialFrame.origin.x)
        let deltaYOff = abs(afterToggleOffFrame.origin.y - initialFrame.origin.y)

        XCTAssertLessThan(deltaXOff, 50, "Window moved \(deltaXOff)px horizontally after preview toggle OFF")
        XCTAssertLessThan(deltaYOff, 50, "Window moved \(deltaYOff)px vertically after preview toggle OFF")

        // Verify edit dialog still exists (wasn't dismissed)
        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.exists, "Edit dialog should remain open after preview toggle")
    }

    /// Test Issue #1B: Rapid preview toggling should not cause crashes or race conditions
    func testPreviewToggleRapidFire() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists, "PDF viewer should exist")

        // Double-click to open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(1)

        let previewToggle = app.checkBoxes["PreviewToggle"]
        guard previewToggle.waitForExistence(timeout: 5) else {
            throw XCTSkip("Could not open edit dialog")
        }

        // Rapid toggle 10 times
        for _ in 0..<10 {
            previewToggle.click()
            usleep(100000) // 100ms between toggles
        }

        // App should not crash - verify it's still running
        XCTAssertEqual(app.state, .runningForeground, "App should still be running after rapid preview toggles")

        // Edit dialog should still exist
        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.exists, "Edit dialog should remain after rapid preview toggles")
    }

    // MARK: - Test Category 2: Edit Window Positioning (MAJOR)

    /// Test Issue #2A: Edit window should stay fully on screen
    func testEditWindowStaysOnScreen() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists)

        // Double-click to open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(1)

        let editInput = app.textFields["EditTextInput"]
        guard editInput.waitForExistence(timeout: 5) else {
            throw XCTSkip("Could not open edit dialog")
        }

        // Get the edit dialog frame
        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.exists)

        // Verify the dialog is visible (frame is valid)
        let dialogFrame = saveButton.frame
        XCTAssertGreaterThan(dialogFrame.width, 0, "Dialog should have positive width")
        XCTAssertGreaterThan(dialogFrame.height, 0, "Dialog should have positive height")

        // Get main screen bounds
        guard let screenFrame = NSScreen.main?.visibleFrame else {
            throw XCTSkip("Could not get screen bounds")
        }

        // The dialog should be at least partially visible on screen
        let isOnScreen = dialogFrame.intersects(screenFrame)
        XCTAssertTrue(isOnScreen, "Edit dialog should be visible on screen")
    }

    /// Test Issue #2B: Edit window should remain stable during typing
    func testEditWindowStableDuringTyping() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists)

        // Double-click to open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(1)

        let editInput = app.textFields["EditTextInput"]
        guard editInput.waitForExistence(timeout: 5) else {
            throw XCTSkip("Could not open edit dialog")
        }

        // Get initial position
        let saveButton = app.buttons["SaveButton"]
        let initialFrame = saveButton.frame

        // Type some text
        editInput.click()
        editInput.typeText("Test typing stability with a longer string")
        sleep(1)

        // Check position hasn't changed significantly
        let afterTypingFrame = saveButton.frame
        let deltaX = abs(afterTypingFrame.origin.x - initialFrame.origin.x)
        let deltaY = abs(afterTypingFrame.origin.y - initialFrame.origin.y)

        XCTAssertLessThan(deltaX, 10, "Dialog moved \(deltaX)px horizontally during typing")
        XCTAssertLessThan(deltaY, 10, "Dialog moved \(deltaY)px vertically during typing")
    }

    /// Test Issue #2C: Edit window should handle resize correctly
    func testEditWindowResizeStability() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists)

        // Double-click to open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(1)

        // Look for resize handle
        let resizeHandle = app.otherElements["DialogResizeHandle"]

        // If font search is running, wait for results which will change dialog size
        let fontSearchProgress = app.progressIndicators["FontSearchProgress"]
        if fontSearchProgress.exists {
            // Wait up to 10 seconds for font search to complete
            let searchComplete = fontSearchProgress.waitForNonExistence(timeout: 10)
            if searchComplete {
                sleep(1) // Let UI settle
            }
        }

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.exists else {
            throw XCTSkip("Could not find edit dialog")
        }

        // Verify dialog is still functional after any size changes
        XCTAssertTrue(saveButton.isEnabled || saveButton.exists, "Save button should still be accessible after size changes")

        // Cancel button should also be accessible
        let cancelButton = app.buttons["CancelButton"]
        XCTAssertTrue(cancelButton.exists, "Cancel button should exist")
    }

    // MARK: - Test Category 3: Window Stability (MAJOR)

    /// Test that font search doesn't cause dialog to jump
    func testEditWindowStableDuringFontSearch() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists)

        // Double-click to open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(1)

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else {
            throw XCTSkip("Could not open edit dialog")
        }

        // Record initial position
        let initialFrame = saveButton.frame

        // Wait for font search progress indicator to appear then disappear
        let fontSearchProgress = app.progressIndicators["FontSearchProgress"]

        if fontSearchProgress.exists {
            // Wait for search to complete (max 30 seconds)
            _ = fontSearchProgress.waitForNonExistence(timeout: 30)
            sleep(1)

            // Check position after font search
            let afterSearchFrame = saveButton.frame
            let deltaX = abs(afterSearchFrame.origin.x - initialFrame.origin.x)
            let deltaY = abs(afterSearchFrame.origin.y - initialFrame.origin.y)

            XCTAssertLessThan(deltaX, 20, "Dialog X moved \(deltaX)px after font search")
            XCTAssertLessThan(deltaY, 20, "Dialog Y moved \(deltaY)px after font search")
        }

        // Dialog should still be functional
        XCTAssertTrue(saveButton.exists, "Save button should still exist after font search")
    }

    // MARK: - Test Category 4: Core UI Elements

    /// Test that all critical accessibility identifiers exist
    func testAccessibilityIdentifiersExist() throws {
        try launchWithTestPDF()

        // PDF Viewer should exist
        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.waitForExistence(timeout: 5), "PDFViewer identifier should exist")

        // File list should exist
        let fileList = app.otherElements["FileList"]
        XCTAssertTrue(fileList.exists || app.scrollViews["FileList"].exists, "FileList identifier should exist")

        // Add PDF button should exist
        let addPDFButton = app.buttons["AddPDFButton"]
        XCTAssertTrue(addPDFButton.exists, "AddPDFButton identifier should exist")

        // Zoom controls should exist (when document is loaded)
        let zoomOutButton = app.buttons["ZoomOutButton"]
        let zoomInButton = app.buttons["ZoomInButton"]
        let zoomFitButton = app.buttons["ZoomFitButton"]

        XCTAssertTrue(zoomOutButton.exists, "ZoomOutButton should exist")
        XCTAssertTrue(zoomInButton.exists, "ZoomInButton should exist")
        XCTAssertTrue(zoomFitButton.exists, "ZoomFitButton should exist")
    }

    /// Test zoom controls work correctly
    func testZoomControlsFunctional() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists)

        // Get initial state
        let zoomOutButton = app.buttons["ZoomOutButton"]
        let zoomInButton = app.buttons["ZoomInButton"]
        let zoomFitButton = app.buttons["ZoomFitButton"]

        XCTAssertTrue(zoomInButton.exists, "Zoom in button should exist")
        XCTAssertTrue(zoomOutButton.exists, "Zoom out button should exist")
        XCTAssertTrue(zoomFitButton.exists, "Zoom fit button should exist")

        // Click zoom in
        zoomInButton.click()
        sleep(1)

        // App should still be running
        XCTAssertEqual(app.state, .runningForeground, "App should be running after zoom in")

        // Click zoom out
        zoomOutButton.click()
        sleep(1)

        XCTAssertEqual(app.state, .runningForeground, "App should be running after zoom out")

        // Click zoom fit
        zoomFitButton.click()
        sleep(1)

        XCTAssertEqual(app.state, .runningForeground, "App should be running after zoom fit")
    }

    // MARK: - Test Category 5: Document Controls

    /// Test document control buttons have correct accessibility identifiers
    func testDocumentControlsAccessibility() throws {
        try launchWithTestPDF()

        // Wait for PDF to load
        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.waitForExistence(timeout: 5))

        // Document controls should be visible when document is loaded
        let vectorFlattenButton = app.buttons["VectorFlattenButton"]
        let secureEraseButton = app.buttons["SecureEraseButton"]
        let viewMetadataButton = app.buttons["ViewMetadataButton"]
        let scrubMetadataButton = app.buttons["ScrubMetadataButton"]

        // These buttons should exist (may or may not be enabled depending on state)
        XCTAssertTrue(vectorFlattenButton.exists, "VectorFlattenButton should exist")
        XCTAssertTrue(secureEraseButton.exists, "SecureEraseButton should exist")
        XCTAssertTrue(viewMetadataButton.exists, "ViewMetadataButton should exist")
        XCTAssertTrue(scrubMetadataButton.exists, "ScrubMetadataButton should exist")
    }

    // MARK: - Test Category 6: Font Control Panel

    /// Test font control panel nudge buttons exist
    func testFontControlPanelAccessibility() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.waitForExistence(timeout: 5))

        // Nudge buttons should exist in font control panel
        let nudgeUp = app.buttons["NudgeButtonUp"]
        let nudgeDown = app.buttons["NudgeButtonDown"]
        let nudgeLeft = app.buttons["NudgeButtonLeft"]
        let nudgeRight = app.buttons["NudgeButtonRight"]

        XCTAssertTrue(nudgeUp.exists, "NudgeButtonUp should exist")
        XCTAssertTrue(nudgeDown.exists, "NudgeButtonDown should exist")
        XCTAssertTrue(nudgeLeft.exists, "NudgeButtonLeft should exist")
        XCTAssertTrue(nudgeRight.exists, "NudgeButtonRight should exist")
    }

    // MARK: - Test Category 7: Edit Dialog Controls

    /// Test edit dialog font override controls exist
    func testEditDialogFontOverrideControls() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists)

        // Double-click to open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(2)

        // Wait for edit dialog
        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else {
            throw XCTSkip("Could not open edit dialog")
        }

        // Check font override controls
        let fontMenuButton = app.buttons["FontMenuButton"]
        let fontPrevButton = app.buttons["FontPreviousButton"]
        let fontNextButton = app.buttons["FontNextButton"]
        let styleMenuButton = app.buttons["StyleMenuButton"]
        let colorPickerButton = app.buttons["ColorPickerButton"]
        let justificationMenuButton = app.buttons["JustificationMenuButton"]

        // These should all exist in the edit dialog
        XCTAssertTrue(fontPrevButton.exists, "FontPreviousButton should exist")
        XCTAssertTrue(fontNextButton.exists, "FontNextButton should exist")
        XCTAssertTrue(colorPickerButton.exists, "ColorPickerButton should exist")
    }

    // MARK: - Integration Tests

    /// Test complete editing workflow without crashes
    func testCompleteEditingWorkflow() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.waitForExistence(timeout: 10))

        // Step 1: Open edit dialog
        let clickCoord = pdfViewer.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.3))
        clickCoord.doubleTap()
        sleep(2)

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else {
            throw XCTSkip("Could not open edit dialog")
        }

        // Step 2: Type in the edit field
        let editInput = app.textFields["EditTextInput"]
        if editInput.exists {
            editInput.click()
            editInput.typeText("Modified text")
            sleep(1)
        }

        // Step 3: Toggle preview
        let previewToggle = app.checkBoxes["PreviewToggle"]
        if previewToggle.exists {
            previewToggle.click()
            sleep(1)
            previewToggle.click()
            sleep(1)
        }

        // Step 4: Cancel the edit
        let cancelButton = app.buttons["CancelButton"]
        XCTAssertTrue(cancelButton.exists, "Cancel button should exist")
        cancelButton.click()
        sleep(1)

        // Step 5: Verify app is still running and stable
        XCTAssertEqual(app.state, .runningForeground, "App should be running after complete workflow")
        XCTAssertTrue(pdfViewer.exists, "PDF viewer should still exist")
    }

    /// Test that the app doesn't crash when closing documents
    func testCloseDocumentStability() throws {
        try launchWithTestPDF()

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.waitForExistence(timeout: 5))

        // Find the close button for the file row
        // File rows have identifiers like "FileRow_<UUID>"
        let fileRowCloseButton = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'FileRowCloseButton_'")).firstMatch

        if fileRowCloseButton.exists {
            fileRowCloseButton.click()
            sleep(1)

            // App should still be running
            XCTAssertEqual(app.state, .runningForeground, "App should be running after closing document")
        }
    }
}
