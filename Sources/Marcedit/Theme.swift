import SwiftUI
import AppKit

struct Theme {
    // Use NSColor system colors that automatically adapt to appearance
    
    static var backgroundColor: Color {
        Color(nsColor: makeAdaptiveColor(
            light: NSColor(red: 0.941, green: 0.957, blue: 0.973, alpha: 1.0),  // #F0F4F8 - soft blue-gray
            dark: NSColor.windowBackgroundColor
        ))
    }
    
    static var secondaryColor: Color {
        Color(nsColor: makeAdaptiveColor(
            light: NSColor(red: 0.929, green: 0.941, blue: 0.957, alpha: 1.0),  // #EDEFEF4 - slightly darker
            dark: NSColor.controlBackgroundColor
        ))
    }
    
    static var cardColor: Color {
        Color(nsColor: makeAdaptiveColor(
            light: NSColor.white,  // Pure white cards stand out against blue-gray bg
            dark: NSColor(red: 0.17, green: 0.17, blue: 0.20, alpha: 1.0)
        ))
    }
    
    static var wellColor: Color {
        Color(nsColor: makeAdaptiveColor(
            light: NSColor(red: 0.910, green: 0.929, blue: 0.953, alpha: 1.0),  // #E8EDF3 - drop zone well
            dark: NSColor(red: 0.13, green: 0.13, blue: 0.16, alpha: 1.0)
        ))
    }
    
    static var accentColor: Color {
        Color(red: 0.29, green: 0.56, blue: 0.89) // #4A90E2
    }
    
    static var textColor: Color {
        Color(NSColor.labelColor)
    }
    
    static var secondaryTextColor: Color {
        Color(NSColor.secondaryLabelColor)
    }
    
    static var borderColor: Color {
        Color(nsColor: makeAdaptiveColor(
            light: NSColor(red: 0.85, green: 0.87, blue: 0.90, alpha: 1.0),  // Softer border
            dark: NSColor(white: 0.35, alpha: 1.0)
        ))
    }
    
    // Helper to create adaptive NSColor
    private static func makeAdaptiveColor(light: NSColor, dark: NSColor) -> NSColor {
        NSColor(name: nil) { appearance in
            if appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua {
                return dark
            } else {
                return light
            }
        }
    }
}

extension View {
    func withAppTheme() -> some View {
        self.background(Theme.backgroundColor)
    }
    
    func cardStyle() -> some View {
        self
            .background(Theme.cardColor)
            .cornerRadius(16)
            .shadow(color: Color.black.opacity(0.1), radius: 5, x: 0, y: 2)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Theme.borderColor.opacity(0.3), lineWidth: 1)
            )
    }
}
