// VisualReport.swift
// MarceditUITests
//
// Accumulates visual verification entries during a test run and generates
// a self-contained HTML report + JSON manifest that an LLM can read to
// visually inspect PDF edit quality.
//
// Output goes to /tmp/marcedit_visual_report/ by default.
//
// Usage:
//   VisualReport.shared.addEntry(...)
//   VisualReport.shared.writeReport()   // call in class tearDown

import Foundation

// MARK: - VisualReportEntry

struct VisualReportEntry: Codable {
    let testName: String
    let caseID: String
    let page: Int
    let targetText: String
    let replacement: String
    let beforePNG: String
    let afterPNG: String
    let cropBeforePNG: String?
    let cropAfterPNG: String?
    let diffBBox: [Int]?    // [x0, y0, x1, y1] or nil
    let status: String      // "success" | "failed" | "skipped"
    let message: String
}

// MARK: - VisualReport

class VisualReport {

    static var outputDir: String {
        ProcessInfo.processInfo.environment["MARCEDIT_VISUAL_REPORT_DIR"]
            ?? FileManager.default.temporaryDirectory
                .appendingPathComponent("marcedit_visual_report", isDirectory: true)
                .path
    }
    static let shared = VisualReport()

    private var entries: [VisualReportEntry] = []
    private let lock = NSLock()

    // ---------------------------------------------------------------------------
    // addEntry
    // ---------------------------------------------------------------------------
    func addEntry(_ entry: VisualReportEntry) {
        lock.lock()
        entries.append(entry)
        lock.unlock()
    }

    // ---------------------------------------------------------------------------
    // ensureOutputDir
    // Creates the output directory and per-case subdirectories.
    // ---------------------------------------------------------------------------
    static func ensureOutputDir() {
        try? FileManager.default.createDirectory(
            atPath: outputDir,
            withIntermediateDirectories: true
        )
    }

    /// Creates a per-case output subdirectory and returns its path.
    static func caseDir(for caseID: String) -> String {
        let path = (outputDir as NSString).appendingPathComponent(caseID)
        try? FileManager.default.createDirectory(
            atPath: path,
            withIntermediateDirectories: true
        )
        return path
    }

    // ---------------------------------------------------------------------------
    // writeReport
    // Writes both visual_report.json and visual_report.html to outputDir.
    // ---------------------------------------------------------------------------
    func writeReport() {
        lock.lock()
        let snapshot = entries
        lock.unlock()

        guard !snapshot.isEmpty else { return }

        VisualReport.ensureOutputDir()
        writeJSON(snapshot)
        writeHTML(snapshot)
    }

    // MARK: - JSON

    private func writeJSON(_ entries: [VisualReportEntry]) {
        let path = (VisualReport.outputDir as NSString).appendingPathComponent("visual_report.json")
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(entries) else { return }
        try? data.write(to: URL(fileURLWithPath: path))
    }

    // MARK: - HTML

    private func writeHTML(_ entries: [VisualReportEntry]) {
        let path = (VisualReport.outputDir as NSString).appendingPathComponent("visual_report.html")
        let baseDir = VisualReport.outputDir

        let successCount = entries.filter { $0.status == "success" }.count
        let failedCount  = entries.filter { $0.status == "failed" }.count
        let skippedCount = entries.filter { $0.status == "skipped" }.count

        let timestamp = {
            let df = DateFormatter()
            df.dateFormat = "yyyy-MM-dd HH:mm:ss"
            return df.string(from: Date())
        }()

        var editCards = ""
        for entry in entries {
            let bg = entry.status == "success" ? "#d4edda" : "#f8d7da"
            let statusColor = entry.status == "success" ? "green" : "red"

            let beforeImg = imgTag(entry.beforePNG, baseDir: baseDir, maxWidth: 420)
            let afterImg  = imgTag(entry.afterPNG, baseDir: baseDir, maxWidth: 420)

            let cropBeforeImg = entry.cropBeforePNG.map { imgTag($0, baseDir: baseDir, maxWidth: 300) } ?? "(no crop)"
            let cropAfterImg  = entry.cropAfterPNG.map { imgTag($0, baseDir: baseDir, maxWidth: 300) } ?? "(no crop)"

            let bboxStr = entry.diffBBox.map { "[\($0.map(String.init).joined(separator: ", "))]" } ?? "none"

            let messageHTML = entry.message.isEmpty ? "" : "<br><i>\(escapeHTML(entry.message))</i>"

            editCards += """
            <div style="background:\(bg);margin:12px 0;padding:12px;border-radius:6px">
              <b>\(escapeHTML(entry.testName))</b> — case \(escapeHTML(entry.caseID)) — page \(entry.page)
              — <span style="color:\(statusColor)">\(entry.status.uppercased())</span><br>
              <code>\(escapeHTML(String(entry.targetText.prefix(60))))</code>
              → <code>\(escapeHTML(String(entry.replacement.prefix(60))))</code>
              \(messageHTML)
              <br><small>Diff bbox: \(bboxStr)</small>
              <table style="margin-top:8px"><tr>
                <td style="padding-right:12px;vertical-align:top"><b>Before</b><br>\(beforeImg)</td>
                <td style="padding-right:12px;vertical-align:top"><b>After</b><br>\(afterImg)</td>
                <td style="vertical-align:top"><b>Crop (Before → After)</b><br>
                  \(cropBeforeImg)<br>\(cropAfterImg)
                </td>
              </tr></table>
            </div>
            """
        }

        let html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <title>Marcedit XCUITest Visual Report</title>
        <style>
          body { font-family: -apple-system, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }
          table { border-collapse: collapse; }
          code { background: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-size: 12px; }
          img { border: 1px solid #ccc; }
        </style>
        </head>
        <body>
        <h1>Marcedit — XCUITest Visual Report</h1>
        <p>Generated: \(timestamp)</p>
        <h2>Summary</h2>
        <p>Total: \(entries.count) &nbsp;|&nbsp;
           ✓ \(successCount) succeeded &nbsp;|&nbsp;
           ✗ \(failedCount) failed &nbsp;|&nbsp;
           — \(skippedCount) skipped</p>

        \(editCards)

        </body>
        </html>
        """

        try? html.write(toFile: path, atomically: true, encoding: .utf8)
    }

    // MARK: - Helpers

    private func imgTag(_ absPath: String, baseDir: String, maxWidth: Int) -> String {
        // Make path relative to baseDir for portable HTML
        let relPath: String
        if absPath.hasPrefix(baseDir) {
            relPath = String(absPath.dropFirst(baseDir.count + 1))
        } else {
            relPath = absPath
        }
        return "<img src=\"\(escapeHTML(relPath))\" style=\"max-width:\(maxWidth)px\">"
    }

    private func escapeHTML(_ text: String) -> String {
        text.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }
}
