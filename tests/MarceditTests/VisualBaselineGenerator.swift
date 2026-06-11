import XCTest
import PDFKit
@testable import Marcedit

/// Utility for generating visual regression baselines
/// Run this when intentionally updating baselines after verified changes
final class VisualBaselineGenerator {

    // MARK: - Properties

    private let framework: VisualRegressionFramework
    private let pdfCorpus: PDFTestCorpus
    private let testDirectory: URL

    // MARK: - Lifecycle

    init(testDirectory: URL) {
        self.testDirectory = testDirectory

        let config = VisualRegressionFramework.Config(baseDirectory: testDirectory)
        self.framework = VisualRegressionFramework(config: config)
        self.pdfCorpus = PDFTestCorpus(tempDirectory: testDirectory)
    }

    // MARK: - Baseline Generation

    /// Generate all baselines for the standard test corpus
    func generateAllBaselines() throws -> BaselineGenerationReport {
        var report = BaselineGenerationReport()

        // Simple PDF baseline
        report.add(try generateSimplePDFBaseline())

        // Font-specific baselines
        report.add(try generateFontBaselines())

        // Multi-page baseline
        report.add(try generateMultiPageBaseline())

        // Unicode baseline
        report.add(try generateUnicodeBaseline())

        // Text replacement baselines
        report.add(try generateTextReplacementBaselines())

        return report
    }

    // MARK: - Individual Baseline Generators

    private func generateSimplePDFBaseline() throws -> String {
        let pdf = try pdfCorpus.createSimplePDF(text: "Simple baseline test")
        _ = try framework.captureBaseline(pdfURL: pdf, pageIndex: 0, identifier: "simple_pdf_baseline")
        return "simple_pdf_baseline"
    }

    private func generateFontBaselines() throws -> [String] {
        var identifiers: [String] = []

        // Helvetica
        let helveticaPDF = try pdfCorpus.createPDFWithFont(
            text: "Helvetica baseline text",
            fontName: "Helvetica",
            fontSize: 12
        )
        _ = try framework.captureBaseline(pdfURL: helveticaPDF, pageIndex: 0, identifier: "font_helvetica_baseline")
        identifiers.append("font_helvetica_baseline")

        // Times
        let timesPDF = try pdfCorpus.createPDFWithFont(
            text: "Times baseline text",
            fontName: "Times-Roman",
            fontSize: 14
        )
        _ = try framework.captureBaseline(pdfURL: timesPDF, pageIndex: 0, identifier: "font_times_baseline")
        identifiers.append("font_times_baseline")

        // Courier
        let courierPDF = try pdfCorpus.createPDFWithFont(
            text: "Courier baseline text",
            fontName: "Courier",
            fontSize: 10
        )
        _ = try framework.captureBaseline(pdfURL: courierPDF, pageIndex: 0, identifier: "font_courier_baseline")
        identifiers.append("font_courier_baseline")

        return identifiers
    }

    private func generateMultiPageBaseline() throws -> [String] {
        var identifiers: [String] = []

        let pages = ["Page 1", "Page 2", "Page 3"]
        let multiPagePDF = try pdfCorpus.createMultiPagePDF(pages: 3, textPerPage: pages)

        for pageIndex in 0..<3 {
            let identifier = "multipage_page\(pageIndex)_baseline"
            _ = try framework.captureBaseline(pdfURL: multiPagePDF, pageIndex: pageIndex, identifier: identifier)
            identifiers.append(identifier)
        }

        return identifiers
    }

    private func generateUnicodeBaseline() throws -> String {
        let unicodePDF = try pdfCorpus.createSimplePDF(text: "Unicode: 世界 🌍 Привет")
        _ = try framework.captureBaseline(pdfURL: unicodePDF, pageIndex: 0, identifier: "unicode_baseline")
        return "unicode_baseline"
    }

    private func generateTextReplacementBaselines() throws -> [String] {
        var identifiers: [String] = []

        // Before replacement
        let beforePDF = try pdfCorpus.createSimplePDF(text: "Original text before replacement")
        _ = try framework.captureBaseline(pdfURL: beforePDF, pageIndex: 0, identifier: "replacement_before_baseline")
        identifiers.append("replacement_before_baseline")

        // After replacement (simulated)
        let afterPDF = try pdfCorpus.createSimplePDF(text: "Modified text after replacement")
        _ = try framework.captureBaseline(pdfURL: afterPDF, pageIndex: 0, identifier: "replacement_after_baseline")
        identifiers.append("replacement_after_baseline")

        return identifiers
    }

    // MARK: - Baseline Management

    /// List all existing baselines
    func listBaselines() throws -> [String] {
        let baselineDir = testDirectory.appendingPathComponent("Baselines")
        let contents = try FileManager.default.contentsOfDirectory(
            at: baselineDir,
            includingPropertiesForKeys: nil
        )

        return contents
            .filter { $0.pathExtension == "png" }
            .map { $0.deletingPathExtension().lastPathComponent }
            .sorted()
    }

    /// Delete all baselines (use with caution!)
    func deleteAllBaselines() throws {
        try framework.deleteAllBaselines()
    }

    /// Delete specific baseline
    func deleteBaseline(identifier: String) throws {
        try framework.deleteBaseline(identifier: identifier)
    }
}

// MARK: - Supporting Types

struct BaselineGenerationReport {
    private(set) var identifiers: [String] = []

    mutating func add(_ identifier: String) {
        identifiers.append(identifier)
    }

    mutating func add(_ identifiers: [String]) {
        self.identifiers.append(contentsOf: identifiers)
    }

    var count: Int {
        identifiers.count
    }

    var summary: String {
        """
        Baseline Generation Report
        --------------------------
        Total baselines generated: \(count)

        Identifiers:
        \(identifiers.map { "  - \($0)" }.joined(separator: "\n"))
        """
    }
}
