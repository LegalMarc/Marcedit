// DocumentControlsTests.swift
// MarceditUITests
//
// Tests for DocumentControlsView: MD5 checksum display, Vector Flatten,
// Secure Erase, View Metadata, and Scrub Metadata.

import XCTest
import Foundation

final class DocumentControlsTests: MarceditTestCase {

    // MARK: - Buttons Disabled Without Document

    /// All document control buttons should be disabled when no document is loaded.
    func testDocumentControlsDisabledWithoutFile() throws {
        app.launch()
        XCTAssertTrue(app.waitForAppWindow(timeout: 15))
        Thread.sleep(forTimeInterval: 1.0)

        let identifiers = ["VectorFlattenButton", "SecureEraseButton",
                           "ViewMetadataButton", "ScrubMetadataButton"]
        for id in identifiers {
            let btn = app.descendants(matching: .button)
                .matching(identifier: id)
                .firstMatch
            if btn.waitForExistence(timeout: 3) {
                XCTAssertFalse(btn.isEnabled,
                               "\(id) should be disabled when no document is loaded")
            }
        }
    }

    // MARK: - MD5 Checksum Displays After Load

    /// After loading a PDF, the MD5ChecksumLabel should show a non-empty hex string.
    func testMD5ChecksumDisplaysAfterFileLoad() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let md5 = app.readMD5Checksum()
        XCTAssertNotNil(md5, "MD5ChecksumLabel not found or has no value")
        if let md5 = md5 {
            XCTAssertFalse(md5.isEmpty, "MD5 checksum is empty")
            // MD5 is a 32-character hex string
            let isValidMD5 = md5.count == 32 && md5.allSatisfy({ $0.isHexDigit })
            XCTAssertTrue(isValidMD5,
                          "MD5 '\(md5)' does not look like a valid MD5 hash (expected 32 hex chars)")
        }
    }

    // MARK: - Vector Flatten Confirmation Dialog

    /// Clicking Vector Flatten should present a confirmation alert.
    func testVectorFlattenShowsConfirmationDialog() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        XCTAssertTrue(app.clickDocumentControl(identifier: "VectorFlattenButton"),
                      "VectorFlattenButton not found or not clickable")

        // Alert should appear
        let alertAppeared = app.alertExists(title: "Vector Flatten Document?")
        XCTAssertTrue(alertAppeared,
                      "Vector Flatten confirmation alert did not appear")

        // Dismiss by cancelling
        app.waitForAlert(title: "Vector Flatten Document?", clickButton: "Cancel")
    }

    // MARK: - Vector Flatten Cancel Does Not Modify

    /// Cancelling the Vector Flatten dialog must not modify the document.
    func testVectorFlattenCancelDoesNotModify() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Record MD5 before
        let before = app.readMD5Checksum()

        app.clickDocumentControl(identifier: "VectorFlattenButton")
        app.waitForAlert(title: "Vector Flatten Document?", clickButton: "Cancel")
        Thread.sleep(forTimeInterval: 0.5)

        // MD5 should be unchanged
        let after = app.readMD5Checksum()
        XCTAssertEqual(before, after,
                       "MD5 changed after cancelling Vector Flatten — document was modified unexpectedly")
    }

    // MARK: - Scrub Metadata Confirmation Dialog

    /// Clicking Scrub Metadata should present a confirmation alert.
    func testScrubMetadataShowsConfirmationDialog() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        XCTAssertTrue(app.clickDocumentControl(identifier: "ScrubMetadataButton"),
                      "ScrubMetadataButton not found or not clickable")

        let alertAppeared = app.alertExists(title: "Scrub Metadata?")
        XCTAssertTrue(alertAppeared, "Scrub Metadata confirmation alert did not appear")

        app.waitForAlert(title: "Scrub Metadata?", clickButton: "Cancel")
    }

    // MARK: - Scrub Metadata Cancel Does Not Modify

    func testScrubMetadataCancelDoesNotModify() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let before = app.readMD5Checksum()

        app.clickDocumentControl(identifier: "ScrubMetadataButton")
        app.waitForAlert(title: "Scrub Metadata?", clickButton: "Cancel")
        Thread.sleep(forTimeInterval: 0.5)

        let after = app.readMD5Checksum()
        XCTAssertEqual(before, after,
                       "MD5 changed after cancelling Scrub Metadata — document was modified")
    }

    // MARK: - Secure Erase Confirmation Dialog

    /// Clicking Secure Erase should present a confirmation alert.
    func testSecureEraseShowsConfirmationDialog() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        XCTAssertTrue(app.clickDocumentControl(identifier: "SecureEraseButton"),
                      "SecureEraseButton not found or not clickable")

        let alertAppeared = app.alertExists(title: "Secure Erase All Traces?")
        XCTAssertTrue(alertAppeared, "Secure Erase confirmation alert did not appear")

        app.waitForAlert(title: "Secure Erase All Traces?", clickButton: "Cancel")
    }

    // MARK: - View Metadata

    /// Clicking View Metadata with a document loaded should produce some result
    /// without crashing. (The actual metadata is shown in a system dialog or alert.)
    func testViewMetadataDoesNotCrash() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        XCTAssertTrue(app.clickDocumentControl(identifier: "ViewMetadataButton"),
                      "ViewMetadataButton not found")
        Thread.sleep(forTimeInterval: 2.0)

        // App should still be running after metadata view
        XCTAssertEqual(app.state, .runningForeground,
                       "App crashed or backgrounded after viewing metadata")

        // Dismiss any alert that may have appeared
        if app.alerts.firstMatch.exists {
            app.alerts.firstMatch.buttons.firstMatch.click()
        }
    }

    // MARK: - Document Menu Commands

    /// The Document > Vector Flatten menu item should trigger the same confirmation.
    func testDocumentMenuVectorFlattenTrigger() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Invoke via menu bar
        let documentMenu = app.menuBars.firstMatch.menuBarItems["Document"]
        guard documentMenu.waitForExistence(timeout: 5) else {
            XCTSkip("Document menu not found — menu commands may not be available in this build")
            return
        }
        documentMenu.click()
        Thread.sleep(forTimeInterval: 0.3)

        let flattenItem = app.menuItems["Vector Flatten..."]
        guard flattenItem.exists else {
            app.typeKey(.escape, modifierFlags: [])
            XCTSkip("Vector Flatten... menu item not found")
            return
        }
        flattenItem.click()
        Thread.sleep(forTimeInterval: 0.5)

        let alertAppeared = app.alertExists(title: "Vector Flatten Document?")
        XCTAssertTrue(alertAppeared, "Vector Flatten alert did not appear via Document menu")
        app.waitForAlert(title: "Vector Flatten Document?", clickButton: "Cancel")
    }
}
