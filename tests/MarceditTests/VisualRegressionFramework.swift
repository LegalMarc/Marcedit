import XCTest
import PDFKit
import AppKit
@testable import Marcedit

/// Visual regression testing framework for PDF editing operations
/// Captures baseline images and compares against them to detect visual changes
final class VisualRegressionFramework {

    // MARK: - Configuration

    struct Config {
        /// Similarity threshold (0.0 = completely different, 1.0 = identical)
        var similarityThreshold: Double = 0.99

        /// DPI for PDF rendering
        var renderDPI: CGFloat = 150.0

        /// Whether to save diff images on failure
        var saveDiffImages: Bool = true

        /// Whether to update baselines automatically (use with caution!)
        var autoUpdateBaselines: Bool = false

        /// Directory for baseline images
        var baselineDirectory: URL

        /// Directory for diff images
        var diffDirectory: URL

        init(baseDirectory: URL) {
            self.baselineDirectory = baseDirectory.appendingPathComponent("Baselines")
            self.diffDirectory = baseDirectory.appendingPathComponent("Diffs")
        }
    }

    // MARK: - Properties

    private let config: Config
    private let fileManager = FileManager.default

    // MARK: - Lifecycle

    init(config: Config) {
        self.config = config

        // Create directories if needed
        try? fileManager.createDirectory(at: config.baselineDirectory, withIntermediateDirectories: true)
        try? fileManager.createDirectory(at: config.diffDirectory, withIntermediateDirectories: true)
    }

    // MARK: - Public API

    /// Capture baseline image for a PDF page
    func captureBaseline(
        pdfURL: URL,
        pageIndex: Int,
        identifier: String
    ) throws -> URL {
        guard let page = getPDFPage(from: pdfURL, at: pageIndex) else {
            throw VisualRegressionError.invalidPDF(pdfURL)
        }

        let image = renderPage(page)
        let baselineURL = config.baselineDirectory.appendingPathComponent("\(identifier).png")

        try saveImage(image, to: baselineURL)

        return baselineURL
    }

    /// Compare current PDF against baseline
    func compareAgainstBaseline(
        pdfURL: URL,
        pageIndex: Int,
        identifier: String
    ) throws -> ComparisonResult {
        // Get baseline
        let baselineURL = config.baselineDirectory.appendingPathComponent("\(identifier).png")
        guard fileManager.fileExists(atPath: baselineURL.path) else {
            if config.autoUpdateBaselines {
                // Create baseline if auto-update enabled
                _ = try captureBaseline(pdfURL: pdfURL, pageIndex: pageIndex, identifier: identifier)
                return ComparisonResult(
                    similarity: 1.0,
                    passed: true,
                    baselineURL: baselineURL,
                    currentURL: nil,
                    diffURL: nil,
                    message: "Baseline created automatically"
                )
            }
            throw VisualRegressionError.baselineNotFound(identifier)
        }

        guard let baselineImage = loadImage(from: baselineURL) else {
            throw VisualRegressionError.invalidBaseline(baselineURL)
        }

        // Render current PDF
        guard let page = getPDFPage(from: pdfURL, at: pageIndex) else {
            throw VisualRegressionError.invalidPDF(pdfURL)
        }

        let currentImage = renderPage(page)

        // Compare
        let similarity = calculateSimilarity(baseline: baselineImage, current: currentImage)
        let passed = similarity >= config.similarityThreshold

        // Save current and diff if failed
        var currentURL: URL? = nil
        var diffURL: URL? = nil

        if !passed && config.saveDiffImages {
            currentURL = config.diffDirectory.appendingPathComponent("\(identifier)_current.png")
            try saveImage(currentImage, to: currentURL!)

            let diffImage = createDiffImage(baseline: baselineImage, current: currentImage)
            diffURL = config.diffDirectory.appendingPathComponent("\(identifier)_diff.png")
            try saveImage(diffImage, to: diffURL!)
        }

        let message = passed
            ? "Visual comparison passed (similarity: \(String(format: "%.2f%%", similarity * 100)))"
            : "Visual comparison failed (similarity: \(String(format: "%.2f%%", similarity * 100)), threshold: \(String(format: "%.2f%%", config.similarityThreshold * 100)))"

        return ComparisonResult(
            similarity: similarity,
            passed: passed,
            baselineURL: baselineURL,
            currentURL: currentURL,
            diffURL: diffURL,
            message: message
        )
    }

    /// Delete baseline for a specific identifier
    func deleteBaseline(identifier: String) throws {
        let baselineURL = config.baselineDirectory.appendingPathComponent("\(identifier).png")
        try fileManager.removeItem(at: baselineURL)
    }

    /// Delete all baselines
    func deleteAllBaselines() throws {
        let contents = try fileManager.contentsOfDirectory(at: config.baselineDirectory, includingPropertiesForKeys: nil)
        for url in contents {
            try fileManager.removeItem(at: url)
        }
    }

    // MARK: - PDF Rendering

    private func getPDFPage(from url: URL, at index: Int) -> PDFPage? {
        guard let document = PDFDocument(url: url) else { return nil }
        return document.page(at: index)
    }

    private func renderPage(_ page: PDFPage) -> NSImage {
        let bounds = page.bounds(for: .mediaBox)

        // Scale for DPI
        let scale = config.renderDPI / 72.0
        let scaledSize = CGSize(
            width: bounds.width * scale,
            height: bounds.height * scale
        )

        let image = NSImage(size: scaledSize)
        image.lockFocus()

        // White background
        NSColor.white.setFill()
        NSRect(origin: .zero, size: scaledSize).fill()

        // Transform for scaling
        let context = NSGraphicsContext.current?.cgContext
        context?.scaleBy(x: scale, y: scale)

        // Render PDF
        page.draw(with: .mediaBox, to: context!)

        image.unlockFocus()

        return image
    }

    // MARK: - Image Comparison

    private func calculateSimilarity(baseline: NSImage, current: NSImage) -> Double {
        guard let baselineBitmap = getBitmapRep(from: baseline),
              let currentBitmap = getBitmapRep(from: current) else {
            return 0.0
        }

        // Check dimensions match
        guard baselineBitmap.pixelsWide == currentBitmap.pixelsWide,
              baselineBitmap.pixelsHigh == currentBitmap.pixelsHigh else {
            return 0.0
        }

        guard let baselineData = baselineBitmap.bitmapData,
              let currentData = currentBitmap.bitmapData else {
            return 0.0
        }

        let width = baselineBitmap.pixelsWide
        let height = baselineBitmap.pixelsHigh
        let bytesPerPixel = baselineBitmap.bitsPerPixel / 8
        let totalPixels = width * height

        var matchingPixels = 0

        for y in 0..<height {
            for x in 0..<width {
                let offset = (y * width + x) * bytesPerPixel

                let br = baselineData[offset]
                let bg = baselineData[offset + 1]
                let bb = baselineData[offset + 2]

                let cr = currentData[offset]
                let cg = currentData[offset + 1]
                let cb = currentData[offset + 2]

                // Calculate color distance (Euclidean distance in RGB space)
                let dr = Int(br) - Int(cr)
                let dg = Int(bg) - Int(cg)
                let db = Int(bb) - Int(cb)

                let distance = sqrt(Double(dr * dr + dg * dg + db * db))

                // Threshold: consider pixels matching if distance < 10 (out of max ~441)
                if distance < 10.0 {
                    matchingPixels += 1
                }
            }
        }

        return Double(matchingPixels) / Double(totalPixels)
    }

    private func createDiffImage(baseline: NSImage, current: NSImage) -> NSImage {
        guard let baselineBitmap = getBitmapRep(from: baseline),
              let currentBitmap = getBitmapRep(from: current) else {
            return NSImage()
        }

        let width = baselineBitmap.pixelsWide
        let height = baselineBitmap.pixelsHigh

        let diffImage = NSImage(size: NSSize(width: width, height: height))
        diffImage.lockFocus()

        guard let context = NSGraphicsContext.current?.cgContext else {
            diffImage.unlockFocus()
            return diffImage
        }

        guard let baselineData = baselineBitmap.bitmapData,
              let currentData = currentBitmap.bitmapData else {
            diffImage.unlockFocus()
            return diffImage
        }

        let bytesPerPixel = baselineBitmap.bitsPerPixel / 8
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)

        guard let diffBitmap = context.data?.bindMemory(to: UInt8.self, capacity: width * height * 4) else {
            diffImage.unlockFocus()
            return diffImage
        }

        // Create diff image: differences in red
        for y in 0..<height {
            for x in 0..<width {
                let offset = (y * width + x) * bytesPerPixel
                let diffOffset = (y * width + x) * 4

                let br = baselineData[offset]
                let bg = baselineData[offset + 1]
                let bb = baselineData[offset + 2]

                let cr = currentData[offset]
                let cg = currentData[offset + 1]
                let cb = currentData[offset + 2]

                let dr = abs(Int(br) - Int(cr))
                let dg = abs(Int(bg) - Int(cg))
                let db = abs(Int(bb) - Int(cb))

                let hasDiff = dr > 10 || dg > 10 || db > 10

                if hasDiff {
                    // Highlight differences in red
                    diffBitmap[diffOffset] = 255     // R
                    diffBitmap[diffOffset + 1] = 0   // G
                    diffBitmap[diffOffset + 2] = 0   // B
                    diffBitmap[diffOffset + 3] = 255 // A
                } else {
                    // Keep original (grayscale)
                    let gray = UInt8((Int(br) + Int(bg) + Int(bb)) / 3)
                    diffBitmap[diffOffset] = gray
                    diffBitmap[diffOffset + 1] = gray
                    diffBitmap[diffOffset + 2] = gray
                    diffBitmap[diffOffset + 3] = 255
                }
            }
        }

        diffImage.unlockFocus()
        return diffImage
    }

    // MARK: - Image I/O

    private func getBitmapRep(from image: NSImage) -> NSBitmapImageRep? {
        guard let tiffData = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiffData) else {
            return nil
        }
        return bitmap
    }

    private func saveImage(_ image: NSImage, to url: URL) throws {
        guard let tiffData = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiffData),
              let pngData = bitmap.representation(using: .png, properties: [:]) else {
            throw VisualRegressionError.imageSaveFailed(url)
        }

        try pngData.write(to: url)
    }

    private func loadImage(from url: URL) -> NSImage? {
        return NSImage(contentsOf: url)
    }
}

// MARK: - Supporting Types

extension VisualRegressionFramework {

    struct ComparisonResult {
        let similarity: Double
        let passed: Bool
        let baselineURL: URL
        let currentURL: URL?
        let diffURL: URL?
        let message: String
    }

    enum VisualRegressionError: Error, LocalizedError {
        case invalidPDF(URL)
        case baselineNotFound(String)
        case invalidBaseline(URL)
        case imageSaveFailed(URL)

        var errorDescription: String? {
            switch self {
            case .invalidPDF(let url):
                return "Invalid PDF at \(url.path)"
            case .baselineNotFound(let identifier):
                return "Baseline not found for identifier: \(identifier)"
            case .invalidBaseline(let url):
                return "Invalid baseline image at \(url.path)"
            case .imageSaveFailed(let url):
                return "Failed to save image to \(url.path)"
            }
        }
    }
}
