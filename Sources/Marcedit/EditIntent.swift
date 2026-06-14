//
//  EditIntent.swift
//  Marcedit
//
//  The single adapter between Swift edit-intent values and the Python wire
//  format (Candidate B). Every Python override key string lives here; callers
//  pass typed `ManualOverrides`, never raw key strings. Before this, the same
//  dict was hand-built at multiple call sites, leaking the wire vocabulary
//  across the seam — a backend rename broke several places silently.
//

import Foundation

enum EditIntent {

    /// Keys shared by both the single-line and block replacement paths:
    /// positioning offsets, tracking, and justification. Block replacement
    /// sends only these (it carries per-span fonts, not a single manual_font).
    static func positioningKeys(_ o: ManualOverrides) -> [String: Any] {
        var d: [String: Any] = [
            "manual_size_delta": o.sizeDelta,
            "manual_x_offset": o.xOffset,
            "manual_y_offset": o.yOffset,
            "manual_tracking_delta": o.trackingDelta,
        ]
        if let j = o.justification { d["justification"] = j }
        return d
    }

    /// Full override projection for single-line replacement: the positioning
    /// subset plus font identity, style flags, and per-edit toggles. Keys that
    /// depend on view-model or app context (skip_collision, exhaustive_search)
    /// are layered on by the caller, not derivable from the overrides alone.
    static func replacementWireDict(_ o: ManualOverrides) -> [String: Any] {
        var d = positioningKeys(o)
        // Python reads "manual_font", not "font_name".
        if let f = o.fontName { d["manual_font"] = f }
        if o.isBold { d["is_bold"] = true }
        if o.isItalic { d["is_italic"] = true }
        if o.skipVisualMatching { d["skip_visual_matching"] = true }
        if o.smartQuotes { d["smart_quotes"] = true }
        // Redaction fill: nil = transparent.
        if let fc = o.fillColor { d["fill_color"] = fc }
        return d
    }

    /// Translate a Swift-detected font identifier into Python's manual_font
    /// wire value, or nil when it cannot be expressed. Pure function of the
    /// identifier — no view-model state.
    ///
    /// Accepts:
    ///   - "system|Name"        → a PyMuPDF built-in id ("helv"/"tiro"/…), if known
    ///   - "/path/to.ttf|PSName" → passed through (Python accepts this directly)
    static func manualFont(fromDetected detected: String) -> String? {
        if detected.hasPrefix("system|") {
            let baseName = String(detected.dropFirst("system|".count))
                .components(separatedBy: "-").first ?? ""
            let builtins: [String: String] = [
                "Helvetica": "helv", "Arial": "helv",
                "Times": "tiro",
                "Courier": "cour",
                "Symbol": "symb",
                "ZapfDingbats": "zadb",
            ]
            return builtins[baseName]
        } else if detected.contains("|") {
            return detected
        }
        return nil
    }
}
