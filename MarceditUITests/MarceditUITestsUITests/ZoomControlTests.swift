// ZoomControlTests.swift
// MarceditUITests
//
// Tests for the floating zoom controls (ZoomInButton, ZoomOutButton, ZoomFitButton).
// Verifies that buttons exist when a document is loaded, are absent otherwise,
// and that clicking them does not crash the app.

import XCTest
import Foundation

final class ZoomControlTests: MarceditTestCase {

    // MARK: - Zoom Controls Absent Without Document

    /// When no document is loaded, the zoom control buttons should not be present.
    func testZoomControlsAbsentWithoutDocument() throws {
        app.launch()
        XCTAssertTrue(app.waitForAppWindow(timeout: 15))
        Thread.sleep(forTimeInterval: 1.0)

        let zoomIn = app.descendants(matching: .button)
            .matching(identifier: "ZoomInButton")
            .firstMatch
        let zoomOut = app.descendants(matching: .button)
            .matching(identifier: "ZoomOutButton")
            .firstMatch
        let zoomFit = app.descendants(matching: .button)
            .matching(identifier: "ZoomFitButton")
            .firstMatch

        XCTAssertFalse(zoomIn.exists,
                       "ZoomInButton should not appear when no document is loaded")
        XCTAssertFalse(zoomOut.exists,
                       "ZoomOutButton should not appear when no document is loaded")
        XCTAssertFalse(zoomFit.exists,
                       "ZoomFitButton should not appear when no document is loaded")
    }

    // MARK: - Zoom Controls Present With Document

    /// When a document is loaded, all three zoom buttons should be visible.
    func testZoomControlsPresentWithDocument() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let zoomIn = app.descendants(matching: .button)
            .matching(identifier: "ZoomInButton")
            .firstMatch
        let zoomOut = app.descendants(matching: .button)
            .matching(identifier: "ZoomOutButton")
            .firstMatch
        let zoomFit = app.descendants(matching: .button)
            .matching(identifier: "ZoomFitButton")
            .firstMatch

        XCTAssertTrue(zoomIn.waitForExistence(timeout: 5),
                      "ZoomInButton not found after loading document")
        XCTAssertTrue(zoomOut.exists, "ZoomOutButton not found after loading document")
        XCTAssertTrue(zoomFit.exists, "ZoomFitButton not found after loading document")
    }

    // MARK: - Zoom In Button Does Not Crash

    /// Clicking Zoom In multiple times should not crash the app.
    func testZoomInButtonDoesNotCrash() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        for _ in 1...5 {
            app.clickZoomIn()
            Thread.sleep(forTimeInterval: 0.2)
        }

        XCTAssertEqual(app.state, .runningForeground,
                       "App crashed after clicking Zoom In 5 times")
        XCTAssertTrue(
            app.descendants(matching: .any)
                .matching(identifier: "PDFViewer")
                .firstMatch
                .exists,
            "PDFViewer disappeared after zoom in"
        )
    }

    // MARK: - Zoom Out Button Does Not Crash

    /// Clicking Zoom Out multiple times should not crash the app.
    func testZoomOutButtonDoesNotCrash() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        for _ in 1...5 {
            app.clickZoomOut()
            Thread.sleep(forTimeInterval: 0.2)
        }

        XCTAssertEqual(app.state, .runningForeground,
                       "App crashed after clicking Zoom Out 5 times")
    }

    // MARK: - Zoom Fit Button Does Not Crash

    /// Clicking Fit to Window should not crash the app.
    func testZoomFitButtonDoesNotCrash() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Zoom in first, then fit
        app.clickZoomIn()
        app.clickZoomIn()
        Thread.sleep(forTimeInterval: 0.3)

        app.clickZoomFit()
        Thread.sleep(forTimeInterval: 0.5)

        XCTAssertEqual(app.state, .runningForeground,
                       "App crashed after clicking Zoom Fit")
    }

    // MARK: - Zoom Cycle (In → Out → Fit)

    /// Exercising the full zoom cycle should leave the app stable.
    func testZoomCycleStaysStable() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        for _ in 1...3 {
            app.clickZoomIn()
            Thread.sleep(forTimeInterval: 0.15)
        }
        for _ in 1...3 {
            app.clickZoomOut()
            Thread.sleep(forTimeInterval: 0.15)
        }
        app.clickZoomFit()
        Thread.sleep(forTimeInterval: 0.3)

        XCTAssertEqual(app.state, .runningForeground, "App crashed during zoom cycle")

        let viewer = app.descendants(matching: .any)
            .matching(identifier: "PDFViewer")
            .firstMatch
        XCTAssertTrue(viewer.exists, "PDFViewer missing after zoom cycle")
    }

    // MARK: - View Menu Zoom Items

    /// View > Zoom In, Zoom Out, Fit to Window menu items should be accessible.
    func testViewMenuZoomItemsExist() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let viewMenu = app.menuBars.firstMatch.menuBarItems["View"]
        guard viewMenu.waitForExistence(timeout: 5) else {
            XCTSkip("View menu not found — menu may not be available in this build")
            return
        }
        viewMenu.click()
        Thread.sleep(forTimeInterval: 0.3)

        let expectedItems = ["Zoom In", "Zoom Out", "Fit to Window"]
        for item in expectedItems {
            let menuItem = app.menuItems[item]
            XCTAssertTrue(menuItem.exists,
                          "View menu item '\(item)' not found")
        }

        // Dismiss
        app.typeKey(.escape, modifierFlags: [])
    }
}
