
import SwiftUI

struct ZoomControls: View {
    @State private var hover = false
    
    var body: some View {
        HStack(spacing: 0) {
            // Zoom Out
            Button(action: {
                NotificationCenter.default.post(name: .zoomOut, object: nil)
            }) {
                Image(systemName: "minus.magnifyingglass")
                    .font(.system(size: 14))
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Zoom Out (Cmd -)")
            .accessibilityIdentifier("ZoomOutButton")
            
            Divider().frame(height: 18)
            
            // Zoom In
            Button(action: {
                NotificationCenter.default.post(name: .zoomIn, object: nil)
            }) {
                Image(systemName: "plus.magnifyingglass")
                    .font(.system(size: 14))
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Zoom In (Cmd +)")
            .accessibilityIdentifier("ZoomInButton")
            
            Divider().frame(height: 18)
            
            // Fit Page
            Button(action: {
                NotificationCenter.default.post(name: .zoomFit, object: nil)
            }) {
                Image(systemName: "arrow.up.left.and.arrow.down.right.circle")
                    .font(.system(size: 14))
                    .frame(width: 32, height: 32)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Fit to Window (Cmd 0)")
            .accessibilityIdentifier("ZoomFitButton")
        }
        .background(.regularMaterial)
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.15), radius: 4, x: 0, y: 2)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.white.opacity(0.2), lineWidth: 0.5)
        )
        .onHover { isHovering in
            withAnimation(.easeInOut(duration: 0.2)) {
                self.hover = isHovering
            }
        }
        .scaleEffect(hover ? 1.02 : 1.0)
    }
}
