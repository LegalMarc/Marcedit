// AccessibilityAuditTests.swift
// MarceditUITests
//
// Verifies that all expected accessibility identifiers are present in the UI.
// These tests are the fastest way to catch regressions where an identifier
// is accidentally removed or a view is restructured.
//
// Run this suite first after any UI structural change.

import XCTest
import Foundation

final class AccessibilityAuditTests: MarceditTestCase {

    // MARK: - Empty State Identifiers

    /// Verifies accessibility identifiers present before any document is loaded.
    func testEmptyStateAccessibilityIdentifiers() throws {
        app.launch()
        XCTAssertTrue(app.waitForAppWindow(timeout: 15))
        Thread.sleep(forTimeInterval: 1.0)

        let staticIdentifiers: [(String, XCUIElement.ElementType)] = [
            ("FileList",      .any),
            ("AddPDFButton",  .button),
            ("OpenPDFButton", .button),
        ]

        for (identifier, elementType) in staticIdentifiers {
            let element: XCUIElement
            if elementType == .any {
                element = app.descendants(matching: .any)
                    .matching(identifier: identifier)
                    .firstMatch
            } else {
                element = app.descendants(matching: elementType)
                    .matching(identifier: identifier)
                    .firstMatch
            }
            XCTAssertTrue(element.waitForExistence(timeout: 5),
                          "Empty-state identifier '\(identifier)' not found")
        }
    }

    // MARK: - Document-Loaded State Identifiers

    /// Verifies identifiers present once a document is loaded.
    func testDocumentLoadedAccessibilityIdentifiers() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let identifiers: [(String, XCUIElement.ElementType)] = [
            ("PDFViewer",          .any),
            ("FileList",           .any),
            ("AddPDFButton",       .button),
            ("ZoomInButton",       .button),
            ("ZoomOutButton",      .button),
            ("ZoomFitButton",      .button),
        ]

        for (identifier, elementType) in identifiers {
            let element: XCUIElement
            if elementType == .any {
                element = app.descendants(matching: .any)
                    .matching(identifier: identifier)
                    .firstMatch
            } else {
                element = app.descendants(matching: elementType)
                    .matching(identifier: identifier)
                    .firstMatch
            }
            XCTAssertTrue(element.waitForExistence(timeout: 5),
                          "Document-state identifier '\(identifier)' not found")
        }
    }

    // MARK: - Document Controls Identifiers

    /// Verifies all DocumentControlsView accessibility identifiers.
    func testDocumentControlsAccessibilityIdentifiers() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let buttonIdentifiers = [
            "VectorFlattenButton",
            "SecureEraseButton",
            "ViewMetadataButton",
            "ScrubMetadataButton",
        ]
        for id in buttonIdentifiers {
            let btn = app.descendants(matching: .button)
                .matching(identifier: id)
                .firstMatch
            XCTAssertTrue(btn.waitForExistence(timeout: 5),
                          "DocumentControls button identifier '\(id)' not found")
        }

        // MD5 checksum label
        let md5 = app.descendants(matching: .staticText)
            .matching(identifier: "MD5ChecksumLabel")
            .firstMatch
        XCTAssertTrue(md5.waitForExistence(timeout: 5),
                      "MD5ChecksumLabel not found after loading document")
    }

    // MARK: - Font Control Panel Identifiers

    /// Verifies all FontControlPanel button identifiers.
    func testFontControlPanelIdentifiers() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let nudgeIdentifiers = [
            "NudgeButtonUp", "NudgeButtonDown",
            "NudgeButtonLeft", "NudgeButtonRight",
            "SizeUp", "SizeDown",
            "KernUp", "KernDown",
        ]
        for id in nudgeIdentifiers {
            let btn = app.descendants(matching: .button)
                .matching(identifier: id)
                .firstMatch
            XCTAssertTrue(btn.waitForExistence(timeout: 5),
                          "FontControlPanel button identifier '\(id)' not found")
        }
    }

    // MARK: - Edit Dialog Identifiers

    /// Opens the edit dialog and verifies all its accessibility identifiers.
    func testEditDialogAccessibilityIdentifiers() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(), "Edit dialog did not open")

        let dialogIdentifiers: [(String, XCUIElement.ElementType)] = [
            ("EditTextInput",     .any),       // textField or textView
            ("SaveButton",        .button),
            ("CancelButton",      .button),
            ("PreviewToggle",     .checkBox),
            ("SmartQuotesToggle", .checkBox),
            ("EditDialogHeader",  .any),
            ("DialogResizeHandle",.any),
        ]

        for (identifier, elementType) in dialogIdentifiers {
            let element: XCUIElement
            if elementType == .any {
                element = app.descendants(matching: .any)
                    .matching(identifier: identifier)
                    .firstMatch
            } else {
                element = app.descendants(matching: elementType)
                    .matching(identifier: identifier)
                    .firstMatch
            }
            XCTAssertTrue(element.waitForExistence(timeout: 5),
                          "Edit dialog identifier '\(identifier)' not found")
        }

        // Dismiss
        app.cancelEdit()
    }

    // MARK: - Sidebar File Row Identifiers

    /// After loading a document, the sidebar should show FileRow identifiers.
    func testSidebarFileRowIdentifiers() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let rows = app.sidebarFileRows()
        XCTAssertFalse(rows.isEmpty, "No FileRow identifiers found in sidebar")

        // Select the first row to expose action buttons
        rows.first?.click()
        Thread.sleep(forTimeInterval: 0.5)

        let closeBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_Close_'"))
            .firstMatch
        XCTAssertTrue(closeBtn.waitForExistence(timeout: 5),
                      "FileRow_Close_ button not found after selecting row")
    }

    // MARK: - Sidebar Toggle Identifier

    /// When the sidebar is visible, SidebarToggleButton should be accessible.
    func testSidebarToggleButtonIdentifier() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        // Launch without a corpus case to get the empty state sidebar toggle
        app.launch()
        XCTAssertTrue(app.waitForAppWindow(timeout: 15))
        Thread.sleep(forTimeInterval: 1.0)

        // SidebarToggleButton is in the empty state footer
        let toggleBtn = app.descendants(matching: .button)
            .matching(identifier: "SidebarToggleButton")
            .firstMatch
        // Note: only visible in empty state footer; may not be present when PDF is loaded
        // This test passes if either the button exists or the app is in PDF mode
        let pdfLoaded = app.descendants(matching: .any)
            .matching(identifier: "PDFViewer").firstMatch.exists
        if !pdfLoaded {
            XCTAssertTrue(toggleBtn.waitForExistence(timeout: 5),
                          "SidebarToggleButton not found in empty state")
        }
    }

    // MARK: - Accessibility Labels Audit

    /// Spot-checks that key buttons have human-readable accessibility labels.
    func testAccessibilityLabelsAreDescriptive() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Check that document control buttons have meaningful labels
        let labelChecks: [(String, String)] = [
            ("VectorFlattenButton", "Vector Flatten"),
            ("SecureEraseButton",   "Secure Erase"),
            ("ViewMetadataButton",  "View Metadata"),
            ("ScrubMetadataButton", "Scrub Metadata"),
        ]
        for (identifier, expectedLabel) in labelChecks {
            let btn = app.descendants(matching: .button)
                .matching(identifier: identifier)
                .firstMatch
            if btn.waitForExistence(timeout: 3) {
                XCTAssertEqual(btn.label, expectedLabel,
                               "Accessibility label for '\(identifier)' is '\(btn.label)', expected '\(expectedLabel)'")
            }
        }

        // AddPDFButton label
        let addBtn = app.descendants(matching: .button)
            .matching(identifier: "AddPDFButton")
            .firstMatch
        if addBtn.waitForExistence(timeout: 3) {
            XCTAssertFalse(addBtn.label.isEmpty,
                           "AddPDFButton has empty accessibility label")
        }
    }
}
