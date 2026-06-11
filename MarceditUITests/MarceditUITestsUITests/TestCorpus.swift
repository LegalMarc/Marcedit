// TestCorpus.swift
// MarceditUITests
//
// Loads the generated PDF corpus manifests from tests/ui_corpus/cases/.
// Each case was created by generate_corpus.py and contains:
//   - input.pdf          (test PDF)
//   - manifest.json      (click position, expected text, replacement, etc.)

import Foundation

// MARK: - CorpusCase

struct CorpusCase: Codable {
    /// Unique ID, e.g. "001_simple_word"
    let id: String
    /// Absolute path to input.pdf (set by generate_corpus.py)
    let pdfPath: String
    /// The full text that should be selected when the test clicks/double-clicks
    let targetText: String
    /// Normalised X position within PDFViewer (0 = left, 1 = right)
    let clickNormX: Double
    /// Normalised Y position within PDFViewer (0 = top, 1 = bottom)
    let clickNormY: Double
    /// Text to type as the replacement
    let replacement: String
    /// Expected text visible in the output PDF after saving
    let expectedOutputText: String
    /// Expected font family in the output PDF, or nil to skip font check
    let expectedFont: String?
    /// 0-based index of the page that contains the target text
    let pageIndex: Int
    /// For split-run cases: what a broken (pre-fix) selection looks like
    let truncatedText: String?

    // ------------------------------------------------------------------
    // Convenience: name suitable for XCTActivity labels
    var displayName: String { id }
}

// MARK: - TestCorpus

struct TestCorpus {

    // ---------------------------------------------------------------------------
    // load() — discover every manifest.json under tests/ui_corpus/cases/ and
    // decode it into a CorpusCase.
    // Returns cases sorted by their ID (lexicographic order matches numeric order
    // for zero-padded IDs like 001_, 002_, …).
    // ---------------------------------------------------------------------------
    static func load() -> [CorpusCase] {
        let fm = FileManager.default

        // Strategy 0a: /tmp/marcedit_uitest_corpus — copied there by the test target
        // build script to avoid macOS Sequoia privacy restrictions on ~/Documents.
        // This is the most reliable path because the test runner can always read /tmp.
        var corpusURL: URL? = nil
        let tmpCorpus = URL(fileURLWithPath: "/tmp/marcedit_uitest_corpus")
        if fm.fileExists(atPath: tmpCorpus.path) {
            corpusURL = tmpCorpus
            print("[TestCorpus] Found corpus at /tmp/marcedit_uitest_corpus")
        }

        // Strategy 0b: /tmp/marcedit_uitest_srcroot.txt written by the test target
        // build script — construct the full path from SRCROOT.
        if corpusURL == nil,
           let srcRootFromFile = try? String(
               contentsOfFile: "/tmp/marcedit_uitest_srcroot.txt", encoding: .utf8
           ) {
            let srcRoot = srcRootFromFile.trimmingCharacters(in: .whitespacesAndNewlines)
            let candidate = URL(fileURLWithPath: srcRoot)
                .appendingPathComponent("tests/ui_corpus/cases")
            if fm.fileExists(atPath: candidate.path) {
                corpusURL = candidate
                print("[TestCorpus] Found corpus via srcroot file: \(candidate.path)")
            }
        }

        // Strategy 1: MARCEDIT_SRCROOT env var set by the xcscheme
        if corpusURL == nil,
           let srcRoot = ProcessInfo.processInfo.environment["MARCEDIT_SRCROOT"] {
            let candidate = URL(fileURLWithPath: srcRoot)
                .appendingPathComponent("tests/ui_corpus/cases")
            if fm.fileExists(atPath: candidate.path) {
                corpusURL = candidate
            }
        }

        // Strategy 2: Walk upward from the test bundle URL (fallback)
        if corpusURL == nil,
           let bundleURL = Bundle(for: _TestCorpusAnchor.self).bundleURL
                             .resolvingSymlinksInPath() as URL? {
            var searchDir: URL? = bundleURL
            for _ in 0..<15 {
                guard let dir = searchDir else { break }
                let candidate = dir.appendingPathComponent("tests/ui_corpus/cases")
                if fm.fileExists(atPath: candidate.path) {
                    corpusURL = candidate
                    break
                }
                searchDir = dir.deletingLastPathComponent()
            }
        }

        // Strategy 3: Walk up from the process current working directory
        if corpusURL == nil {
            var searchDir: URL? = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            for _ in 0..<10 {
                guard let dir = searchDir else { break }
                let candidate = dir.appendingPathComponent("tests/ui_corpus/cases")
                if fm.fileExists(atPath: candidate.path) {
                    corpusURL = candidate
                    break
                }
                searchDir = dir.deletingLastPathComponent()
            }
        }

        // Strategy 4: Check other common xcodebuild-set env vars
        for envKey in ["SOURCE_ROOT", "PROJECT_DIR", "SRCROOT"] {
            if corpusURL != nil { break }
            if let root = ProcessInfo.processInfo.environment[envKey] {
                let candidate = URL(fileURLWithPath: root)
                    .appendingPathComponent("tests/ui_corpus/cases")
                if fm.fileExists(atPath: candidate.path) {
                    corpusURL = candidate
                }
            }
        }

        guard let casesDir = corpusURL else {
            print("[TestCorpus] WARNING: Could not locate tests/ui_corpus/cases/")
            print("[TestCorpus]   Env vars: \(ProcessInfo.processInfo.environment.filter { $0.key.contains("ROOT") || $0.key.contains("DIR") || $0.key.contains("MARCEDIT") })")
            return []
        }

        // Enumerate case subdirectories
        var cases: [CorpusCase] = []
        do {
            let entries = try fm.contentsOfDirectory(
                at: casesDir,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            )
            for entry in entries {
                var isDir: ObjCBool = false
                fm.fileExists(atPath: entry.path, isDirectory: &isDir)
                guard isDir.boolValue else { continue }

                let manifestURL = entry.appendingPathComponent("manifest.json")
                guard fm.fileExists(atPath: manifestURL.path) else { continue }

                do {
                    let data = try Data(contentsOf: manifestURL)
                    let decoder = JSONDecoder()
                    var c = try decoder.decode(CorpusCase.self, from: data)
                    // If pdfPath is relative, make it absolute relative to the case dir
                    if !c.pdfPath.hasPrefix("/") {
                        let abs = entry.appendingPathComponent(c.pdfPath).path
                        c = CorpusCase(
                            id: c.id,
                            pdfPath: abs,
                            targetText: c.targetText,
                            clickNormX: c.clickNormX,
                            clickNormY: c.clickNormY,
                            replacement: c.replacement,
                            expectedOutputText: c.expectedOutputText,
                            expectedFont: c.expectedFont,
                            pageIndex: c.pageIndex,
                            truncatedText: c.truncatedText
                        )
                    }
                    cases.append(c)
                } catch {
                    print("[TestCorpus] Failed to decode \(manifestURL.path): \(error)")
                }
            }
        } catch {
            print("[TestCorpus] Failed to enumerate cases dir: \(error)")
        }

        return cases.sorted { $0.id < $1.id }
    }

    // ---------------------------------------------------------------------------
    // Convenience: load a single case by ID
    // ---------------------------------------------------------------------------
    static func loadCase(id: String) -> CorpusCase? {
        load().first { $0.id == id || $0.id.hasPrefix(id) }
    }
}

// Used only for Bundle(for:) so we can walk upward from the test bundle
private final class _TestCorpusAnchor: NSObject {}
