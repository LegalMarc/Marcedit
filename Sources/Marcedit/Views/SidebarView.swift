import SwiftUI
import UniformTypeIdentifiers

struct SidebarView: View {
    @ObservedObject var vm: EditorViewModelV2
    @State private var isTargeted = false
    
    var body: some View {
        VStack(spacing: 0) {
            // File List (always visible, may be empty)
            ScrollView {
                VStack(spacing: 2) {
                    ForEach(vm.documents) { doc in
                        FileRow(doc: doc, isSelected: vm.selectedDocID == doc.id, vm: vm)
                    }
                }
                .padding(.horizontal, 4)
                .padding(.top, 8)  // Add top spacing from card edge
            }
            .frame(maxHeight: .infinity)
            .accessibilityIdentifier("FileList")
            
            // Add PDF Button / Drop Zone
            Button(action: { vm.showFileImporter = true }) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(isTargeted ? Theme.accentColor.opacity(0.2) : Theme.wellColor)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(
                                    isTargeted ? Theme.accentColor : Theme.borderColor,
                                    style: StrokeStyle(lineWidth: 1.5, dash: [6, 4])
                                )
                        )
                    
                    VStack(spacing: 6) {
                        Image(systemName: "plus.circle.fill")
                            .font(.title2)
                            .foregroundColor(Theme.accentColor)
                        Text("Add PDF")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(Theme.textColor)
                        Text("Browse or Drop")
                            .font(.caption2)
                            .foregroundColor(Theme.secondaryTextColor)
                    }
                }
                .frame(height: 80)
                .contentShape(Rectangle())
                .onDrop(of: [UTType.pdf], isTargeted: $isTargeted) { providers in
                    vm.handleDrop(providers: providers)
                }
            }
            .buttonStyle(.plain)
            .focusable(false)
            .padding(12)
            .accessibilityIdentifier("AddPDFButton")
            .accessibilityLabel("Add PDF file")
            

        }
        .frame(minWidth: 220)
        // Background handled by parent card
    }
    
}

struct FileRow: View {
    let doc: DocumentFile
    let isSelected: Bool
    @ObservedObject var vm: EditorViewModelV2
    
    var body: some View {
        HStack {
            // Icon
            Image(systemName: "doc.text.fill")
                .foregroundColor(isSelected ? Theme.accentColor : .secondary)
            
            // Name
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(doc.name)
                        .lineLimit(3)
                        .truncationMode(.middle)
                        .fixedSize(horizontal: false, vertical: true)
                        .fontWeight(isSelected ? .medium : .regular)
                        .foregroundColor(isSelected ? Theme.accentColor : Theme.textColor)
                        .help(doc.name)
                    
                    if doc.isDirty {
                        Circle()
                            .fill(Color.orange)
                            .frame(width: 6, height: 6)
                            .help("Unsaved Changes")
                    }
                }
            }

            
            Spacer()
            
            // Actions
            if isSelected { // Only show actions on hover/select, dirty state is shown via dot
                HStack(spacing: 6) {
                    // Revert
                    Button(action: { vm.revertFile(doc.id) }) {
                        Image(systemName: "arrow.uturn.backward")
                            .font(.caption)
                    }
                    .buttonStyle(.borderless)
                    .disabled(!doc.isDirty)
                    .help("Revert to Original")
                    .accessibilityIdentifier("FileRow_Revert_\(doc.id.uuidString)")
                    .accessibilityLabel("Revert \(doc.name)")

                    // Save (Overwrite)
                    Button(action: { vm.saveFile(doc.id) }) {
                        Image(systemName: "square.and.arrow.down")
                            .font(.caption)
                    }
                    .buttonStyle(.borderless)
                    .disabled(!doc.isDirty)
                    .help("Save (Overwrite)")
                    .accessibilityIdentifier("FileRow_Save_\(doc.id.uuidString)")
                    .accessibilityLabel("Save \(doc.name)")

                    // Save As (Export)
                    Button(action: { vm.exportFile(doc.id) }) {
                        Image(systemName: "square.and.arrow.up")
                            .font(.caption)
                    }
                    .buttonStyle(.borderless)
                    .help("Save As Copy...")
                    .accessibilityIdentifier("FileRow_SaveAs_\(doc.id.uuidString)")
                    .accessibilityLabel("Save As \(doc.name)")

                    // Close
                    Button(action: { vm.closeFile(doc.id) }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.borderless)
                    .help("Close File")
                    .accessibilityIdentifier("FileRow_Close_\(doc.id.uuidString)")
                    .accessibilityLabel("Close \(doc.name)")
                }
            }
        }
        .padding(8)
        .background(isSelected ? Theme.accentColor.opacity(0.1) : Color.clear)
        .cornerRadius(6)
        .padding(.horizontal, 4)
        .contentShape(Rectangle()) // Make full row clickable
        .onTapGesture {
            vm.selectFile(doc.id)
        }
        .contextMenu {
            Button("Save Changes") { vm.saveFile(doc.id) }
                .disabled(!doc.isDirty)
            Button("Save As...") { vm.exportFile(doc.id) }
            Button("Revert to Original") { vm.revertFile(doc.id) }
                .disabled(!doc.isDirty)
            Divider()
            Button("Reveal in Finder") { vm.revealInFinder(doc.id) }
            Divider()
            Button("Close Document") { vm.closeFile(doc.id) }
        }
        .accessibilityIdentifier("FileRow_\(doc.id.uuidString)")
        .accessibilityLabel("PDF file: \(doc.name)")
    }
}
