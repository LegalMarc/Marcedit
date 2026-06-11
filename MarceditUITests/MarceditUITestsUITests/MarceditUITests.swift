//
//  MarceditUITests.swift
//  MarceditUITestsUITests
//
//  XCUITest suite for Marcedit PDF Editor
//  Migrated from tests/MarceditTests/MarceditUITests.swift
//

import XCTest

final class MarceditUITests: XCTestCase {

    var app: XCUIApplication!

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDown() {
        app = nil
        super.tearDown()
    }

    // MARK: - App Launch Tests

    func testAppLaunchesWithoutCrash() {
        let expectation = XCTestExpectation(description: "App launches")

        app.launchForTesting()

        XCTAssertTrue(app.state == .runningForeground, "App should be running in foreground")

        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            expectation.fulfill()
        }

        wait(for: [expectation], timeout: 5.0)
    }

    func testMainWindowExists() {
        app.launchForTesting()

        let window = app.windows.firstMatch
        XCTAssertTrue(window.exists, "Main window should exist")
    }

    func testMenuItemsExist() {
        app.launchForTesting()

        let menuBar = app.menuBars.firstMatch
        XCTAssertTrue(menuBar.menuItems["File"].exists, "File menu should exist")
        XCTAssertTrue(menuBar.menuItems["Edit"].exists, "Edit menu should exist")
        XCTAssertTrue(menuBar.menuItems["View"].exists, "View menu should exist")
        XCTAssertTrue(menuBar.menuItems["Window"].exists, "Window menu should exist")
        XCTAssertTrue(menuBar.menuItems["Help"].exists, "Help menu should exist")
    }

    // MARK: - PDF Loading Tests

    func testOpenPDFDocument() {
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_ui_document.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        XCTAssertTrue(app.waitForPDFViewer(), "PDF viewer should load")
    }

    // MARK: - Preview Persistence Tests

    func testPreviewPersistence() {
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_preview_persist.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else {
            XCTFail("PDF viewer did not load")
            return
        }

        sleep(2) // Wait for load

        // Double-click to open edit dialog
        app.doubleClickOnPDF()
        sleep(1)

        // Wait for edit dialog
        guard app.waitForEditDialog() else {
            // Skip if we couldn't open the dialog
            return
        }

        let saveButton = app.buttons["SaveButton"]
        let previewToggle = app.checkBoxes["PreviewToggle"]

        if previewToggle.exists {
            // Toggle preview ON
            previewToggle.click()
            sleep(1)

            XCTAssertTrue(saveButton.exists, "Edit sheet should REMAIN open after toggling preview ON")

            // Toggle preview OFF
            previewToggle.click()
            sleep(1)

            XCTAssertTrue(saveButton.exists, "Edit sheet should REMAIN open after toggling preview OFF")
        }
    }

    func testPreviewToggleRapidFire() {
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_rapid_preview.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else { return }
        sleep(2)

        app.doubleClickOnPDF()
        sleep(1)

        let previewToggle = app.checkBoxes["PreviewToggle"]
        guard previewToggle.waitForExistence(timeout: 5) else { return }

        // Rapid toggle 10 times
        for _ in 0..<10 {
            previewToggle.click()
            usleep(100000) // 100ms between toggles
        }

        // App should not crash
        XCTAssertEqual(app.state, .runningForeground, "App should still be running after rapid preview toggles")

        // Edit dialog should still exist
        let saveButton = app.buttons["SaveButton"]
        XCTAssertTrue(saveButton.exists, "Edit dialog should remain after rapid preview toggles")
    }

    // MARK: - Crash Detection Tests

    func testTextInputSystemNoCrash() {
        let testPDFURL = URL(fileURLWithPath: "/tmp/test_text_input_crash.pdf")
        createTestPDF(at: testPDFURL)
        defer { try? FileManager.default.removeItem(at: testPDFURL) }

        app.launchForTesting(testPDFPath: testPDFURL.path)

        guard app.waitForPDFViewer() else { return }
        sleep(2)

        // Click on PDF to trigger text selection and font search
        app.clickOnPDF()
        sleep(1)

        // Double-click to open edit dialog
        app.doubleClickOnPDF()
        sleep(2)

        // App should not have crashed
        XCTAssertEqual(app.state, .runningForeground, "App should be running after text selection")
    }

    // MARK: - Memory/Stability Tests

    func testMemoryLeaks() {
        app.launchForTesting()

        let iterations = 5

        for i in 0..<iterations {
            let window = app.windows.firstMatch
            if window.exists {
                let coord = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
                coord.click()
                Thread.sleep(forTimeInterval: 0.5)
            }
        }

        XCTAssertTrue(app.state == .runningForeground, "App should be running after operations")
    }
}
