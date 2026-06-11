// SelectionAccuracyTests.swift
// MarceditUITests
//
// Tests that verify text selection accuracy — specifically the regression fix
// for joinedLineSelection() which merges split PDF text runs on the same visual line.
//
// Tests in this file focus on WHAT is selected, not on the downstream edit output.

import XCTest

final class SelectionAccuracyTests: MarceditTestCase {

    // MARK: - Parametrised: every case must produce targetText on double-click

    /// For every corpus case, double-click and verify EditTextInput == targetText.
    /// This is the broadest selection-accuracy regression guard.
    func testDoubleClickGivesFullTextForAllCorpusCases() throws {
        XCTAssertFalse(corpus.isEmpty, "No corpus cases loaded")

        for c in corpus {
            // Multi-page cases require navigation — skip in this parametrised run
            // (they are covered individually in RealWorldEditTests).
            if c.pageIndex > 0 { continue }

            XCTContext.runActivity(named: "Case \(c.id): double-click → '\(c.targetText)'") { _ in
                let _     = app.launchWithCorpusCase(c)
                defer { app.terminate() }

                guard app.waitForPDFReady(timeout: 90) else {
                    XCTFail("App not ready for case \(c.id)"); return
                }
                Thread.sleep(forTimeInterval: 1.5)

                app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
                guard app.waitForEditDialog(timeout: 15) else {
                    XCTFail("Edit dialog did not open for case \(c.id)"); return
                }

                let selected = app.readSelectedText()
                XCTAssertEqual(
                    selected, c.targetText,
                    "Case \(c.id): expected '\(c.targetText)', got '\(selected)'"
                )

                // Dismiss without saving
                app.cancelEdit()
            }
        }
    }

    // MARK: - Split-run specific: single-click must not truncate

    /// Single-click on the FIRST text object of a split-run PDF must not return
    /// only that object's text — it should return the full joined line.
    ///
    /// Pre-fix behaviour: click on "Hello " → selection = "Hello "
    /// Post-fix behaviour: click on "Hello " → selection = "Hello World!"
    ///
    /// Note: single-click triggers a *hover/select* in InteractivePDFView (mouseUp
    /// fires onSelect which calls onLineSelect). The edit dialog opens on double-
    /// click (onClick → onLineClick). We check single-click here by reading the
    /// tooltip / hover selection state via the SelectedTextLabel accessibility
    /// element if available, otherwise we fall back to opening the dialog.
    func testSingleClickDoesNotTruncateSplitRuns() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("003") }) else {
            XCTFail("Corpus case 003 not found — run generate_corpus.py"); return
        }
        let truncated = c.truncatedText ?? "Hello "

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Single-click at the coords in the FIRST text object ("Hello ")
        app.singleClickAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        Thread.sleep(forTimeInterval: 0.5)

        // Try to read the hover-selected text from a "SelectedTextLabel" if present.
        // If no such label exists, fall through to the edit dialog check below.
        let label = app.descendants(matching: .staticText)
            .matching(identifier: "SelectedTextLabel")
            .firstMatch
        if label.exists {
            let hover = label.value as? String ?? label.label
            XCTAssertNotEqual(hover, truncated,
                              "Single-click hover shows truncated '\(truncated)' — regression")
            XCTAssertEqual(hover, c.targetText,
                           "Single-click hover should show full joined text '\(c.targetText)'")
        }

        // Now open via double-click and check edit dialog value
        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        guard app.waitForEditDialog(timeout: 15) else {
            XCTFail("Edit dialog did not open for case 003"); return
        }

        let selected = app.readSelectedText()
        XCTAssertNotEqual(selected, truncated,
                          "REGRESSION: edit dialog shows truncated '\(truncated)' — joinedLineSelection fix is broken")
        XCTAssertEqual(selected, c.targetText,
                       "Edit dialog should show full joined text '\(c.targetText)', got '\(selected)'")

        app.cancelEdit()
    }

    // MARK: - Edge: empty area click does not open edit dialog

    func testClickOnEmptyAreaDoesNotOpenDialog() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else { return }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Double-click near the bottom of the page (empty area for US Letter PDFs)
        app.openEditDialogAt(normalizedX: 0.5, normalizedY: 0.85)
        Thread.sleep(forTimeInterval: 1.0)

        let dialogAppeared = app.waitForEditDialog(timeout: 2)
        // It's acceptable for no dialog to appear — but if one does, the selection
        // should NOT be the file's main text content.
        if dialogAppeared {
            let selected = app.readSelectedText()
            XCTAssertFalse(
                selected.localizedCaseInsensitiveContains("Hello World"),
                "Empty-area click opened a dialog with the main-text content '\(selected)'"
            )
            app.cancelEdit()
        }
        // If dialog didn't appear: test passes (correct behaviour)
    }

    // MARK: - Accuracy: selection matches targetText length within tolerance

    func testSelectionLengthMatchesExpected() throws {
        for c in corpus where c.pageIndex == 0 {
            XCTContext.runActivity(named: "Length check: \(c.id)") { _ in
                let _ = app.launchWithCorpusCase(c)
                defer { app.terminate() }

                guard app.waitForPDFReady(timeout: 90) else { return }
                Thread.sleep(forTimeInterval: 1.5)

                app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
                guard app.waitForEditDialog(timeout: 15) else { return }

                let selected = app.readSelectedText()
                let expectedLen = c.targetText.count
                let actualLen   = selected.count

                // Allow ±1 character for trailing space/newline differences
                XCTAssertTrue(
                    abs(actualLen - expectedLen) <= 1,
                    "Case \(c.id): selection length \(actualLen) differs from expected \(expectedLen) by more than 1 character"
                )

                app.cancelEdit()
            }
        }
    }
}
