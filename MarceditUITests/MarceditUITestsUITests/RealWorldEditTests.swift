// RealWorldEditTests.swift
// MarceditUITests
//
// Core end-to-end edit + verify test suite.
// Each test corresponds to one corpus case (001–005).
//
// What these tests validate:
//   001 — Basic single-word replacement
//   002 — Full-line replacement (longer text)
//   003 — Split text runs on one visual line (regression test for joinedLineSelection fix)
//   004 — Multi-page: edit on page 2
//   005 — Font preservation (Helvetica-Bold)

import XCTest

struct XCTVisualVerificationError: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}

final class RealWorldEditTests: MarceditTestCase {

    // MARK: - Case 001: Simple word replacement

    func testCase001_SimpleWord() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("001") }) else {
            XCTFail("Corpus case 001 not found — run generate_corpus.py"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))

        // TestBridge auto-opens the PDF after 1.5 s; wait for it
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(), "Edit sheet did not open for case 001")

        let selected = app.readSelectedText()
        XCTAssertEqual(selected, c.targetText,
                       "001: selected text should be '\(c.targetText)', got '\(selected)'")

        app.typeReplacement(c.replacement)
        app.saveEdit()

        // Allow a moment for the file write
        Thread.sleep(forTimeInterval: 1.5)

        let outputPath = latestPDF(in: outputDir) ?? fallbackInputPath(for: c)
        verifyOutputPDF(at: outputPath,
                        contains: c.expectedOutputText,
                        font: c.expectedFont,
                        page: c.pageIndex)
    }

    // MARK: - Case 002: Full-line replacement

    func testCase002_FullLine() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("002") }) else {
            XCTFail("Corpus case 002 not found"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(), "Edit sheet did not open for case 002")

        XCTAssertEqual(app.readSelectedText(), c.targetText,
                       "002: unexpected selection")

        app.typeReplacement(c.replacement)
        app.saveEdit()
        Thread.sleep(forTimeInterval: 1.5)

        let outputPath = latestPDF(in: outputDir) ?? fallbackInputPath(for: c)
        verifyOutputPDF(at: outputPath,
                        contains: c.expectedOutputText,
                        page: c.pageIndex)
    }

    // MARK: - Case 003: Split text runs — key regression test

    /// This test directly validates the joinedLineSelection() fix.
    ///
    /// The input PDF has TWO separate PDF text objects at the SAME visual Y:
    ///   object 1 at x=72: "Hello "
    ///   object 2 at x=106: "World!"
    ///
    /// Pre-fix: selectionForLine returned only "Hello " (first object only).
    /// Post-fix: joinedLineSelection() uses a horizontal band rect to merge both
    ///           objects into "Hello World!" before populating EditTextInput.
    ///
    /// The test additionally uses the `truncatedText` manifest field to assert that
    /// the BROKEN selection does NOT appear (belt-and-suspenders regression guard).
    func testCase003_SplitRunsNoTruncation() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("003") }) else {
            XCTFail("Corpus case 003 not found"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Double-click in the FIRST text object ("Hello ") at the click coords
        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(), "Edit sheet did not open for case 003")

        let selected = app.readSelectedText()

        // PRIMARY assertion: full joined text is selected
        XCTAssertEqual(selected, c.targetText,
                       "003 (split-runs): joinedLineSelection should produce '\(c.targetText)'; got '\(selected)'")

        // SECONDARY assertion: broken/truncated text must NOT appear
        if let truncated = c.truncatedText {
            XCTAssertNotEqual(selected, truncated,
                              "003 (split-runs): REGRESSION — selection is the truncated '\(truncated)' only")
        }

        // Complete the edit to verify the full replace+save pipeline
        app.typeReplacement(c.replacement)
        app.saveEdit()
        Thread.sleep(forTimeInterval: 1.5)

        let outputPath = latestPDF(in: outputDir) ?? fallbackInputPath(for: c)
        verifyOutputPDF(at: outputPath,
                        contains: c.expectedOutputText,
                        page: c.pageIndex)
    }

    // MARK: - Case 004: Multi-page edit

    /// Edits text on page 2 (index 1). The PDFViewer must scroll/navigate to the
    /// second page.  We use postDistributed to jump to page 2 before clicking.
    func testCase004_MultiPage() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("004") }) else {
            XCTFail("Corpus case 004 not found"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        // Ask the app to navigate to page 2 via distributed notification
        app.postDistributed("com.marcedit.test.GoToPage",
                            userInfo: ["pageIndex": c.pageIndex])
        Thread.sleep(forTimeInterval: 0.6)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(timeout: 15),
                      "Edit sheet did not open for case 004 (page 2)")

        XCTAssertEqual(app.readSelectedText(), c.targetText,
                       "004: unexpected selection on page 2")

        app.typeReplacement(c.replacement)
        app.saveEdit()
        Thread.sleep(forTimeInterval: 1.5)

        let outputPath = latestPDF(in: outputDir) ?? fallbackInputPath(for: c)
        verifyOutputPDF(at: outputPath,
                        contains: c.expectedOutputText,
                        page: c.pageIndex)
    }

    // MARK: - Case 005: Font preservation

    func testCase005_FontPreservation() throws {
        guard let c = corpus.first(where: { $0.id.hasPrefix("005") }) else {
            XCTFail("Corpus case 005 not found"); return
        }
        guard let expectedFont = c.expectedFont else {
            XCTFail("Case 005 has no expectedFont in manifest"); return
        }

        let outputDir = app.launchWithCorpusCase(c)
        XCTAssertTrue(app.waitForPDFReady(timeout: 90))
        Thread.sleep(forTimeInterval: 1.5)

        app.openEditDialogAt(normalizedX: c.clickNormX, normalizedY: c.clickNormY)
        XCTAssertTrue(app.waitForEditDialog(), "Edit sheet did not open for case 005")

        XCTAssertEqual(app.readSelectedText(), c.targetText,
                       "005: unexpected selection")

        app.typeReplacement(c.replacement)
        app.saveEdit()
        Thread.sleep(forTimeInterval: 2.0)

        let outputPath = latestPDF(in: outputDir) ?? fallbackInputPath(for: c)

        // Font preservation is the primary check for this case
        verifyOutputPDF(at: outputPath,
                        contains: c.expectedOutputText,
                        font: expectedFont,
                        page: c.pageIndex)
    }

    // MARK: - Visual Report: all cases

    /// Runs all corpus cases and emits per-case manifests for the external
    /// renderer that builds the final /tmp/marcedit_visual_report artifacts.
    func testVisualReport_AllCases() throws {
        for c in corpus {
            try runCaseWithVisualCapture(c.id) { outputPath, verifier in
                guard try verifier.containsText(c.expectedOutputText, onPage: c.pageIndex) else {
                    throw XCTVisualVerificationError(
                        "Output PDF at \(outputPath) does not contain '\(c.expectedOutputText)' on page \(c.pageIndex)"
                    )
                }
                if let expectedFont = c.expectedFont {
                    let actualFont = try verifier.fontForText(c.expectedOutputText, onPage: c.pageIndex)
                    let expectedFamily = expectedFont.components(separatedBy: "-").first ?? expectedFont
                    guard actualFont?.localizedCaseInsensitiveContains(expectedFamily) == true else {
                        throw XCTVisualVerificationError(
                            "Font mismatch for '\(c.expectedOutputText)': expected '\(expectedFont)', got '\(actualFont ?? "nil")'"
                        )
                    }
                }
            }
            app.terminate()
            Thread.sleep(forTimeInterval: 0.5)
        }
    }

    // MARK: - Private helpers

    private func latestPDF(in dir: String) -> String? {
        let fm = FileManager.default
        guard let files = try? fm.contentsOfDirectory(atPath: dir) else { return nil }
        let pdfs = files.filter { $0.hasSuffix(".pdf") }
            .map { (dir as NSString).appendingPathComponent($0) }
            .sorted {
                let d1 = (try? FileManager.default.attributesOfItem(atPath: $0)[.modificationDate] as? Date) ?? .distantPast
                let d2 = (try? FileManager.default.attributesOfItem(atPath: $1)[.modificationDate] as? Date) ?? .distantPast
                return d1 > d2
            }
        return pdfs.first
    }

    private func fallbackInputPath(for c: CorpusCase) -> String {
        // The TestBridge copied input.pdf to /tmp/marcedit_uitest_<id>_<ts>/input.pdf
        let fm = FileManager.default
        let tmp = NSTemporaryDirectory()
        if let match = (try? fm.contentsOfDirectory(atPath: tmp))?
            .first(where: { $0.hasPrefix("marcedit_uitest_\(c.id)_") }) {
            return tmp + match + "/input.pdf"
        }
        return c.pdfPath
    }
}
