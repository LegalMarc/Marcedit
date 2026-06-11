import SwiftUI

/// macOS-style 144-color palette picker
struct ColorPalettePopover: View {
    @Binding var selectedColorId: String?
    var onSelect: () -> Void
    @Environment(\.dismiss) private var dismiss
    
    // 12 columns × 12 rows = 144 colors (matching macOS standard)
    // Organized: red, orange, yellow, green, cyan, blue, purple, magenta, brown, then grays
    private static let paletteData: [[ColorEntry]] = generateMacOSPalette()
    
    var body: some View {
        VStack(spacing: 8) {
            // Transparent option at top
            Button(action: {
                selectedColorId = nil
                onSelect()
                dismiss()
            }) {
                HStack {
                    Image(systemName: "circle.dotted")
                        .frame(width: 16, height: 16)
                    Text("Transparent")
                        .font(.caption)
                    Spacer()
                    if selectedColorId == nil {
                        Image(systemName: "checkmark")
                            .font(.caption)
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            
            Divider()
            
            // Color grid
            VStack(spacing: 1) {
                ForEach(0..<12, id: \.self) { row in
                    HStack(spacing: 1) {
                        ForEach(0..<12, id: \.self) { col in
                            let entry = Self.paletteData[row][col]
                            Button(action: {
                                selectedColorId = entry.id
                                onSelect()
                                dismiss()
                            }) {
                                Rectangle()
                                    .fill(entry.color)
                                    .frame(width: 18, height: 18)
                                    .overlay(
                                        Rectangle()
                                            .stroke(selectedColorId == entry.id ? Color.white : Color.clear, lineWidth: 2)
                                    )
                                    .overlay(
                                        Rectangle()
                                            .stroke(Color.black.opacity(0.15), lineWidth: 0.5)
                                    )
                            }
                            .buttonStyle(.plain)
                            .help(entry.name)
                        }
                    }
                }
            }
            .padding(4)
            .background(Color(white: 0.95))
            .cornerRadius(4)
        }
        .padding(8)
        .frame(width: 240)
    }
    
    /// Convert color ID to SwiftUI Color
    static func colorForId(_ id: String?) -> Color? {
        guard let id = id else { return nil }
        for row in paletteData {
            if let entry = row.first(where: { $0.id == id }) {
                return entry.color
            }
        }
        return nil
    }
    
    /// Get display name for color ID
    static func nameForId(_ id: String?) -> String {
        guard let id = id else { return "Transparent" }
        for row in paletteData {
            if let entry = row.first(where: { $0.id == id }) {
                return entry.name
            }
        }
        return id.capitalized
    }
    
    struct ColorEntry: Identifiable {
        let id: String
        let name: String
        let color: Color
        let rgb: (Double, Double, Double)
    }
    
    /// Generate the 144-color macOS-style palette
    private static func generateMacOSPalette() -> [[ColorEntry]] {
        var palette: [[ColorEntry]] = []
        
        // Base hues matching macOS layout (12 columns)
        // Each column is a hue family, rows go from saturated/dark to light/pastel
        let hueColumns: [(String, Double)] = [
            ("red", 0.0),
            ("orange", 30.0),
            ("yellow", 55.0),
            ("chartreuse", 80.0),
            ("green", 120.0),
            ("spring", 150.0),
            ("cyan", 180.0),
            ("azure", 210.0),
            ("blue", 240.0),
            ("purple", 270.0),
            ("magenta", 300.0),
            ("rose", 330.0),
        ]
        
        // 12 rows: vary saturation and brightness
        for row in 0..<12 {
            var rowEntries: [ColorEntry] = []
            
            for (_, (hueName, hue)) in hueColumns.enumerated() {
                let (s, b) = saturationBrightnessForRow(row)
                let color = Color(hue: hue / 360.0, saturation: s, brightness: b)
                
                // Convert to RGB for Python backend
                let rgb = hsbToRgb(h: hue / 360.0, s: s, b: b)
                
                // Create unique ID
                let id = "\(hueName)_\(row)"
                let name = colorNameForPosition(hueName: hueName, row: row)
                
                rowEntries.append(ColorEntry(id: id, name: name, color: color, rgb: rgb))
            }
            
            palette.append(rowEntries)
        }
        
        return palette
    }
    
    /// Get saturation and brightness for each row (0 = darkest, 11 = lightest)
    private static func saturationBrightnessForRow(_ row: Int) -> (Double, Double) {
        switch row {
        case 0: return (1.0, 0.4)   // Dark saturated
        case 1: return (1.0, 0.5)
        case 2: return (1.0, 0.6)
        case 3: return (1.0, 0.7)
        case 4: return (1.0, 0.8)
        case 5: return (1.0, 0.9)   // Bright saturated
        case 6: return (0.8, 0.95)
        case 7: return (0.6, 0.95)
        case 8: return (0.4, 0.95)
        case 9: return (0.25, 0.98) // Pastel
        case 10: return (0.12, 1.0) // Very light
        case 11: return (0.05, 1.0) // Nearly white tint
        default: return (1.0, 0.5)
        }
    }
    
    /// Human-readable name based on position
    private static func colorNameForPosition(hueName: String, row: Int) -> String {
        let intensity: String
        switch row {
        case 0...2: intensity = "Dark"
        case 3...5: intensity = ""
        case 6...8: intensity = "Light"
        case 9...11: intensity = "Pale"
        default: intensity = ""
        }
        
        let base = hueName.capitalized
        return intensity.isEmpty ? base : "\(intensity) \(base)"
    }
    
    /// Convert HSB to RGB
    private static func hsbToRgb(h: Double, s: Double, b: Double) -> (Double, Double, Double) {
        let c = b * s
        let x = c * (1 - abs((h * 6).truncatingRemainder(dividingBy: 2) - 1))
        let m = b - c
        
        var r: Double, g: Double, bb: Double
        
        let segment = Int(h * 6) % 6
        switch segment {
        case 0: (r, g, bb) = (c, x, 0)
        case 1: (r, g, bb) = (x, c, 0)
        case 2: (r, g, bb) = (0, c, x)
        case 3: (r, g, bb) = (0, x, c)
        case 4: (r, g, bb) = (x, 0, c)
        case 5: (r, g, bb) = (c, 0, x)
        default: (r, g, bb) = (0, 0, 0)
        }
        
        return (r + m, g + m, bb + m)
    }
}

// MARK: - Updated FontOverrideControls

struct FontOverrideControls: View {
    @ObservedObject var vm: EditorViewModelV2
    var onOverride: () -> Void
    @State private var showColorPicker = false
    
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
             // Font Column
             VStack(alignment: .leading, spacing: 4) {
                 Text("Override Font")
                     .font(.caption).bold()
                     .foregroundColor(.secondary)
                 
                 // PHASE 4: Font cycling with prev/next arrows
                 HStack(spacing: 2) {
                     // Previous font button
                     Button(action: { cycleFontSelection(direction: -1) }) {
                         Image(systemName: "chevron.left")
                             .frame(width: 20, height: 20)
                     }
                     .buttonStyle(.borderless)
                     .disabled(vm.availableFonts.isEmpty)
                     .help("Previous font match")
                     .accessibilityIdentifier("FontPreviousButton")
                     
                     Menu {
                         Button(action: {
                             vm.manualOverrides.fontName = nil
                             onOverride()
                         }) {
                             HStack {
                                 Text(autoDetectLabel)
                                 if vm.manualOverrides.fontName == nil { Image(systemName: "checkmark") }
                             }
                         }
                         Divider()
                         ForEach(vm.availableFonts, id: \.self) { font in
                             Button(action: {
                                 vm.manualOverrides.fontName = font["id"]
                                 onOverride()
                             }) {
                                 HStack {
                                     Text(font["name"] ?? "Unknown").font(fontFromID(font["id"]))
                                     if vm.manualOverrides.fontName == font["id"] { Image(systemName: "checkmark") }
                                 }
                             }
                         }
                     } label: {
                         HStack {
                             Text(selectedFontDisplayName)
                                 .lineLimit(1)
                                 .foregroundColor(vm.manualOverrides.fontName == nil ? .secondary : .primary)
                                 .font(fontFromID(vm.manualOverrides.fontName))
                             Spacer()
                             Image(systemName: "chevron.down")
                         }
                         .padding(4)
                         .background(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.2), lineWidth: 1))
                     }
                     .frame(maxWidth: .infinity)
                     .buttonStyle(.plain)
                     .accessibilityIdentifier("FontMenuButton")

                     // Next font button
                     Button(action: { cycleFontSelection(direction: 1) }) {
                         Image(systemName: "chevron.right")
                             .frame(width: 20, height: 20)
                     }
                     .buttonStyle(.borderless)
                     .disabled(vm.availableFonts.isEmpty)
                     .help("Next font match")
                     .accessibilityIdentifier("FontNextButton")
                 }
             }
             
             // Style Column
             VStack(alignment: .leading, spacing: 4) {
                 Text("Override Style")
                     .font(.caption).bold()
                     .foregroundColor(.secondary)
                 
                 Menu {
                     Button(action: {
                         vm.manualOverrides.fontStyle = nil
                         onOverride()
                     }) {
                         HStack {
                             Text("Use Auto-Detected")
                             if vm.manualOverrides.fontStyle == nil { Image(systemName: "checkmark") }
                         }
                     }
                     Divider()
                     ForEach(["Regular", "Bold", "Italic", "Bold Italic"], id: \.self) { style in
                         Button(action: {
                             vm.manualOverrides.fontStyle = style
                             onOverride()
                         }) {
                             HStack {
                                 Text(style)
                                 if vm.manualOverrides.fontStyle == style { Image(systemName: "checkmark") }
                             }
                         }
                     }
                 } label: {
                     HStack {
                         Text(vm.manualOverrides.fontStyle ?? "Auto-Detect")
                             .foregroundColor(vm.manualOverrides.fontStyle == nil ? .secondary : .primary)
                             .frame(maxWidth: .infinity, alignment: .leading)
                         Image(systemName: "chevron.down")
                     }
                     .padding(4)
                     .background(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.2), lineWidth: 1))
                 }
                 .frame(maxWidth: .infinity)
                 .buttonStyle(.plain)
                 .accessibilityIdentifier("StyleMenuButton")
             }

             // Fill Color Column - Using popover for grid picker
             VStack(alignment: .leading, spacing: 4) {
                 Text("Fill Color")
                     .font(.caption).bold()
                     .foregroundColor(.secondary)
                 
                 Button(action: {
                     showColorPicker.toggle()
                 }) {
                     HStack {
                         if let fillId = vm.manualOverrides.fillColor,
                            let color = ColorPalettePopover.colorForId(fillId) {
                             RoundedRectangle(cornerRadius: 2)
                                 .fill(color)
                                 .frame(width: 16, height: 16)
                                 .overlay(RoundedRectangle(cornerRadius: 2).stroke(Color.gray.opacity(0.5), lineWidth: 0.5))
                             Text(ColorPalettePopover.nameForId(fillId))
                                 .foregroundColor(.primary)
                                 .lineLimit(1)
                         } else {
                             Image(systemName: "circle.dotted")
                                 .frame(width: 16, height: 16)
                             Text("Transparent")
                                 .foregroundColor(.secondary)
                         }
                         Spacer()
                         Image(systemName: "chevron.down")
                     }
                     .padding(4)
                     .background(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.2), lineWidth: 1))
                 }
                 .buttonStyle(.plain)
                 .accessibilityIdentifier("ColorPickerButton")
                 .popover(isPresented: $showColorPicker) {
                     ColorPalettePopover(
                         selectedColorId: $vm.manualOverrides.fillColor,
                         onSelect: onOverride
                     )
                 }
             }

             // Justification Column
             VStack(alignment: .leading, spacing: 4) {
                 Text("Justify")
                     .font(.caption).bold()
                     .foregroundColor(.secondary)
                 
                 Menu {
                     Button(action: {
                         vm.manualOverrides.justification = nil
                         onOverride()
                     }) {
                         HStack {
                             Text("Auto-Detect")
                             if vm.manualOverrides.justification == nil { Image(systemName: "checkmark") }
                         }
                     }
                     Divider()
                     ForEach(["left", "center", "right", "justified"], id: \.self) { justify in
                         Button(action: {
                             vm.manualOverrides.justification = justify
                             onOverride()
                         }) {
                             HStack {
                                 Image(systemName: justificationIcon(justify))
                                 Text(justify.capitalized)
                                 if vm.manualOverrides.justification == justify { Image(systemName: "checkmark") }
                             }
                         }
                     }
                 } label: {
                     HStack {
                         if let justify = vm.manualOverrides.justification {
                             Image(systemName: justificationIcon(justify))
                             Text(justify.capitalized)
                                 .foregroundColor(.primary)
                         } else {
                             Text("Auto")
                                 .foregroundColor(.secondary)
                         }
                         Spacer()
                         Image(systemName: "chevron.down")
                     }
                     .padding(4)
                     .background(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.2), lineWidth: 1))
                 }
                 .frame(maxWidth: .infinity)
                 .buttonStyle(.plain)
                 .accessibilityIdentifier("JustificationMenuButton")
             }
         }
    }
    
    // Helper for Auto-Detect label
    private var autoDetectLabel: String {
        return "Use Auto-Detected"
    }
    
    // Display name for the override font picker
    private var selectedFontDisplayName: String {
        if let id = vm.manualOverrides.fontName {
            // User has selected an override font
            if let font = vm.availableFonts.first(where: { $0["id"] == id }) {
                return font["name"] ?? id
            }
            // ID exists but not in list - show filename portion
            return NSString(string: id).lastPathComponent
        }
        // No override set - show placeholder
        return autoDetectLabel
    }
    
    // Helper to resolve font from ID "path|ps_name" or built-in name
    private func fontFromID(_ id: String?) -> Font? {
        guard let id = id else { return nil }
        
        // Handle path|ps_name format (system fonts)
        let parts = id.components(separatedBy: "|")
        if parts.count >= 2 {
            // Use PostScript name for accurate system rendering
            return Font.custom(parts[1], size: 14)
        }
        
        // Handle built-in fonts by mapping to system equivalents
        switch id.lowercased() {
        case "helv", "helvetica":
            return Font.custom("Helvetica", size: 14)
        case "tiro", "times":
            return Font.custom("Times-Roman", size: 14)
        case "cour", "courier":
            return Font.custom("Courier", size: 14)
        default:
            // Attempt to use ID as font name directly
            return Font.custom(id, size: 14)
        }
    }
    
    // PHASE 4: Cycle through available fonts with prev/next arrows
    private func cycleFontSelection(direction: Int) {
        guard !vm.availableFonts.isEmpty else { return }
        
        // Current index in the font list (-1 if "Auto-Detect" selected)
        let currentIndex: Int
        if let currentId = vm.manualOverrides.fontName {
            currentIndex = vm.availableFonts.firstIndex(where: { $0["id"] == currentId }) ?? -1
        } else {
            currentIndex = -1  // Auto-Detect is at position -1
        }
        
        // Calculate new index with wrap-around
        // -1 = Auto-Detect, 0..N-1 = fonts in list
        let totalOptions = vm.availableFonts.count + 1  // +1 for Auto-Detect
        let newIndex = (currentIndex + 1 + direction + totalOptions) % totalOptions - 1
        
        if newIndex < 0 {
            // Back to Auto-Detect
            vm.manualOverrides.fontName = nil
        } else {
            // Select font at new index
            vm.manualOverrides.fontName = vm.availableFonts[newIndex]["id"]
        }
        
        onOverride()  // Trigger preview update
    }
    
    // Helper for justification SF Symbol icons
    private func justificationIcon(_ type: String) -> String {
        switch type {
        case "left": return "text.alignleft"
        case "center": return "text.aligncenter"
        case "right": return "text.alignright"
        case "justified": return "text.justify"
        default: return "text.alignleft"
        }
    }
}
