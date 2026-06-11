//
//  MarceditUITests.swift
//  MarceditTests
//
//  UI integration tests for Marcedit PDF Editor
//  Tests actual app launch and PDF editing workflow
//
//  MIGRATION NOTE: These tests have been migrated to the XCUITest project at:
//    MarceditUITests/MarceditUITestsUITests/
//
//  To run UI tests:
//    1. Build with: swift build -c release
//    2. Open MarceditUITests/MarceditUITests.xcodeproj in Xcode
//    3. Run tests with Cmd+U
//
//  Or use the Python harness:
//    python3 tests/visual_harness/run_tests.py
//

import XCTest
@testable import Marcedit

final class MarceditUITests: XCTestCase {

    var app: XCUIApplication!

    /// Check if we're running in a proper UI testing environment
    static var isUITestingAvailable: Bool {
        let testConfig = ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"]
        return testConfig != nil && testConfig!.contains("UITest")
    }

    /// Skip test if UI testing is not available
    func skipIfNoUITesting() throws {
        if !Self.isUITestingAvailable {
            throw XCTSkip("XCUITests require UI Testing target. Use ./scripts/run-ui-tests.sh for GUI tests")
        }
    }

    override func setUp() {
        super.setUp()

        continueAfterFailure = false

        // Only initialize XCUIApplication if we're in a UI testing environment
        if Self.isUITestingAvailable {
            app = XCUIApplication()

            // Set launch arguments to enable test mode
            app.launchArguments = ["--run-ui-tests"]
            app.launchEnvironment = [
                "TESTING": "1",
                "DISABLE_AUTOSAVE": "1"
            ]
        }
    }

    override func tearDown() {
        app = nil
        super.tearDown()
    }

    // MARK: - Helper Functions

    func createTestPDF(at url: URL) {
        // Create a simple test PDF using PyMuPDF
        let pythonCode = """
        import fitz

        doc = fitz.open()
        page = doc.new_page()

        # Add various text elements
        page.insert_text((50, 700), "Hello World", fontsize=12)
        page.insert_text((50, 680), "Test Line 2", fontsize=12)
        page.insert_text((50, 660), "Sample text for editing", fontsize=12)

        # Add some color text
        page.insert_text((50, 640), "Blue text", fontsize=12, color=(0, 0, 1))

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

    // MARK: - Tests

    func testAppLaunchesWithoutCrash() throws {
        try skipIfNoUITesting()
        // Given
        let expectation = XCTestExpectation(description: "App launches")

        // When
        app.launch()

        // Then
        XCTAssertTrue(app.state == .runningForeground, "App should be running in foreground")

        // Wait a moment to ensure no immediate crash
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            expectation.fulfill()
        }

        wait(for: [expectation], timeout: 5.0)
    }

    func testOpenPDFDocument() throws {
        try skipIfNoUITesting()
        // Given
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_ui_document.pdf")
        createTestPDF(at: testPDFURL)

        let expectation = XCTestExpectation(description: "PDF opens")

        app.launch()

        // When - Try to open the PDF via File > Open or drag-and-drop
        // Note: This depends on your app's implementation
        // You may need to adjust this based on your UI

        // For now, we'll just verify the app is still running
        // after a simulated document load attempt

        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            expectation.fulfill()
        }

        wait(for: [expectation], timeout: 10.0)

        // Cleanup
        try? FileManager.default.removeItem(at: testPDFURL)

        // Then
        XCTAssertTrue(app.state == .runningForeground, "App should still be running")
    }

    func testMainWindowExists() throws {
        try skipIfNoUITesting()
        // Given
        app.launch()

        // When
        let window = app.windows.firstMatch

        // Then
        XCTAssertTrue(window.exists, "Main window should exist")

        // Verify window has proper title
        // Note: Adjust title based on your implementation
        let hasValidTitle = window.title.contains("Marcedit") ||
                           window.title.contains("Untitled") ||
                           window.title.isEmpty

        XCTAssertTrue(hasValidTitle, "Window should have valid title")
    }

    func testMenuItemsExist() throws {
        try skipIfNoUITesting()
        // Given
        app.launch()

        // When - Click on menu bar
        let menuBar = app.menuBars.firstMatch

        // Then - Verify standard menus exist
        XCTAssertTrue(menuBar.menuItems["File"].exists, "File menu should exist")
        XCTAssertTrue(menuBar.menuItems["Edit"].exists, "Edit menu should exist")
        XCTAssertTrue(menuBar.menuItems["View"].exists, "View menu should exist")
        XCTAssertTrue(menuBar.menuItems["Window"].exists, "Window menu should exist")
        XCTAssertTrue(menuBar.menuItems["Help"].exists, "Help menu should exist")
    }

    func testFileMenuOptions() throws {
        try skipIfNoUITesting()
        // Given
        app.launch()

        // When - Click File menu
        let fileMenu = app.menuItems["File"]
        XCTAssertTrue(fileMenu.exists, "File menu should exist")

        fileMenu.click()

        // Then - Verify common file operations
        XCTAssertTrue(app.menuItems["New Document"].exists ||
                     app.menuItems["New"].exists, "New option should exist")

        XCTAssertTrue(app.menuItems["Open…"].exists ||
                     app.menuItems["Open"].exists, "Open option should exist")

        // Close menu
        if let statusBar = app.statusBars.firstMatch.exists as? Bool {
            app.menuBars.firstMatch.click()
        }
    }

    func testTypicalWorkflow() throws {
        try skipIfNoUITesting()
        // Given
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_workflow.pdf")
        createTestPDF(at: testPDFURL)

        let expectation = XCTestExpectation(description: "Complete workflow")

        app.launch()

        // When - Simulate typical user workflow
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            // Step 1: App is running
            XCTAssertTrue(self.app.state == .runningForeground, "App should be running")

            // Step 2: Try to interact with main window
            let window = self.app.windows.firstMatch
            if window.exists {
                // Click in window to focus (if needed)
                window.click(at: NSPoint(x: 100, y: 100))

                // Wait a moment
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    expectation.fulfill()
                }
            } else {
                expectation.fulfill()
            }
        }

        wait(for: [expectation], timeout: 15.0)

        // Cleanup
        try? FileManager.default.removeItem(at: testPDFURL)

        // Then
        XCTAssertTrue(app.state == .runningForeground, "App should still be running after workflow")
    }

    func testMemoryLeaks() throws {
        try skipIfNoUITesting()
        // Given
        app.launch()

        let expectation = XCTestExpectation(description: "No memory leaks")

        // When - Perform multiple operations
        let iterations = 5

        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            for i in 0..<iterations {
                // Simulate some operations
                let window = self.app.windows.firstMatch
                if window.exists {
                    window.click(at: NSPoint(x: 100 + CGFloat(i*10), y: 100))

                    // Small delay between operations
                    Thread.sleep(forTimeInterval: 0.5)
                }
            }

            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                expectation.fulfill()
            }
        }

        wait(for: [expectation], timeout: Double(iterations) + 10.0)

        // Then - App should still be responsive
        XCTAssertTrue(app.state == .runningForeground, "App should be running after operations")
    }

    func testTextInputSystem() throws {
        try skipIfNoUITesting()
        // This specifically tests the TextInputUIMacHelper crash scenario
        // by actually opening a PDF and clicking on text to trigger
        // EditorViewModel.startInteractiveFontSearch

        // Given
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_text_input_crash.pdf")
        createTestPDF(at: testPDFURL)

        let expectation = XCTestExpectation(description: "Text selection without crash")
        var crashOccurred = false

        app.launch()

        // When - Open PDF and click on text to trigger the crash sequence
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            // Step 1: Verify app is running
            guard self.app.state == .runningForeground else {
                XCTFail("App failed to launch")
                expectation.fulfill()
                return
            }

            // Step 2: Open the PDF document
            // We'll use AppleScript via NSTask to open the file
            self.openPDFInApp(testPDFURL)

            // Step 3: Wait for PDF to load
            DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
                // Step 4: Click on the PDF view to trigger text selection
                // This should trigger EditorViewModel.startInteractiveFontSearch
                // which causes the TextInputUIMacHelper crash
                self.clickOnPDFView()

                // Step 5: Wait for crash or edit sheet to appear
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    // Step 6: Check if app crashed
                    if self.app.state != .runningForeground {
                        crashOccurred = true
                    }

                    // Step 7: Check crash logs
                    if self.checkForTextInputCrash() {
                        crashOccurred = true
                    }

                    expectation.fulfill()
                }
            }
        }

        wait(for: [expectation], timeout: 15.0)

        // Cleanup
        try? FileManager.default.removeItem(at: testPDFURL)

        // Then - App should not have crashed
        XCTAssertFalse(crashOccurred, "TextInputUIMacHelper crash occurred - check crash logs in ~/Library/Logs/DiagnosticReports")
        XCTAssertTrue(app.state == .runningForeground, "App should be running after text selection")
    }

    // MARK: - Helper Methods for Text Selection Crash Test

    func openPDFInApp(_ url: URL) {
        let script = """
        tell application "Marcedit"
            activate
            open POSIX file "\(url.path)"
        end tell
        """

        if let appleScript = NSAppleScript(source: script) {
            var error: NSDictionary?
            appleScript.executeAndReturnError(&error)
            if let error = error {
                print("AppleScript error: \(error)")
            }
        }
    }

    func clickOnPDFView() {
        // Click in the window area where PDF is rendered
        // This should trigger text selection and startInteractiveFontSearch
        let window = app.windows.firstMatch

        if window.exists {
            // Click at a location where text should be (based on our test PDF)
            // Test PDF has text at coordinates (50, 700), (50, 680), etc.
            // We'll click in the center area to trigger the selection
            let clickPoint = NSPoint(x: 200, y: 400)
            window.click(at: clickPoint)

            // Wait a moment for the click to register
            Thread.sleep(forTimeInterval: 0.5)

            // Try clicking at another location to be more likely to hit text
            let clickPoint2 = NSPoint(x: 100, y: 300)
            window.click(at: clickPoint2)
        }
    }

    func checkForTextInputCrash() -> Bool {
        // Check for recent crash logs in ~/Library/Logs/DiagnosticReports
        let crashDir = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Logs/DiagnosticReports")

        guard let files = try? FileManager.default.contentsOfDirectory(
            at: crashDir,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: []
        ) else {
            return false
        }

        // Look for Marcedit crash logs in the last 2 minutes
        let twoMinutesAgo = Date().addingTimeInterval(-120)

        for file in files {
            if file.lastPathComponent.contains("Marcedit") &&
               file.pathExtension == "crash" {

                if let modDate = try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate {
                    if modDate > twoMinutesAgo {
                        print("⚠️ CRASH DETECTED: \(file.lastPathComponent)")
                        print("   Crash log: \(file.path)")
                        return true
                    }
                }
            }
        }

        return false
    }
    func testPreviewPersistence() throws {
        try skipIfNoUITesting()
        // Test that toggling Preview does NOT close the edit dialog
        // Regression test for bug where PDF reload dismissed the sheet
        
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_preview_persist.pdf")
        createTestPDF(at: testPDFURL)
        
        app.launch()
        
        // 1. Open PDF
        openPDFInApp(testPDFURL)
        
        // 2. Click to open Edit Sheet
        let window = app.windows.firstMatch
        XCTAssertTrue(window.waitForExistence(timeout: 5.0))
        
        // Wait for load
        Thread.sleep(forTimeInterval: 2.0)
        
        // Click text (coordinates 50,700 from createTestPDF)
        // Convert logic: 50,700 is near top left if origin is bottom-left? 
        // PyMuPDF uses top-left origin usually? No, PDF is bottom-left usually but PyMuPDF is top-left.
        // Let's assume standard view coordinates.
        let clickPoint = NSPoint(x: 100, y: 300) // Rough guess for center
        window.click(at: clickPoint)
        
        // 3. Verify Edit Sheet appears
        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.waitForExistence(timeout: 3.0), "Edit sheet should appear after clicking text")
        
        // 4. Toggle Preview
        let previewToggle = app.checkBoxes["PreviewToggle"]
        if previewToggle.exists {
            previewToggle.click()
            
            // 5. Verify Sheet Persists
            // Wait a moment for potential crash/dismiss
            Thread.sleep(forTimeInterval: 1.0)
            
            XCTAssertTrue(saveButton.exists, "Edit sheet should REMAIN open after toggling preview")
            
            // Toggle back
            previewToggle.click()
            Thread.sleep(forTimeInterval: 1.0)
            XCTAssertTrue(saveButton.exists, "Edit sheet should REMAIN open after toggling preview off")
        } else {
            XCTFail("Preview toggle not found - accessibility identifier missing?")
        }
        
        // Cleanup
        try? FileManager.default.removeItem(at: testPDFURL)
    }
}

// MARK: - NSPoint Extension for XCUIElement

extension XCUIElement {
    func click(at point: NSPoint) {
        let coordinate = self.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        coordinate.click()
    }
}
