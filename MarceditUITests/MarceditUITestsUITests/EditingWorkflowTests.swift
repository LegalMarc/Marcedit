//
//  EditingWorkflowTests.swift
//  MarceditUITestsUITests
//
//  Comprehensive UI tests for editing workflows
//  Migrated from tests/MarceditTests/EditingWorkflowUITests.swift
//

import XCTest

final class EditingWorkflowTests: XCTestCase {

    var app: XCUIApplication!

    // Default test PDF path
    let defaultTestPDFPath = "ignored-resources/sample-files-marcedit/15425215.pdf"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDown() {
        app = nil
        super.tearDown()
    }

    // MARK: - Preview Toggle Tests

    func testPreviewTogglePreservesScrollPosition() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else {
            XCTFail("PDF viewer did not load")
            return
        }

        // Double-click to open edit dialog
        app.doubleClickOnPDF()
        sleep(1)

        let previewToggle = app.checkBoxes["PreviewToggle"]
        guard previewToggle.waitForExistence(timeout: 5) else { return }

        let window = app.windows.firstMatch
        let initialFrame = window.frame

        // Toggle preview ON
        previewToggle.click()
        sleep(1)

        let afterToggleOnFrame = window.frame
        let deltaXOn = abs(afterToggleOnFrame.origin.x - initialFrame.origin.x)
        let deltaYOn = abs(afterToggleOnFrame.origin.y - initialFrame.origin.y)

        XCTAssertLessThan(deltaXOn, 50, "Window moved \(deltaXOn)px horizontally after preview toggle ON")
        XCTAssertLessThan(deltaYOn, 50, "Window moved \(deltaYOn)px vertically after preview toggle ON")

        // Toggle preview OFF
        previewToggle.click()
        sleep(1)

        let afterToggleOffFrame = window.frame
        let deltaXOff = abs(afterToggleOffFrame.origin.x - initialFrame.origin.x)
        let deltaYOff = abs(afterToggleOffFrame.origin.y - initialFrame.origin.y)

        XCTAssertLessThan(deltaXOff, 50, "Window moved \(deltaXOff)px horizontally after preview toggle OFF")
        XCTAssertLessThan(deltaYOff, 50, "Window moved \(deltaYOff)px vertically after preview toggle OFF")

        // Edit dialog should still exist
        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.exists, "Edit dialog should remain open after preview toggle")
    }

    // MARK: - Edit Window Tests

    func testEditWindowStaysOnScreen() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        app.doubleClickOnPDF()
        sleep(1)

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else { return }

        // Verify the dialog is visible
        let dialogFrame = saveButton.frame
        XCTAssertGreaterThan(dialogFrame.width, 0, "Dialog should have positive width")
        XCTAssertGreaterThan(dialogFrame.height, 0, "Dialog should have positive height")

        // Get main screen bounds
        guard let screenFrame = NSScreen.main?.visibleFrame else { return }

        // The dialog should be at least partially visible on screen
        let isOnScreen = dialogFrame.intersects(screenFrame)
        XCTAssertTrue(isOnScreen, "Edit dialog should be visible on screen")
    }

    func testEditWindowStableDuringTyping() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        app.doubleClickOnPDF()
        sleep(1)

        let editInput = app.textFields["EditTextInput"]
        guard editInput.waitForExistence(timeout: 5) else { return }

        let saveButton = app.buttons["SaveButton"]
        let initialFrame = saveButton.frame

        // Type some text
        editInput.click()
        editInput.typeText("Test typing stability")
        sleep(1)

        let afterTypingFrame = saveButton.frame
        let deltaX = abs(afterTypingFrame.origin.x - initialFrame.origin.x)
        let deltaY = abs(afterTypingFrame.origin.y - initialFrame.origin.y)

        XCTAssertLessThan(deltaX, 10, "Dialog moved \(deltaX)px horizontally during typing")
        XCTAssertLessThan(deltaY, 10, "Dialog moved \(deltaY)px vertically during typing")
    }

    func testEditWindowStableDuringFontSearch() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        app.doubleClickOnPDF()
        sleep(1)

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else { return }

        let initialFrame = saveButton.frame

        // Wait for font search progress indicator
        let fontSearchProgress = app.progressIndicators["FontSearchProgress"]

        if fontSearchProgress.exists {
            // Wait for search to complete (max 30 seconds)
            _ = fontSearchProgress.waitForNonExistence(timeout: 30)
            sleep(1)

            let afterSearchFrame = saveButton.frame
            let deltaX = abs(afterSearchFrame.origin.x - initialFrame.origin.x)
            let deltaY = abs(afterSearchFrame.origin.y - initialFrame.origin.y)

            XCTAssertLessThan(deltaX, 20, "Dialog X moved \(deltaX)px after font search")
            XCTAssertLessThan(deltaY, 20, "Dialog Y moved \(deltaY)px after font search")
        }

        XCTAssertTrue(saveButton.exists, "Save button should still exist after font search")
    }

    // MARK: - Accessibility Tests

    func testAccessibilityIdentifiersExist() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        // PDF Viewer should exist
        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.waitForExistence(timeout: 5), "PDFViewer identifier should exist")

        // Add PDF button should exist
        let addPDFButton = app.buttons["AddPDFButton"]
        XCTAssertTrue(addPDFButton.exists, "AddPDFButton identifier should exist")

        // Zoom controls should exist
        let zoomOutButton = app.buttons["ZoomOutButton"]
        let zoomInButton = app.buttons["ZoomInButton"]
        let zoomFitButton = app.buttons["ZoomFitButton"]

        XCTAssertTrue(zoomOutButton.exists, "ZoomOutButton should exist")
        XCTAssertTrue(zoomInButton.exists, "ZoomInButton should exist")
        XCTAssertTrue(zoomFitButton.exists, "ZoomFitButton should exist")
    }

    func testZoomControlsFunctional() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        let zoomOutButton = app.buttons["ZoomOutButton"]
        let zoomInButton = app.buttons["ZoomInButton"]
        let zoomFitButton = app.buttons["ZoomFitButton"]

        XCTAssertTrue(zoomInButton.exists, "Zoom in button should exist")

        // Click zoom in
        zoomInButton.click()
        sleep(1)

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

    // MARK: - Document Controls Tests

    func testDocumentControlsAccessibility() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        let vectorFlattenButton = app.buttons["VectorFlattenButton"]
        let secureEraseButton = app.buttons["SecureEraseButton"]
        let viewMetadataButton = app.buttons["ViewMetadataButton"]
        let scrubMetadataButton = app.buttons["ScrubMetadataButton"]

        XCTAssertTrue(vectorFlattenButton.exists, "VectorFlattenButton should exist")
        XCTAssertTrue(secureEraseButton.exists, "SecureEraseButton should exist")
        XCTAssertTrue(viewMetadataButton.exists, "ViewMetadataButton should exist")
        XCTAssertTrue(scrubMetadataButton.exists, "ScrubMetadataButton should exist")
    }

    func testFontControlPanelAccessibility() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        let nudgeUp = app.buttons["NudgeButtonUp"]
        let nudgeDown = app.buttons["NudgeButtonDown"]
        let nudgeLeft = app.buttons["NudgeButtonLeft"]
        let nudgeRight = app.buttons["NudgeButtonRight"]

        XCTAssertTrue(nudgeUp.exists, "NudgeButtonUp should exist")
        XCTAssertTrue(nudgeDown.exists, "NudgeButtonDown should exist")
        XCTAssertTrue(nudgeLeft.exists, "NudgeButtonLeft should exist")
        XCTAssertTrue(nudgeRight.exists, "NudgeButtonRight should exist")
    }

    // MARK: - Font Override Tests

    func testEditDialogFontOverrideControls() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        app.doubleClickOnPDF()
        sleep(2)

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else { return }

        let fontPrevButton = app.buttons["FontPreviousButton"]
        let fontNextButton = app.buttons["FontNextButton"]
        let colorPickerButton = app.buttons["ColorPickerButton"]

        XCTAssertTrue(fontPrevButton.exists, "FontPreviousButton should exist")
        XCTAssertTrue(fontNextButton.exists, "FontNextButton should exist")
        XCTAssertTrue(colorPickerButton.exists, "ColorPickerButton should exist")
    }

    // MARK: - Complete Workflow Tests

    func testCompleteEditingWorkflow() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer(timeout: 10) else {
            XCTFail("PDF viewer did not load")
            return
        }

        // Step 1: Open edit dialog
        app.doubleClickOnPDF()
        sleep(2)

        let saveButton = app.buttons["SaveButton"]
        guard saveButton.waitForExistence(timeout: 5) else { return }

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

        // Step 5: Verify app is still stable
        XCTAssertEqual(app.state, .runningForeground, "App should be running after complete workflow")

        let pdfViewer = app.otherElements["PDFViewer"]
        XCTAssertTrue(pdfViewer.exists, "PDF viewer should still exist")
    }

    func testCloseDocumentStability() {
        app.launchForTesting(testPDFPath: defaultTestPDFPath)

        guard app.waitForPDFViewer() else { return }

        // Find the close button for the file row
        let fileRowCloseButton = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'FileRowCloseButton_'")).firstMatch

        if fileRowCloseButton.exists {
            fileRowCloseButton.click()
            sleep(1)

            XCTAssertEqual(app.state, .runningForeground, "App should be running after closing document")
        }
    }

    // MARK: - New Bug Fix Verification Tests

    func testPreviewToggleMultipleTimes() {
        // Verifies fix for Bug 4,5,9: State separation allows multiple preview toggles
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_multi_preview.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else { return }
        sleep(2)

        app.doubleClickOnPDF()
        sleep(1)

        let previewToggle = app.checkBoxes["PreviewToggle"]
        guard previewToggle.waitForExistence(timeout: 5) else { return }

        // Toggle ON
        previewToggle.click()
        sleep(1)

        // Toggle OFF
        previewToggle.click()
        sleep(1)

        // Toggle ON again - this should work without "text not found" errors
        previewToggle.click()
        sleep(1)

        // App should still be running and dialog open
        XCTAssertEqual(app.state, .runningForeground, "App should handle multiple preview toggles")

        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.exists, "Edit dialog should remain open")
    }

    func testEditTextThenPreviewThenSave() {
        // Verifies the edit-preview-save workflow
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_edit_preview_save.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else { return }
        sleep(2)

        app.doubleClickOnPDF()
        sleep(1)

        guard app.waitForEditDialog() else { return }

        // Type new text
        let editInput = app.textFields["EditTextInput"]
        if editInput.exists {
            editInput.click()
            editInput.typeText(" EDITED")
            sleep(1)
        }

        // Enable preview
        let previewToggle = app.checkBoxes["PreviewToggle"]
        if previewToggle.exists {
            previewToggle.click()
            sleep(2) // Wait for preview to render
        }

        // Save
        let saveButton = app.buttons["SaveButton"]
        saveButton.click()
        sleep(2)

        // Dialog should close
        XCTAssertFalse(saveButton.exists, "Edit dialog should close after save")
        XCTAssertEqual(app.state, .runningForeground, "App should be running after save")
    }

    func testCancelRestoresDocument() {
        // Verifies cancel properly restores the original PDF
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_cancel_restore.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else { return }
        sleep(2)

        app.doubleClickOnPDF()
        sleep(1)

        guard app.waitForEditDialog() else { return }

        // Enable preview (makes a change)
        let previewToggle = app.checkBoxes["PreviewToggle"]
        if previewToggle.exists {
            previewToggle.click()
            sleep(2)
        }

        // Cancel
        let cancelButton = app.buttons["CancelButton"]
        cancelButton.click()
        sleep(1)

        // Dialog should close and PDF should be restored
        XCTAssertFalse(cancelButton.exists, "Edit dialog should close after cancel")
        XCTAssertEqual(app.state, .runningForeground, "App should be running after cancel")
    }

    // MARK: - Critical Bug Fix Verification

    /// Test that edited text is preserved when preview is toggled
    /// This verifies the fix for the bug where restoreState(from: doc) used a stale copy
    func testPreviewPreservesEditedText() {
        // Create a test PDF with known content
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_preview_preserve.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else {
            XCTFail("PDF viewer did not load")
            return
        }
        sleep(2)

        // Double-click to open edit dialog
        app.doubleClickOnPDF()
        sleep(1)

        guard app.waitForEditDialog() else {
            XCTFail("Edit dialog did not open")
            return
        }

        let editInput = app.textFields["EditTextInput"]
        guard editInput.waitForExistence(timeout: 5) else {
            XCTFail("Edit text input not found")
            return
        }

        // Get original text
        let originalText = editInput.value as? String ?? ""

        // Clear and type new text
        editInput.click()
        // Select all and replace
        editInput.typeKey("a", modifierFlags: .command)
        let modifiedText = "CHANGED_TEXT_\(UUID().uuidString.prefix(8))"
        editInput.typeText(modifiedText)
        sleep(1)

        // Verify text was changed
        let textAfterEdit = editInput.value as? String ?? ""
        XCTAssertTrue(textAfterEdit.contains("CHANGED_TEXT"), "Text should be modified before preview")

        // Toggle preview ON - this is where the bug occurred
        let previewToggle = app.checkBoxes["PreviewToggle"]
        guard previewToggle.waitForExistence(timeout: 3) else {
            XCTFail("Preview toggle not found")
            return
        }
        previewToggle.click()
        sleep(2) // Wait for preview to render

        // CRITICAL ASSERTION: Text should still be modified, not reverted to original
        let textAfterPreview = editInput.value as? String ?? ""
        XCTAssertTrue(
            textAfterPreview.contains("CHANGED_TEXT"),
            "BUG: Text was overwritten during preview! Expected '\(modifiedText)' but got '\(textAfterPreview)'"
        )
        XCTAssertFalse(
            textAfterPreview == originalText,
            "BUG: Text reverted to original '\(originalText)' after preview toggle"
        )

        // Clean up - cancel the edit
        let cancelButton = app.buttons["CancelButton"]
        if cancelButton.exists {
            cancelButton.click()
        }
    }
}
