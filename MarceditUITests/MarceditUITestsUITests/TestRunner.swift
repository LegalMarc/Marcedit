// TestRunner.swift
// MarceditUITests
//
// Base XCTestCase subclass for all Marcedit UI tests.
//
// Provides:
//   - `app`        — the XCUIApplication under test
//   - `corpus`     — all loaded CorpusCases
//   - `setUpWithError()`  — CI/sentinel skip guards and test launch configuration
//   - `tearDown()` — XCTest cleanup
//   - Helper: `runCase(_:verify:)` — full edit-and-verify pipeline
//   - Helper: `verifyOutputPDF(at:contains:font:page:)`
//
// CI Safety:
//   Set MARCEDIT_FORCE_UI_TESTS=1 to run UI tests in CI environments.
//   Create /tmp/marcedit_skip_ui_tests to skip on a per-machine basis.

import XCTest
import Foundation

struct XCUICaseResult: Codable {
    let testName: String
    let caseID: String
    let page: Int
    let targetText: String
    let replacement: String
    let expectedOutputText: String
    let expectedFont: String?
    let inputPDF: String
    let outputPDF: String
    let status: String
    let message: String
}

private struct XCUICaseFailure: Error, CustomStringConvertible {
    let description: String

    init(_ description: String) {
        self.description = description
    }
}

class MarceditTestCase: XCTestCase {

    // MARK: - Properties

    var app: XCUIApplication!
    var corpus: [CorpusCase] = []

    // MARK: - setUp / tearDown

    override func setUpWithError() throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        let forceUITests = env["MARCEDIT_FORCE_UI_TESTS"] == "1"

        // Skip in CI unless explicitly forced
        if !forceUITests {
            if env["CI"] == "1" || env["CODEX_CI"] == "1" || env["GITHUB_ACTIONS"] == "true" {
                throw XCTSkip("UI tests skipped in CI environment. Set MARCEDIT_FORCE_UI_TESTS=1 to override.")
            }
        }

        // Skip via sentinel file (per-machine disable mechanism)
        let tmpDir = env["TMPDIR"] ?? "/tmp/"
        let sentinelPath = tmpDir + "marcedit_skip_ui_tests"
        if FileManager.default.fileExists(atPath: sentinelPath) {
            let reason = (try? String(contentsOfFile: sentinelPath, encoding: .utf8))?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            throw XCTSkip("Skip sentinel at \(sentinelPath)\(reason.isEmpty ? "" : ": \(reason)")")
        }

        app = XCUIApplication()
        app.launchEnvironment["UITEST_ACTIVE"] = "1"

        // Prevent window restoration so each test starts with a clean slate
        app.launchArguments += [
            "-ApplePersistenceIgnoreState", "YES",
            "-NSQuitAlwaysKeepsWindows", "NO"
        ]

        corpus = TestCorpus.load()

        if corpus.isEmpty {
            XCTFail("""
                [TestRunner] No corpus cases found.
                Run: python3 tests/ui_corpus/generate_corpus.py
                """)
        }

        // Stale app cleanup is handled by tests/run_visual_tests.sh before xcodebuild
        // starts. Calling XCUIApplication.terminate() here can block while XCTest
        // resolves stale app state before the app has launched.
    }

    override func tearDown() {
        super.tearDown()
    }

    // MARK: - Convenience: full edit pipeline

    /// Loads a corpus case, drives the full edit flow, and calls the verify closure.
    /// - Parameters:
    ///   - caseID:   prefix or full case ID, e.g. "001" or "001_simple_word"
    ///   - verify:   closure passed the output PDF path and the verifier
    func runCase(_ caseID: String,
                 verify: (String, PDFVerifier) throws -> Void) throws {
        guard let c = corpus.first(where: {
            $0.id == caseID || $0.id.hasPrefix(caseID)
        }) else {
            XCTFail("Corpus case '\(caseID)' not found")
            return
        }

        let outputDir = app.launchWithCorpusCase(c)

        XCTAssertTrue(app.waitForPDFReady(timeout: 90),
                      "App did not reach ready state")

        // Wait for the TestBridge to auto-open the PDF (1.5s delay in TestBridge)
        Thread.sleep(forTimeInterval: 1.5)

        // Open edit dialog by double-clicking at the corpus click coordinates
        app.openEditDialog(for: c)

        XCTAssertTrue(app.waitForEditDialog(timeout: 15),
                      "Edit dialog did not appear after double-click on case \(c.id)")

        // Verify selection matches targetText
        let selected = app.readSelectedText()
        XCTAssertEqual(selected, c.targetText,
                       "Selected text mismatch for case \(c.id)")

        // Type replacement
        app.typeReplacement(c.replacement)

        // Save
        app.saveEdit()

        // Wait for app to write output — Marcedit saves to the same path by default.
        // When run with --test-output-dir the Python layer writes to that dir.
        // Poll for an output PDF, falling back to the input path.
        let outputPath: String
        if let found = app.waitForOutputFile(in: outputDir) {
            outputPath = found
        } else {
            let inputPDFDir = (outputDir as NSString).deletingLastPathComponent
            outputPath = (inputPDFDir as NSString).appendingPathComponent("input.pdf")
        }

        let verifier = PDFVerifier(pdfPath: outputPath)
        try verify(outputPath, verifier)
    }

    // MARK: - Convenience: full edit pipeline with visual capture

    /// Like `runCase`, but emits a lightweight per-case manifest for the external
    /// visual renderer. Rendering happens after XCTest exits to avoid sandbox flake.
    func runCaseWithVisualCapture(_ caseID: String,
                                  testName: String = #function,
                                  verify: (String, PDFVerifier) throws -> Void) throws {
        guard let c = corpus.first(where: {
            $0.id == caseID || $0.id.hasPrefix(caseID)
        }) else {
            XCTFail("Corpus case '\(caseID)' not found")
            return
        }

        let outputDir = app.launchWithCorpusCase(c, autoOpenEdit: true)
        let inputPDFDir = (outputDir as NSString).deletingLastPathComponent
        let inputPDF = (inputPDFDir as NSString).appendingPathComponent("input.pdf")
        var outputPath = inputPDF
        do {
            guard app.waitForPDFReady(timeout: 90) else {
                throw XCUICaseFailure("App did not reach ready state")
            }

            Thread.sleep(forTimeInterval: 1.5)

            // ---------- Drive the edit ----------
            if !app.waitForEditDialog(timeout: 10) {
                app.openEditDialog(for: c)
                guard app.waitForEditDialog(timeout: 15) else {
                    throw XCUICaseFailure("Edit dialog did not appear for case \(c.id)")
                }
            }

            let selected = app.readSelectedText()
            guard selected == c.targetText else {
                throw XCUICaseFailure(
                    "Selected text mismatch for case \(c.id): expected '\(c.targetText)', got '\(selected)'"
                )
            }

            app.typeReplacement(c.replacement)
            app.saveEdit()
            Thread.sleep(forTimeInterval: 1.5)

            // ---------- Locate output PDF ----------
            if let found = app.waitForOutputFile(in: outputDir) {
                outputPath = found
            }

            // ---------- Run the caller's verification closure ----------
            let verifier = PDFVerifier(pdfPath: outputPath)
            try verify(outputPath, verifier)
            writeXCUICaseResult(XCUICaseResult(
                testName: testName,
                caseID: c.id,
                page: c.pageIndex,
                targetText: c.targetText,
                replacement: c.replacement,
                expectedOutputText: c.expectedOutputText,
                expectedFont: c.expectedFont,
                inputPDF: inputPDF,
                outputPDF: outputPath,
                status: "success",
                message: ""
            ), in: inputPDFDir)
        } catch {
            writeXCUICaseResult(XCUICaseResult(
                testName: testName,
                caseID: c.id,
                page: c.pageIndex,
                targetText: c.targetText,
                replacement: c.replacement,
                expectedOutputText: c.expectedOutputText,
                expectedFont: c.expectedFont,
                inputPDF: inputPDF,
                outputPDF: outputPath,
                status: "failed",
                message: String(describing: error)
            ), in: inputPDFDir)
            throw error
        }
    }

    private func writeXCUICaseResult(_ result: XCUICaseResult, in directory: String) {
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(result)
            try FileManager.default.createDirectory(
                atPath: directory,
                withIntermediateDirectories: true,
                attributes: nil
            )
            let url = URL(fileURLWithPath: directory)
                .appendingPathComponent("xcui_case_result.json")
            try data.write(to: url, options: .atomic)
            print("[XCUICaseResult] wrote \(url.path)")
        } catch {
            XCTFail("Failed to write XCUITest visual manifest for \(result.caseID): \(error)")
        }
    }

    // MARK: - Convenience: verifyOutputPDF

    func verifyOutputPDF(at path: String,
                         contains text: String,
                         font expectedFont: String? = nil,
                         page: Int = 0,
                         file: StaticString = #file,
                         line: UInt = #line) {
        let verifier = PDFVerifier(pdfPath: path)
        do {
            let found = try verifier.containsText(text, onPage: page)
            XCTAssertTrue(found,
                          "Output PDF does not contain '\(text)' on page \(page)",
                          file: file, line: line)

            if let expectedFont = expectedFont {
                let actualFont = try verifier.fontForText(text, onPage: page)
                // Font names may include style suffix (e.g. "Helvetica-Bold");
                // check for containment to be resilient to minor naming differences.
                let match = actualFont.map {
                    $0.localizedCaseInsensitiveContains(
                        expectedFont.components(separatedBy: "-").first ?? expectedFont
                    )
                } ?? false
                XCTAssertTrue(match,
                              "Font mismatch for '\(text)': expected '\(expectedFont)', got '\(actualFont ?? "nil")'",
                              file: file, line: line)
            }
        } catch {
            XCTFail("PDFVerifier error for '\(text)': \(error)", file: file, line: line)
        }
    }

    // MARK: - Class-level sentinel helpers

    /// Creates a sentinel file that causes all UI tests to skip until removed.
    /// Useful for temporarily disabling tests during rapid development.
    static func createSkipSentinel(reason: String = "") {
        let env = ProcessInfo.processInfo.environment
        let tmpDir = env["TMPDIR"] ?? "/tmp/"
        let path = tmpDir + "marcedit_skip_ui_tests"
        try? reason.write(toFile: path, atomically: true, encoding: .utf8)
    }

    /// Removes the skip sentinel, re-enabling UI tests.
    static func removeSkipSentinel() {
        let env = ProcessInfo.processInfo.environment
        let tmpDir = env["TMPDIR"] ?? "/tmp/"
        let path = tmpDir + "marcedit_skip_ui_tests"
        try? FileManager.default.removeItem(atPath: path)
    }
}
