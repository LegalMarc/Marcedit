import SwiftUI
import AppKit

/// Represents a single text span with full styling information from a PDF block
struct SpanInfo: Identifiable, Codable, Equatable, Hashable {
    var id: UUID
    var text: String
    var font: String
    var size: Double
    var flags: Int
    var isBold: Bool
    var isItalic: Bool
    var color: [Double]  // RGB 0-1
    var bbox: [Double]   // [x0, y0, x1, y1]
    var lineIndex: Int
    
    // Memberwise init
    init(id: UUID = UUID(), text: String, font: String, size: Double, flags: Int, isBold: Bool, isItalic: Bool, color: [Double], bbox: [Double], lineIndex: Int) {
        self.id = id
        self.text = text
        self.font = font
        self.size = size
        self.flags = flags
        self.isBold = isBold
        self.isItalic = isItalic
        self.color = color
        self.bbox = bbox
        self.lineIndex = lineIndex
    }

    /// Initialize from dictionary returned by Python
    init(from dict: [String: Any]) {
        self.id = UUID()
        
        // Validate required keys
        if dict["text"] == nil {
            print("Warning: SpanInfo missing 'text' key") // Or log using LogManager if available globally
        }
        
        self.text = dict["text"] as? String ?? ""
        self.font = dict["font"] as? String ?? ""
        self.size = dict["size"] as? Double ?? 12.0
        self.flags = dict["flags"] as? Int ?? 0
        self.isBold = dict["is_bold"] as? Bool ?? false
        self.isItalic = dict["is_italic"] as? Bool ?? false
        self.color = dict["color"] as? [Double] ?? [0, 0, 0]
        self.bbox = dict["bbox"] as? [Double] ?? [0, 0, 0, 0]
        self.lineIndex = dict["line_index"] as? Int ?? 0
    }
    
    /// Create NSFont for this span
    var nsFont: NSFont {
        var traits: NSFontTraitMask = []
        if isBold { traits.insert(.boldFontMask) }
        if isItalic { traits.insert(.italicFontMask) }
        
        // Try to find system font matching the PDF font name
        let fontManager = NSFontManager.shared
        
        // Try exact name first
        if let exactFont = NSFont(name: font, size: CGFloat(size)) {
            return exactFont
        }
        
        // Fallback: use system font with traits
        // Fallback: use system font with traits
        // Consider weight explicitly for better matching
        let weight: NSFont.Weight = isBold ? .bold : .regular
        let baseFont = NSFont.systemFont(ofSize: CGFloat(size), weight: weight)
        
        if isItalic {
            return fontManager.convert(baseFont, toHaveTrait: .italicFontMask)
        }
        return baseFont
    }
    
    /// Create NSColor for this span
    /// Adapts dark colors to be visible in dark mode
    var nsColor: NSColor {
        // Handle RGB (3) or RGBA (4)
        guard color.count >= 3 else { return .textColor }
        let alpha = color.count > 3 ? CGFloat(color[3]) : 1.0

        let r = CGFloat(color[0])
        let g = CGFloat(color[1])
        let b = CGFloat(color[2])

        // Check if color is dark (average < 0.3)
        let brightness = (r + g + b) / 3.0

        // If dark color, use adaptive text color that works in both light/dark modes
        if brightness < 0.3 {
            return .textColor  // System text color (black in light mode, white in dark mode)
        }

        // Otherwise use the original PDF color
        return NSColor(red: r, green: g, blue: b, alpha: alpha)
    }
}

/// A rich text editor that displays and edits styled spans from a PDF block
struct RichTextEditor: NSViewRepresentable {
    @Binding var spans: [SpanInfo]
    @Binding var selectedRange: NSRange
    var onTextChange: ((String) -> Void)?
    
    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else {
            // Should never happen with scrollableTextView, but safe fallback
            return NSScrollView()
        }
        
        textView.delegate = context.coordinator
        textView.isRichText = true
        textView.allowsUndo = true
        textView.isEditable = true
        textView.isSelectable = true
        textView.usesFontPanel = false
        textView.font = NSFont.systemFont(ofSize: 14)
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.backgroundColor = NSColor.textBackgroundColor
        
        // Apply initial content
        updateTextView(textView)
        
        return scrollView
    }
    
    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        
        // Update coordinator with latest parent (bindings)
        context.coordinator.parent = self
        
        // Only update if spans changed (avoid cursor jumping)
        // Use equality check instead of hash to avoid collisions
        if context.coordinator.lastSpans != spans {
            updateTextView(textView)
            context.coordinator.lastSpans = spans
        }
    }
    
    private func updateTextView(_ textView: NSTextView) {
        let attributedString = NSMutableAttributedString()
        
        // Initialize to 0 so we count newlines from start if needed
        var lastLineIndex = 0
        
        for span in spans {
            // Calculate newlines to append
            // If first span starts on line > 0, we might want leading newlines
            // But usually PDF content starts at line 0 relative to block. 
            // If we want exact reproduction, we use difference.
            
            // Special case for first span: 
            // If Parse starts at line 0, logic 0-0=0. Correct.
            // If Parse starts at line 2 (e.g. " \n\nText"), logic 2-0=2. Correct.
            
            // However, we must ensure we don't double count if we just initialized.
            // If span.lineIndex < lastLineIndex, something is wrong (unordered).
            
            let delta = max(0, span.lineIndex - lastLineIndex)
            
            // Append newlines
            if delta > 0 {
                attributedString.append(NSAttributedString(string: String(repeating: "\n", count: delta)))
            }
            
            lastLineIndex = span.lineIndex
            
            let attrs: [NSAttributedString.Key: Any] = [
                .font: span.nsFont,
                .foregroundColor: span.nsColor
            ]
            attributedString.append(NSAttributedString(string: span.text, attributes: attrs))
        }
        
        textView.textStorage?.setAttributedString(attributedString)
    }
    
    static func dismantleNSView(_ scrollView: NSScrollView, coordinator: Coordinator) {
        if let textView = scrollView.documentView as? NSTextView {
            textView.delegate = nil
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }
    
    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: RichTextEditor
        var lastSpans: [SpanInfo] = []
        
        init(_ parent: RichTextEditor) {
            self.parent = parent
        }
        
        func textViewDidChangeSelection(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            DispatchQueue.main.async {
                self.parent.selectedRange = textView.selectedRange()
            }
        }
        
        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            guard let storage = textView.textStorage else { return }
            
            let fullString = storage.string
            var newSpans: [SpanInfo] = []
            var lastLineIndex = 0
            
            storage.enumerateAttributes(in: NSRange(location: 0, length: storage.length), options: []) { (attrs, range, stop) in
                let subText = (fullString as NSString).substring(with: range)
                if subText.isEmpty { return }
                
                // Get style from attributes
                let font = attrs[.font] as? NSFont ?? NSFont.systemFont(ofSize: 12)
                let color = attrs[.foregroundColor] as? NSColor ?? NSColor.textColor
                
                // Determine styling flags
                let traits = NSFontManager.shared.traits(of: font)
                let isBold = traits.contains(.boldFontMask)
                let isItalic = traits.contains(.italicFontMask)
                
                // Colors to [0-1] RGB
                var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
                color.usingColorSpace(.deviceRGB)?.getRed(&r, green: &g, blue: &b, alpha: &a)
                
                // Split by newlines to handle line_index
                let parts = subText.components(separatedBy: "\n")
                
                for (i, part) in parts.enumerated() {
                    if !part.isEmpty {
                        // Create span for this segment (bbox=0 triggers auto-flow)
                        let span = SpanInfo(
                            id: UUID(),
                            text: part,
                            font: font.fontName,
                            size: Double(font.pointSize),
                            flags: 0,
                            isBold: isBold,
                            isItalic: isItalic,
                            color: [Double(r), Double(g), Double(b)],
                            bbox: [0, 0, 0, 0], 
                            lineIndex: lastLineIndex
                        )
                        newSpans.append(span)
                    }
                    
                    if i < parts.count - 1 {
                        lastLineIndex += 1
                    }
                }
            }
            
            // Dispatch update
            DispatchQueue.main.async {
                self.lastSpans = newSpans // Prevent re-render loop
                self.parent.spans = newSpans
                self.parent.onTextChange?(fullString)
            }
        }
    }
}

#Preview {
    @Previewable @State var spans: [SpanInfo] = [
        SpanInfo(from: ["text": "Hello ", "font": "Helvetica-Bold", "size": 14.0, "is_bold": true, "is_italic": false, "color": [0, 0, 0], "bbox": [0, 0, 50, 20], "line_index": 0]),
        SpanInfo(from: ["text": "World!", "font": "Helvetica", "size": 14.0, "is_bold": false, "is_italic": true, "color": [1, 0, 0], "bbox": [50, 0, 100, 20], "line_index": 0])
    ]
    @Previewable @State var selectedRange = NSRange(location: 0, length: 0)
    
    RichTextEditor(spans: $spans, selectedRange: $selectedRange)
        .frame(width: 400, height: 200)
}
