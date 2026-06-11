// SidebarTests.swift
// MarceditUITests
//
// Tests for the sidebar: adding files, selecting files, file row actions,
// context menu, and multiple-file workflows.

import XCTest
import Foundation

final class SidebarTests: MarceditTestCase {

    // MARK: - Add PDF Button

    /// Clicking AddPDFButton should open the system file picker (sheet or panel).
    func testAddPDFButtonOpensFileImporter() throws {
        app.launch()
        XCTAssertTrue(app.waitForAppWindow(timeout: 15), "App window did not appear")
        Thread.sleep(forTimeInterval: 1.0)

        // The add PDF button should exist even when no document is loaded
        let addBtn = app.descendants(matching: .button)
            .matching(identifier: "AddPDFButton")
            .firstMatch
        XCTAssertTrue(addBtn.waitForExistence(timeout: 5), "AddPDFButton not found")
        addBtn.click()

        // A file open panel should appear as a separate window on macOS.
        // We dismiss with Escape and verify the app is still alive.
        Thread.sleep(forTimeInterval: 1.0)
        app.typeKey(.escape, modifierFlags: [])
        Thread.sleep(forTimeInterval: 0.5)

        // After dismissal, the app should still be running
        XCTAssertEqual(app.state, .runningForeground,
                       "App crashed or backgrounded after file picker")
    }

    // MARK: - File Selection

    /// After launching with a corpus PDF, the sidebar should show a file row,
    /// and clicking it should keep the PDF displayed.
    func testSelectFileInSidebar() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90), "App did not reach PDF-ready state")
        Thread.sleep(forTimeInterval: 1.5)

        // FileList should exist
        let fileList = app.descendants(matching: .any)
            .matching(identifier: "FileList")
            .firstMatch
        XCTAssertTrue(fileList.waitForExistence(timeout: 5), "FileList not found")

        // At least one FileRow should be present
        let rows = app.sidebarFileRows()
        XCTAssertFalse(rows.isEmpty, "No file rows found after loading PDF")

        // Tapping the first row selects it (click; it may already be selected)
        rows.first?.click()
        Thread.sleep(forTimeInterval: 0.5)

        // PDFViewer should still be visible
        let viewer = app.descendants(matching: .any)
            .matching(identifier: "PDFViewer")
            .firstMatch
        XCTAssertTrue(viewer.exists, "PDFViewer disappeared after selecting sidebar row")
    }

    // MARK: - File Row Actions Visible When Selected

    /// When a file row is selected, the revert/save/saveAs/close buttons should appear.
    func testFileRowShowsActionsWhenSelected() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Select the first row (click on it)
        let rows = app.sidebarFileRows()
        guard let firstRow = rows.first else {
            XCTFail("No sidebar rows found"); return
        }
        firstRow.click()
        Thread.sleep(forTimeInterval: 0.5)

        // The row's id suffix (UUID) is needed to find the action buttons.
        // We look for any button whose identifier starts with "FileRow_Close_"
        let closeBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_Close_'"))
            .firstMatch
        XCTAssertTrue(closeBtn.waitForExistence(timeout: 5),
                      "FileRow_Close button did not appear after selecting the row")

        let saveBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_Save_' AND NOT (identifier CONTAINS 'SaveAs')"))
            .firstMatch
        XCTAssertTrue(saveBtn.exists, "FileRow_Save button not found")

        let saveAsBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_SaveAs_'"))
            .firstMatch
        XCTAssertTrue(saveAsBtn.exists, "FileRow_SaveAs button not found")

        let revertBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_Revert_'"))
            .firstMatch
        XCTAssertTrue(revertBtn.exists, "FileRow_Revert button not found")
    }

    // MARK: - Revert Button Disabled When Clean

    /// When the document has no unsaved changes, the Revert button should be disabled.
    func testRevertFileButtonIsDisabledWhenClean() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Select the first row
        let rows = app.sidebarFileRows()
        rows.first?.click()
        Thread.sleep(forTimeInterval: 0.5)

        let revertBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_Revert_'"))
            .firstMatch
        XCTAssertTrue(revertBtn.waitForExistence(timeout: 5), "Revert button not found")

        // No unsaved changes → should be disabled
        XCTAssertFalse(revertBtn.isEnabled,
                       "Revert button should be disabled when document has no unsaved changes")
    }

    // MARK: - Close File Removes Row

    /// Clicking the Close button for a selected file should remove it from the sidebar.
    func testCloseFileRemovesFromList() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let beforeCount = app.sidebarFileRows().count
        XCTAssertGreaterThan(beforeCount, 0, "No file rows before close")

        // Select and close
        let rows = app.sidebarFileRows()
        rows.first?.click()
        Thread.sleep(forTimeInterval: 0.3)

        let closeBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_Close_'"))
            .firstMatch
        XCTAssertTrue(closeBtn.waitForExistence(timeout: 5))
        closeBtn.click()
        Thread.sleep(forTimeInterval: 0.8)

        let afterCount = app.sidebarFileRows().count
        XCTAssertLessThan(afterCount, beforeCount,
                          "File row count did not decrease after closing the document")
    }

    // MARK: - Context Menu

    /// Right-clicking a file row should reveal the context menu with expected items.
    func testSidebarContextMenuShowsAllOptions() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let rows = app.sidebarFileRows()
        guard let firstRow = rows.first else {
            XCTFail("No sidebar rows"); return
        }

        firstRow.rightClick()
        Thread.sleep(forTimeInterval: 0.5)

        // Verify context menu items are present
        let expectedItems = ["Save Changes", "Save As...", "Revert to Original",
                             "Reveal in Finder", "Close Document"]
        for item in expectedItems {
            let menuItem = app.menuItems[item]
            XCTAssertTrue(menuItem.exists,
                          "Context menu item '\(item)' not found")
        }

        // Dismiss the context menu
        app.typeKey(.escape, modifierFlags: [])
        Thread.sleep(forTimeInterval: 0.3)
    }

    // MARK: - Save As Enabled Even When Clean

    /// "Save As..." should be enabled even when there are no unsaved changes.
    func testSaveAsButtonIsAlwaysEnabled() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        let rows = app.sidebarFileRows()
        rows.first?.click()
        Thread.sleep(forTimeInterval: 0.3)

        let saveAsBtn = app.descendants(matching: .button)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'FileRow_SaveAs_'"))
            .firstMatch
        XCTAssertTrue(saveAsBtn.waitForExistence(timeout: 5))
        XCTAssertTrue(saveAsBtn.isEnabled,
                      "Save As button should always be enabled")
    }
}
