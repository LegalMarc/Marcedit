
import SwiftUI
import PDFKit
import CoreText
import CoreImage

class InteractivePDFView: PDFView {
    // Selection heuristic constants
    private static let gapDetectionMinSpaces = 2  // Minimum consecutive spaces to detect table columns
    // Raised from 8.0 → 15.0: the old threshold was too aggressive and incorrectly
    // switched uppercase/wide-character lines (e.g. "MONTHLY INVOICE TOTAL") to word
    // selection. Table gaps also require double-spaces to be present (see use sites).
    private static let avgCharWidthThreshold: CGFloat = 15.0  // pt - suggests gaps/tables
    private static let minCharsForGapDetection = 5  // Avoid false positives on short text
    private static let defaultPageMargin: CGFloat = 50  // pt - typical left/right margin
    private static let estimatedLineHeight: CGFloat = 14  // pt - typical line height

    // BUG #45 FIX: Extract repeated empty string check to helper
    /// Check if a string contains meaningful (non-whitespace) content
    private func hasContent(_ string: String?) -> Bool {
        guard let string = string else { return false }
        return !string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var onHover: ((PDFSelection?, PDFPage?, CGRect) -> Void)?
    var onSelect: ((PDFSelection?, PDFPage?) -> Void)?  // Single-click: select text
    var onClick: ((PDFSelection?, PDFPage?) -> Void)?   // Double-click: edit text
    var onKeyDown: ((NSEvent) -> Bool)?
    var onLayoutChange: ((CGFloat, PDFDestination?) -> Void)? // Hook for state persistence

    // UI State
    var isEditing: Bool = false
    var selectionMode: String = "line"

    // Track current selection for persistent highlight
    private var selectedTextInfo: (selection: PDFSelection, page: PDFPage, rect: CGRect)?

    // Cached text margins per page (computed lazily, invalidated on document change)
    // fileprivate so PDFKitView.updateNSView (same file) can invalidate on document change
    fileprivate var pageMarginCache: [ObjectIdentifier: (left: CGFloat, right: CGFloat)] = [:]
    
    // ... tracking area ...
    
    // MARK: - Zoom & Cursor Handling
    
    public override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        if window != nil {
             // Remove any existing observers first to prevent stacking on re-attach
             NotificationCenter.default.removeObserver(self)

             // BUG #65 FIX: Use type-safe notification names instead of string literals
             NotificationCenter.default.addObserver(self, selector: #selector(performZoomIn), name: .zoomIn, object: nil)
             NotificationCenter.default.addObserver(self, selector: #selector(performZoomOut), name: .zoomOut, object: nil)
             NotificationCenter.default.addObserver(self, selector: #selector(performZoomFit), name: .zoomFit, object: nil)

             // State Persistence Observers
             NotificationCenter.default.addObserver(self, selector: #selector(handleLayoutChange), name: .pdfViewScaleChanged, object: self)
             NotificationCenter.default.addObserver(self, selector: #selector(handleLayoutChange), name: .pdfViewVisiblePagesChanged, object: self)
             
             // PDF Content Reload Observers
             NotificationCenter.default.addObserver(self, selector: #selector(prepareForReload), name: .prepareForPDFReload, object: nil)
             NotificationCenter.default.addObserver(self, selector: #selector(didReload), name: .didReloadPDF, object: nil)

             // Preview error tint observer
             NotificationCenter.default.addObserver(self, selector: #selector(handlePreviewErrorChanged), name: .previewErrorChanged, object: nil)
        } else {
             NotificationCenter.default.removeObserver(self)
        }
    }
    
    @objc func handlePreviewErrorChanged(_ notification: Notification) {
        if let hasError = notification.userInfo?["hasError"] as? Bool {
            setPreviewError(hasError)
        }
    }

    @objc func performZoomIn() {
        if self.autoScales { self.autoScales = false }
        self.scaleFactor *= 1.2
    }
    
    @objc func performZoomOut() {
        if self.autoScales { self.autoScales = false }
        self.scaleFactor /= 1.2
    }
    
    @objc func performZoomFit() {
        self.autoScales = true
        self.minScaleFactor = self.scaleFactorForSizeToFit
    }
    
    @objc private func handleLayoutChange() {
        onLayoutChange?(self.scaleFactor, self.currentDestination)
    }
    
    // MARK: - State Preservation
    // Store by index (not page object reference) since replacePages() invalidates old PDFPage objects
    private var savedPageIndex: Int?
    private var savedPoint: CGPoint?
    private var savedScaleFactor: CGFloat?
    private var savedAutoScales: Bool?

    @objc private func prepareForReload(_ notification: Notification) {
        // Capture current scroll position by PAGE INDEX (not page object)
        // Page objects become invalid after replacePages()
        if let dest = self.currentDestination, let page = dest.page, let doc = self.document {
            let index = doc.index(for: page)
            // BUG #63 FIX: Use guard for clearer index validation
            guard index != NSNotFound, index < doc.pageCount else { return }
            self.savedPageIndex = index
            self.savedPoint = dest.point
        }
        // Always save zoom state
        self.savedScaleFactor = self.scaleFactor
        self.savedAutoScales = self.autoScales
    }

    @objc private func didReload(_ notification: Notification) {
        // Verify document is ready
        guard self.document != nil else {
            NSLog("InteractivePDFView: WARNING - didReload called but document is nil")
            return
        }

        NSLog("InteractivePDFView: Restoring state - pageIndex=\(savedPageIndex ?? -1), point=\(savedPoint?.debugDescription ?? "nil")")

        // CRITICAL: Force PDFView to re-layout after pages are replaced
        // Without this, PDFKit may cache the old rendered content
        self.layoutDocumentView()

        // Restore zoom FIRST (before navigation, so page fits correctly)
        if let scale = self.savedScaleFactor {
            if let autoScales = self.savedAutoScales {
                if autoScales {
                    self.autoScales = true
                } else {
                    self.autoScales = false
                    self.scaleFactor = scale
                }
            } else {
                // No saved preference - default to auto
                NSLog("InteractivePDFView: No saved autoScales preference, defaulting to auto")
                self.autoScales = true
            }
        } else {
            self.autoScales = true
        }

        // Restore scroll position with validation
        var navigationSucceeded = false
        if let pageIndex = self.savedPageIndex,
           let point = self.savedPoint,
           let doc = self.document {

            if pageIndex >= doc.pageCount {
                NSLog("InteractivePDFView: ERROR - Saved page index \(pageIndex) exceeds page count \(doc.pageCount)")
            } else if let newPage = doc.page(at: pageIndex) {
                // BUG #64 FIX: Validate point is within page bounds with margin
                // Clamping exactly to bounds can cause edge rendering issues
                let pageBounds = newPage.bounds(for: .mediaBox)
                let margin: CGFloat = 1.0  // Small margin to avoid exact edge
                let clampedPoint = CGPoint(
                    x: min(max(point.x, pageBounds.minX + margin), pageBounds.maxX - margin),
                    y: min(max(point.y, pageBounds.minY + margin), pageBounds.maxY - margin)
                )

                if clampedPoint != point {
                    NSLog("InteractivePDFView: Point \(point) outside bounds, clamped to \(clampedPoint)")
                }

                let newDest = PDFDestination(page: newPage, at: clampedPoint)
                self.go(to: newDest)
                navigationSucceeded = true
                NSLog("InteractivePDFView: Navigation successful")
            } else {
                NSLog("InteractivePDFView: ERROR - Could not get page at index \(pageIndex)")
            }
        } else {
            NSLog("InteractivePDFView: No saved state to restore")
        }

        // Clear state only if navigation succeeded or wasn't needed
        if navigationSucceeded || self.savedPageIndex == nil {
            self.savedPageIndex = nil
            self.savedPoint = nil
            self.savedScaleFactor = nil
            self.savedAutoScales = nil
        } else {
            NSLog("InteractivePDFView: Navigation failed, preserving state for debugging")
        }

        // Force display update
        self.setNeedsDisplay(self.bounds)
    }
    
    override func cursorUpdate(with event: NSEvent) {
        // If the hover overlay is active, we are over selectable text -> I-Beam
        // Otherwise use default arrow
        if hoverOverlay != nil && hoverOverlay?.superlayer != nil {
            NSCursor.iBeam.set()
        } else {
            NSCursor.arrow.set()
        }
    }
    
    // Handle Esc to clear selection
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { // Esc
             clearCurrentSelection()
             return
        }
        
        if let onKeyDown = onKeyDown, onKeyDown(event) {
            return
        }
        super.keyDown(with: event)
    }
    
    private var trackingArea: NSTrackingArea?
    private var hoverOverlay: CAShapeLayer?
    private var selectionOverlay: CAShapeLayer?  // Persistent selection highlight
    
    // MARK: - Drag-to-Select State
    private var isDragging: Bool = false
    private var dragStartPoint: CGPoint?  // In view coordinates
    private var dragStartPage: PDFPage?
    private var dragOverlay: CAShapeLayer?  // Visual rectangle during drag
    // Drag threshold scaled for Retina displays
    private var dragThreshold: CGFloat {
        return (window?.backingScaleFactor ?? 1.0) * 5.0
    }
    
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        
        if let trackingArea = trackingArea {
            removeTrackingArea(trackingArea)
        }
        
        let options: NSTrackingArea.Options = [.mouseEnteredAndExited, .mouseMoved, .cursorUpdate, .activeInKeyWindow, .inVisibleRect]
        let newTrackingArea = NSTrackingArea(rect: bounds, options: options, owner: self, userInfo: nil)
        addTrackingArea(newTrackingArea)
        self.trackingArea = newTrackingArea
    }
    
    /// Returns the actual left/right text margins for a page by sampling line selections.
    /// Results are cached per page so hover performance is not impacted after the first visit.
    private func textMargins(for page: PDFPage) -> (left: CGFloat, right: CGFloat) {
        let key = ObjectIdentifier(page)
        if let cached = pageMarginCache[key] { return cached }

        let pageBounds = page.bounds(for: .mediaBox)
        var minX = pageBounds.width
        var maxX: CGFloat = 0

        // Sample 8 evenly-spaced Y positions across the page
        let samples = 8
        let phantomMarginThreshold: CGFloat = 20.0
        for i in 1...samples {
            let y = pageBounds.minY + pageBounds.height * CGFloat(i) / CGFloat(samples + 1)
            let pt = CGPoint(x: pageBounds.midX, y: y)
            if let sel = page.selectionForLine(at: pt),
               let str = sel.string,
               !str.trimmingCharacters(in: .whitespaces).isEmpty {
                let b = sel.bounds(for: page)
                // Phantom-text guard: selectionForLine follows content-stream order and can return
                // a selection whose bounds are far from the queried point. Only use bounds that are
                // actually near the sample point; otherwise the margin calculation gets skewed.
                guard b.insetBy(dx: -phantomMarginThreshold, dy: -phantomMarginThreshold).contains(pt) else { continue }
                if b.minX < minX { minX = b.minX }
                if b.maxX > maxX { maxX = b.maxX }
            }
        }

        let result: (left: CGFloat, right: CGFloat)
        if maxX > minX {
            result = (left: max(minX, 0), right: max(pageBounds.width - maxX, 0))
        } else {
            result = (left: Self.defaultPageMargin, right: Self.defaultPageMargin)
        }
        pageMarginCache[key] = result
        return result
    }

    override func mouseMoved(with event: NSEvent) {
        // Stop hover effects if editing or no document
        if isEditing {
             onHover?(nil, nil, .zero)
             clearHighlight()
             return
        }
        
        let point = self.convert(event.locationInWindow, from: nil)
        
        guard let page = self.page(for: point, nearest: true) else {
            onHover?(nil, nil, .zero)
            return
        }

        
        let pagePoint = self.convert(point, to: page)

        // Guard: cursor must be within the page's own media box.
        // page(for:nearest:true) returns the nearest page even when the cursor is in
        // inter-page whitespace, causing converted coordinates that are outside any text.
        let pageBounds = page.bounds(for: .mediaBox)
        guard pageBounds.insetBy(dx: -4, dy: -4).contains(pagePoint) else {
            clearHighlight()
            onHover?(nil, nil, .zero)
            return
        }

        // SMART SELECTION: Use line first, but detect gaps for table context
        var selection = page.selectionForLine(at: pagePoint)

        // JOIN adjacent text runs on the same visual line.
        // selectionForLine returns only the text object at the queried point; the joiner
        // widens it to the full visual line using a thin Y-band selection.
        if let initial = selection {
            selection = joinedLineSelection(from: initial, on: page)
        }

        // Check if line selection spans a large horizontal gap (indicates table columns)
        if let lineSelection = selection,
           let lineString = lineSelection.string,
           hasContent(lineString) {

            // Analyze bounds for gaps
            let bounds = lineSelection.bounds(for: page)
            if !bounds.isEmpty {
                let charCount = CGFloat(lineString.count)
                let avgCharWidth = bounds.width / max(charCount, 1)

                // Require BOTH wide average width AND explicit double-spaces to detect table columns.
                // Requiring both prevents wide-font lines (e.g. "MONTHLY INVOICE TOTAL") from
                // incorrectly switching to word selection when no gap is present.
                let multipleSpaces = String(repeating: " ", count: Self.gapDetectionMinSpaces)
                let hasWideChars = avgCharWidth > Self.avgCharWidthThreshold && charCount > CGFloat(Self.minCharsForGapDetection)
                let hasDoubleSpace = lineString.contains(multipleSpaces)
                if hasWideChars && hasDoubleSpace {
                    // Table context: use word selection instead
                    selection = page.selectionForWord(at: pagePoint)
                }
            } else {
                // Invalid bounds - skip gap analysis, use line selection
                selection = lineSelection
            }
        }
        
        if let sel = selection,
           let string = sel.string, hasContent(string) {
            var bounds = sel.bounds(for: page)
            guard !bounds.isEmpty else { return }

            // Phantom-text guard: PDFKit's selectionForLine/selectionForWord follow the PDF
            // content-stream order, not visual position. The returned selection can render far
            // from the queried point. Skip the hover rect if the cursor is not within ~20 pt
            // of the selection's actual bounds — that's a phantom from stream-order contamination.
            let phantomThreshold: CGFloat = 20.0
            guard bounds.insetBy(dx: -phantomThreshold, dy: -phantomThreshold).contains(pagePoint) else {
                clearHighlight()
                onHover?(nil, nil, .zero)
                return
            }

            // Paragraph Mode Heuristic: Expand visual highlight to suggest block selection
            if selectionMode == "paragraph" {
                // Expand to full column width and add vertical padding to suggest multi-line block
                // We don't know exact paragraph bounds until Python processes it, but we can
                // estimate by expanding to typical margin widths
                let pageBounds = page.bounds(for: .mediaBox)

                // Horizontal: Expand to actual text column using sampled margins
                let margins = textMargins(for: page)
                let expandedX = pageBounds.minX + margins.left
                let expandedW = pageBounds.width - margins.left - margins.right

                // Vertical: Add generous padding to suggest multi-line content
                let lineHeight = Self.estimatedLineHeight
                let verticalPadding = lineHeight * 2  // Suggest ~2 more lines above/below

                bounds = CGRect(
                    x: expandedX,
                    y: bounds.minY - verticalPadding,
                    width: expandedW,
                    height: bounds.height + (verticalPadding * 2)
                )
            }
            
            let viewRect = self.convert(bounds, from: page)
            drawHighlight(rect: viewRect)
            onHover?(sel, page, bounds)
        } else {
            clearHighlight()
            onHover?(nil, nil, .zero)
        }
    }
    
    override func scrollWheel(with event: NSEvent) {
        // Block scroll while the edit dialog is open so the selected text
        // stays in view. Without this the user can scroll away and not see
        // the result of their edit when it completes.
        if isEditing { return }
        super.scrollWheel(with: event)
    }

    override func mouseDown(with event: NSEvent) {
        if isEditing { return }
        
        let point = self.convert(event.locationInWindow, from: nil)
        guard let page = self.page(for: point, nearest: true) else {
            super.mouseDown(with: event)
            return
        }
        
        // Double-click: Open edit dialog immediately (no drag)
        if event.clickCount >= 2 {
            let pagePoint = self.convert(point, to: page)

            // Guard A: cursor must be inside the page's media box.
            // page(for:nearest:true) can return a page for inter-page whitespace.
            let pageBounds = page.bounds(for: .mediaBox)
            guard pageBounds.insetBy(dx: -4, dy: -4).contains(pagePoint) else { return }

            if let selection = page.selectionForLine(at: pagePoint) ?? page.selectionForWord(at: pagePoint),
               let string = selection.string, hasContent(string) {
                // Guard B: skip phantom selections whose bounds are far from the click point.
                let bounds = selection.bounds(for: page)
                let phantomThreshold: CGFloat = 20.0
                guard bounds.insetBy(dx: -phantomThreshold, dy: -phantomThreshold).contains(pagePoint) else { return }
                onClick?(selection, page)
            }
            return
        }
        
        // Single-click: Start potential drag
        dragStartPoint = point
        dragStartPage = page
        isDragging = false  // Not dragging yet, just potential
        
        #if DEBUG
        Swift.print("[InteractivePDFView] mouseDown: Potential drag started at \(point)")
        #endif
    }
    
    override func mouseDragged(with event: NSEvent) {
        if isEditing { return }
        guard let startPoint = dragStartPoint else { return }
        
        let currentPoint = self.convert(event.locationInWindow, from: nil)
        let distance = hypot(currentPoint.x - startPoint.x, currentPoint.y - startPoint.y)
        
        // Only start drag mode if user has moved more than threshold
        if distance > dragThreshold {
            isDragging = true
            
            // Calculate rectangle in view coordinates
            let rect = CGRect(
                x: min(startPoint.x, currentPoint.x),
                y: min(startPoint.y, currentPoint.y),
                width: abs(currentPoint.x - startPoint.x),
                height: abs(currentPoint.y - startPoint.y)
            )
            
            // Draw drag overlay
            drawDragOverlay(rect: rect)
            
            #if DEBUG
            if Int(distance) % 20 == 0 {  // Log occasionally
                Swift.print("[InteractivePDFView] mouseDragged: rect=\(rect)")
            }
            #endif
        }
    }
    
    override func mouseUp(with event: NSEvent) {
        if isEditing { return }
        
        defer {
            // Always reset drag state
            dragStartPoint = nil
            dragStartPage = nil
            isDragging = false
            clearDragOverlay()
        }
        
        let endPoint = self.convert(event.locationInWindow, from: nil)
        
        if isDragging, let startPoint = dragStartPoint, let startPage = dragStartPage {
            // DRAG COMPLETED: Select text within the rectangle

            // Convert both points to page coordinates
            let pageStartPoint = self.convert(startPoint, to: startPage)
            let pageEndPoint = self.convert(endPoint, to: startPage)

            // Create selection rect in page coordinates
            let selectionRect = CGRect(
                x: min(pageStartPoint.x, pageEndPoint.x),
                y: min(pageStartPoint.y, pageEndPoint.y),
                width: abs(pageEndPoint.x - pageStartPoint.x),
                height: abs(pageEndPoint.y - pageStartPoint.y)
            )

            #if DEBUG
            Swift.print("[InteractivePDFView] mouseUp: Drag selection rect=\(selectionRect)")
            #endif

            // Get text selection within rectangle
            if var selection = startPage.selection(for: selectionRect),
               var string = selection.string, hasContent(string) {

                // BOUNDS-GATE: Detect ghost text from PDF content stream order contamination
                // PDFKit's selection(for:) selects by content stream order, not visual position,
                // so text stored adjacently in the PDF's internal structure can leak in even when
                // it renders far from the drag rect. Detect this via bounds inflation and fall back
                // to word-level sampling which is inherently bounds-aware.
                let selBounds = selection.bounds(for: startPage)
                if selectionNeedsCleaning(selBounds, dragRect: selectionRect) {
                    #if DEBUG
                    Swift.print("[InteractivePDFView] Bounds-gate triggered: selBounds=\(selBounds) vs dragRect=\(selectionRect)")
                    #endif
                    if let cleaned = wordSampledSelection(in: selectionRect, on: startPage) {
                        selection = cleaned
                        string = cleaned.string ?? string
                    }
                }

                // NOTE: constrainToFirstLogicalUnit() is intentionally NOT called here.
                // The user drew an explicit bounding box, so the app must honour all text
                // that falls inside it — including multi-line content. That function is
                // only appropriate for single-click / auto-detected selections.

                #if DEBUG
                Swift.print("[InteractivePDFView] Drag selection length=\(string.count)")
                #endif

                // Store selection info
                let bounds = selection.bounds(for: startPage)
                let viewRect = self.convert(bounds, from: startPage)
                selectedTextInfo = (selection, startPage, bounds)
                drawSelectionHighlight(rect: viewRect)

                // Open edit dialog directly for drag selection
                onClick?(selection, startPage)
            } else {
                #if DEBUG
                Swift.print("[InteractivePDFView] Drag selection: No text in region")
                #endif
            }
        } else if let startPoint = dragStartPoint, let startPage = dragStartPage {
            // NOT A DRAG: Treat as single-click (original line/word selection)
            let pagePoint = self.convert(startPoint, to: startPage)
            
            // Use smart selection (same as before)
            var selection = startPage.selectionForLine(at: pagePoint)

            // JOIN adjacent text runs on the same visual line.
            // selectionForLine returns only the text object at the queried point; the joiner
            // widens it to the full visual line using a thin Y-band selection.
            if let initial = selection {
                selection = joinedLineSelection(from: initial, on: startPage)
            }

            // MULTI-LINE TABLE CELL FIX: Check if there are additional wrapped lines BELOW
            // that belong to the same table cell (same left-X, consecutive descending Y).
            // PDF page space is Y-up: lower minY = lower on the visual page.
            // The previous implementation used maxY+2 (going UP), which was backwards and
            // always broke on the first iteration once the verticalGap guard was added.
            // Fixed to use minY-2 (going DOWN) with the correct gap formula.
            if let initialSelection = selection,
               let initialString = initialSelection.string,
               hasContent(initialString) {

                let initialBounds = initialSelection.bounds(for: startPage)
                let combinedSelection = initialSelection
                // currentBottomY = bottom edge of the current last line (Y-up: lower = more negative)
                var currentBottomY = initialBounds.minY
                let maxLinesToCheck = 5  // Limit to prevent infinite loops
                let maxAllowedGap: CGFloat = 4.0  // pt between text-box bottom and next top (tight leading)

                for _ in 0..<maxLinesToCheck {
                    // Sample 2pt BELOW the current bottom edge (Y-up: subtract to go down)
                    let nextPoint = CGPoint(x: initialBounds.minX + 5, y: currentBottomY - 2)

                    if let nextLine = startPage.selectionForLine(at: nextPoint),
                       let nextString = nextLine.string,
                       hasContent(nextString) {

                        let nextBounds = nextLine.bounds(for: startPage)

                        // 1. Same column: left edges must be within 5pt
                        let xDiff = abs(nextBounds.minX - initialBounds.minX)
                        guard xDiff < 5.0 else {
                            break  // Different column, stop
                        }

                        // 2. Tight leading: gap between current bottom and next top must be small.
                        //    In Y-up space: currentBottomY > nextBounds.maxY for consecutive lines.
                        //    verticalGap = currentBottomY - nextBounds.maxY (gap between boxes).
                        let verticalGap = currentBottomY - nextBounds.maxY
                        guard verticalGap >= 0, verticalGap < maxAllowedGap else {
                            break  // Gap too large → separate table row, or overlap → not below
                        }

                        // 3. Total vertical extent must be reasonable (prevent runaway)
                        let totalHeight = initialBounds.maxY - nextBounds.minY
                        let maxCellHeight = initialBounds.height * 6  // Max 6 lines per cell
                        guard totalHeight < maxCellHeight else {
                            break  // Cell too tall, stop expanding
                        }

                        // All checks passed - combine selections
                        combinedSelection.add(nextLine)
                        currentBottomY = nextBounds.minY  // Advance bottom to new line's bottom
                    } else {
                        break  // No more lines below
                    }
                }

                selection = combinedSelection
            }
            
            // Check for table columns (large gaps) - require BOTH wide chars AND double-spaces
            if let lineSelection = selection,
               let lineString = lineSelection.string,
               hasContent(lineString) {
                let bounds = lineSelection.bounds(for: startPage)
                let charCount = CGFloat(lineString.count)
                let avgCharWidth = bounds.width / max(charCount, 1)
                let hasWideChars = avgCharWidth > Self.avgCharWidthThreshold && charCount > CGFloat(Self.minCharsForGapDetection)
                let hasDoubleSpace = lineString.contains(String(repeating: " ", count: Self.gapDetectionMinSpaces))
                if hasWideChars && hasDoubleSpace {
                    selection = startPage.selectionForWord(at: pagePoint)
                }
            }
            
            // Fallback to word selection
            if selection == nil || !hasContent(selection?.string) {
                selection = startPage.selectionForWord(at: pagePoint)
            }
            
            if let sel = selection,
               let string = sel.string, hasContent(string) {
                
                let bounds = sel.bounds(for: startPage)
                let viewRect = self.convert(bounds, from: startPage)
                selectedTextInfo = (sel, startPage, bounds)
                drawSelectionHighlight(rect: viewRect)
                onSelect?(sel, startPage)
                
                #if DEBUG
                Swift.print("[InteractivePDFView] Click selected: '\(string)'")
                #endif
            } else {
                clearSelectionHighlight()
                selectedTextInfo = nil
            }
        }
    }
    
    // MARK: - Horizontal Text-Run Joiner

    /// Extends a `selectionForLine` result to include ALL text objects on the same visual
    /// line. PDFKit's `selectionForLine(at:)` follows the PDF content stream and returns
    /// only the text object that contains the queried point. When a visual line is composed
    /// of multiple PDF text objects (split across formatting runs, hyphenation, or internal
    /// structure), the other objects are missed, producing truncated selections like "when y"
    /// instead of "when you need to…".
    ///
    /// Fix: use `selection(for:)` with a thin horizontal band matching the initial
    /// selection's Y position. This captures every text object whose bounding box
    /// intersects the band, i.e. every run on the same visual line.
    /// A Y-tolerance guard rejects ghost text from content-stream-order contamination.
    private func joinedLineSelection(from initial: PDFSelection, on page: PDFPage) -> PDFSelection {
        let initialBounds = initial.bounds(for: page)
        guard !initialBounds.isEmpty, initialBounds.height > 0 else { return initial }

        let pageBounds = page.bounds(for: .mediaBox)

        // Thin band spanning the exact Y range of this line, inset 1pt on each side
        // so we don't accidentally catch text from immediately adjacent lines.
        let yInset: CGFloat = 1.0
        let band = CGRect(
            x: pageBounds.minX,
            y: initialBounds.minY + yInset,
            width: pageBounds.width,
            height: max(1.0, initialBounds.height - 2.0 * yInset)
        )

        guard let extended = page.selection(for: band),
              let extStr = extended.string, hasContent(extStr) else {
            return initial
        }

        let extBounds = extended.bounds(for: page)

        // Ghost-text guard: the joined selection's Y range must stay within 4pt of the
        // original. If it drifts further, PDFKit grabbed unrelated content via stream order.
        let yTolerance: CGFloat = 4.0
        guard abs(extBounds.minY - initialBounds.minY) < yTolerance,
              abs(extBounds.maxY - initialBounds.maxY) < yTolerance else {
            #if DEBUG
            Swift.print("[InteractivePDFView] joinedLineSelection: rejected (Y drift \(abs(extBounds.minY - initialBounds.minY))pt)")
            #endif
            return initial
        }

        #if DEBUG
        if extStr.count > (initial.string?.count ?? 0) {
            Swift.print("[InteractivePDFView] joinedLineSelection: initialLength=\(initial.string?.count ?? 0), extendedLength=\(extStr.count)")
        }
        #endif

        return extended
    }

    // MARK: - Bounds-Gate Ghost Text Detection

    /// Returns true if the selection bounds extend significantly beyond the drag rect,
    /// indicating contamination from PDF content stream order (ghost text).
    private func selectionNeedsCleaning(_ selBounds: CGRect, dragRect: CGRect) -> Bool {
        let threshold: CGFloat = 15.0
        // Check if selection bounds extend >15pt beyond drag rect in any direction
        let extendsLeft   = dragRect.minX - selBounds.minX > threshold
        let extendsRight  = selBounds.maxX - dragRect.maxX > threshold
        let extendsUp     = selBounds.maxY - dragRect.maxY > threshold
        let extendsDown   = dragRect.minY - selBounds.minY > threshold
        // Also flag if selection is more than 2x wider than the drag rect
        let wayTooWide = selBounds.width > dragRect.width * 2

        return extendsLeft || extendsRight || extendsUp || extendsDown || wayTooWide
    }

    /// Fallback selection that samples words across the drag rect, keeping only those
    /// whose visual bounds actually overlap the rect. This avoids ghost text from
    /// PDFKit's content-stream-order selection.
    private func wordSampledSelection(in rect: CGRect, on page: PDFPage) -> PDFSelection? {
        var merged: PDFSelection? = nil
        let stepX: CGFloat = 8.0
        // Use the same dense step vertically as horizontally so that every text line is
        // hit regardless of how many lines fit in the drag rect (the old "height / 3"
        // would skip lines when more than three rows were selected).
        let stepY: CGFloat = 8.0
        var seen = Set<String>()  // Deduplicate by bounds identity

        // Vertical scanning: sample at multiple Y positions to catch multi-line text
        var y = rect.minY + 2
        while y < rect.maxY {
            var x = rect.minX + 2
            while x < rect.maxX {
                let pt = CGPoint(x: x, y: y)
                if let word = page.selectionForWord(at: pt),
                   let wordStr = word.string,
                   hasContent(wordStr) {
                    let wordBounds = word.bounds(for: page)
                    // Keep only if bounds meaningfully overlap the drag rect
                    let overlap = rect.intersection(wordBounds)
                    if !overlap.isNull && overlap.width > 0 && overlap.height > 0 && overlap.width > wordBounds.width * 0.5 {
                        // Use higher precision to distinguish close-but-different positions
                        let key = "\(String(format: "%.1f", wordBounds.minX)),\(String(format: "%.1f", wordBounds.minY))"
                        if !seen.contains(key) {
                            seen.insert(key)
                            // BUG #42 FIX: Make selection mutation clearer
                            // PDFSelection is a reference type - add() mutates in-place
                            if merged != nil {
                                merged?.add(word)  // Mutates existing selection
                            } else {
                                merged = word  // Initialize first selection
                            }
                        }
                    }
                }
                x += stepX
            }
            y += stepY
        }

        // Vertical sampling is now integrated above - no separate pass needed

        #if DEBUG
        Swift.print("[InteractivePDFView] wordSampledSelection: resultLength=\(merged?.string?.count ?? 0)")
        #endif

        return merged
    }

    // MARK: - Safe Selection Boundary Detection

    /// Constrains a selection to the first logical unit (text block, table cell, etc.)
    /// This prevents users from accidentally selecting across multiple editable units.
    private func constrainToFirstLogicalUnit(selection: PDFSelection, page: PDFPage, originalRect: CGRect) -> PDFSelection? {
        guard let string = selection.string else { return nil }

        // Boundary indicators that suggest multiple logical units:
        // 1. Newlines - different lines/paragraphs
        // 2. Tab characters - table columns
        // 3. Multiple consecutive spaces - column separators

        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }

        // Check for boundary indicators
        let hasNewline = string.contains("\n") || string.contains("\r")
        let hasTab = string.contains("\t")
        // Use 3+ consecutive spaces as the column-gap indicator instead of 2.
        // Double spaces are common after periods in older PDFs, abbreviations ("U.S.  Navy"),
        // and formatted names — too aggressive for safe-selection fragmentation.
        let hasColumnGap = string.contains("   ")  // Triple space reliably indicates columns

        // If no boundaries, return original selection
        if !hasNewline && !hasTab && !hasColumnGap {
            return selection
        }

        #if DEBUG
        Swift.print("[SafeSelection] Detected boundaries - newline:\(hasNewline) tab:\(hasTab) gap:\(hasColumnGap)")
        #endif

        // Strategy: Find the first logical unit by:
        // 1. Getting selection at the START of the drag
        // 2. Using line selection there as the safe unit

        let startPoint = CGPoint(x: originalRect.minX + 2, y: originalRect.midY)

        // Try line selection at start point
        if let lineSelection = page.selectionForLine(at: startPoint),
           let lineString = lineSelection.string,
           hasContent(lineString) {

            // Verify this line is within our original rect
            let lineBounds = lineSelection.bounds(for: page)
            if originalRect.intersects(lineBounds) {
                #if DEBUG
                Swift.print("[SafeSelection] Constrained to line length=\(lineString.count)")
                #endif
                return lineSelection
            }
        }

        // Fallback: Try word selection at start
        if let wordSelection = page.selectionForWord(at: startPoint),
           let wordString = wordSelection.string,
           hasContent(wordString) {

            #if DEBUG
            Swift.print("[SafeSelection] Constrained to word: '\(wordString)'")
            #endif
            return wordSelection
        }

        // If all else fails, return original (let user deal with complex selection)
        #if DEBUG
        Swift.print("[SafeSelection] Could not constrain, using original")
        #endif
        return selection
    }

    // MARK: - Drag Overlay Drawing

    private func drawDragOverlay(rect: CGRect) {
        if self.layer == nil { self.wantsLayer = true }
        
        if dragOverlay == nil || dragOverlay?.superlayer == nil {
            if let overlay = dragOverlay, overlay.superlayer != nil {
                overlay.removeFromSuperlayer()
            }
            let layer = CAShapeLayer()
            layer.fillColor = NSColor.systemBlue.withAlphaComponent(0.1).cgColor
            layer.strokeColor = NSColor.systemBlue.withAlphaComponent(0.6).cgColor
            layer.lineWidth = 1.5
            layer.lineDashPattern = [4, 2]
            layer.zPosition = 1002  // Above other overlays
            self.layer?.addSublayer(layer)
            self.dragOverlay = layer
        }
        
        dragOverlay?.path = CGPath(rect: rect, transform: nil)
        dragOverlay?.isHidden = false
    }
    
    private func clearDragOverlay() {
        dragOverlay?.isHidden = true
    }
    
    /// Clear the current selection (called when edit dialog closes or user clicks elsewhere)
    func clearCurrentSelection() {
        selectedTextInfo = nil
        clearSelectionHighlight()
        setPreviewError(false)
    }
    
    private func drawHighlight(rect: CGRect) {
        // Ensure we have a layer for drawing
        if self.layer == nil {
            self.wantsLayer = true
        }
        
        // Always check if overlay needs to be recreated (handles detached overlays after document reload)
        if hoverOverlay == nil || hoverOverlay?.superlayer == nil {
            if let overlay = hoverOverlay, overlay.superlayer != nil {
                overlay.removeFromSuperlayer()
            }
            let layer = CAShapeLayer()
            layer.fillColor = NSColor.clear.cgColor
            layer.strokeColor = NSColor.red.cgColor
            layer.lineWidth = 1.5
            layer.lineDashPattern = [4, 2]
            layer.zPosition = 1000 // Ensure it's on top
            self.layer?.addSublayer(layer)
            self.hoverOverlay = layer
        }
        
        hoverOverlay?.path = CGPath(rect: rect, transform: nil)
        hoverOverlay?.isHidden = false
    }
    
    private func clearHighlight() {
        hoverOverlay?.isHidden = true
    }
    
    func highlightParagraph(rect: CGRect, pageIndex: Int) {
        // Validate pageIndex before use - page(at:) with negative index can crash
        guard pageIndex >= 0, let page = self.document?.page(at: pageIndex) else { return }
        
        // PyMuPDF returns Top-Left coordinates. PDFKit uses Bottom-Left.
        // We need to flip the Y coordinate using the page's MediaBox.
        // rect is [x0, y0, width, height] in Top-Left space.
        let pageBounds = page.bounds(for: .mediaBox)
        
        // PyMuPDF y0 is distance from top.
        // PDFKit y0 is distance from bottom.
        // The visual top of the rect (PyMuPDF y0) becomes (PageHeight - y0) in PDFKit (which is the TOP of the rect).
        // The visual bottom of the rect (PyMuPDF y1) becomes (PageHeight - y1) in PDFKit (which is the BOTTOM/origin of the rect).
        // So PDFKit Origin Y = PageHeight - PyMuPDF_MaxY
        
        let pdfHeight = rect.height
        let pyMuPDF_MaxY = rect.origin.y + pdfHeight
        let invertedY = pageBounds.maxY - pyMuPDF_MaxY
        
        let pdfRect = CGRect(x: rect.origin.x, y: invertedY, width: rect.width, height: pdfHeight)
        
        let viewRect = self.convert(pdfRect, from: page)
        drawSelectionHighlight(rect: viewRect)
    }
    
    internal func drawSelectionHighlight(rect: CGRect) {
        // Ensure we have a layer for drawing
        if self.layer == nil {
            self.wantsLayer = true
        }
        
        // Create selection overlay if needed - subtle gray outline only (no fill)
        if selectionOverlay == nil || selectionOverlay?.superlayer == nil {
            if let overlay = selectionOverlay, overlay.superlayer != nil {
                overlay.removeFromSuperlayer()
            }
            let layer = CAShapeLayer()
            layer.fillColor = NSColor.clear.cgColor  // No fill - less distracting
            layer.strokeColor = NSColor.gray.withAlphaComponent(0.5).cgColor  // Subtle gray
            layer.lineWidth = 1.0  // Thinner line
            layer.lineDashPattern = [2, 2]  // Dotted/Micro-dashed for paragraph box
            layer.zPosition = 999 // Below hover overlay
            self.layer?.addSublayer(layer)
            self.selectionOverlay = layer
        }
        
        selectionOverlay?.path = CGPath(rect: rect, transform: nil)
        selectionOverlay?.isHidden = false
    }
    
    override func viewDidChangeBackingProperties() {
        super.viewDidChangeBackingProperties()
        if let scale = self.window?.backingScaleFactor {
            self.previewLayer?.contentsScale = scale
            self.hoverOverlay?.contentsScale = scale
            self.selectionOverlay?.contentsScale = scale
            self.dragOverlay?.contentsScale = scale
        }
    }
    
    private var previewLayer: CATextLayer?
    private var previewLayerOriginalForeground: CGColor = NSColor.black.cgColor
    private var previewGenerationTask: Task<Void, Never>?
    internal var previewHasError: Bool = false  // Track if preview has a collision error

    func updatePreview(text: String?, fontName: String?, pageIndex: Int, isItalic: Bool = false, isBold: Bool = false) {
        // Log received font through app logging system
        LogManager.shared.log("InteractivePDFView: updatePreview - fontName: '\(fontName ?? "nil")', textLength=\(text?.count ?? 0)")
        
        // Cancel any pending generation
        previewGenerationTask?.cancel()

        // If no text, hide layer immediately
        guard let text = text, let info = selectedTextInfo,
              let infoPageIndex = self.document?.index(for: info.page),
              infoPageIndex != NSNotFound, infoPageIndex == pageIndex,
              let currentPage = self.document?.page(at: infoPageIndex) else {
            previewLayer?.isHidden = true
            setPreviewError(false)
            return
        }

        // Ensure layer setup
        if self.layer == nil { self.wantsLayer = true }
        if previewLayer == nil || previewLayer?.superlayer == nil {
            if let layer = previewLayer, layer.superlayer != nil {
                layer.removeFromSuperlayer()
            }
            let layer = CATextLayer()
            // Use CLEAR/TRANSPARENT background - let PDF show through
            // This avoids complex background sampling while still showing preview
            layer.backgroundColor = NSColor.clear.cgColor
            layer.foregroundColor = NSColor.black.cgColor // Default black text
            layer.alignmentMode = .left
            layer.contentsScale = self.window?.backingScaleFactor ?? 2.0
            layer.zPosition = 1001 // Topmost
            self.layer?.addSublayer(layer)
            self.previewLayer = layer
            self.previewLayerOriginalForeground = layer.foregroundColor ?? NSColor.black.cgColor
        }

        // Calculate rect in view coordinates
        // Use freshly-fetched currentPage instead of potentially stale info.page
        var viewRect = self.convert(info.rect, from: currentPage)
        
        // Extend width to accommodate replacement text
        // Always add buffer since different characters have different widths
        let originalLen = max(info.selection.string?.count ?? 1, 1)
        let newLen = text.count
        let ratio = CGFloat(newLen) / CGFloat(originalLen)
        // Base extension: 1.2x for same length (char width variance), scales with text length ratio
        let extension_multiplier = max(ratio * 1.2, 1.2) // Minimum 1.2x, scales up for longer text
        let calculatedWidth = viewRect.width * min(extension_multiplier, 3.0) // Cap at 3x

        // Clamp to page bounds to prevent overflow
        let pageBounds = self.convert(currentPage.bounds(for: .mediaBox), from: currentPage)
        let margin: CGFloat = 10.0 // Leave small margin from page edge
        let maxWidth = max(pageBounds.maxX - viewRect.minX - margin, 1.0)
        viewRect.size.width = min(calculatedWidth, maxWidth)
        
        // Configure layer frame primarily
        previewLayer?.frame = viewRect
        previewLayer?.string = text
        
        // Determine font size from rect height (heuristic: ~80% of line height)
        let fontSize = viewRect.height * 0.8
        
        // Hide until font is loaded to prevent flash of wrong font
        previewLayer?.isHidden = true
        
        // Offload font loading to background task
        previewGenerationTask = Task {
            // Load font with style fallback
            // If fontName is provided, use it. If not, fallback to system.
            // In both cases, apply traits if requested.
            var fontToUse: NSFont? = nil
            
            if let fontName = fontName {
                 fontToUse = self.loadFontWithStyleFallback(fontName, size: fontSize)
            } else {
                 fontToUse = NSFont.systemFont(ofSize: fontSize)
            }
            
            // If we have explicit traits from VM/Manual overrides, force them
            if (isItalic || isBold) {
                if let base = fontToUse {
                    var traits: NSFontTraitMask = []
                    if isItalic { traits.insert(.italicFontMask) }
                    if isBold { traits.insert(.boldFontMask) }
                    
                    let manager = NSFontManager.shared
                    fontToUse = manager.convert(base, toHaveTrait: traits)
                }
            }
            
            if Task.isCancelled { return }
            
            let finalFont = fontToUse
            
            // MEASURE TEXT (Remove magic numbers)
            // Calculate exact width needed for the text with the loaded font
            var newWidth = viewRect.width
            if let font = finalFont {
                 let attributes: [NSAttributedString.Key: Any] = [.font: font]
                 let size = (text as NSString).size(withAttributes: attributes)
                 // Add logic: If text is growing, use measured width. 
                 // If shrinking, maybe keep original or shrink? Standard is to match content.
                 // Add small buffer for cursor/rendering
                 newWidth = size.width + 10.0
            }
            
            let calculatedWidth = newWidth

            await MainActor.run {
                self.previewLayer?.font = finalFont
                self.previewLayer?.fontSize = fontSize

                // Update frame with accurate width, but RE-APPLY page bounds clamp
                if var frame = self.previewLayer?.frame {
                    // Recalculate maxWidth from current frame position
                    let pageBounds = self.convert(currentPage.bounds(for: .mediaBox), from: currentPage)
                    let margin: CGFloat = 10.0
                    let maxWidth = max(pageBounds.maxX - frame.minX - margin, 1.0)

                    // Apply same clamping as initial calculation for consistency
                    frame.size.width = min(calculatedWidth, maxWidth)
                    self.previewLayer?.frame = frame

                } else {
                    // No need for truncation tracking — collision detection handles it
                }

                self.previewLayer?.isHidden = false

                // Apply error tint if preview has a collision error
                self.applyPreviewErrorTint()
            }
        }
    }
    
    // Helper to resolve font (similar to FontControlPanel but returning specific type)
    private func fontFromID(_ id: String, size: CGFloat) -> CFTypeRef? {
        return loadFontWithStyleFallback(id, size: size)
    }
    
    /// Attempt to load font, or create a styled fallback by detecting italic/bold in font name
    private func loadFontWithStyleFallback(_ fontName: String, size: CGFloat) -> NSFont? {
        LogManager.shared.log("loadFontWithStyleFallback: Input='\(fontName)', size=\(size)")
        
        // STEP 1: Check for path|name format (extracted temp font)
        if fontName.contains("|") {
            let parts = fontName.split(separator: "|", maxSplits: 1)
            if parts.count == 2 {
                let pathPart = String(parts[0])
                let namePart = String(parts[1])
                
                LogManager.shared.log("loadFontWithStyleFallback: Detected path|name")
                
                // If path starts with / it's a file path
                if pathPart.hasPrefix("/") || pathPart.hasPrefix("file://") {
                    LogManager.shared.log("loadFontWithStyleFallback: Attempting loadFontFromPath...")
                    if let font = loadFontFromPath(pathPart, size: size) {
                        LogManager.shared.log("loadFontWithStyleFallback: ✓ SUCCESS - loaded: \(font.fontName)")
                        return font
                    }
                    LogManager.shared.log("loadFontWithStyleFallback: ✗ loadFontFromPath FAILED")
                    // Fallback: try the name part as system font
                }
                // Not a file path - treat as normal processing with namePart
                // Continue to process just the name part
                return loadFontWithStyleFallback(namePart, size: size)
            }
        }
        
        // Handle PyMuPDF builtin font shortcodes
        let builtinFontMap: [String: String] = [
            "cour": "Courier",
            "helv": "Helvetica", 
            "tiro": "Times-Roman",
            "symb": "Symbol",
            "zadb": "ZapfDingbats"
        ]
        
        // If it's a shortcode, resolve it to system name
        let resolvedName = builtinFontMap[fontName] ?? fontName

        // First, try direct match with resolved name
        if let font = NSFont(name: resolvedName, size: size) {
            return font
        }
        
        // Detect style keywords for embedded PDF fonts (e.g., "AAAAAA+Calibri,Italic")
        let nameToAnalyze = resolvedName
        let normalizedName = nameToAnalyze.lowercased()
        let isItalic = normalizedName.contains("italic") || normalizedName.contains("oblique")
        let isBold = normalizedName.contains("bold") || normalizedName.contains("heavy") || 
                     normalizedName.contains("black") || normalizedName.contains("semibold")
        
        // Extract base font name (strip subset prefix like "AAAAAA+")
        var baseName = nameToAnalyze
        if let plusRange = nameToAnalyze.range(of: "+") {
            baseName = String(nameToAnalyze[plusRange.upperBound...])
        }
        
        // Remove style suffixes to get clean base name
        for suffix in [",Italic", "-Italic", ",Bold", "-Bold", ",BoldItalic", "-BoldItalic",
                       "Italic", "Bold", "Regular", "-Regular", ",Regular"] {
            if baseName.hasSuffix(suffix) {
                baseName = String(baseName.dropLast(suffix.count))
            }
        }
        
        // Try to find a system font matching the base name
        let candidates = [baseName, baseName + "-Regular", baseName + "-Roman"]
        for candidate in candidates {
            if let baseFont = NSFont(name: candidate, size: size) {
                // Apply traits using NSFontManager
                var traits: NSFontTraitMask = []
                if isItalic { traits.insert(.italicFontMask) }
                if isBold { traits.insert(.boldFontMask) }
                
                if !traits.isEmpty {
                    let manager = NSFontManager.shared
                    let styledFont = manager.convert(baseFont, toHaveTrait: traits)
                    return styledFont
                }
                return baseFont
            }
        }
        
        // Last resort: Use system font with detected traits
        if isItalic || isBold {
            var traits: NSFontTraitMask = []
            if isItalic { traits.insert(.italicFontMask) }
            if isBold { traits.insert(.boldFontMask) }
            
            let systemFont = NSFont.systemFont(ofSize: size)
            let manager = NSFontManager.shared
            return manager.convert(systemFont, toHaveTrait: traits)
        }
        
        return nil
    }
    
    /// Load a font from a file path using CoreText
    private func loadFontFromPath(_ path: String, size: CGFloat) -> NSFont? {
        let url: URL
        if path.hasPrefix("file://") {
            guard let parsedURL = URL(string: path) else { return nil }
            url = parsedURL
        } else {
            url = URL(fileURLWithPath: path)
        }
        
        // Check file exists
        guard FileManager.default.fileExists(atPath: url.path) else {
            LogManager.shared.log("loadFontFromPath: Font file not found")
            return nil
        }
        
        // Register the font for this process
        var error: Unmanaged<CFError>?
        let success = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error)
        
        if !success {
            if let cfError = error?.takeRetainedValue() {
                LogManager.shared.log("loadFontFromPath: Failed to register font: \(cfError)")
            }
            // Font might already be registered - continue anyway
        }
        
        // Create CTFont from the file
        guard let dataProvider = CGDataProvider(url: url as CFURL),
              let cgFont = CGFont(dataProvider) else {
            LogManager.shared.log("loadFontFromPath: Failed to create CGFont")
            return nil
        }
        
        let ctFont = CTFontCreateWithGraphicsFont(cgFont, size, nil, nil)
        
        // Convert to NSFont
        let nsFont = ctFont as NSFont
        
        LogManager.shared.log("loadFontFromPath: ✓ Loaded font from file: \(nsFont.fontName)")
        
        return nsFont
    }

    private func clearSelectionHighlight() {
        selectionOverlay?.isHidden = true
    }

    /// Update preview layer appearance based on collision error state
    func setPreviewError(_ hasError: Bool) {
        previewHasError = hasError
        applyPreviewErrorTint()
    }

    private func applyPreviewErrorTint() {
        previewLayer?.foregroundColor = previewHasError
            ? NSColor.systemRed.withAlphaComponent(0.5).cgColor
            : previewLayerOriginalForeground
        previewLayer?.borderColor = previewHasError
            ? NSColor.systemRed.cgColor
            : nil
        previewLayer?.borderWidth = previewHasError ? 1.5 : 0
    }
    
    // MARK: - Dark Mode
    func setDarkMode(_ enabled: Bool) {
        if enabled {
            // 1. Disable shadows to prevent "white glow" effect
            if self.pageShadowsEnabled {
                self.pageShadowsEnabled = false
            }
            
            // 2. Set base background to match the Sidebar (Theme.cardColor)
            // Math: Target(0.17) = Text(0.90) * (1-x) + Page(0.13) * x
            // x ≈ 0.95 (where x is the input grayscale value)
            self.backgroundColor = NSColor(white: 0.95, alpha: 1.0)
            
            // 3. Use CIFalseColor to map White/Black to App Theme Colors
            // Target: Text = White (0.9), Background = Dark Theme (0.15)
            // Note: inputColor0 replaces numeric 0 (Black/Dark areas - Text)
            //       inputColor1 replaces numeric 1 (White/Light areas - Background)
            
            // Text Color: Slightly off-white for comfort (#E0E0E0)
            let textColor = CIColor(red: 0.90, green: 0.90, blue: 0.90)
            
            // Background Color: Match App Theme Well Color (#212129 approx)
            // R: 0.13, G: 0.13, B: 0.16
            let bgColor = CIColor(red: 0.13, green: 0.13, blue: 0.16)
            
            if let filter = CIFilter(name: "CIFalseColor") {
                filter.setValue(textColor, forKey: "inputColor0") // Map Black source (Text) to White
                filter.setValue(bgColor, forKey: "inputColor1")   // Map White source (Paper) to Dark Gray
                
                // We assume input is the view layer content
                self.layer?.filters = [filter]
            }
        } else {
            // Restore defaults
            if !self.pageShadowsEnabled {
                self.pageShadowsEnabled = true
            }
            self.backgroundColor = NSColor.clear
            self.layer?.filters = nil
        }
    }
}

struct PDFKitView: NSViewRepresentable {
    let document: PDFDocument?
    let isDarkMode: Bool
    let isEditing: Bool
    let selectionMode: String
    let paragraphRect: CGRect?
    let paragraphPageIndex: Int
    @Binding var currentScaleFactor: CGFloat
    @Binding var currentDestination: PDFDestination?
    
    let onLineSelect: (String, Int) -> Void   // Single-click: select text
    let onLineClick: (String, Int) -> Void    // Double-click: open edit dialog
    var onKeyDown: ((NSEvent) -> Bool)? = nil
    
    // Default initializer support for previous calls
    init(document: PDFDocument?, 
         isDarkMode: Bool, 
         isEditing: Bool = false,
         selectionMode: String = "line",
         paragraphRect: CGRect? = nil, 
         paragraphPageIndex: Int = 0, 
         currentScaleFactor: Binding<CGFloat>,
         currentDestination: Binding<PDFDestination?>,
         onLineSelect: @escaping (String, Int) -> Void, 
         onLineClick: @escaping (String, Int) -> Void, 
         onKeyDown: ((NSEvent) -> Bool)? = nil) {
        self.document = document
        self.isDarkMode = isDarkMode
        self.isEditing = isEditing
        self.selectionMode = selectionMode
        self.paragraphRect = paragraphRect
        self.paragraphPageIndex = paragraphPageIndex
        self._currentScaleFactor = currentScaleFactor
        self._currentDestination = currentDestination
        self.onLineSelect = onLineSelect
        self.onLineClick = onLineClick
        self.onKeyDown = onKeyDown
    }

    
    func makeNSView(context: Context) -> InteractivePDFView {
        let pdfView = InteractivePDFView()
        pdfView.autoScales = true
        pdfView.backgroundColor = NSColor.clear
        pdfView.wantsLayer = true
        pdfView.setAccessibilityIdentifier("PDFViewer")
        
        // Single-click: select text (starts font search)
        pdfView.onSelect = { selection, page in
            guard let sel = selection, let p = page, let str = sel.string, !str.isEmpty else {
                if selection?.string == nil {
                    print("[InteractivePDFView] onSelect: selection.string is nil")
                }
                return
            }
            guard let pageIndex = pdfView.document?.index(for: p), pageIndex != NSNotFound else {
                print("[InteractivePDFView] onSelect: invalid page index")
                return
            }
            onLineSelect(str, pageIndex)
        }

        // Double-click: open edit dialog
        pdfView.onClick = { selection, page in
            guard let sel = selection, let p = page, let str = sel.string, !str.isEmpty else {
                if selection?.string == nil {
                    print("[InteractivePDFView] onClick: selection.string is nil")
                }
                return
            }
            guard let pageIndex = pdfView.document?.index(for: p), pageIndex != NSNotFound else {
                print("[InteractivePDFView] onClick: invalid page index")
                return
            }
            onLineClick(str, pageIndex)
        }
        
        pdfView.onKeyDown = onKeyDown
        
        // Callback to update bindings
        pdfView.onLayoutChange = { scale, dest in
            DispatchQueue.main.async {
                self.currentScaleFactor = scale
                self.currentDestination = dest
            }
        }
        
        return pdfView
    }
    
    func updateNSView(_ pdfView: InteractivePDFView, context: Context) {
        pdfView.setAccessibilityIdentifier("PDFViewer")
        pdfView.subviews.compactMap { $0 as? NSScrollView }.first?.setAccessibilityIdentifier("PDFViewer")
        pdfView.setDarkMode(isDarkMode)
        pdfView.isEditing = isEditing
        pdfView.selectionMode = selectionMode
        
        // Update selection highlight if paragraph mode is active
        if let rect = paragraphRect {
            pdfView.highlightParagraph(rect: rect, pageIndex: paragraphPageIndex)
        }
        
        // Real preview is handled by Python replacement
        // No overlay update needed here

        if pdfView.document != document {
            pdfView.clearCurrentSelection() // Fix ghost selection
            // Prevent visual flash by freezing updates until we restore position
            pdfView.window?.disableScreenUpdatesUntilFlush()
            
            // Capture current state to preserve scroll position AND zoom across edits
            // If explicit bindings are set (non-default), use them. 
            // Otherwise fall back to view's current state (legacy behavior)
            let previousDest = currentDestination ?? pdfView.currentDestination
            let previousScaleFactor = currentScaleFactor > 0.1 ? currentScaleFactor : pdfView.scaleFactor
            
            // Suppress ALL animations during swap (CATransaction + NSAnimationContext)
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            
            NSAnimationContext.runAnimationGroup { animationContext in
                animationContext.duration = 0
                animationContext.allowsImplicitAnimation = false
                
                pdfView.document = document
                pdfView.pageMarginCache.removeAll()  // Invalidate margin cache on document change
                pdfView.layoutDocumentView() // Force immediate layout update
                
                // Restore zoom level
                // Note: We prioritize the ViewModel's state if available
                if previousScaleFactor > 0.1 {
                     pdfView.scaleFactor = previousScaleFactor
                }
                
                // Restore position
                if let oldDest = previousDest {
                    // Try to map to new document
                    if let oldPage = oldDest.page, let oldDoc = oldPage.document,
                       let newDoc = document {
                        // Document Switch or Reload
                        let pageIndex = oldDoc.index(for: oldPage)
                        if pageIndex != NSNotFound, pageIndex < newDoc.pageCount, let newPage = newDoc.page(at: pageIndex) {
                            let newDest = PDFDestination(page: newPage, at: oldDest.point)
                            newDest.zoom = previousScaleFactor
                            pdfView.go(to: newDest)
                        }
                    } else if let page = oldDest.page, let _ = page.document {
                         // Same document but reloaded instance? Or simplistic restore
                         pdfView.go(to: oldDest)
                    }
                }
            }
            
            CATransaction.commit()
            
            // FALLBACK: Re-apply zoom after layout settles (timing issue workaround)
            // Some PDFs trigger internal layout that overrides scaleFactor
            // Use observation instead of fixed delay to avoid race conditions
            if previousScaleFactor > 0.1 {
                var observation: NSKeyValueObservation?
                var retryCount = 0
                let maxRetries = 5

                observation = pdfView.observe(\.scaleFactor, options: [.new]) { [weak pdfView] _, change in
                    guard let newScale = change.newValue, let pdfView = pdfView else { return }

                    if abs(newScale - previousScaleFactor) > 0.01 && retryCount < maxRetries {
                        retryCount += 1
                        pdfView.scaleFactor = previousScaleFactor
                    } else if abs(newScale - previousScaleFactor) < 0.01 {
                        // Scale factor stabilized at correct value
                        observation?.invalidate()
                    } else if retryCount >= maxRetries {
                        // Give up after max retries
                        observation?.invalidate()
                    } else {
                        // Unexpected state — clean up to prevent leak
                        observation?.invalidate()
                    }
                }

                // Clean up observation after 1 second even if not stabilized
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    observation?.invalidate()
                }
            }
        }
    }
}
