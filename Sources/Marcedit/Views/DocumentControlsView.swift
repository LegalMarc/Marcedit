import SwiftUI

struct DocumentControlsView: View {
    @ObservedObject var vm: EditorViewModelV2
    @State private var showingFlattenConfirmation = false
    @State private var showingScrubConfirmation = false
    @State private var showingSecureEraseConfirmation = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Document Controls")
                .font(.headline)
                .foregroundColor(Theme.textColor)
            
            VStack(spacing: 8) {
                // MD5 Checksum
                if let checksum = vm.selectedDocument?.md5Checksum {
                    HStack {
                         Text("MD5:")
                             .font(.caption)
                             .foregroundColor(Theme.secondaryTextColor)
                         Text(checksum)
                             .font(.caption.monospaced())
                             .foregroundColor(Theme.textColor)
                             .lineLimit(1)
                             .truncationMode(.middle)
                             .textSelection(.enabled) // Allow copying
                             .accessibilityIdentifier("MD5ChecksumLabel")
                             .accessibilityLabel("MD5 checksum")
                             .accessibilityValue(checksum)
                         Spacer()
                    }
                    .padding(.horizontal, 4)
                    .help("MD5 Checksum: Verify file integrity bit-for-bit")
                }
                
                // Vector Flatten / Secure Erase Buttons (in row)
                HStack(spacing: 8) {
                    // Vector Flatten Button
                    Button(action: {
                        showingFlattenConfirmation = true
                    }) {
                        HStack(spacing: 6) {
                            Image(systemName: "square.stack.3d.down.forward.fill")
                                .font(.system(size: 16))
                            VStack(spacing: 2) {
                                Text("Vector")
                                Text("Flatten")
                            }
                            .font(.caption)
                            .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 8)
                        .background(Color.red.opacity(0.1))
                        .foregroundColor(.red)
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.red.opacity(0.3), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(vm.selectedDocID == nil)
                    .help("Convert all text to vector shapes (irreversible)")
                    .accessibilityIdentifier("VectorFlattenButton")
                    .accessibilityLabel("Vector Flatten")

                    // Secure Erase Button
                    Button(action: {
                        showingSecureEraseConfirmation = true
                    }) {
                        HStack(spacing: 6) {
                            Image(systemName: "trash.fill")
                                .font(.system(size: 16))
                            VStack(spacing: 2) {
                                Text("Secure")
                                Text("Erase")
                            }
                            .font(.caption)
                            .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 8)
                        .background(Color.purple.opacity(0.1))
                        .foregroundColor(.purple)
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.purple.opacity(0.3), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(vm.selectedDocID == nil)
                    .help("Securely erase all files with 3-pass overwrite - leaves NO trace")
                    .accessibilityIdentifier("SecureEraseButton")
                    .accessibilityLabel("Secure Erase")
                }
                
                // View / Scrub Metadata Buttons (in row)
                HStack(spacing: 8) {
                    // View Metadata Button
                    Button(action: {
                        Task {
                            await vm.viewCurrentDocumentMetadata()
                        }
                    }) {
                        HStack(spacing: 6) {
                            Image(systemName: "magnifyingglass")
                                .font(.system(size: 16))
                            VStack(spacing: 2) {
                                Text("View")
                                Text("Metadata")
                            }
                            .font(.caption)
                            .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 8)
                        .background(Theme.wellColor)
                        .foregroundColor(Theme.textColor)
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Theme.borderColor, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(vm.selectedDocID == nil)
                    .help("View all metadata without modifying the document")
                    .accessibilityIdentifier("ViewMetadataButton")
                    .accessibilityLabel("View Metadata")

                    // Scrub Metadata Button
                    Button(action: {
                        showingScrubConfirmation = true
                    }) {
                        HStack(spacing: 6) {
                            Image(systemName: "eraser.fill")
                                .font(.system(size: 16))
                            VStack(spacing: 2) {
                                Text("Scrub")
                                Text("Metadata")
                            }
                            .font(.caption)
                            .fontWeight(.medium)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 8)
                        .background(Color.orange.opacity(0.1))
                        .foregroundColor(.orange)
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.orange.opacity(0.3), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(vm.selectedDocID == nil)
                    .help("Remove all metadata (irreversible)")
                    .accessibilityIdentifier("ScrubMetadataButton")
                    .accessibilityLabel("Scrub Metadata")
                }
            }
        }
        .padding(12)
        .background(Theme.wellColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Theme.borderColor, lineWidth: 1)
        )
        // Confirmation Dialog: Flatten
        .alert("Vector Flatten Document?", isPresented: $showingFlattenConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Flatten", role: .destructive) {
                Task {
                    await vm.flattenCurrentDocument()
                }
            }
        } message: {
            Text("This will convert all text to vector outlines.\n\nThe document will no longer be editable as text, but will look identical and be print-ready.\n\nThis action cannot be undone.")
        }
        // Confirmation Dialog: Scrub
        .alert("Scrub Metadata?", isPresented: $showingScrubConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Scrub", role: .destructive) {
                Task {
                    await vm.scrubCurrentDocument()
                }
            }
        } message: {
            Text("This will remove all standard metadata (Title, Author, etc.), XMP data, and perform a deep clean of the file structure.\n\nThis action cannot be undone.")
        }
        // Confirmation Dialog: Secure Erase
        .alert("Permanently Delete Original File?", isPresented: $showingSecureEraseConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete Permanently", role: .destructive) {
                Task {
                    await vm.secureEraseCurrentDocument()
                }
            }
        } message: {
            let path = vm.selectedDocument?.originalURL.path ?? "the selected file"
            Text("This will permanently delete:\n\n\(path)\n\n…along with any modified copies, temp files, and scrub reports.\n\nNote: On APFS / SSD, overwrite passes cannot guarantee that original data blocks are physically zeroed. For at-rest protection, use FileVault.\n\nThis action cannot be undone.")
        }
        // Menu command receivers (Document menu bar items)
        .onReceive(NotificationCenter.default.publisher(for: .menuVectorFlatten)) { _ in
            guard vm.selectedDocID != nil else { return }
            showingFlattenConfirmation = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuViewMetadata)) { _ in
            guard vm.selectedDocID != nil else { return }
            Task { await vm.viewCurrentDocumentMetadata() }
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuScrubMetadata)) { _ in
            guard vm.selectedDocID != nil else { return }
            showingScrubConfirmation = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .menuSecureErase)) { _ in
            guard vm.selectedDocID != nil else { return }
            showingSecureEraseConfirmation = true
        }
    }
}
