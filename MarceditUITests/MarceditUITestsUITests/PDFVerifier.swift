// PDFVerifier.swift
// MarceditUITests
//
// Verifies the content of output PDFs using an embedded PyMuPDF script run as
// a subprocess.  Does NOT import PDFKit or AppKit — the verifier runs in the
// test process and calls /usr/bin/python3 to inspect the PDF.
//
// Usage:
//   let v = PDFVerifier(pdfPath: outputPath)
//   XCTAssertTrue(try v.containsText("Hi there"))
//   XCTAssertEqual(try v.fontForText("Hi there"), "Helvetica-Bold")

import Foundation
import XCTest

// MARK: - PDFVerifier

struct PDFVerifier {

    let pdfPath: String

    // ---------------------------------------------------------------------------
    // containsText(_:onPage:)
    // Returns true if the given string appears anywhere in the extracted text
    // blocks on the specified page.
    // ---------------------------------------------------------------------------
    func containsText(_ text: String, onPage page: Int = 0) throws -> Bool {
        let blocks = try extractText(onPage: page)
        return blocks.contains { $0.localizedCaseInsensitiveContains(text) }
    }

    // ---------------------------------------------------------------------------
    // extractText(onPage:)
    // Returns an array of text strings — one per PDF text block — from the page.
    // ---------------------------------------------------------------------------
    func extractText(onPage page: Int = 0) throws -> [String] {
        let result = try runScript(mode: "text", page: page, needle: nil)
        guard let arr = result["blocks"] as? [String] else { return [] }
        return arr
    }

    // ---------------------------------------------------------------------------
    // fontForText(_:onPage:)
    // Returns the font family name of the first span that contains the given text,
    // or nil if not found.
    // ---------------------------------------------------------------------------
    func fontForText(_ text: String, onPage page: Int = 0) throws -> String? {
        let result = try runScript(mode: "font", page: page, needle: text)
        return result["font"] as? String
    }

    // MARK: - Private: embedded Python script

    private static let pythonScript = """
import sys, json, fitz

path  = sys.argv[1]
mode  = sys.argv[2]   # "text" | "font"
page_index = int(sys.argv[3])
needle = sys.argv[4] if len(sys.argv) > 4 else ""

try:
    doc  = fitz.open(path)
    page = doc[page_index]

    if mode == "text":
        blocks = page.get_text("blocks")          # list of (x0,y0,x1,y1,text,…)
        texts  = [b[4].strip() for b in blocks if b[4].strip()]
        print(json.dumps({"blocks": texts}))

    elif mode == "font":
        result = None
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if needle.lower() in span["text"].lower():
                        result = span["font"]
                        break
                if result:
                    break
            if result:
                break
        print(json.dumps({"font": result}))

    doc.close()
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
"""

    // ---------------------------------------------------------------------------
    // runScript(mode:page:needle:)
    // Writes the embedded Python to a temp file and invokes it via /usr/bin/python3.
    // ---------------------------------------------------------------------------
    private func runScript(mode: String,
                           page: Int,
                           needle: String?) throws -> [String: Any] {

        // Write script to a stable temp path (overwrite each time — no cleanup needed)
        let scriptPath = NSTemporaryDirectory() + "marcedit_verify.py"
        try PDFVerifier.pythonScript.write(toFile: scriptPath,
                                           atomically: true,
                                           encoding: .utf8)

        // Build arguments
        var args = [scriptPath, pdfPath, mode, String(page)]
        if let n = needle { args.append(n) }

        // Run process
        let (stdout, stderr, exitCode) = runProcess(executable: pythonExecutablePath(),
                                                    arguments: args)

        guard exitCode == 0 else {
            throw PDFVerifierError.scriptFailed(
                "Exit \(exitCode): \(stderr.isEmpty ? stdout : stderr)"
            )
        }

        let trimmed = stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw PDFVerifierError.invalidOutput("Could not parse JSON: \(trimmed)")
        }

        if let err = json["error"] as? String {
            throw PDFVerifierError.scriptFailed(err)
        }
        return json
    }

    private func pythonExecutablePath() -> String {
        let fm = FileManager.default
        let env = ProcessInfo.processInfo.environment
        if let configured = env["MARCEDIT_PYTHON"], fm.isExecutableFile(atPath: configured) {
            return configured
        }

        for candidate in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"] {
            if fm.isExecutableFile(atPath: candidate) {
                return candidate
            }
        }
        return "/usr/bin/python3"
    }

    // ---------------------------------------------------------------------------
    // runProcess — synchronously runs an executable and captures stdout/stderr
    // ---------------------------------------------------------------------------
    private func runProcess(executable: String,
                            arguments: [String]) -> (stdout: String,
                                                      stderr: String,
                                                      exitCode: Int32) {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: executable)
        proc.arguments = arguments

        let outPipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError  = errPipe

        do {
            try proc.run()
        } catch {
            return ("", "Failed to launch: \(error)", 1)
        }
        proc.waitUntilExit()

        let outData  = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData  = errPipe.fileHandleForReading.readDataToEndOfFile()
        let stdout   = String(data: outData, encoding: .utf8) ?? ""
        let stderr   = String(data: errData, encoding: .utf8) ?? ""
        return (stdout, stderr, proc.terminationStatus)
    }
}

// MARK: - PDFVerifierError

enum PDFVerifierError: Error, LocalizedError {
    case scriptFailed(String)
    case invalidOutput(String)

    var errorDescription: String? {
        switch self {
        case .scriptFailed(let msg):  return "PDFVerifier script failed: \(msg)"
        case .invalidOutput(let msg): return "PDFVerifier bad output: \(msg)"
        }
    }
}
