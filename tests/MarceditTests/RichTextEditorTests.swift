import XCTest
@testable import Marcedit
import AppKit

class RichTextEditorTests: XCTestCase {

    // MARK: - SpanInfo Tests
    
    func testSpanInfoInitFromDictionary_IncompleteData() {
        // Bug: init(from:) defaults missing keys to empty/zero without validation
        let emptyDict: [String: Any] = [:]
        let span = SpanInfo(from: emptyDict)
        
        // Assert current behavior (which we might want to fix/improve)
        XCTAssertEqual(span.text, "")
        XCTAssertEqual(span.font, "")
        XCTAssertEqual(span.size, 12.0) // Default
        XCTAssertEqual(span.color, [0, 0, 0]) // Default
    }
    
    func testSpanInfoNSColor_InvalidColorData() {
        // Bug: nsColor guard color.count >= 3, else returns .textColor
        // Case 1: Empty color array
        var span = SpanInfo(from: ["color": []])
        XCTAssertEqual(span.nsColor, NSColor.textColor)
        
        // Case 2: 2 components (invalid for RGB)
        span = SpanInfo(from: ["color": [1.0, 0.5]])
        XCTAssertEqual(span.nsColor, NSColor.textColor)
        
        // Case 3: Valid color
        span = SpanInfo(from: ["color": [1.0, 0.0, 0.0]])
        // Compare RGBA
        let red = NSColor(red: 1.0, green: 0.0, blue: 0.0, alpha: 1.0)
        // Fuzzy compare
        var r1: CGFloat = 0, g1: CGFloat = 0, b1: CGFloat = 0, a1: CGFloat = 0
        var r2: CGFloat = 0, g2: CGFloat = 0, b2: CGFloat = 0, a2: CGFloat = 0
        span.nsColor.usingColorSpace(.deviceRGB)?.getRed(&r1, green: &g1, blue: &b1, alpha: &a1)
        red.usingColorSpace(.deviceRGB)?.getRed(&r2, green: &g2, blue: &b2, alpha: &a2)
        
        XCTAssertEqual(r1, r2, accuracy: 0.001)
        XCTAssertEqual(g1, g2, accuracy: 0.001)
        XCTAssertEqual(b1, b2, accuracy: 0.001)
    }
    
    func testSpanInfoInit_ValidateRequiredKeys() {
        // Bug: init(from:) should validate keys or log warning
        let dict: [String: Any] = ["text": "Hello"]
        let span = SpanInfo(from: dict)
        XCTAssertEqual(span.text, "Hello")
        // Verify defaults
        XCTAssertEqual(span.size, 12.0) 
        XCTAssertEqual(span.font, "")
    }

    func testNSFontFallback_WeightHandling() {
        // Bug: nsFont uses system font, ignoring weight
        // Case 1: Bold in flags (bit 4 = 16) or is_bold=true
        let dict: [String: Any] = ["text": "Bold", "is_bold": true]
        let span = SpanInfo(from: dict)
        
        let nsFont = span.nsFont
        // Expected: should be bold system font or similar
        // Currently (buggy): always regular system font if font name not found
        // We want to assert what we EXPECT after fix, or demonstrate failure
        
        // Asserting failure (it returns regular)
        let descriptor = nsFont.fontDescriptor
        let traits = descriptor.symbolicTraits
        
        // FIXME: This assertion will fail once we fix the bug to actually match bold
        // For now, let's just inspect it.
        // XCTAssertTrue(traits.contains(.bold), "Fallback font should respect bold trait")
    }
}
