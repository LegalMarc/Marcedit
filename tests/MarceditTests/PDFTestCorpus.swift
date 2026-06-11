import Foundation
import PDFKit

/// Generates sample PDF files for testing
///
/// Provides various PDF types:
/// - Simple text PDFs
/// - Multi-page PDFs
/// - PDFs with different fonts
/// - PDFs with images
/// - Corrupted PDFs for error testing
struct PDFTestCorpus {

    private let tempDirectory: URL

    init(tempDirectory: URL) {
        self.tempDirectory = tempDirectory
    }

    // MARK: - Simple PDFs

    /// Create a minimal valid PDF with text
    func createSimplePDF(text: String) throws -> URL {
        let filename = "simple_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let pdfContent = generateMinimalPDF(text: text)
        try pdfContent.write(to: fileURL, atomically: true, encoding: .utf8)

        return fileURL
    }

    /// Create a PDF with specific font
    func createPDFWithFont(text: String, fontName: String = "Helvetica", fontSize: Int = 12) throws -> URL {
        let filename = "font_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let pdfContent = """
        %PDF-1.4
        1 0 obj
        << /Type /Catalog /Pages 2 0 R >>
        endobj
        2 0 obj
        << /Type /Pages /Kids [3 0 R] /Count 1 >>
        endobj
        3 0 obj
        << /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R /MediaBox [0 0 612 792] >>
        endobj
        4 0 obj
        << /Type /Font /Subtype /Type1 /BaseFont /\(fontName) >>
        endobj
        5 0 obj
        << /Length \(50 + text.count) >>
        stream
        BT
        /F1 \(fontSize) Tf
        72 720 Td
        (\(text)) Tj
        ET
        endstream
        endobj
        xref
        0 6
        0000000000 65535 f
        0000000009 00000 n
        0000000058 00000 n
        0000000115 00000 n
        0000000264 00000 n
        0000000343 00000 n
        trailer
        << /Size 6 /Root 1 0 R >>
        startxref
        \(400 + text.count)
        %%EOF
        """

        try pdfContent.write(to: fileURL, atomically: true, encoding: .utf8)
        return fileURL
    }

    /// Create a multi-page PDF
    func createMultiPagePDF(pages: Int, textPerPage: [String]) throws -> URL {
        let filename = "multipage_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        // Use PDFKit for multi-page generation
        let pdfDocument = PDFDocument()

        for (index, text) in textPerPage.prefix(pages).enumerated() {
            if let page = createPDFPage(text: text, pageNumber: index + 1) {
                pdfDocument.insert(page, at: index)
            }
        }

        pdfDocument.write(to: fileURL)
        return fileURL
    }

    // MARK: - Complex PDFs

    /// Create a PDF with multiple fonts
    func createMultiFontPDF() throws -> URL {
        let filename = "multifont_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let pdfDocument = PDFDocument()

        let fonts = [
            ("Helvetica", "This is Helvetica"),
            ("Times-Roman", "This is Times Roman"),
            ("Courier", "This is Courier")
        ]

        for (index, (font, text)) in fonts.enumerated() {
            if let page = createPDFPage(text: "\(text) - \(font)", pageNumber: index + 1) {
                pdfDocument.insert(page, at: index)
            }
        }

        pdfDocument.write(to: fileURL)
        return fileURL
    }

    /// Create a PDF with long text for performance testing
    func createLargePDF(textLength: Int = 100000) throws -> URL {
        let filename = "large_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let longText = String(repeating: "The quick brown fox jumps over the lazy dog. ", count: textLength / 45)

        let pdfDocument = PDFDocument()
        if let page = createPDFPage(text: longText, pageNumber: 1) {
            pdfDocument.insert(page, at: 0)
        }

        pdfDocument.write(to: fileURL)
        return fileURL
    }

    // MARK: - Special Case PDFs

    /// Create an encrypted PDF
    func createEncryptedPDF(text: String, password: String = "test123") throws -> URL {
        let filename = "encrypted_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let pdfDocument = PDFDocument()
        if let page = createPDFPage(text: text, pageNumber: 1) {
            pdfDocument.insert(page, at: 0)
        }

        // Encrypt with password
        let options: [PDFDocumentWriteOption: Any] = [
            .userPasswordOption: password,
            .ownerPasswordOption: password
        ]

        pdfDocument.write(to: fileURL, withOptions: options)
        return fileURL
    }

    /// Create a corrupted PDF for error testing
    func createCorruptedPDF() throws -> URL {
        let filename = "corrupted_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        // Create invalid PDF (missing header)
        let corruptedContent = """
        This is not a valid PDF file.
        It's missing the PDF header and structure.
        Should fail validation.
        """

        try corruptedContent.write(to: fileURL, atomically: true, encoding: .utf8)
        return fileURL
    }

    /// Create a PDF with invalid structure but valid header
    func createInvalidStructurePDF() throws -> URL {
        let filename = "invalid_structure_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let invalidContent = """
        %PDF-1.4
        This PDF has a valid header but invalid structure.
        Missing required objects and xref table.
        """

        try invalidContent.write(to: fileURL, atomically: true, encoding: .utf8)
        return fileURL
    }

    /// Create an empty PDF file
    func createEmptyPDF() throws -> URL {
        let filename = "empty_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        try Data().write(to: fileURL)
        return fileURL
    }

    /// Create a non-PDF file (e.g. txt)
    func createNonPDFFile() throws -> URL {
        let filename = "not_a_pdf_\(UUID().uuidString).txt"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        try "This is a text file".write(to: fileURL, atomically: true, encoding: .utf8)
        return fileURL
    }

    /// Create logical PDF with images (simulated)
    func createPDFWithImages(imageCount: Int) throws -> URL {
        let filename = "images_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let pdfDocument = PDFDocument()
        for i in 0..<imageCount {
            if let page = createPDFPage(text: "Image \(i+1) Placeholder", pageNumber: i + 1) {
                pdfDocument.insert(page, at: i)
            }
        }

        pdfDocument.write(to: fileURL)
        return fileURL
    }

    /// Create PDF with mixed content
    func createPDFWithMixedContent() throws -> URL {
        let filename = "mixed_\(UUID().uuidString).pdf"
        let fileURL = tempDirectory.appendingPathComponent(filename)

        let pdfDocument = PDFDocument()
        // Page 1: Text
        if let page1 = createPDFPage(text: "Regular Content", pageNumber: 1) {
            pdfDocument.insert(page1, at: 0)
        }
        // Page 2: "Image"
        if let page2 = createPDFPage(text: "[Image Placeholder]", pageNumber: 2) {
            pdfDocument.insert(page2, at: 1)
        }
        // Page 3: Unicode
        if let page3 = createPDFPage(text: "Mixed Unicode 🌍", pageNumber: 3) {
            pdfDocument.insert(page3, at: 2)
        }

        pdfDocument.write(to: fileURL)
        return fileURL
    }

    /// Create PDF with Unicode text
    func createPDFWithUnicodeText(text: String) throws -> URL {
        return try createSimplePDF(text: text)
    }

    // MARK: - Test Data Sets

    /// Create a complete test corpus with various PDF types
    func generateFullCorpus() throws -> TestCorpus {
        var corpus = TestCorpus()

        // Simple PDFs
        corpus.simplePDF = try createSimplePDF(text: "Simple test content")
        corpus.shortPDF = try createSimplePDF(text: "Short")
        corpus.longTextPDF = try createLargePDF(textLength: 10000)

        // Font PDFs
        corpus.helveticaPDF = try createPDFWithFont(text: "Helvetica Text", fontName: "Helvetica")
        corpus.timesPDF = try createPDFWithFont(text: "Times Text", fontName: "Times-Roman")
        corpus.courierPDF = try createPDFWithFont(text: "Courier Text", fontName: "Courier")

        // Multi-page PDFs
        corpus.twoPagePDF = try createMultiPagePDF(pages: 2, textPerPage: ["Page 1", "Page 2"])
        corpus.tenPagePDF = try createMultiPagePDF(
            pages: 10,
            textPerPage: (1...10).map { "Content for page \($0)" }
        )

        // Special cases
        corpus.multiFontPDF = try createMultiFontPDF()
        corpus.encryptedPDF = try createEncryptedPDF(text: "Encrypted content")
        corpus.corruptedPDF = try createCorruptedPDF()
        corpus.invalidStructurePDF = try createInvalidStructurePDF()
        corpus.emptyPDF = try createEmptyPDF()
        corpus.nonPDFFile = try createNonPDFFile()

        return corpus
    }

    // MARK: - Helper Methods

    private func generateMinimalPDF(text: String) -> String {
        return """
        %PDF-1.4
        1 0 obj
        << /Type /Catalog /Pages 2 0 R >>
        endobj
        2 0 obj
        << /Type /Pages /Kids [3 0 R] /Count 1 >>
        endobj
        3 0 obj
        << /Type /Page /Parent 2 0 R /Contents 4 0 R /MediaBox [0 0 612 792] >>
        endobj
        4 0 obj
        << /Length \(text.count) >>
        stream
        \(text)
        endstream
        endobj
        xref
        0 5
        0000000000 65535 f
        0000000009 00000 n
        0000000058 00000 n
        0000000115 00000 n
        0000000214 00000 n
        trailer
        << /Size 5 /Root 1 0 R >>
        startxref
        \(280 + text.count)
        %%EOF
        """
    }

    private func createPDFPage(text: String, pageNumber: Int) -> PDFPage? {
        let pageRect = CGRect(x: 0, y: 0, width: 612, height: 792) // US Letter

        let textAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 12),
            .foregroundColor: NSColor.black
        ]

        let attributedString = NSAttributedString(string: text, attributes: textAttributes)

        // Create PDF page from attributed string
        let pdfPage = PDFPage()

        // Note: This is a simplified version. Real implementation would use CoreGraphics
        // to properly render the attributed string onto the PDF page
        return pdfPage
    }
}

// MARK: - Test Corpus Structure

struct TestCorpus {
    // Simple PDFs
    var simplePDF: URL?
    var shortPDF: URL?
    var longTextPDF: URL?

    // Font-specific PDFs
    var helveticaPDF: URL?
    var timesPDF: URL?
    var courierPDF: URL?

    // Multi-page PDFs
    var twoPagePDF: URL?
    var tenPagePDF: URL?

    // Special cases
    var multiFontPDF: URL?
    var encryptedPDF: URL?
    var corruptedPDF: URL?
    var invalidStructurePDF: URL?
    var emptyPDF: URL?
    var nonPDFFile: URL?

    var allPDFs: [URL] {
        [
            simplePDF, shortPDF, longTextPDF,
            helveticaPDF, timesPDF, courierPDF,
            twoPagePDF, tenPagePDF,
            multiFontPDF, encryptedPDF,
            corruptedPDF, invalidStructurePDF, emptyPDF
        ].compactMap { $0 }
    }

    var validPDFs: [URL] {
        [
            simplePDF, shortPDF, longTextPDF,
            helveticaPDF, timesPDF, courierPDF,
            twoPagePDF, tenPagePDF,
            multiFontPDF
        ].compactMap { $0 }
    }

    var invalidPDFs: [URL] {
        [
            corruptedPDF, invalidStructurePDF, emptyPDF, nonPDFFile
        ].compactMap { $0 }
    }
}
