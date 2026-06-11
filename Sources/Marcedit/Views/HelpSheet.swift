
import SwiftUI

struct HelpSheet: View {
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Keyboard Shortcuts")
                    .font(.headline)
                Spacer()
                Button(action: { dismiss() }) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding()
            .background(Theme.secondaryColor)
            
            Divider()
            
            // Content
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    
                    SectionView(title: "General", items: [
                        ("⌘O", "Open PDF"),
                        ("⌘W", "Close Document"),
                        ("⌘S", "Save Changes"),
                        ("⌘Z", "Undo"),
                        ("⇧⌘Z", "Redo")
                    ])
                    
                    SectionView(title: "Editing", items: [
                        ("Double Click", "Edit Line (or Paragraph)"),
                        ("Option + Click", "Force Word Selection"),
                        ("Esc", "Clear Selection / Cancel Edit")
                    ])
                    
                    SectionView(title: "Nudge (Edit Mode)", items: [
                        ("Arrow Keys", "Move Text (X/Y)"),
                        ("Shift + Arrows", "Resize Text Area"),
                        ("Option + Arrows", "Adjust Kerning")
                    ])
                    
                    SectionView(title: "View", items: [
                        ("⌘+", "Zoom In"),
                        ("⌘-", "Zoom Out"),
                        ("⌘0", "Fit to Page"),
                        ("Space", "Pan Tool (Hold)")
                    ])
                }
                .padding()
            }
        }
        .frame(width: 400, height: 500)
        .background(Theme.backgroundColor)
        .cornerRadius(12)
    }
}

struct SectionView: View {
    let title: String
    let items: [(String, String)]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(Theme.accentColor)
            
            Grid(alignment: .leading, horizontalSpacing: 20, verticalSpacing: 6) {
                ForEach(items, id: \.0) { item in
                    GridRow {
                        Text(item.0)
                            .font(.system(.body, design: .monospaced))
                            .fontWeight(.bold)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.1))
                            .cornerRadius(4)
                        
                        Text(item.1)
                            .foregroundColor(Theme.textColor)
                    }
                }
            }
        }
    }
}
