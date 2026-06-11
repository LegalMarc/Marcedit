// VisualVerifier.swift
// MarceditUITests
//
// Renders PDF pages to PNG and computes pixel diffs for visual verification.
// Uses the same subprocess pattern as PDFVerifier.swift — an embedded PyMuPDF
// script is written to /tmp and invoked via /usr/bin/python3.
//
// Usage:
//   let v = VisualVerifier()
//   try v.renderPage(ofPDF: path, page: 0, dpi: 150, to: "/tmp/before.png")
//   try v.renderPage(ofPDF: path, page: 0, dpi: 150, to: "/tmp/after.png")
//   let bbox = try v.computeDiffBBox(before: "/tmp/before.png", after: "/tmp/after.png")
//   try v.saveCrop(before: "/tmp/before.png", after: "/tmp/after.png",
//                  cropBefore: "/tmp/crop_before.png", cropAfter: "/tmp/crop_after.png")

import Foundation

// MARK: - VisualVerifier

struct VisualVerifier {

    static let defaultDPI: Int = 150
    static let defaultThreshold: Int = 8
    static let defaultCropPadding: Int = 80

    // ---------------------------------------------------------------------------
    // renderPage(ofPDF:page:dpi:to:)
    // Renders a single PDF page to a PNG file at the given DPI.
    // ---------------------------------------------------------------------------
    func renderPage(ofPDF pdfPath: String, page: Int = 0,
                    dpi: Int = VisualVerifier.defaultDPI,
                    to outputPath: String) throws {
        try? FileManager.default.createDirectory(
            atPath: (outputPath as NSString).deletingLastPathComponent,
            withIntermediateDirectories: true
        )
        let result = try runScript(
            mode: "render",
            args: [pdfPath, String(page), String(dpi), outputPath]
        )
        if let error = result["error"] as? String {
            throw VisualVerifierError.renderFailed(error)
        }
    }

    // ---------------------------------------------------------------------------
    // computeDiffBBox(before:after:threshold:)
    // Returns (x0, y0, x1, y1) bounding box of pixels that differ, or nil if identical.
    // ---------------------------------------------------------------------------
    func computeDiffBBox(before: String, after: String,
                         threshold: Int = VisualVerifier.defaultThreshold) throws -> (Int, Int, Int, Int)? {
        let result = try runScript(
            mode: "diff",
            args: [before, after, String(threshold)]
        )
        if let error = result["error"] as? String {
            throw VisualVerifierError.diffFailed(error)
        }
        guard let bbox = result["bbox"] as? [Int], bbox.count == 4 else {
            return nil  // images are identical
        }
        return (bbox[0], bbox[1], bbox[2], bbox[3])
    }

    // ---------------------------------------------------------------------------
    // saveCrop(before:after:cropBefore:cropAfter:padding:)
    // Computes the diff region, expands by padding, and saves cropped PNGs.
    // Returns the crop bounding box or nil on failure.
    // ---------------------------------------------------------------------------
    func saveCrop(before: String, after: String,
                  cropBefore: String, cropAfter: String,
                  padding: Int = VisualVerifier.defaultCropPadding) throws -> (Int, Int, Int, Int)? {
        let result = try runScript(
            mode: "crop",
            args: [before, after, cropBefore, cropAfter, String(padding)]
        )
        if let error = result["error"] as? String {
            throw VisualVerifierError.cropFailed(error)
        }
        guard let bbox = result["bbox"] as? [Int], bbox.count == 4 else {
            return nil
        }
        return (bbox[0], bbox[1], bbox[2], bbox[3])
    }

    // ---------------------------------------------------------------------------
    // Convenience: captureBeforeState
    // Renders the "before" PNG for a test case.
    // ---------------------------------------------------------------------------
    func captureBeforeState(pdfPath: String, page: Int,
                            outputDir: String, editLabel: String) throws -> String {
        let path = (outputDir as NSString).appendingPathComponent("\(editLabel)_before.png")
        try renderPage(ofPDF: pdfPath, page: page, to: path)
        return path
    }

    // ---------------------------------------------------------------------------
    // Convenience: captureAfterState
    // Renders the "after" PNG and computes diff crop against the before image.
    // Returns (afterPNG, cropBeforePNG?, cropAfterPNG?, diffBBox?).
    // ---------------------------------------------------------------------------
    func captureAfterState(pdfPath: String, page: Int,
                           outputDir: String, editLabel: String,
                           beforePNG: String) throws -> (afterPNG: String,
                                                          cropBefore: String?,
                                                          cropAfter: String?,
                                                          diffBBox: (Int, Int, Int, Int)?) {
        let afterPath = (outputDir as NSString).appendingPathComponent("\(editLabel)_after.png")
        try renderPage(ofPDF: pdfPath, page: page, to: afterPath)

        let cropBeforePath = (outputDir as NSString).appendingPathComponent("\(editLabel)_crop_before.png")
        let cropAfterPath = (outputDir as NSString).appendingPathComponent("\(editLabel)_crop_after.png")

        let bbox = try? saveCrop(before: beforePNG, after: afterPath,
                                 cropBefore: cropBeforePath, cropAfter: cropAfterPath)

        if bbox != nil {
            return (afterPath, cropBeforePath, cropAfterPath, bbox)
        } else {
            return (afterPath, nil, nil, nil)
        }
    }

    // MARK: - Private: embedded Python script

    private static let pythonScript = #"""
import sys, json, os
import fitz

def render(args):
    """Render a PDF page to PNG."""
    pdf_path, page_idx, dpi, out_path = args[0], int(args[1]), int(args[2]), args[3]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
    pix.save(out_path)
    doc.close()
    return {"ok": True}

def diff_bbox(before_path, after_path, threshold=8):
    """Compute bounding box of differing pixels between two PNGs using fitz."""
    pix1 = fitz.Pixmap(before_path)
    pix2 = fitz.Pixmap(after_path)
    if pix1.width != pix2.width or pix1.height != pix2.height:
        raise ValueError("Image dimensions differ")
    w, h, n = pix1.width, pix1.height, pix1.n
    s1, s2 = pix1.samples, pix2.samples
    min_x, min_y, max_x, max_y = w, h, -1, -1
    stride = w * n
    for y in range(h):
        row_off = y * stride
        for x in range(w):
            off = row_off + x * n
            d = max(abs(s1[off + c] - s2[off + c]) for c in range(min(n, 3)))
            if d > threshold:
                if x < min_x: min_x = x
                if y < min_y: min_y = y
                if x > max_x: max_x = x
                if y > max_y: max_y = y
    if max_x < 0:
        return None
    return [min_x, min_y, max_x, max_y]

def do_diff(args):
    """Diff mode: return bounding box of changed pixels."""
    before_path, after_path, threshold = args[0], args[1], int(args[2])
    bbox = diff_bbox(before_path, after_path, threshold)
    return {"bbox": bbox}

def do_crop(args):
    """Crop mode: compute diff, expand by padding, save cropped PNGs."""
    before_path, after_path = args[0], args[1]
    crop_before, crop_after = args[2], args[3]
    os.makedirs(os.path.dirname(crop_before), exist_ok=True)
    os.makedirs(os.path.dirname(crop_after), exist_ok=True)
    padding = int(args[4])
    pix_ref = fitz.Pixmap(before_path)
    w, h = pix_ref.width, pix_ref.height
    bbox = diff_bbox(before_path, after_path)
    if bbox is None:
        x0, y0 = max(0, w // 4), max(0, h // 4)
        x1, y1 = min(w - 1, w * 3 // 4), min(h - 1, h * 3 // 4)
    else:
        x0 = max(0, bbox[0] - padding)
        y0 = max(0, bbox[1] - padding)
        x1 = min(w - 1, bbox[2] + padding)
        y1 = min(h - 1, bbox[3] + padding)
    clip = fitz.IRect(x0, y0, x1 + 1, y1 + 1)
    for src, dst in [(before_path, crop_before), (after_path, crop_after)]:
        pix = fitz.Pixmap(src)
        cropped = fitz.Pixmap(pix.colorspace, clip, pix.alpha)
        cropped.copy(pix, clip)
        cropped.save(dst)
    return {"bbox": [x0, y0, x1, y1]}

def main():
    mode = sys.argv[1]
    args = sys.argv[2:]
    try:
        if mode == "render":
            result = render(args)
        elif mode == "diff":
            result = do_diff(args)
        elif mode == "crop":
            result = do_crop(args)
        else:
            result = {"error": f"Unknown mode: {mode}"}
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
"""#

    // ---------------------------------------------------------------------------
    // runScript(mode:args:)
    // Writes the embedded Python to a unique temp file and invokes it.
    // ---------------------------------------------------------------------------
    private func runScript(mode: String, args: [String]) throws -> [String: Any] {
        let scriptURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("marcedit_visual_verify_\(UUID().uuidString).py")
        let scriptPath = scriptURL.path
        try VisualVerifier.pythonScript.write(to: scriptURL,
                                              atomically: true,
                                              encoding: .utf8)
        defer {
            try? FileManager.default.removeItem(at: scriptURL)
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonExecutablePath())
        proc.arguments = [scriptPath, mode] + args

        let outPipe = Pipe()
        let errPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe
        let finished = DispatchSemaphore(value: 0)
        proc.terminationHandler = { _ in finished.signal() }

        do {
            try proc.run()
        } catch {
            throw VisualVerifierError.launchFailed("Failed to launch python3: \(error)")
        }

        if finished.wait(timeout: .now() + 30) == .timedOut {
            proc.terminate()
            _ = finished.wait(timeout: .now() + 2)
            throw VisualVerifierError.scriptFailed("Timed out after 30 seconds running mode '\(mode)'")
        }

        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        let stdout = String(data: outData, encoding: .utf8) ?? ""
        let stderr = String(data: errData, encoding: .utf8) ?? ""

        guard proc.terminationStatus == 0 else {
            throw VisualVerifierError.scriptFailed(
                "Exit \(proc.terminationStatus): \(stderr.isEmpty ? stdout : stderr)"
            )
        }

        let trimmed = stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw VisualVerifierError.invalidOutput("Could not parse JSON: \(trimmed)")
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
}

// MARK: - VisualVerifierError

enum VisualVerifierError: Error, LocalizedError {
    case renderFailed(String)
    case diffFailed(String)
    case cropFailed(String)
    case launchFailed(String)
    case scriptFailed(String)
    case invalidOutput(String)

    var errorDescription: String? {
        switch self {
        case .renderFailed(let msg):  return "VisualVerifier render failed: \(msg)"
        case .diffFailed(let msg):    return "VisualVerifier diff failed: \(msg)"
        case .cropFailed(let msg):    return "VisualVerifier crop failed: \(msg)"
        case .launchFailed(let msg):  return "VisualVerifier launch failed: \(msg)"
        case .scriptFailed(let msg):  return "VisualVerifier script failed: \(msg)"
        case .invalidOutput(let msg): return "VisualVerifier bad output: \(msg)"
        }
    }
}
