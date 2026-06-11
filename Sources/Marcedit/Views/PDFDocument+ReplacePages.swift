import PDFKit

extension PDFDocument {
    /// Replace all pages with pages from a new document at the given URL.
    /// Preserves PDFDocument object identity to prevent SwiftUI re-renders.
    ///
    /// Validates the full new page set before mutating `self`, so a partial
    /// load (corrupt/locked source) never leaves the document empty.
    ///
    /// - Returns: True if all pages were loaded and swapped; false otherwise.
    @discardableResult
    func replacePages(from url: URL) -> Bool {
        guard let newDoc = PDFDocument(url: url) else {
            return false
        }

        // Collect all new pages first — do not touch self until we know they're all valid.
        let newPageCount = newDoc.pageCount
        guard newPageCount > 0 else { return false }

        var newPages: [PDFPage] = []
        newPages.reserveCapacity(newPageCount)
        for i in 0..<newPageCount {
            guard let page = newDoc.page(at: i) else {
                // Partial load — abort without mutating self.
                return false
            }
            newPages.append(page)
        }

        // Swap without ever hitting zero pages: append all new pages beyond the
        // current end, then remove the originals from the front.  pageCount
        // never drops to zero, so KVO observers never see an empty document.
        let originalCount = self.pageCount
        for page in newPages {
            self.insert(page, at: self.pageCount)
        }
        for _ in 0..<originalCount {
            self.removePage(at: 0)
        }

        return self.pageCount == newPageCount
    }

    /// Replace pages and copy document attributes from another document.
    func replaceContent(from newDoc: PDFDocument) {
        let newPageCount = newDoc.pageCount
        guard newPageCount > 0 else { return }

        var newPages: [PDFPage] = []
        newPages.reserveCapacity(newPageCount)
        for i in 0..<newPageCount {
            guard let page = newDoc.page(at: i) else { return }
            newPages.append(page)
        }

        // Same zero-page-free strategy: append new pages first, then remove originals.
        let originalCount = self.pageCount
        for page in newPages {
            self.insert(page, at: self.pageCount)
        }
        for _ in 0..<originalCount {
            self.removePage(at: 0)
        }
    }
}
