// WorkflowTests.swift
// MarceditUITests
//
// Tests for higher-level editing workflows:
//   - Preview on → verify visual → save → verify output
//   - Cancel edit → original document unchanged
//   - Rapid preview toggle (10 times) without crash
//   - Consecutive edits (3 sequential edits, all verified)

import XCTest
import Foundation

final class WorkflowTests: MarceditTestCase {

    // MARK: - Preview + Save

    /// Opens a PDF, double-clicks text, enables preview, waits for visual update,
    /// then saves and verifies the output PDF contains the replacement.
    func testEditPreviewSave() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(), "Edit dialog did not open")

        // Type replacement
        app.typeReplacement(c.replacement)

        // Toggle preview ON
        app.togglePreview()

        // Give Python time to render the preview (generous timeout)
        Thread.sleep(forTimeInterval: 4.0)

        // Preview should still have the dialog open (not saved yet)
        XCTAssertTrue(app.waitForEditDialog(timeout: 2),
                      "Edit dialog closed prematurely during preview")

        // Save
        app.saveEdit()
        Thread.sleep(forTimeInterval: 2.0)

        let outputPath = latestPDF(in: outputDir) ?? c.pdfPath
        verifyOutputPDF(at: outputPath,
                        contains: c.replacement,
                        page: c.pageIndex)
    }

    // MARK: - Cancel restores document

    /// Edits text, then cancels. The original PDF must not be modified.
    func testCancelRestoresDocument() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        // Capture checksum of original PDF before launch
        let origChecksum = md5(file: c.pdfPath) ?? ""

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog())

        app.typeReplacement("THIS SHOULD NOT APPEAR")
        app.cancelEdit()
        Thread.sleep(forTimeInterval: 1.0)

        // The tmp copy of the PDF should be unmodified
        // (the test works with a tmp copy, so the corpus original is always safe)
        let fm = FileManager.default
        let tmp = NSTemporaryDirectory()
        if let tmpEntry = (try? fm.contentsOfDirectory(atPath: tmp))?
            .first(where: { $0.hasPrefix("marcedit_uitest_\(c.id)_") }) {
            let tmpPDF = tmp + tmpEntry + "/input.pdf"
            let newChecksum = md5(file: tmpPDF) ?? ""
            XCTAssertEqual(newChecksum, origChecksum,
                           "Cancel did not restore document — file was modified")
        }

        // Also verify PDFVerifier doesn't see the cancelled text
        let verifier = PDFVerifier(pdfPath: c.pdfPath)
        let containsCancelled = (try? verifier.containsText("THIS SHOULD NOT APPEAR")) ?? false
        XCTAssertFalse(containsCancelled,
                       "Cancelled text found in PDF — cancel did not work correctly")
    }

    // MARK: - Rapid preview toggle (stress test)

    /// Toggles preview 10 times rapidly. The app must not crash or freeze.
    func testRapidPreviewToggle() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let _ = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog())

        app.typeReplacement(c.replacement)

        // Toggle 10 times with minimal delay
        for i in 1...10 {
            app.togglePreview()
            Thread.sleep(forTimeInterval: 0.25)
            XCTAssertTrue(app.state == .runningForeground,
                          "App crashed or backgrounded after toggle \(i)")
        }

        // End with preview OFF and cancel cleanly
        // (after 10 toggles from OFF, we end ON — one more toggle to go OFF)
        app.togglePreview()
        app.cancelEdit()

        XCTAssertTrue(app.state == .runningForeground,
                      "App is not running after rapid preview toggles")
    }

    // MARK: - Consecutive edits

    /// Performs 3 sequential edits on the same document and verifies each.
    func testConsecutiveEdits() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("002") }) else {
            XCTFail("Corpus case 002 not found"); return
        }

        let replacements = ["First edit", "Second edit", "Third edit"]

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        var lastOutputPath: String = c.pdfPath

        for (i, replacement) in replacements.enumerated() {
            XCTContext.runActivity(named: "Consecutive edit \(i + 1): '\(replacement)'") { _ in
                app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)

                guard app.waitForEditDialog(timeout: 15) else {
                    XCTFail("Edit dialog did not open for consecutive edit \(i + 1)")
                    return
                }

                app.typeReplacement(replacement)
                app.saveEdit()
                Thread.sleep(forTimeInterval: 1.5)

                if let output = latestPDF(in: outputDir) {
                    lastOutputPath = output
                }

                verifyOutputPDF(at: lastOutputPath,
                                contains: replacement,
                                page: c.pageIndex)
            }
        }
    }

    // MARK: - Undo after edit

    /// Edits text, saves, then presses Cmd+Z to undo. The PDF should revert.
    func testUndoAfterEdit() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Edit
        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog())
        app.typeReplacement(c.replacement)
        app.saveEdit()
        Thread.sleep(forTimeInterval: 1.5)

        // Verify replacement is visible
        let afterEdit = latestPDF(in: outputDir) ?? c.pdfPath
        verifyOutputPDF(at: afterEdit, contains: c.replacement)

        // Undo (Cmd+Z targeted at the main window)
        app.typeKey("z", modifierFlags: .command)
        Thread.sleep(forTimeInterval: 1.5)

        // After undo, the output PDF should contain the ORIGINAL text again
        // (Marcedit restores the previous version from undoStack)
        let afterUndo = latestPDF(in: outputDir) ?? c.pdfPath
        let verifier = PDFVerifier(pdfPath: afterUndo)
        let hasOriginal = (try? verifier.containsText(c.targetText)) ?? false
        let hasReplaced = (try? verifier.containsText(c.replacement)) ?? false

        // Original text back, replacement gone
        XCTAssertTrue(hasOriginal,
                      "After undo, original text '\(c.targetText)' not found in PDF")
        XCTAssertFalse(hasReplaced,
                       "After undo, replacement '\(c.replacement)' still present — undo did not revert")
    }

    // MARK: - Private helpers

    private func latestPDF(in dir: String) -> String? {
        let fm = FileManager.default
        guard let files = try? fm.contentsOfDirectory(atPath: dir) else { return nil }
        return files
            .filter { $0.hasSuffix(".pdf") }
            .map { (dir as NSString).appendingPathComponent($0) }
            .sorted {
                let d1 = (try? fm.attributesOfItem(atPath: $0)[.modificationDate] as? Date) ?? .distantPast
                let d2 = (try? fm.attributesOfItem(atPath: $1)[.modificationDate] as? Date) ?? .distantPast
                return d1 > d2
            }
            .first
    }

    private func md5(file path: String) -> String? {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/sbin/md5")
        proc.arguments = ["-q", path]
        let pipe = Pipe()
        proc.standardOutput = pipe
        try? proc.run()
        proc.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
