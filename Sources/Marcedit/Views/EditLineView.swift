
import SwiftUI

struct EditLineView: View {
    let originalText: String
    let pageIndex: Int
    let detectedFont: String? // e.g. "Helvetica - 12.0pt"
    let currentFont: String? // Font that will be used for replacement
    let onClose: () -> Void
    
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject var vm: EditorViewModelV2 // Access to search state
    // NOTE: We use vm.editingText directly instead of local @State
    // This prevents edits from being lost when SwiftUI recreates the view
    
    // Window Position State
    @AppStorage("editWindowX") private var windowX: Double = 0
    @AppStorage("editWindowY") private var windowY: Double = 0
    @AppStorage("exhaustiveFontSearch") private var exhaustiveFontSearch: Bool = false
    
    // Resizing State
    @AppStorage("editWindowWidth") private var windowWidth: Double = 450
    @AppStorage("editWindowHeight") private var windowHeight: Double = 300
    
    @State private var dragStartSize: CGSize? // For resizing
    @State private var dragStartPosition: CGPoint? // For moving
    @State private var selectedFont: FontSearchResult? // Selected font override (nil = use auto-detected)
    @State private var showPreview: Bool = false // Toggle for live preview on PDF
    @State private var userHasExplicitlySelected: Bool = false // Tracks if user manually selected a font
    @State private var loadingTimeExceeded: Bool = false // Shows warning if font search takes too long
    @State private var loadingTimeoutTask: Task<Void, Never>?

    // Minimum dimensions
    private let minWidth: Double = 300
    private let minHeight: Double = 150

    // Dynamic height adjustment for font search UI
    private var effectiveMinHeight: Double {
        // If font search is running or showing results (non-deterministic),
        // expand dialog to accommodate progress bar and font list
        if vm.isSearchingFonts {
            return 400  // Expanded for progress UI
        } else if let results = vm.fontSearchResults[cacheKey],
                  !results.isEmpty,
                  let firstScore = results.first?.score,
                  firstScore < 0.85 {  // Low-confidence match — require explicit user choice
            return 450  // Expanded for font picker list
        }
        return minHeight  // Default compact size
    }

    /// Whether font results are confident enough to use without showing the picker.
    /// Score >= 0.85 means auto-select silently; lower scores require explicit user choice.
    private var fontMatchIsConfident: Bool {
        guard let results = vm.fontSearchResults[cacheKey],
              let firstScore = results.first?.score else { return false }
        return firstScore >= 0.85
    }
    
    /// Font weight descriptions for CJK fonts (w0-w9)
    private static let weightDescriptions: [String: String] = [
        "w0": "Weight0 (Hairline)",
        "w1": "Weight1 (Ultra Light)",
        "w2": "Weight2 (Light)",
        "w3": "Weight3 (Regular)",
        "w4": "Weight4 (Medium)",
        "w5": "Weight5 (Demi-Bold)",
        "w6": "Weight6 (Bold)",
        "w7": "Weight7 (Extra Bold)",
        "w8": "Weight8 (Heavy)",
        "w9": "Weight9 (Black)"
    ]
    
    /// Format font name to expand weight abbreviations (e.g., "hiragino sans w7" -> "Hiragino Sans Weight7 (Extra Bold)")
    private func formatFontName(_ name: String) -> String {
        var result = name
        
        // Check for weight suffix pattern (e.g., " w7" or " W7")
        for (abbrev, full) in Self.weightDescriptions {
            let pattern = " \(abbrev)"
            if result.lowercased().hasSuffix(pattern) {
                let prefixEnd = result.index(result.endIndex, offsetBy: -pattern.count)
                let prefix = String(result[..<prefixEnd])
                // Capitalize each word in prefix
                let capitalizedPrefix = prefix.split(separator: " ").map { $0.capitalized }.joined(separator: " ")
                result = "\(capitalizedPrefix) \(full)"
                break
            }
        }
        
        return result
    }
    
    init(originalText: String, pageIndex: Int, detectedFont: String? = nil, currentFont: String? = nil, onClose: @escaping () -> Void) {
        self.originalText = originalText
        self.pageIndex = pageIndex
        self.detectedFont = detectedFont
        self.currentFont = currentFont
        self.onClose = onClose
        // NOTE: vm.editingText is set by continueLineSelection before this view appears
    }

    /// Editor font - uses system font for consistent UI (font preview happens on PDF, not here)
    private var editorFont: Font {
        // Use a readable size for text editing
        return .system(size: 14)
    }

    /// Cache key that includes exhaustive mode for proper lookup
    /// Uses VM's targetTextForReplacement for consistency with EditorViewModel
    private var cacheKey: String {
        "\(vm.targetTextForReplacement)|\(pageIndex)|\(exhaustiveFontSearch ? "exhaustive" : "common")"
    }

    /// Clamp dialog position to ensure it stays visible on screen
    private func clampDialogToScreen() {
        guard let screen = NSScreen.main else { return }
        let screenFrame = screen.visibleFrame
        let dialogWidth = windowWidth
        let dialogHeight = max(effectiveMinHeight, windowHeight)

        // If position is default (0,0), center on screen
        if windowX == 0 && windowY == 0 {
            windowX = (screenFrame.width - dialogWidth) / 2 + screenFrame.minX
            windowY = (screenFrame.height - dialogHeight) / 2 + screenFrame.minY
        } else {
            // Ensure dialog is fully visible on screen
            // Clamp right edge
            if windowX + dialogWidth > screenFrame.maxX {
                windowX = screenFrame.maxX - dialogWidth - 20
            }
            // Clamp bottom edge
            if windowY + dialogHeight > screenFrame.maxY {
                windowY = screenFrame.maxY - dialogHeight - 20
            }
            // Clamp left edge
            if windowX < screenFrame.minX {
                windowX = screenFrame.minX + 20
            }
            // Clamp top edge
            if windowY < screenFrame.minY {
                windowY = screenFrame.minY + 20
            }
        }
    }

    /// Update preview - runs actual PDF replacement (not an overlay approximation)
    private func updatePreview() {
        // Use vm.editingText directly - it's the single source of truth
        // This persists in the ViewModel even if SwiftUI recreates this view
        LogManager.shared.log("EditLineView: updatePreview() called - showPreview=\(showPreview), editingTextLength=\(vm.editingText.count)")

        // Ensure this view matches the currently active editing session in VM
        // Use vm.editingPageIndex directly instead of local pageIndex for reliability
        let actualPageIndex = vm.editingPageIndex

        if showPreview {
            // Start preview mode if not already
            if !vm.isShowingPreview {
                vm.startPreview()
            }

            // Build overrides from current state
            var overrides = vm.manualOverrides

            // Apply selected font if any
            if let selected = selectedFont {
                overrides.fontName = selected.path + "|" + selected.name
            }

            LogManager.shared.log("EditLineView: Running preview with fontName='\(overrides.fontName ?? "nil")'")

            // Run actual replacement (debounced)
            // Use vm.targetTextForReplacement which is IMMUTABLE during the edit session
            // Use vm.editingText for the replacement (persists even if view recreated)
            vm.runPreviewReplacement(
                targetText: vm.targetTextForReplacement,
                replacementText: vm.editingText,
                pageIndex: actualPageIndex,  // Use vm.editingPageIndex for reliability
                overrides: overrides
            )
        } else {
            // Cancel preview if it was showing
            if vm.isShowingPreview {
                vm.cancelPreview()
            }
        }
    }

    /// Extract the main content area to reduce body complexity
    @ViewBuilder
    private func contentView() -> some View {
        VStack(spacing: 12) {
            // Input Field - switches based on selection mode
            if vm.selectionMode == "paragraph" && !vm.editingSpans.isEmpty {
                // Paragraph mode: Rich text editor with styled spans
                RichTextEditor(
                    spans: $vm.editingSpans,
                    selectedRange: $vm.selectedTextRange,
                    onTextChange: { newValue in
                        vm.editingText = newValue
                    }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.secondaryColor)
                .cornerRadius(6)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.borderColor, lineWidth: 1))
                .accessibilityIdentifier("EditTextInput")
            } else if vm.selectionMode == "paragraph" && vm.editingSpans.isEmpty {
                // Loading State for Rich Text
                VStack(spacing: 12) {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Loading rich text...")
                        .font(.caption)
                        .foregroundColor(Theme.secondaryTextColor)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.secondaryColor)
                .accessibilityIdentifier("LoadingIndicator")
            } else {
                // Line mode: Use SwiftUI TextEditor bound directly to vm.editingText
                // This ensures edits persist in the ViewModel even if the view is recreated
                TextEditor(text: $vm.editingText)
                    .font(editorFont)
                    .scrollContentBackground(.hidden)
                    .padding(4)
                    .background(Theme.secondaryColor)
                    .cornerRadius(6)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.borderColor, lineWidth: 1))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("EditTextInput")
                    .accessibilityLabel("Text to replace")
            }

            // Manual Font Overrides (if in line mode or paragraph mode with spans)
            FontOverrideControls(vm: vm, onOverride: {
                // When user selects a font override, trigger preview update
                updatePreview()
            })
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            headerView()
            Divider()
            contentView()
            fontSearchFeedbackView()
            Divider()
            actionButtonsView()
        }
        .frame(width: max(minWidth, windowWidth), height: max(effectiveMinHeight, windowHeight))
        .background(Theme.cardColor)
        .cornerRadius(12)
        .shadow(radius: 10)
        .onAppear {
            // Clamp dialog position to screen bounds
            clampDialogToScreen()

            // Reset loading timeout state
            loadingTimeExceeded = false

            // CRITICAL FIX: Sync local showPreview with ViewModel state
            // This handles view recreation during preview - @State would reset to false,
            // but vm.isShowingPreview is the source of truth
            if vm.isShowingPreview && !showPreview {
                LogManager.shared.log("EditLineView.onAppear: Syncing showPreview=true from vm.isShowingPreview")
                showPreview = true
            }

            // Only start search if not already cached
            if let cached = vm.fontSearchResults[cacheKey], !cached.isEmpty {
                print("[EditLineView] onAppear - using cached results for textLength=\(originalText.count)")
                // AUTO-SELECT first match from cache only when confident (score >= 0.85).
                // Low-confidence results expand the picker for explicit user choice.
                if selectedFont == nil && fontMatchIsConfident {
                    selectedFont = cached.first
                }
            } else {
                print("[EditLineView] onAppear - font search already started by continueLineSelection")
                // Font search is already triggered by continueLineSelection - don't duplicate

                // Start 3-second timeout for loading feedback (tracked for cancellation)
                loadingTimeoutTask?.cancel()
                loadingTimeoutTask = Task {
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    guard !Task.isCancelled else { return }
                    if vm.isSearchingFonts {
                        await MainActor.run {
                            loadingTimeExceeded = true
                        }
                    }
                }
            }
        }
        .onDisappear {
            loadingTimeoutTask?.cancel()
        }
        // Re-clamp when dialog height changes (e.g., when font picker expands)
        .onChange(of: effectiveMinHeight) { _, _ in
            clampDialogToScreen()
        }
        // Auto-select the first font when results become available, but ONLY when the
        // match is confident (score >= 0.85). For low-confidence results the picker
        // expands to let the user choose explicitly — auto-selecting in that case would
        // contradict the "please pick one" UI signal.
        .onChange(of: vm.fontSearchResults[cacheKey]) { oldValue, newValue in
            if let results = newValue, !results.isEmpty,
               selectedFont == nil,
               !userHasExplicitlySelected,
               fontMatchIsConfident {
                selectedFont = results.first
            }
        }
        // Update preview when showPreview, text, or font changes
        .onChange(of: showPreview) { oldValue, newValue in
            updatePreview()
        }
        .onChange(of: vm.editingText) { oldValue, newValue in
            vm.allowCollisionOverrun = false  // Text changed — invalidate overrun
            if showPreview { updatePreview() }
        }
        .onChange(of: selectedFont) { oldValue, newValue in
            if showPreview { updatePreview() }
        }
        .onChange(of: vm.manualOverrides.fontName) { oldValue, newValue in
            if showPreview { updatePreview() }
        }
        .onChange(of: vm.manualOverrides.fontStyle) { oldValue, newValue in
            if showPreview { updatePreview() }
        }
        .onChange(of: vm.manualOverrides.fillColor) { oldValue, newValue in
            if showPreview { updatePreview() }
        }
        .onChange(of: vm.manualOverrides.justification) { oldValue, newValue in
            if showPreview { updatePreview() }
        }
        .onChange(of: vm.manualOverrides.smartQuotes) { oldValue, newValue in
            if showPreview { updatePreview() }
        }
        // Trigger preview update when font search completes (fixes race condition)
        .onReceive(NotificationCenter.default.publisher(for: .fontSearchCompleted)) { _ in
            if showPreview { updatePreview() }
        }
        // Tint preview layer red on collision errors
        .onChange(of: vm.previewStatus) { _, newValue in
            NotificationCenter.default.post(
                name: .previewErrorChanged,
                object: nil,
                userInfo: ["hasError": newValue.isBlockingError]
            )
        }

        // Manual Resize Handle
        .overlay(alignment: .bottomTrailing) {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .foregroundColor(.secondary.opacity(0.5))
                .font(.caption2)
                .padding(4)
                .background(Color.black.opacity(0.01)) // Hit area
                .accessibilityIdentifier("DialogResizeHandle")
                .gesture(
                    DragGesture()
                        .onChanged { value in
                            if dragStartSize == nil {
                                dragStartSize = CGSize(width: windowWidth, height: windowHeight)
                            }
                            guard let start = dragStartSize else { return }
                            windowWidth = max(minWidth, start.width + value.translation.width)
                            windowHeight = max(minHeight, start.height + value.translation.height)
                        }
                        .onEnded { _ in
                            dragStartSize = nil
                        }
                )
        }
        .offset(x: windowX, y: windowY)
    }

    /// Header view with draggable window
    @ViewBuilder
    private func headerView() -> some View {
        HStack {
            Text("Edit Text")
                .font(.headline)
                .foregroundColor(Theme.secondaryTextColor)
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                if let fontInfo = detectedFont {
                    Text("Original Font: \(fontInfo)")
                        .font(.headline)
                        .foregroundColor(Theme.secondaryTextColor.opacity(0.8))
                        .accessibilityIdentifier("DetectedFontLabel")
                        .accessibilityValue(fontInfo)
                }
                if let current = currentFont {
                    Text("Current Font: \(current)")
                        .font(.headline)
                        .foregroundColor(Theme.secondaryTextColor.opacity(0.8))
                        .accessibilityIdentifier("CurrentFontLabel")
                        .accessibilityValue(current)
                }
            }
        }
        .padding(12)
        .background(Theme.secondaryColor)
        .contentShape(Rectangle())
        .accessibilityIdentifier("EditDialogHeader")
        .gesture(
            DragGesture()
                .onChanged { value in
                    if dragStartPosition == nil {
                        dragStartPosition = CGPoint(x: windowX, y: windowY)
                    }
                    guard let start = dragStartPosition else { return }
                    windowX = start.x + value.translation.width
                    windowY = start.y + value.translation.height
                }
                .onEnded { _ in
                    dragStartPosition = nil
                }
        )
    }

    /// Action buttons (Cancel, Preview, Save)
    @ViewBuilder
    private func actionButtonsView() -> some View {
        VStack(spacing: 8) {
            // Full-width status banner for errors (above button bar)
            if showPreview {
                switch vm.previewStatus {
                case .collisionError(_, let ratio):
                    HStack(spacing: 8) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.red)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Text overlaps existing content\(ratio.map { " (\(Int($0))%)" } ?? "")")
                                .font(.caption)
                                .fontWeight(.medium)
                                .foregroundColor(.red)
                            Text("Shorten text, reduce font, decrease kern, or nudge text")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Button {
                            vm.allowCollisionOverrun = true
                            updatePreview()
                        } label: {
                            Label("Allow Overrun", systemImage: "arrow.right.to.line")
                                .font(.caption)
                        }
                        .buttonStyle(.bordered)
                        .foregroundColor(.orange)
                    }
                    .padding(10)
                    .background(Color.red.opacity(0.08))
                    .cornerRadius(8)
                case .otherError(let message):
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text(message)
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .padding(10)
                    .background(Color.orange.opacity(0.08))
                    .cornerRadius(8)
                default:
                    EmptyView()
                }
            }

            // Button bar
            HStack {
                Button("Cancel") {
                    // Cancel any active preview (restores original PDF)
                    if vm.isShowingPreview {
                        vm.cancelPreview()
                    }
                    onClose()
                }
                .keyboardShortcut(.cancelAction) // Esc
                .buttonStyle(.bordered)
                .accessibilityIdentifier("CancelButton")

                Spacer()

                // Smart Quotes toggle
                Toggle("Smart Quotes", isOn: $vm.manualOverrides.smartQuotes)
                    .toggleStyle(.checkbox)
                    .help("Convert straight quotes (\", ') to typographic curly quotes. Turn off for measurements (5'10\"), code, or names (O'Brien).")
                    .accessibilityIdentifier("SmartQuotesToggle")

                // Preview toggle
                Toggle("Preview", isOn: $showPreview)
                    .toggleStyle(.checkbox)
                    .help("Preview text and font changes on PDF (runs actual replacement)")
                    .accessibilityIdentifier("PreviewToggle")

                // Inline status: only spinner and success (small indicators)
                if showPreview {
                    switch vm.previewStatus {
                    case .running:
                        ProgressView()
                            .scaleEffect(0.6)
                    case .success(let warnings):
                        if let w = warnings {
                            HStack(spacing: 4) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                                    .font(.caption)
                                Text(w).font(.caption2).foregroundColor(.secondary)
                            }
                        }
                    default:
                        EmptyView()
                    }
                }

                Button("Save") {
                    LogManager.shared.log("EditLineView: Save button clicked - isShowingPreview=\(vm.isShowingPreview)")
                    LogManager.shared.log("EditLineView: targetLength=\(vm.targetTextForReplacement.count), editingTextLength=\(vm.editingText.count)")

                    // If a font is selected, apply it as the manual font choice
                    if let selected = selectedFont {
                        vm.manualOverrides.fontName = selected.path + "|" + selected.name
                    }

                    if vm.isShowingPreview {
                        // Preview already has the replacement applied - just confirm it
                        LogManager.shared.log("EditLineView: Taking confirm preview path")
                        // CRITICAL: Set local showPreview to false BEFORE confirmPreview
                        // This prevents onChange handlers from calling updatePreview() which would
                        // re-stash the temp URL and break subsequent operations
                        showPreview = false
                        vm.confirmPreview()
                        onClose()
                    } else {
                        // No preview - run the replacement directly via ViewModel
                        LogManager.shared.log("EditLineView: Taking direct save path - calling vm.replaceText()")
                        Task {
                            // Use targetTextForReplacement (immutable) as the original text
                            // Use vm.editingText which is the single source of truth
                            // CRITICAL: Use vm.editingPageIndex (source of truth) not stale local pageIndex
                            await vm.replaceText(original: vm.targetTextForReplacement, newText: vm.editingText, pageIndex: vm.editingPageIndex)
                            // Close AFTER save completes
                            await MainActor.run {
                                onClose()
                            }
                        }
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(showPreview && vm.previewStatus.isBlockingError)
                .accessibilityIdentifier("SaveButton")
            }
        }
        .padding(16)
    }

    /// Font search feedback section
    @ViewBuilder
    private func fontSearchFeedbackView() -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if vm.isSearchingFonts {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Analysing Fonts...")
                            .font(.caption)
                            .fontWeight(.medium)
                        Spacer()
                        Button(action: { vm.cancelFontSearch() }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.secondary)
                                .font(.caption)
                        }
                        .buttonStyle(.plain)
                        .help("Cancel font search")
                        .accessibilityIdentifier("FontSearchCancelButton")
                    }

                    ProgressView(value: vm.searchProgress)
                        .progressViewStyle(.linear)
                        .accessibilityIdentifier("FontSearchProgress")

                    Text(formatFontName(vm.searchingFontName))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 6)

                // Loading timeout warning
                if loadingTimeExceeded {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text("Font search is taking longer than expected. You can proceed without waiting.")
                            .font(.caption2)
                            .foregroundColor(.orange)
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 4)
                }

                // Dynamic note about exhaustive mode (shown during search)
                if exhaustiveFontSearch {
                    Text("To search only common PDF fonts, disable Exhaustive Font Search in Preferences.")
                        .font(.caption2)
                        .foregroundColor(.orange)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                } else {
                    Text("To search all installed fonts, enable Exhaustive Font Search in Preferences.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                }
            } else if let results = vm.fontSearchResults[cacheKey], !results.isEmpty {
                // Check if this is a deterministic match (only 100% internal font = hide picker)
                // 0.95 threshold: Hide for System Font matches too
                let isDeterministicMatch = results.first?.score ?? 0 >= 0.95

                if !isDeterministicMatch {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Likely Fonts (Top matches):")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(.secondary)

                        // Display Top 5 with radio selection - in ScrollView with fixed height
                        ScrollView {
                            VStack(spacing: 4) {
                                ForEach(results.prefix(5)) { match in
                                    HStack {
                                        // Radio button for font selection
                                        Button(action: {
                                            userHasExplicitlySelected = true  // Track that user made a manual selection
                                            if selectedFont?.id == match.id {
                                                selectedFont = nil // Deselect
                                            } else {
                                                selectedFont = match // Select this font
                                            }
                                        }) {
                                            Image(systemName: selectedFont?.id == match.id ? "circle.inset.filled" : "circle")
                                                .foregroundColor(selectedFont?.id == match.id ? .accentColor : .secondary)
                                                .font(.caption)
                                        }
                                        .buttonStyle(.plain)
                                        .help(selectedFont?.id == match.id ? "Deselect font" : "Select this font")
                                        .accessibilityIdentifier("FontRadioButton_\(match.name.replacingOccurrences(of: " ", with: "_"))")

                                        // Display font name IN that font's actual style
                                        if let nsFont = NSFont(name: match.name, size: 13) {
                                            Text(formatFontName(match.name))
                                                .font(Font(nsFont))
                                                .fontWeight(selectedFont?.id == match.id ? .semibold : .regular)
                                        } else {
                                            // Fallback to system font if font not available
                                            Text(formatFontName(match.name))
                                                .font(.system(size: 13))
                                                .fontWeight(selectedFont?.id == match.id ? .semibold : .regular)
                                        }
                                        Spacer()
                                        Text(String(format: "%.0f%%", match.score * 100))
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                    .padding(4)
                                    .background(selectedFont?.id == match.id ? Color.accentColor.opacity(0.15) : Color.secondary.opacity(0.1))
                                    .cornerRadius(4)
                                }
                            }
                        }
                        .frame(maxHeight: 140) // Fixed max height to preserve editing space
                        .accessibilityIdentifier("FontSearchResults")
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 6)

                    // Dynamic note about exhaustive mode (only show for non-deterministic)
                    if exhaustiveFontSearch {
                        Text("To search only common PDF fonts, disable Exhaustive Font Search in Preferences.")
                            .font(.caption2)
                            .foregroundColor(.orange)
                            .padding(.horizontal, 16)
                            .padding(.bottom, 8)
                    } else {
                        Text("To search all installed fonts, enable Exhaustive Font Search in Preferences.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 16)
                            .padding(.bottom, 8)
                    }
                }
                // else: deterministic match - show nothing extra, just use the header font info
            }
        }
        .transition(.opacity)
    }
}
