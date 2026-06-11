
import SwiftUI
import PDFKit
import UniformTypeIdentifiers

// MARK: - Main View
struct ContentView: View {
    @StateObject private var vm = EditorViewModelV2()

    // Shortcuts State
    @FocusState private var isSidebarFocused: Bool
    
    // Resizable left panel
    @State private var leftPanelWidth: CGFloat = 280
    @State private var isSidebarCollapsed: Bool = false
    @GestureState private var dragOffset: CGFloat = 0
    private let minLeftPanelWidth: CGFloat = 220
    private let maxLeftPanelWidth: CGFloat = 450
    
    // New UX States
    @State private var showHelpSheet = false
    @State private var isDragTargeted = false
    @State private var showToast = false
    @State private var toastMessage = ""
    @State private var toastType: ToastType = .info
    @State private var toastDismissTask: Task<Void, Never>?
    
    // Global Preferences
    @AppStorage("pdfAppearance") private var pdfAppearance: String = "auto"
    @Environment(\.colorScheme) private var colorScheme
    
    enum ToastType { case info, error, success, warning }
    
    // Computed property: Determining effective PDF dark mode
    private var isPDFDarkMode: Bool {
        switch pdfAppearance {
        case "light": return false
        case "dark": return true
        default: return colorScheme == .dark
        }
    }
    
    var body: some View {
        innerBody
            .onChange(of: vm.errorMessage) { _, msg in
                if let msg { presentToast(msg, type: .error, dismissAfterNS: 4_000_000_000) { vm.errorMessage = nil } }
            }
            .onChange(of: vm.scrubWarningMessage) { _, msg in
                if let msg { presentToast(msg, type: .warning, dismissAfterNS: 5_000_000_000) { vm.scrubWarningMessage = nil } }
            }
            .sheet(isPresented: $showHelpSheet) { HelpSheet() }
            .onAppear { vm.registerTerminationHandler() }
            .onReceive(NotificationCenter.default.publisher(for: .menuOpenPDF)) { _ in vm.showFileImporter = true }
            .onReceive(NotificationCenter.default.publisher(for: .menuToggleHelp)) { _ in showHelpSheet.toggle() }
            .environmentObject(vm)
            .focusedSceneValue(\.sidebarCollapsed, $isSidebarCollapsed)
    }

    // Extracted to break the modifier chain for the Swift type-checker.
    private var innerBody: some View {
        Group {
            HStack(spacing: 0) {
                leftColumn
                resizableDivider
                ZStack {
                    mainContent
                    processingOverlay
                    overlays
                }
                .cardStyle()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .padding(16)
            .background(Theme.backgroundColor)
        }
        .frame(minWidth: 900, minHeight: 600)
        .onDrop(of: [UTType.pdf], isTargeted: nil) { providers in
            vm.handleDrop(providers: providers)
        }
        .fileImporter(isPresented: $vm.showFileImporter, allowedContentTypes: [.pdf], allowsMultipleSelection: true) { result in
            switch result {
            case .success(let urls): vm.add(urls: urls)
            case .failure(let error): vm.errorMessage = error.localizedDescription
            }
        }
        .background(shortcutsView)
        .alert(vm.closeActionType == .quit ? "Quit Application?" : "Close Document?",
               isPresented: $vm.showUnsavedAlert) {
            Button("Cancel", role: .cancel) {}
            Button(vm.closeActionType == .quit ? "Quit Anyway" : "Discard Changes",
                   role: .destructive) { vm.quitAnyway() }
            .keyboardShortcut(.defaultAction)
        } message: {
            Text(vm.closeActionType == .quit
                 ? "You have unsaved changes. Do you really want to quit?"
                 : "You have unsaved changes. Do you really want to close this document?")
        }
        .background(invisibleCloseButton)
    }
}

// MARK: - Helpers
extension ContentView {
    private func presentToast(_ message: String, type: ToastType, dismissAfterNS: UInt64 = 4_000_000_000, onDismiss: @escaping @MainActor () -> Void = {}) {
        toastType = type
        toastMessage = message
        withAnimation { showToast = true }
        toastDismissTask?.cancel()
        toastDismissTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: dismissAfterNS)
            guard !Task.isCancelled else { return }
            if showToast && toastType == type {
                withAnimation { showToast = false }
                onDismiss()
            }
        }
    }
}

// MARK: - Subviews
extension ContentView {
    
    private var leftColumn: some View {
        HStack(spacing: 0) {
            if !isSidebarCollapsed {
                VStack(spacing: 16) {
                    SidebarView(vm: vm)
                        .cardStyle()
                        .frame(minHeight: 200, maxHeight: .infinity)
                    
                    FontControlPanel(vm: vm)
                        .padding(.top, 0)
                        .cardStyle()
                        .frame(minHeight: 250)
                        
                    DocumentControlsView(vm: vm)
                        .padding(.top, 0)
                        .cardStyle()
                        .frame(minHeight: 150)
                }
                .frame(width: min(max(leftPanelWidth + dragOffset, minLeftPanelWidth), maxLeftPanelWidth))
                .padding(.trailing, 8)
                .transition(.move(edge: .leading))
            }
        }
    }
    
    private var resizableDivider: some View {
        Rectangle()
            .fill(Color.clear)
            .frame(width: 8)
            .contentShape(Rectangle())
            .onHover { hovering in
                if hovering { NSCursor.resizeLeftRight.push() }
                else { NSCursor.pop() }
            }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .updating($dragOffset) { value, state, _ in
                        state = value.translation.width
                    }
                    .onEnded { value in
                        leftPanelWidth = min(max(leftPanelWidth + value.translation.width, minLeftPanelWidth), maxLeftPanelWidth)
                    }
            )
            .overlay(
                Rectangle()
                    .fill(Theme.borderColor.opacity(0.5))
                    .frame(width: 1)
            )
    }
    
    private var mainContent: some View {
        Group {
            if let _ = vm.selectedPDF {
                pdfKitView
            } else {
                emptyState
            }
        }
    }
    
    private var pdfKitView: some View {
        // Calculate paragraph rect if applicable
        let paragraphRect: CGRect? = {
            if vm.selectionMode == "paragraph" && vm.blockBbox.count == 4 {
                let x0 = vm.blockBbox[0]
                let y0 = vm.blockBbox[1]
                let x1 = vm.blockBbox[2]
                let y1 = vm.blockBbox[3]
                return CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
            }
            return nil
        }()

        return PDFKitView(document: vm.selectedPDF, isDarkMode: isPDFDarkMode, isEditing: vm.showEditSheet, selectionMode: vm.selectionMode, paragraphRect: paragraphRect, paragraphPageIndex: vm.editingPageIndex,
        currentScaleFactor: $vm.currentScaleFactor,
        currentDestination: $vm.currentDestination,
        onLineSelect: { text, pageIdx in
            vm.handleLineSelection(text: text, pageIndex: pageIdx)
        }, onLineClick: { text, pageIdx in
            // Drag-to-select and double-click: Same action as single-click
            // This enables safe selection where user drags to select text
            vm.handleLineSelection(text: text, pageIndex: pageIdx)
        }, onKeyDown: { event in
            let amount = event.modifierFlags.contains(.command) ? 1.0 : 0.1
            switch event.keyCode {
            case 123: vm.nudge(direction: "left",  amount: amount); return true
            case 124: vm.nudge(direction: "right", amount: amount); return true
            case 125: vm.nudge(direction: "down",  amount: amount); return true
            case 126: vm.nudge(direction: "up",    amount: amount); return true
            default: return false
            }
        })
        .id(vm.pdfViewID)
        .background(Color(NSColor.textBackgroundColor))
        .focusable()
        .focusEffectDisabled()
        .accessibilityIdentifier("PDFViewer")
    }
    
    private var emptyState: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "doc.text.viewfinder")
                .font(.system(size: 64, weight: .thin))
                .foregroundColor(Theme.secondaryTextColor.opacity(0.5))
            
            Text("No Document Selected")
                .font(.title2)
                .fontWeight(.medium)
                .foregroundColor(Theme.secondaryTextColor)
            
            Button(action: { vm.showFileImporter = true }) {
                HStack {
                    Image(systemName: "folder.badge.plus")
                    Text("Open PDF File")
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Theme.accentColor)
                .foregroundColor(.white)
                .cornerRadius(8)
            }
            .buttonStyle(.plain)
            .shadow(radius: 2)
            .focusable(false) // Remove focus ring (square box)
            .accessibilityIdentifier("OpenPDFButton")
            .accessibilityLabel("Open PDF File")
            
            Text("or drag and drop a file here")
                .font(.caption)
                .foregroundColor(.secondary)
            
            Spacer()
            
            HStack(spacing: 16) {
                Button(action: { withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isSidebarCollapsed.toggle() } }) {
                    Image(systemName: "sidebar.left")
                        .foregroundColor(Theme.secondaryTextColor)
                }
                .buttonStyle(.plain)
                .help("Toggle Sidebar (Cmd+B)")
                .accessibilityIdentifier("SidebarToggleButton")
                .accessibilityLabel("Toggle Sidebar")
                
                StatusBadge(icon: "checkmark.circle.fill", text: "Ready", color: .green)
                Spacer()
                if let lastSaved = vm.lastSavedTime {
                    Text("Last saved: " + lastSaved.formatted(date: .omitted, time: .shortened))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                Text("Marcedit PDF Editor")
                    .font(.caption2)
                    .foregroundColor(Theme.secondaryTextColor.opacity(0.7))
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 24)
            .background(.ultraThinMaterial)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.backgroundColor)
    }
    
    private var processingOverlay: some View {
        Group {
            if vm.isProcessing {
                Color.black.opacity(0.3).ignoresSafeArea()
                VStack {
                    ProgressView().controlSize(.large)
                    Text("Processing...").padding(.top)
                    // Suppress cancel hint during secure erase — it is non-cancellable.
                    if !vm.isErasureInProgress {
                        Text("Press Esc to cancel").font(.caption).foregroundColor(.secondary).padding(.top, 4)
                    }
                }
                .padding()
                .background(.regularMaterial)
                .cornerRadius(12)
                .accessibilityIdentifier("ProcessingOverlay")

                // Escape key handler — disabled during secure erase (operation is non-cancellable).
                Button("Cancel") {
                    vm.cancelProcessing()
                }
                .keyboardShortcut(.cancelAction)
                .opacity(0)
                .disabled(vm.isErasureInProgress)
                .accessibilityIdentifier("CancelProcessingButton")
            }
        }
    }
    
    private var overlays: some View {
        Group {
            // Edit Sheet
            if vm.showEditSheet {
                editSheet
            }

            // Zoom Controls
            if vm.selectedDocument != nil {
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        ZoomControls().padding(20)
                    }
                }
            }
            
            // Drag Overlay
            if isDragTargeted {
                dragOverlay
            }

            // Toast
            if showToast {
                toastView
            }
        }
    }
    
    private var editSheet: some View {
        ZStack {
            Color.black.opacity(0.2)
                .ignoresSafeArea()
                .onTapGesture {
                    // Don't close dialog if preview is active
                    if !vm.isShowingPreview {
                        vm.showEditSheet = false
                    }
                }
            
            EditLineView(
                originalText: vm.editingOriginalText,
                pageIndex: vm.editingPageIndex,
                detectedFont: vm.originalDetectedFont,
                currentFont: (vm.manualOverrides.fontName != nil)
                    ? (vm.formattedManualFontName ?? vm.detectedFont ?? "Auto-match")
                    : (vm.detectedFont ?? "Auto"),
                onClose: { vm.showEditSheet = false }
            )
            .transition(.move(edge: .bottom))
        }
    }
    
    private var dragOverlay: some View {
        ZStack {
            Color.black.opacity(0.4)
            RoundedRectangle(cornerRadius: 16)
                .stroke(Theme.accentColor, style: StrokeStyle(lineWidth: 4, dash: [10]))
                .padding(20)
            
            VStack(spacing: 16) {
                Image(systemName: "arrow.down.doc.fill")
                .font(.system(size: 60))
                .foregroundColor(.white)
                Text("Drop PDF to Open")
                .font(.title)
                .foregroundColor(.white)
            }
        }
        .background(.ultraThinMaterial)
    }
    
    private var toastView: some View {
        VStack {
            Spacer()
            HStack(spacing: 12) {
                Image(systemName: toastType == .error ? "exclamationmark.triangle.fill" : toastType == .warning ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                    .foregroundColor(toastType == .error ? .red : toastType == .warning ? .orange : .green)
                Text(toastMessage)
                    .foregroundColor(.white)
                    .fontWeight(.medium)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color.black.opacity(0.85))
            .cornerRadius(24)
            .shadow(radius: 4)
            .padding(.bottom, 30)
            .onTapGesture { withAnimation { showToast = false } }
            .accessibilityIdentifier("ToastMessage")
            .accessibilityValue(toastMessage)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .zIndex(100)
    }
    
    private var shortcutsView: some View {
        ZStack {
            Button("") { if let id = vm.selectedDocID { vm.saveFile(id) } }
                .keyboardShortcut("s", modifiers: [.command])
            
            Button("") { if let id = vm.selectedDocID { vm.revertFile(id) } }
                .keyboardShortcut("r", modifiers: [.command])
            
            Button("") { vm.undo() }
                .keyboardShortcut("z", modifiers: [.command])
            
            Button("") { vm.redo() }
                .keyboardShortcut("z", modifiers: [.command, .shift])
            
            Button("") { vm.redo() }
                .keyboardShortcut("y", modifiers: [.command])
             
            // Control alternatives
            Button("") { vm.undo() }
                .keyboardShortcut("z", modifiers: [.control])
             
            Button("") { vm.redo() }
                .keyboardShortcut("y", modifiers: [.control])
            
            Button("Shortcuts") { showHelpSheet.toggle() }
                .keyboardShortcut("?", modifiers: [.command])
                .accessibilityIdentifier("HelpButton")
        }
        .buttonStyle(.plain)
        .frame(width: 0, height: 0)
        .opacity(0)
    }
    
    private var invisibleCloseButton: some View {
        Button("") { vm.requestCloseDocument() }
            .keyboardShortcut("w", modifiers: .command)
            .hidden()
    }
}

struct StatusBadge: View {
    let icon: String
    let text: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .foregroundColor(color)
                .font(.caption)
            Text(text)
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(Theme.textColor)
        }
    }
}
