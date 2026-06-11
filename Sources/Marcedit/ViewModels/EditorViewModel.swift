import SwiftUI
import PDFKit
import os.log
import CryptoKit // For Insecure.MD5
import UniformTypeIdentifiers
import Combine

// MARK: - Logging
private let logger = Logger(subsystem: "com.marclaw.Marcedit", category: "EditorViewModel")

// MARK: - State Persistence
struct DocumentUIState {
    // Edit Sheet State
    var showEditSheet: Bool = false
    var targetTextForReplacement: String = ""
    var editingText: String = ""
    var editingPageIndex: Int = 0
    
    // Font & Overrides
    var manualOverrides = ManualOverrides()
    var detectedFont: String? = nil
    var detectedFontName: String? = nil
    var detectedFontFlags: Int = 0
    var originalDetectedFont: String? = nil
    var isSearchingFonts: Bool = false
    var searchingFontName: String = ""
    var searchProgress: Double = 0.0
    
    // Selection & History
    var selectionMode: String = "line"
    var undoStack: [EditHistoryItem] = []
    var redoStack: [EditHistoryItem] = []
    
    // Block Editing
    var editingSpans: [SpanInfo] = []
    var blockBbox: [Double] = []
    var selectedTextRange: NSRange = NSRange(location: 0, length: 0)
    
    // PDF View State
    var pdfScaleFactor: CGFloat = 1.0
    var pdfDestinationPageIndex: Int? = nil
    var pdfDestinationPoint: CGPoint? = nil
}

struct DocumentFile: Identifiable, Hashable {
    let id = UUID()
    var originalURL: URL
    var currentURL: URL
    var isDirty: Bool = false
    var uiState: DocumentUIState = DocumentUIState()
    var pendingReloadFlag: Bool = false  // Flag indicating PDF needs reload after sheet closes

    var name: String { originalURL.lastPathComponent }
    var md5Checksum: String? = nil

    // Explicit Hashable/Equatable to ignore uiState for list diffing
    static func == (lhs: DocumentFile, rhs: DocumentFile) -> Bool {
        return lhs.id == rhs.id &&
               lhs.originalURL == rhs.originalURL &&
               lhs.currentURL == rhs.currentURL &&
               lhs.isDirty == rhs.isDirty &&
               lhs.md5Checksum == rhs.md5Checksum
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
        hasher.combine(originalURL)
        hasher.combine(currentURL)
        hasher.combine(isDirty)
        hasher.combine(md5Checksum)
    }
}

struct ManualOverrides {
    var fontName: String? = nil // "System Helvetica" or path
    var fontStyle: String? = nil // "Regular", "Bold", "Italic", "Bold Italic"
    var sizeDelta: Double = 0.0
    var xOffset: Double = 0.0
    var yOffset: Double = 0.0
    var trackingDelta: Double = 0.0 // placeholder
    var skipVisualMatching: Bool = false // Skip redundant font matching when already done in Edit dialog
    var fillColor: String? = nil // Redaction fill color: nil = transparent, "white", "black", etc.
    var justification: String? = nil // "left", "center", "right", "justified", or nil for auto-detect
    var smartQuotes: Bool = false // Convert straight quotes to typographic quotes (off by default)

    var isBold: Bool { fontStyle?.contains("Bold") == true }
    var isItalic: Bool { fontStyle?.contains("Italic") == true }
}

struct EditHistoryItem {
    let inputURL: URL
    let outputURL: URL
    let targetText: String
    var replacementText: String
    let pageIndex: Int
    var overrides: ManualOverrides
    var originalFontInfo: String? // Preserved from before first edit
}

struct FontSearchResult: Codable, Identifiable, Hashable {
    var id: String { name }
    let name: String
    let path: String
    let score: Double
    var source: String? = nil
}

enum CloseActionType {
    case quit
    case closeDocument
}

@MainActor
final class EditorViewModel: ObservableObject {
    @Published var documents: [DocumentFile] = []
    @Published var selectedDocID: UUID?
    @Published var showFileImporter = false
    @Published var showUnsavedAlert = false
    @Published var closeActionType: CloseActionType = .quit
    @Published var pendingCloseAction: (() -> Void)?
    
    // Derived selected document
    var selectedDocument: DocumentFile? {
        get { documents.first(where: { $0.id == selectedDocID }) }
        set {
            if let val = newValue {
                documents = documents.map { $0.id == val.id ? val : $0 }
            }
        }
    }
    
    @Published var selectedPDF: PDFDocument?
    /// Tracks the URL of the content currently displayed in the PDFView.
    /// This is updated after replacePages() since PDFDocument.documentURL doesn't change.
    private var displayedContentURL: URL?
    @Published var pdfViewID = UUID()
    
    // Zoom & Scroll Persistence (Bound to PDFView)
    @Published var currentScaleFactor: CGFloat = 1.0
    @Published var currentDestination: PDFDestination? = nil
    
    // UI State
    @Published var errorMessage: String? = nil
    /// Non-fatal scrub warning message to surface as a toast (distinct from errorMessage).
    @Published var scrubWarningMessage: String? = nil
    @Published var lastSavedTime: Date?
    @Published var showEditSheet = false
    @Published var fontSourceInfo: String? = nil  // Displays font source/substitution info inline
    @Published var isProcessing: Bool = false
    /// True only while a secure erase is running. Distinct from isProcessing so the UI
    /// can suppress the Cancel button — destroying files is irreversible and cannot be interrupted.
    @Published var isErasureInProgress: Bool = false
    @Published var showScrubReport = false
    private var isReloading: Bool = false  // Track reload state to prevent async update races
    @Published var scrubReportURL: URL? = nil
    
    /// Selection mode: "line" for single line, "paragraph" for full text block/cell
    @Published var selectionMode: String = "line"
    
    /// Block editing: array of styled spans when in paragraph mode
    @Published var editingSpans: [SpanInfo] = []
    @Published var blockBbox: [Double] = []
    @Published var selectedTextRange: NSRange = NSRange(location: 0, length: 0)
    
    /// Stores the last scrub report URL per document ID
    var lastScrubReportURLs: [UUID: URL] = [:]
    /// Stores the last scrub data directory URL per document ID (used by secureErase to find the right dir)
    var lastScrubDataDirURLs: [UUID: URL] = [:]
    
    // Font & Manual Controls
    @Published var availableFonts: [[String: String]] = []
    @Published var manualOverrides = ManualOverrides()
    @Published var undoStack: [EditHistoryItem] = []
    @Published var redoStack: [EditHistoryItem] = []
    
    // Legacy single-item history removed in favor of stack
    var lastEdit: EditHistoryItem? { undoStack.last }
    
    // Active Editing
    /// Text to search for in PDF - NEVER mutated during edit session
    /// Set once when text is selected, used as the target for all replacements
    @Published var targetTextForReplacement: String = ""
    /// Alias for ContentView compatibility (same value as targetTextForReplacement)
    var editingOriginalText: String { targetTextForReplacement }
    /// User's current edited text (may differ from target)
    @Published var editingText: String = ""
    @Published var editingPageIndex: Int = 0
    @Published var detectedFont: String? = nil
    @Published var detectedFontName: String? = nil
    @Published var detectedFontFlags: Int = 0 
    @Published var originalDetectedFont: String? = nil // Preserved from initial selection
    @Published var isSearchingFonts: Bool = false // Indicates visual font matching in progress
    
    // MARK: - Preview Status (deterministic collision architecture)
    enum PreviewStatus: Equatable {
        case idle
        case running
        case success(warnings: String?)
        case collisionError(message: String, ratio: Double?)
        case otherError(message: String)

        var isBlockingError: Bool {
            switch self {
            case .collisionError: return true
            default: return false
            }
        }
    }

    @Published var previewStatus: PreviewStatus = .idle
    @Published var allowCollisionOverrun: Bool = false

    // Real Preview State (preview = actual replacement, cancel = restore stashed)
    @Published var isShowingPreview: Bool = false
    @Published var previewStashedURL: URL? = nil  // URL to restore on Cancel
    private var previewStashedOriginalText: String? = nil  // Original text to restore on Cancel
    @Published var previewPendingText: String? = nil  // Text for debounced preview
    private var previewDebounceTask: Task<Void, Never>? = nil
    private var nudgeDebounceTask: Task<Void, Never>? = nil
    
    // Interactive Font Search
    private var terminationHandlerRetryCount = 0
    @Published var searchProgress: Double = 0.0
    @Published var searchingFontName: String = ""
    @Published var fontSearchResults: [String: [FontSearchResult]] = [:] // Cache key: originalText
    
    // Computed helpers for detected font traits
    var detectedIsItalic: Bool { (detectedFontFlags & 2) != 0 }
    var detectedIsBold: Bool { (detectedFontFlags & 16) != 0 }
    
    private var fontDetectionTask: Task<Void, Never>?
    private var fontSearchTask: Task<Void, Never>?
    private let injectedRunner: PythonRunnerProtocol?
    private let maxEditHistoryItems = 50
    private let maxFontSearchCacheEntries = 100
    private var runner: PythonRunnerProtocol? {
        return injectedRunner ?? AppDelegate.pythonRunner
    }
    
    // Task tracking for cancellation
    private var processingTask: Task<Void, Never>?
    
    // MARK: - Initialization

    init(runner: PythonRunnerProtocol? = nil) {
        self.injectedRunner = runner
        Task {
            await fetchFonts()
        }

        NotificationCenter.default.addObserver(self, selector: #selector(handleCloseRequest), name: .attemptToCloseApp, object: nil)

        // BUG #40: All weak self patterns properly handled
        // - Use `guard let self = self else { return }` for multi-statement closures
        // - Use `self?.method()` for single-statement optional execution
        // Listen for test mode PDF loading
        NotificationCenter.default.addObserver(
            forName: .LoadTestPDF,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            if let path = notification.userInfo?["path"] as? String {
                let url = URL(fileURLWithPath: path)
                if FileManager.default.fileExists(atPath: path) {
                    Task { @MainActor [weak self] in
                        self?.add(urls: [url])
                    }
                } else {
                    print("[TestMode] Test PDF not found: \(path)")
                }
            }
        }
        loadPDFFromUITestArgumentsIfNeeded()

        // TEST AUTOMATION: Trigger edit dialog with specified text
        NotificationCenter.default.addObserver(
            forName: .TriggerEditDialog,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            let text = notification.userInfo?["text"] as? String ?? "CLICK_HERE_TO_EDIT"
            let pageIndex = notification.userInfo?["pageIndex"] as? Int ?? 0
            print("[TestMode] TriggerEditDialog: textLength=\(text.count), page=\(pageIndex)")
            Task { @MainActor [weak self] in
                self?.handleLineSelection(text: text, pageIndex: pageIndex)
            }
        }

        // TEST AUTOMATION: Set text in edit field
        NotificationCenter.default.addObserver(
            forName: .SetEditText,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            if let text = notification.userInfo?["text"] as? String {
                print("[TestMode] SetEditText: textLength=\(text.count)")
                Task { @MainActor [weak self] in
                    self?.editingText = text
                }
            }
        }

        // TEST AUTOMATION: Toggle preview
        NotificationCenter.default.addObserver(
            forName: .TogglePreview,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            let requestedEnable = notification.userInfo?["enable"] as? Bool
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                let enable = requestedEnable ?? !self.isShowingPreview
                print("[TestMode] TogglePreview: \(enable)")
                self.isShowingPreview = enable
            }
        }

        // TEST AUTOMATION: Query current state (writes to file for test script to read)
        NotificationCenter.default.addObserver(
            forName: .TestQueryState,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            let outputPath = notification.userInfo?["outputPath"] as? String ?? "/tmp/marcedit_test_state.json"
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                let state: [String: Any] = [
                    "showEditSheet": self.showEditSheet,
                    "editingText": self.editingText,
                    "targetText": self.targetTextForReplacement,
                    "isShowingPreview": self.isShowingPreview,
                    "pageIndex": self.editingPageIndex
                ]
                if let data = try? JSONSerialization.data(withJSONObject: state, options: .prettyPrinted) {
                    try? data.write(to: URL(fileURLWithPath: outputPath))
                    print("[TestMode] QueryState written to: \(outputPath)")
                }
            }
        }

        registerTerminationHandler()
    }

    private func loadPDFFromUITestArgumentsIfNeeded() {
        guard CommandLine.arguments.contains("--run-ui-tests"),
              let pathArg = CommandLine.arguments.first(where: { $0.hasPrefix("--test-pdf-path=") }) else {
            return
        }

        let path = String(pathArg.dropFirst("--test-pdf-path=".count))
        guard FileManager.default.fileExists(atPath: path) else {
            print("[TestMode] Test PDF not found: \(path)")
            return
        }

        let url = URL(fileURLWithPath: path)
        Task { @MainActor [weak self] in
            self?.add(urls: [url])
        }
    }
    
    func cancelProcessing() {
        guard isProcessing, !isErasureInProgress else { return }
        logger.info("User requested cancellation of processing task")
        processingTask?.cancel()
        isProcessing = false
        processingTask = nil
    }
    
    deinit {
        // Remove all NotificationCenter observers to prevent memory leaks
        NotificationCenter.default.removeObserver(self)

        // Cancel any running background tasks to prevent resource leaks
        fontDetectionTask?.cancel()
        fontSearchTask?.cancel()
        previewDebounceTask?.cancel()
    }
    
    func registerTerminationHandler() {
        if let appDelegate = AppDelegate.shared {
            appDelegate.terminationCheck = { [weak self] in
                guard let self = self else {
                    LogManager.shared.log("TerminationCheck: self is nil, allowing quit")
                    return true
                }

                // Log each document's dirty status
                let docStatuses = self.documents.map { "\($0.originalURL.lastPathComponent): isDirty=\($0.isDirty)" }
                LogManager.shared.log("TerminationCheck: \(self.documents.count) documents - [\(docStatuses.joined(separator: ", "))]")

                let hasDirty = self.documents.contains(where: { $0.isDirty })
                LogManager.shared.log("TerminationCheck: hasDirty=\(hasDirty), returning canTerminate=\(!hasDirty)")
                return !hasDirty
            }
            appDelegate.isProcessingCheck = { [weak self] in
                return self?.isProcessing ?? false
            }
            appDelegate.isErasureInProgressCheck = { [weak self] in
                return self?.isErasureInProgress ?? false
            }
            appDelegate.cancelProcessingCallback = { [weak self] in
                self?.cancelProcessing()
            }
            logger.info("Termination check registered successfully")
            LogManager.shared.log("Termination check registered successfully via AppDelegate.shared")
        } else {
            // AppDelegate not ready yet - retry after a short delay (max 10 retries)
            terminationHandlerRetryCount += 1
            if terminationHandlerRetryCount < 10 {
                LogManager.shared.log("AppDelegate.shared not ready, will retry in 0.5s (attempt \(terminationHandlerRetryCount)/10)")
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
                    self?.registerTerminationHandler()
                }
            } else {
                logger.warning("AppDelegate.shared never became ready after 10 retries")
            }
        }
    }
    
    @objc func handleCloseRequest() {
        LogManager.shared.log("handleCloseRequest called (Quit)")
        Task { @MainActor in
            self.closeActionType = .quit
            self.showUnsavedAlert = true
            
            // If the request came from CMD-Q, we want the "Quit Anyway" to terminate app
            self.pendingCloseAction = {
                 AppDelegate.shared?.terminationCheck = nil
                 NSApplication.shared.terminate(nil)
            }
        }
    }
    
    func requestCloseDocument() {
        guard let id = selectedDocID, let doc = documents.first(where: { $0.id == id }) else { return }
        
        LogManager.shared.log("requestCloseDocument called for \(doc.originalURL.lastPathComponent)")
        
        if doc.isDirty {
            self.closeActionType = .closeDocument
            self.showUnsavedAlert = true
            
            self.pendingCloseAction = { [weak self] in
                self?.closeDocument(id: id)
            }
        } else {
            closeDocument(id: id)
        }
    }
    
    func closeDocument(id: UUID) {
        if let idx = documents.firstIndex(where: { $0.id == id }) {
            let doc = documents[idx]
            // Cleanup temp file if different from original
            if doc.currentURL != doc.originalURL {
                cleanupTempFile(doc.currentURL)
            }
            documents.remove(at: idx)
            if selectedDocID == id {
                selectedDocID = nil
                selectedPDF = nil
                // Select another document if available
                if let first = documents.first {
                    selectFile(first.id)
                }
            }
        }
    }
    
    func quitAnyway() {
        pendingCloseAction?()
    }

    // MARK: - Font Management
    func fetchFonts() async {
        guard let runner = self.runner else { return }
        
        // Offload blocking call to background thread to prevent UI freeze
        let result = await Task.detached(priority: .userInitiated) {
             return try? runner.listAvailableFonts()
        }.value
        
        if let fonts = result {
            self.availableFonts = fonts
        } else {
            logger.error("Failed to fetch fonts")
        }
    }
    
    var formattedManualFontName: String? {
        guard let name = manualOverrides.fontName else { return nil }
        
        // Map Base-14 shortcodes to human-readable names
        let shortcodeMap = [
            "helv": "Helvetica",
            "tiro": "Times Roman", 
            "cour": "Courier",
            "symb": "Symbol",
            "zadb": "Zapf Dingbats"
        ]
        if let mapped = shortcodeMap[name] {
            return mapped
        }
        
        // Handle path|ps_name format (preferred for display)
        if name.contains("|") {
            let parts = name.split(separator: "|")
            if parts.count > 1 {
                // Return clean PS Name (e.g. AlBayan-Bold)
                return String(parts[1])
            }
            // Fallback to path part
            let path = String(parts[0])
            let url = URL(fileURLWithPath: path)
            return url.deletingPathExtension().lastPathComponent
        }
        
        // If it looks like a path, get the filename without extension
        if name.contains("/") {
            let url = URL(fileURLWithPath: name)
            // Remove extension and return name
            return url.deletingPathExtension().lastPathComponent
        }
        return name
    }
    
    
    /// Check edit history for the original font of previously edited text
    func lookupOriginalFontFromHistory(text: String, pageIndex: Int) -> String? {
        // Check if this text matches the replacementText of any previous edit
        // If so, return the stored originalFontInfo
        for item in undoStack.reversed() {
            if item.replacementText == text && item.pageIndex == pageIndex {
                return item.originalFontInfo
            }
        }
        return nil
    }
    
    /// Check edit history for overrides used on previously edited text
    /// Returns the ManualOverrides used in the most recent edit for this text, if any
    func lookupOverridesFromHistory(text: String, pageIndex: Int) -> ManualOverrides? {
        for item in undoStack.reversed() {
            if item.replacementText == text && item.pageIndex == pageIndex {
                // This text was previously edited - return the overrides used
                logger.info("Found override history for text: fontName='\(item.overrides.fontName ?? "nil")'")
                return item.overrides
            }
        }
        return nil
    }
    
    func detectFont() async {
        guard let doc = selectedDocument, let runner = self.runner else { return }
        if editingText.isEmpty { 
            detectedFont = nil
            return 
        }
        
        
        // +1 for 1-based page index in core.py
            guard self.editingPageIndex >= 0, self.editingPageIndex != Int.max else {
                logger.error("Invalid page index: \(self.editingPageIndex)")
                self.detectedFont = nil
                return
            }
            let inputPath = doc.currentURL.path
            let pageNum = editingPageIndex + 1
            let target = editingText
            
            // Cancel previous task if any
            fontDetectionTask?.cancel()
            
            // Offload blocking Python call to background task
            fontDetectionTask = Task.detached(priority: .userInitiated) {
                // Check cancellation
                if Task.isCancelled { return }
                
                let val = try? runner.identifyFont(inputPath: inputPath, pageNumber: pageNum, targetText: target)
                
                if Task.isCancelled { return }
                
                // Update UI on MainActor
                await MainActor.run {
                    self.processFontInfo(val)
                }
            }
    }
    
    // Separate method to handle result safely on MainActor
    private func processFontInfo(_ info: [String: Any]?) {
        // Ignore updates if document is being reloaded
        guard !isReloading else {
            logger.debug("processFontInfo: Ignoring update during reload")
            return
        }

        guard let info = info else {
            self.detectedFont = nil
            self.detectedFontName = nil
            self.detectedFontFlags = 0
            return
        }
        
        // Update UI on MainActor
        logger.info("processFontInfo: \(info)") // Debug logging
        
        if let success = info["success"] as? Bool, success,
           let name = info["fontname"] as? String, 
           let size = info["fontsize"] as? Double {
            
            // Capture flags if present
            if let flags = info["flags"] as? Int {
                self.detectedFontFlags = flags
            } else if let flagsDouble = info["flags"] as? Double {
                self.detectedFontFlags = Int(flagsDouble)
            } else {
                self.detectedFontFlags = 0
            }
            
            // Display Name Logic
            var displayName = name
            if displayName == "cour" { displayName = "Courier" }
            else if displayName == "helv" { displayName = "Helvetica" }
            else if displayName == "tiro" { displayName = "Times Roman" }
            else if displayName == "symb" { displayName = "Symbol" }
            else if displayName == "zapf" { displayName = "Zapf Dingbats" }
            else if displayName.lowercased().contains("allandnone") { displayName = "Embedded Font (AllAndNone)" }
            else if displayName.contains("+") {
                let parts = displayName.components(separatedBy: "+")
                if parts.count > 1 {
                    displayName = "Embedded: \(parts[1])"
                }
            }
            
            // Internal ID Logic (for Preview)
            if let previewPath = info["preview_font_path"] as? String {
                // Use extracted native font file
                self.detectedFontName = previewPath + "|" + name
            } else {
                // Fallback to system/mapped names
                if name == "cour" { self.detectedFontName = "Courier" }
                else if name == "helv" { self.detectedFontName = "Helvetica" }
                else if name == "tiro" { self.detectedFontName = "Times-Roman" }
                else if name == "symb" { self.detectedFontName = "Symbol" }
                else if name == "zapf" { self.detectedFontName = "ZapfDingbats" }
                else { self.detectedFontName = name }
            }
            
            self.detectedFont = String(format: "%@ - %.1f pt", displayName, size)
            
            // Preserve original font from first detection
            if self.originalDetectedFont == nil {
                self.originalDetectedFont = self.detectedFont
            }
        } else {
            // Use message if available, otherwise generic
            if let message = info["message"] as? String {
                logger.info("Font detection: \(message)")
            }
            self.detectedFont = "Unknown Font"
            self.detectedFontName = nil
            // Preserve original font from first detection
            if self.originalDetectedFont == nil {
                self.originalDetectedFont = self.detectedFont
            }
        }
    }

    // MARK: - File Management
    func add(urls: [URL]) {
        for url in urls {
             // Avoid duplicates by path
            if !documents.contains(where: { $0.originalURL.path == url.path }) {
                let doc = DocumentFile(originalURL: url, currentURL: url, isDirty: false)
                documents.append(doc)
                // Always select the new document
                selectFile(doc.id)
                // Calculate Checksum
                calculateChecksum(for: doc.id)
            }
        }
    }
    
    // MARK: - Drop Handling
    
    func handleDrop(providers: [NSItemProvider]) -> Bool {
        var urls: [URL] = []
        let group = DispatchGroup()
        
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.pdf.identifier) {
                group.enter()
                provider.loadItem(forTypeIdentifier: UTType.pdf.identifier, options: nil) { (item, error) in
                    if let url = item as? URL {
                        // CRITICAL FIX: Dispatch append AND leave together to prevent race condition
                        DispatchQueue.main.async {
                            urls.append(url)
                            group.leave()
                        }
                    } else {
                        group.leave()
                    }
                }
            }
        }
        
        group.notify(queue: .main) {
            if !urls.isEmpty {
                self.add(urls: urls)
            }
        }
        return true
    }
    
    func selectFile(_ id: UUID, preserveState: Bool = false) {
        guard let doc = documents.first(where: { $0.id == id }) else { return }
        
        // Track if we're switching to a different document (not just reloading current)
        let isSwitchingDocuments = selectedDocID != id
        
        let url = doc.currentURL

        // Security-scoped access is only needed for user-selected files.
        // Temp files (from previous edits/previews, or test mode) don't need scoping.
        // NOTE: FileManager.temporaryDirectory returns /var/folders/… on macOS, but test
        // files and intermediate outputs live in /tmp (a symlink to /private/tmp). We
        // check all three so that test-mode PDFs are never rejected by the scope guard.
        let systemTempDir = FileManager.default.temporaryDirectory.path
        let isTempFile = url.path.hasPrefix(systemTempDir)
            || url.path.hasPrefix("/tmp/")
            || url.path.hasPrefix("/private/tmp/")
        let access = isTempFile ? false : url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }

        // For non-temp files, verify we have security-scoped access (or direct readability).
        // For temp files, verify the file exists and is readable.
        if !isTempFile && !access {
            // Fall back to direct readability check (covers test mode, drag-and-drop without
            // a security-scoped bookmark, and any other non-sandbox scenario).
            if !FileManager.default.isReadableFile(atPath: url.path) {
                self.errorMessage = "Cannot access file: \(doc.name). Please re-open it using File > Open."
                logger.warning("Security-scoped resource access failed for: \(url.lastPathComponent)")
                return
            }
            // File is readable directly — proceed without security scope.
        }
        if isTempFile && !FileManager.default.isReadableFile(atPath: url.path) {
            self.errorMessage = "Cannot access temp file: file not found"
            logger.warning("Temp file not readable: \(url.lastPathComponent)")
            return
        }

        // CANCEL PREVIEW when switching to a different document.
        // Preview state (isShowingPreview, previewStashedURL) is not document-scoped,
        // so leaving it active while switching would cause the stash to reference the
        // old document's URL and corrupt subsequent operations on the new document.
        if isSwitchingDocuments && isShowingPreview {
            cancelPreview()
        }

        // SAVE STATE of current document before switching
        if let oldID = selectedDocID, oldID != id,
           let oldIdx = documents.firstIndex(where: { $0.id == oldID }) {
            saveCurrentState(to: &documents[oldIdx])
        }

        selectedDocID = id

        // Check if URL changed - use displayedContentURL instead of selectedPDF.documentURL
        // because replacePages() doesn't update documentURL, causing false negatives
        let urlChanged = (displayedContentURL?.path ?? "") != url.path
        LogManager.shared.log("selectFile: url='\(url.lastPathComponent)', displayedContentURL='\(displayedContentURL?.lastPathComponent ?? "nil")', urlChanged=\(urlChanged)")

        // RELOAD LOGIC:
        // - If preserveState + existing PDF: Use replacePages() to preserve object identity
        // - Otherwise: Create new PDFDocument
        
        // Always notify view to save state if we're preserving
        if preserveState {
            isReloading = true  // Mark as reloading to prevent async updates
            NotificationCenter.default.post(name: .prepareForPDFReload, object: nil)
        }

        defer {
            if preserveState {
                isReloading = false  // Clear reload flag
            }
        }

        if urlChanged, preserveState, let existingPDF = selectedPDF {
            // CRITICAL FIX: Replace pages in-place to preserve PDFDocument identity
            // This prevents SwiftUI re-render which would dismiss overlays and reset scroll
            LogManager.shared.log("selectFile: BRANCH 1 - replacePages (urlChanged=true, preserveState=true)")

            if existingPDF.replacePages(from: url) {
                LogManager.shared.log("selectFile: replacePages SUCCESS from '\(url.lastPathComponent)'")
                logger.info("PDF pages replaced in-place from: \(url.lastPathComponent)")
                displayedContentURL = url  // Track what's now displayed
            } else {
                LogManager.shared.log("selectFile: replacePages FAILED")
                logger.error("Failed to replace pages")
            }

            // Notify view to restore state
            NotificationCenter.default.post(name: .didReloadPDF, object: nil)

            // No state restore needed - we preserved the object and view state handles scroll restoration


        } else if !urlChanged, let _ = selectedPDF {
            // URL hasn't changed - keep existing PDFDocument
            LogManager.shared.log("selectFile: BRANCH 2 - URL unchanged, no reload needed")
            logger.info("PDF URL unchanged, preserving existing PDFDocument for view state")

            // Still restore state if we saved it
            if preserveState {
                NotificationCenter.default.post(name: .didReloadPDF, object: nil)
            }

        } else if let pdf = PDFDocument(url: url) {
            // URL changed and no preservation - create new PDFDocument
            self.selectedPDF = pdf
            self.displayedContentURL = url  // Track what's now displayed

            // Only regenerate pdfViewID when switching to a DIFFERENT document
            // AND not in preview mode (to prevent sheet dismissal during live preview)
            if isSwitchingDocuments && !isShowingPreview {
                self.pdfViewID = UUID()
            }

            logger.info("Selected PDF: \(doc.name), preserveState=\(preserveState), isSwitching=\(isSwitchingDocuments)")

            // Notify view to restore state (even with new PDFDocument, we can restore scroll position)
            if preserveState {
                NotificationCenter.default.post(name: .didReloadPDF, object: nil)
            }

            // RESTORE STATE
            if isSwitchingDocuments {
                restoreState(from: doc)
            } else if preserveState {
                // CRITICAL FIX: Save current state BEFORE restoring when reloading same document
                // This ensures showEditSheet=true is preserved during preview/replace operations
                if let idx = documents.firstIndex(where: { $0.id == id }) {
                    saveCurrentState(to: &documents[idx])
                    logger.info("Saved current state before restoring (same document reload)")
                    // FIX: Restore from freshly-saved document, not stale 'doc' copy
                    restoreState(from: documents[idx])
                }
            } else {
                // Clear history when forced reload
                self.clearEditHistory()
                self.fontSourceInfo = nil
            }
        } else {
            self.errorMessage = "Could not open PDF: \(doc.name)"

            // Restore state even on error if we saved it
            if preserveState {
                NotificationCenter.default.post(name: .didReloadPDF, object: nil)
            }
        }
    }
    
    private func saveCurrentState(to doc: inout DocumentFile) {
        var state = doc.uiState
        
        // Save Editing State
        state.showEditSheet = showEditSheet
        state.targetTextForReplacement = targetTextForReplacement
        state.editingText = editingText
        state.editingPageIndex = editingPageIndex
        
        // Save Font State
        state.manualOverrides = manualOverrides
        state.detectedFont = detectedFont
        state.detectedFontName = detectedFontName
        state.detectedFontFlags = detectedFontFlags
        state.originalDetectedFont = originalDetectedFont
        state.isSearchingFonts = isSearchingFonts
        state.searchingFontName = searchingFontName
        state.searchProgress = searchProgress
        
        // Save History
        state.selectionMode = selectionMode
        state.undoStack = undoStack
        state.redoStack = redoStack
        
        // Save Block Editing
        state.editingSpans = editingSpans
        state.blockBbox = blockBbox
        state.selectedTextRange = selectedTextRange
        
        // Save View State
        state.pdfScaleFactor = currentScaleFactor
        if let dest = currentDestination, let page = dest.page, let pdf = selectedPDF {
            let idx = pdf.index(for: page)
            if idx != NSNotFound {
                state.pdfDestinationPageIndex = idx
                state.pdfDestinationPoint = dest.point
            } else {
                state.pdfDestinationPageIndex = nil
                state.pdfDestinationPoint = nil
            }
        } else {
            state.pdfDestinationPageIndex = nil
            state.pdfDestinationPoint = nil
        }
        
        doc.uiState = state
        // Note: mutating doc here updates the array via 'inout'
    }
    
    // BUG #62: Individual property assignment is verbose but clear
    // This could be optimized with KeyPath-based bulk assignment or Codable,
    // but the current approach is explicit and type-safe
    private func restoreState(from doc: DocumentFile) {
        let state = doc.uiState

        // Restore Editing State
        showEditSheet = state.showEditSheet
        targetTextForReplacement = state.targetTextForReplacement
        editingText = state.editingText
        editingPageIndex = state.editingPageIndex

        // Restore Font State
        manualOverrides = state.manualOverrides
        detectedFont = state.detectedFont
        detectedFontName = state.detectedFontName
        detectedFontFlags = state.detectedFontFlags
        originalDetectedFont = state.originalDetectedFont
        isSearchingFonts = state.isSearchingFonts
        searchingFontName = state.searchingFontName
        searchProgress = state.searchProgress

        // Restore History
        selectionMode = state.selectionMode
        let droppedUndoHistory = Array(state.undoStack.dropLast(maxEditHistoryItems))
        let droppedRedoHistory = Array(state.redoStack.dropLast(maxEditHistoryItems))
        undoStack = Array(state.undoStack.suffix(maxEditHistoryItems))
        redoStack = Array(state.redoStack.suffix(maxEditHistoryItems))
        cleanupHistoryItems(droppedUndoHistory + droppedRedoHistory)

        // Restore Block Editing
        editingSpans = state.editingSpans
        blockBbox = state.blockBbox
        selectedTextRange = state.selectedTextRange
        
        // Restore View State
        currentScaleFactor = state.pdfScaleFactor
        if let pageIndex = state.pdfDestinationPageIndex,
           let point = state.pdfDestinationPoint,
           let pdf = selectedPDF, pageIndex >= 0, pageIndex < pdf.pageCount,
           let page = pdf.page(at: pageIndex) {
            currentDestination = PDFDestination(page: page, at: point)
        } else {
            currentDestination = nil
        }
    }
    
    func revealInFinder(_ id: UUID) {
        guard let doc = documents.first(where: { $0.id == id }) else { return }
        // Use the original URL for reveal (shows where user expects the file to be)
        NSWorkspace.shared.activateFileViewerSelecting([doc.originalURL])
    }
    
    func closeFile(_ id: UUID) {
        guard let idx = documents.firstIndex(where: { $0.id == id }) else { return }
        let doc = documents[idx]
        
        if doc.isDirty {
            self.selectedDocID = id // Switch to it so user sees it
            self.closeActionType = .closeDocument  // Show "Close Document?" not "Quit Application?"
            self.pendingCloseAction = { [weak self] in
                self?.forceCloseFile(id)
            }
            self.showUnsavedAlert = true
        } else {
            forceCloseFile(id)
        }
    }
    
    private func forceCloseFile(_ id: UUID) {
        if let idx = documents.firstIndex(where: { $0.id == id }) {
            let doc = documents[idx]

            // Cancel active preview if it belongs to this document
            if selectedDocID == id && isShowingPreview {
                previewDebounceTask?.cancel()
                previewDebounceTask = nil
                // Clean up preview temp file if different from stashed
                if let stashed = previewStashedURL, doc.currentURL != stashed {
                    cleanupTempFile(doc.currentURL)
                }
                previewStashedURL = nil
                previewStashedOriginalText = nil
                previewPendingText = nil
                previewStatus = .idle
                allowCollisionOverrun = false
                isShowingPreview = false
                showEditSheet = false
            }

            // Cleanup temp file if needed
            if doc.currentURL != doc.originalURL {
                cleanupTempFile(doc.currentURL)
            }
            documents.remove(at: idx)
            if selectedDocID == id {
                selectedDocID = nil
                selectedPDF = nil
                // Select another if available
                if let first = documents.first {
                    selectFile(first.id)
                }
            }
        }
    }
    
    func revertFile(_ id: UUID) {
        guard let idx = documents.firstIndex(where: { $0.id == id }) else { return }
        var doc = documents[idx]
        
        if doc.isDirty {
             // Cleanup old temp file
             if doc.currentURL != doc.originalURL {
                 cleanupTempFile(doc.currentURL)
             }
             // Revert currentURL to originalURL
             doc.currentURL = doc.originalURL
             doc.isDirty = false
             documents[idx] = doc
             selectFile(id) // Reload
        }
    }
    
    func saveFile(_ id: UUID) {
        // In this architecture, 'save' might mean overwriting original with current?
        // Or exporting? 
        // User asked for "Save" button. 
        // If we overwrite original, we must be careful. 
        // But 'currentURL' is likely a temp file `_edited`.
        // So we copy currentURL to originalURL.
        
        guard let idx = documents.firstIndex(where: { $0.id == id }) else { return }
        var doc = documents[idx]
        
        if !doc.isDirty { return }
        
        do {
            let original = doc.originalURL
            let current = doc.currentURL
            
            let hasAccess = original.startAccessingSecurityScopedResource()
            defer { if hasAccess { original.stopAccessingSecurityScopedResource() } }
            
            guard hasAccess else {
                self.errorMessage = "Cannot access file: permission denied"
                return
            }
            
            // Apply metadata preservation if requested
            let shouldPreserve = UserDefaults.standard.bool(forKey: "preserveMetadata")
            
            if shouldPreserve {
                do {
                    let attrs = try FileManager.default.attributesOfItem(atPath: original.path)
                    if let creationDate = attrs[.creationDate] as? Date {
                        try FileManager.default.setAttributes([.creationDate: creationDate], ofItemAtPath: current.path)
                    }
                } catch {
                    logger.warning("Failed to preserve attributes: \(error)")
                }
            }
            
            // Atomic save: replaces original with current (temp) file safely
            // This moves the temp file to the original location
            _ = try FileManager.default.replaceItem(
                at: original,
                withItemAt: current,
                backupItemName: nil,
                options: shouldPreserve ? [] : .usingNewMetadataOnly, 
                resultingItemURL: nil
            )
            
            doc.isDirty = false
            doc.currentURL = original 
            documents[idx] = doc
            clearEditHistory()
            
            // Recalculate checksum on save
            calculateChecksum(for: id)
            
            logger.info("Saved file: \(doc.name)")
        } catch let error as NSError {
            if error.domain == NSCocoaErrorDomain && error.code == NSFileWriteNoPermissionError {
                 self.errorMessage = "Permission denied: Cannot save to \(doc.name). Check file permissions."
            } else {
                 self.errorMessage = "Save failed: \(error.localizedDescription)"
            }
            logger.error("Save failed: \(error)")
        }
    }
    
    func exportFile(_ id: UUID) {
        guard let idx = documents.firstIndex(where: { $0.id == id }) else { return }
        let doc = documents[idx]
        
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.pdf]
        panel.nameFieldStringValue = doc.name
        panel.title = "Save Copy As..."
        panel.canCreateDirectories = true
        
        panel.begin { response in
            if response == .OK, let url = panel.url {
                Task { [weak self] in
                    guard let self = self else { return }
                    do {
                        // Check if file exists and remove it safely? 
                        // NSSavePanel usually handles overwrite confirmation.
                        if FileManager.default.fileExists(atPath: url.path) {
                            try FileManager.default.removeItem(at: url)
                        }
                        try FileManager.default.copyItem(at: doc.currentURL, to: url)
                        
                        await MainActor.run {
                            // Update the document to point to the new file
                            if let docIdx = self.documents.firstIndex(where: { $0.id == id }) {
                                var updatedDoc = self.documents[docIdx]
                                // Clean up old temp file if different from original
                                if updatedDoc.currentURL != updatedDoc.originalURL {
                                    self.cleanupTempFile(updatedDoc.currentURL)
                                }
                                // Update to new location
                                updatedDoc.originalURL = url
                                updatedDoc.currentURL = url
                                updatedDoc.isDirty = false
                                self.documents[docIdx] = updatedDoc
                                
                                // Reload the PDF view to reflect the new file
                                self.selectFile(id, preserveState: true)
                            }
                            logger.info("Exported and updated file")
                        }
                    } catch {
                        await MainActor.run {
                            self.errorMessage = "Export failed: \(error.localizedDescription)"
                        }
                    }
                }
            }
        }
    }
    
    func clearQueue() {
        documents.removeAll()
        selectedDocID = nil
        selectedPDF = nil
    }

    // MARK: - Editing
    
    // MARK: - Selection Handling
    
    func handleLineSelection(text: String, pageIndex: Int) {
        // SAFE SELECTION: Always use line mode for predictable, single-unit editing
        // The paragraph mode is parked (v0.9-line-paragraph-mode tag) but disabled
        // to provide a simpler, more reliable editing experience.
        //
        // User selects text via drag or click → opens EditLineView for that text only
        continueLineSelection(text: text, pageIndex: pageIndex)
    }
    
    private func continueLineSelection(text: String, pageIndex: Int) {
        // CRITICAL: Cancel stale preview state FIRST, before setting new state
        // This prevents cancelPreview() from restoring stale editingText
        if self.isShowingPreview {
            self.cancelPreview()
        }

        // NOW set the new editing state
        self.targetTextForReplacement = text  // IMMUTABLE: Used for all replacements during this edit session
        self.editingText = text  // Mutable: User can modify this
        self.editingPageIndex = pageIndex
        self.detectedFont = nil
        
        // Check if this text was previously edited - restore those overrides
        // This preserves the user's font choice when re-editing the same text
        if let previousOverrides = self.lookupOverridesFromHistory(text: text, pageIndex: pageIndex) {
            self.manualOverrides = previousOverrides
            logger.info("Restored overrides from history: fontName='\(previousOverrides.fontName ?? "nil")'")
        } else {
            // Fresh edit - reset overrides to defaults
            self.manualOverrides = ManualOverrides()
        }
        
        self.originalDetectedFont = self.lookupOriginalFontFromHistory(text: text, pageIndex: pageIndex)
        
        // Start font search
        Task { await self.startInteractiveFontSearch(text: text, pageIndex: pageIndex) }
        
        // Open Edit Sheet
        self.showEditSheet = true
    }
    
    private func expandToParagraph(text: String, pageIndex: Int) async -> String {
        guard let doc = selectedDocument,
              let runner = self.runner else {
            return text
        }
        
        do {
            let path = doc.currentURL.path
            let pageNum = pageIndex + 1
            
            // Fix Crash: Offload blocking Python call to detached task
            let result = try await Task.detached {
                return try runner.expandToParagraph(
                    inputPath: path,
                    pageNumber: pageNum,
                    spanText: text
                )
            }.value
            
            if let expandedText = result["expanded_text"] as? String, !expandedText.isEmpty {
                logger.info("Paragraph expansion: inputLength=\(text.count), expandedLength=\(expandedText.count)")
                return expandedText
            }
        } catch {
            logger.error("Paragraph expansion failed: \(error)")
        }
        return text
    }
    
    private func fetchBlockSpans(spanText: String, pageIndex: Int) async {
        guard let doc = selectedDocument,
              let runner = self.runner else { return }

        // CRITICAL: Set immutable state FIRST, before async work
        // This ensures targetTextForReplacement is set once and never mutates
        await MainActor.run {
            self.targetTextForReplacement = spanText  // IMMUTABLE for this edit session
            self.editingPageIndex = pageIndex
        }

        let path = doc.currentURL.path
        let pageNum = pageIndex + 1

        do {
            // Add 5-second timeout to prevent hanging on complex/colored text
            let result = try await withThrowingTaskGroup(of: (success: Bool, blockBbox: [Double], spans: [[String: Any]], message: String).self) { group in
                // Task 1: The actual getBlockSpans call
                group.addTask {
                    return try await Task.detached(priority: .userInitiated) {
                        return try runner.getBlockSpans(
                            inputPath: path,
                            pageNumber: pageNum,
                            spanText: spanText
                        )
                    }.value
                }

                // Task 2: Timeout watchdog (5 seconds)
                group.addTask {
                    try await Task.sleep(nanoseconds: 5_000_000_000)
                    logger.warning("getBlockSpans timed out after 5s - text may have complex styling")
                    return (success: false, blockBbox: [], spans: [], message: "Timeout: Text block is too complex. Try selecting a smaller area.")
                }

                // Return the first one to complete
                guard let result = try await group.next() else {
                    throw NSError(domain: "TaskGroup", code: -1,
                                  userInfo: [NSLocalizedDescriptionKey: "TaskGroup returned no result"])
                }
                group.cancelAll()
                return result
            }

            await MainActor.run {
                if result.success {
                    // Populate block data
                    self.blockBbox = result.blockBbox

                    // Convert dictionaries to SpanInfo objects
                    self.editingSpans = result.spans.map { SpanInfo(from: $0) }

                    // Set detected font from first span
                    self.detectedFont = self.editingSpans.first?.font

                    // Show editor
                    self.showEditSheet = true

                    logger.info("Loaded block with \(self.editingSpans.count) spans")
                } else {
                    logger.error("Failed to get block spans: \(result.message)")
                    // Fallback to line mode on failure
                    self.continueLineSelection(text: spanText, pageIndex: pageIndex)
                }
            }
        } catch {
            await MainActor.run {
                logger.error("Error fetching block spans: \(error)")
                self.continueLineSelection(text: spanText, pageIndex: pageIndex)
            }
        }
    }
    
    func handleLineDoubleClick(text: String, pageIndex: Int) {
        // Reset state
        self.targetTextForReplacement = text  // IMMUTABLE: Used for all replacements
        self.editingText = text  // Mutable: User can modify
        self.editingPageIndex = pageIndex
        self.editingSpans = [] // Clear previous spans
        
        // CRITICAL: Cancel any running font search (from the preceding single click)
        // This prevents race conditions where single-click Python task blocks double-click Python task
        self.fontSearchTask?.cancel() 
        
        // Cancel any stale preview state
        if self.isShowingPreview {
            self.cancelPreview()
        }
        
        // Auto-detect Paragraph mode if selection is multi-line
        // This ensures Rich Text editing is used for blocks even if toggle wasn't set
        if text.contains("\n") && self.selectionMode != "paragraph" {
            self.selectionMode = "paragraph"
        }
        
        // If in Paragraph selection mode, fetch rich text spans
        if self.selectionMode == "paragraph" {
            // Processing...
            // Offload to loading task handles the UI transition
            Task {
                await self.fetchBlockSpans(spanText: text, pageIndex: pageIndex)
            }
            return
        }
        
        // Line Mode: Standard setup
        if self.detectedFont == nil || self.editingText != text {
            self.detectedFont = nil
            // Start fresh analysis
            self.originalDetectedFont = self.lookupOriginalFontFromHistory(text: text, pageIndex: pageIndex)
            Task { await self.startInteractiveFontSearch(text: text, pageIndex: pageIndex) }
        }
        self.showEditSheet = true
    }

    // MARK: - Nudges
    
    func nudge(direction: String, amount: Double) {
        guard !editingText.isEmpty else { return }

        // Step 1: Accumulate the delta immediately — updates the UI label on every tick
        // with no Python involved, giving instant visual feedback during hold-to-repeat.
        switch direction {
        case "up":        manualOverrides.yOffset -= amount
        case "down":      manualOverrides.yOffset += amount
        case "left":      manualOverrides.xOffset -= amount
        case "right":     manualOverrides.xOffset += amount
        case "size_up":   manualOverrides.sizeDelta += amount
        case "size_down": manualOverrides.sizeDelta -= amount
        case "kern_up":   manualOverrides.trackingDelta += amount
        case "kern_down": manualOverrides.trackingDelta -= amount
        case "font_change":
            break // Already applied via UI binding; fall through to debounced replacement
        default: return
        }

        // Step 2: Debounce the Python replacement — cancel any in-flight debounce and
        // schedule a fresh one.  Only the final tick (when the user releases the button)
        // actually reaches performReplacement, so rapid hold-repeats never pile up.
        nudgeDebounceTask?.cancel()
        nudgeDebounceTask = Task { @MainActor [weak self] in
            guard let self else { return }
            try? await Task.sleep(nanoseconds: 200_000_000) // 200 ms quiet period
            guard !Task.isCancelled else { return }
            guard !self.editingText.isEmpty,
                  let docURL = self.selectedDocument?.currentURL else { return }

            let inputURL: URL
            let searchText: String
            if let existing = self.lastEdit,
               existing.targetText == self.targetTextForReplacement,
               FileManager.default.isReadableFile(atPath: existing.inputURL.path) {
                inputURL = existing.inputURL
                searchText = self.targetTextForReplacement
            } else {
                inputURL = docURL
                searchText = self.editingText
            }

            await self.performReplacement(
                inputURL: inputURL,
                targetText: searchText,
                replacementText: self.editingText,
                pageIndex: self.editingPageIndex,
                overrides: self.manualOverrides,
                showLoading: false
            )
        }
    }



    // MARK: - Interactive Font Search
    
    func startInteractiveFontSearch(text: String, pageIndex: Int) async {
        // Return if empty
        guard !text.isEmpty else { return }

        // Cancel any existing search to prevent race conditions/hangs
        fontSearchTask?.cancel()
        fontSearchTask = nil
        
        guard let runner = self.runner else { return }
        guard let doc = selectedDocument else { return }
        
        let inputPath = doc.currentURL.path
        let exhaustive = UserDefaults.standard.bool(forKey: "exhaustiveFontSearch")
        
        // Cache key includes document ID, pageIndex, and exhaustive flag
        // This prevents cache pollution across different documents with same text
        let docKey = selectedDocID?.uuidString ?? "unknown"
        let cacheKey = "\(docKey)|\(text)|\(pageIndex)|\(exhaustive ? "exhaustive" : "common")"
        
        // CHECK CACHE FIRST (Optimize: Avoid redundant identification if we matched this before)
        if let cached = fontSearchResults[cacheKey], !cached.isEmpty, let best = cached.first {
             print("[FontSearch] Using cached results for key: \(cacheKey)")
             self.detectedFontName = best.path + "|" + best.name
             let scorePercent = Int(best.score * 100)
             
             if let source = best.source {
                 self.detectedFont = "\(best.name) (\(source))"
             } else {
                 self.detectedFont = "\(best.name) (Visual Match: \(scorePercent)%)"
             }
             
             self.isSearchingFonts = false
             self.searchProgress = 1.0
             self.searchingFontName = "Complete (Cached)"
             return
        }
        
        // Already on MainActor since class is @MainActor
        
        print("[FontSearch] Starting search: textLength=\(text.count)")

        // Set initial search state synchronously - we're already on MainActor
        // and EditLineView hasn't finished appearing yet, so this is safe
        self.isSearchingFonts = true
        self.searchProgress = 0.0
        self.searchingFontName = "Identifying original font..."
        self.originalDetectedFont = "Identifying..."
        self.detectedFont = "Analyzing..."
        
        // Step 1: First identify the actual PDF font (fast operation)
        // This gives us the accurate "Original Font" information
        // Always run this to ensure we have current font info (not stale "Loading...")
        
        // Wrap the entire sequence in a tracked task
        fontSearchTask = Task { [weak self] in
            guard let self = self else { return }
            if Task.isCancelled { return }

                logger.info("Font search: Starting for textLength=\(text.count) on page \(pageIndex)")

            do {
                let pageNum = pageIndex + 1

                logger.info("Font search: Calling identifyFont...")
                // Use detached task for the blocking Python call
                let fontInfo = try await Task.detached { [runner, inputPath, pageNum, text] in
                    return try runner.identifyFont(inputPath: inputPath, pageNumber: pageNum, targetText: text)
                }.value
                logger.info("Font search: identifyFont completed successfully")

                // Process the actual PDF font info
                if let success = fontInfo["success"] as? Bool, success,
                   var name = fontInfo["fontname"] as? String,
                   let size = fontInfo["fontsize"] as? Double {

                    // Map base-14 abbreviation to full name
                    if name == "cour" { name = "Courier" }
                    else if name == "helv" { name = "Helvetica" }
                    else if name == "tiro" { name = "Times Roman" }
                    else if name == "symb" { name = "Symbol" }
                    else if name == "zapf" { name = "Zapf Dingbats" }
                    // Handle problematic embedded fonts with clearer labels
                    else if name.lowercased().contains("allandnone") {
                        name = "Embedded (subset font)"
                    }
                    else if name.contains("+") {
                        // Subset fonts often have patterns like ABCDEF+FontName
                        let parts = name.components(separatedBy: "+")
                        if parts.count > 1 {
                            name = "Embedded: \(parts[1])"
                        }
                    }

                    self.originalDetectedFont = String(format: "%@ - %.1f pt", name, size)
                    logger.info("Font search: Original font identified as \(name)")

                    // OPTIMIZATION: Check if this is a known system font we can use directly
                    let knownSystemFonts = [
                        "helvetica", "helvetica-bold", "helvetica-oblique",
                        "times", "times-roman", "times-bold", "times-italic",
                        "courier", "courier-bold", "courier-oblique",
                        "arial", "arial-bold", "arial-italic"
                    ]

                    let normalizedName = name.lowercased()
                        .replacingOccurrences(of: " ", with: "-")
                        .replacingOccurrences(of: "psmt", with: "")
                        .replacingOccurrences(of: "ps-", with: "-")

                    if knownSystemFonts.contains(normalizedName) || normalizedName.contains("helvetica") || normalizedName.contains("times") || normalizedName.contains("arial") {
                        // This is a system font - use it directly without visual matching
                        logger.info("Font search: '\(name)' is a known system font - skipping visual matching")
                        self.detectedFont = "\(name) (System Font)"
                        self.detectedFontName = "system|\(name)"
                        self.isSearchingFonts = false
                        self.searchProgress = 1.0
                        self.searchingFontName = "Complete"

                        // Cache this result
                        let results = [FontSearchResult(name: name, path: "system", score: 1.0, source: "System Font")]
                        self.storeFontSearchResults(results, for: cacheKey)

                        logger.info("Font search: Complete (system font, instant)")
                        return  // DONE - skip visual matching entirely
                    }
                } else {
                    // OCR Detection: If font identification fails, it may be an OCR/scanned PDF
                    // Stop early with a fallback message instead of running long visual matching
                    let message = fontInfo["message"] as? String ?? ""

                    if message.contains("Text not found") || message.contains("not found") {
                        // OCR document - text exists visually but not in PDF text layer
                        self.originalDetectedFont = "OCR Document (No Embedded Font)"
                        self.detectedFont = "OCR Document (No Embedded Font)"
                        self.isSearchingFonts = false
                        self.searchProgress = 1.0
                        self.searchingFontName = "Complete (OCR detected)"

                        // Cache a Helvetica fallback for OCR documents
                        let results = [FontSearchResult(name: "Helvetica", path: "helv", score: 0.8, source: "OCR Fallback")]
                        self.storeFontSearchResults(results, for: cacheKey)

                        logger.info("Font search: OCR document detected - using Helvetica fallback")
                        return  // DONE - skip visual matching for OCR
                    }

                    self.originalDetectedFont = "Unknown embedded font"
                    logger.warning("Font search: Font info returned success=false or missing fields")
                }
            } catch {
                self.originalDetectedFont = "Unable to identify font: \(error.localizedDescription)"
                logger.error("Font identification failed: \(error)")
            }

            // Step 2: Run font search (only for non-system fonts)
            logger.info("Font search: Not a known system font, running visual matching...")
            self.searchingFontName = "Searching for font match..."

        do {
            logger.info("Font search: Calling findFontInteractive")

            // Add timeout to prevent hanging (30 seconds max)
            let timeout: TimeInterval = 30.0
            let searchStarted = Date()

            // Wrap in detached task to avoid blocking MainActor
            // Use nonisolated closure to avoid data race on progress tracking
            let result = try await withThrowingTaskGroup(of: [String: Any]?.self) { group in
                // Task 1: The actual font search
                group.addTask {
                    try await Task.detached { [weak self, runner, inputPath, text, pageIndex, exhaustive] in
                        // Thread-safe progress tracking using atomic-like pattern
                        // Progress updates are dispatched to MainActor where actual state is managed
                        var lastProgress: Double = 0.0

                        return try runner.findFontInteractive(
                            inputPath: inputPath,
                            pageIndex: pageIndex,
                            text: text,
                            exhaustive: exhaustive
                        ) { msg, progress in
                            // Check for cancellation before updating UI
                            guard !Task.isCancelled else { return }

                            // Throttle: only dispatch if progress changed by at least 2%
                            if progress - lastProgress >= 0.02 || progress >= 1.0 {
                                lastProgress = progress
                                Task { @MainActor in
                                    guard !Task.isCancelled else { return }
                                    self?.searchingFontName = msg
                                    self?.searchProgress = progress
                                }
                            }
                        }
                    }.value
                }

                // Task 2: Timeout watchdog
                group.addTask {
                    try await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                    logger.warning("Font search timed out after \(timeout)s")
                    return ["success": false, "message": "Search timed out - using interim font"]
                }

                // Return the first one to complete
                guard let result = try await group.next() else {
                    throw NSError(domain: "TaskGroup", code: -1,
                                  userInfo: [NSLocalizedDescriptionKey: "TaskGroup returned no result"])
                }
                group.cancelAll()
                return result
            }

            logger.info("Font search: findFontInteractive completed in \(Date().timeIntervalSince(searchStarted))s")

            // Parse result on MainActor
            if let result = result, let success = result["success"] as? Bool, success {
                var results: [FontSearchResult] = []
                let sourceLabel = result["source"] as? String

                if let candidates = result["candidates"] as? [[String: Any]] {
                    for c in candidates {
                        if let name = c["name"] as? String,
                           let path = c["path"] as? String,
                           let score = c["score"] as? Double {
                            results.append(FontSearchResult(name: name, path: path, score: score, source: sourceLabel))
                        }
                    }
                } else if let best = result["best_match"] as? [String: Any],
                          let name = best["name"] as? String,
                          let path = best["path"] as? String,
                          let score = best["score"] as? Double {
                    results.append(FontSearchResult(name: name, path: path, score: score, source: sourceLabel))
                }

                // Only cache non-empty results (empty results should trigger re-search)
                if !results.isEmpty {
                    self.storeFontSearchResults(results, for: cacheKey)
                    print("[FontSearch] Stored \(results.count) results for cacheKey: \(cacheKey)")

                    // Notify that font search completed - allows preview to update with matched font
                    NotificationCenter.default.post(
                        name: .fontSearchCompleted,
                        object: nil,
                        userInfo: ["cacheKey": cacheKey]
                    )
                } else {
                    print("[FontSearch] No results found, not caching for: \(cacheKey)")
                }

                if let best = results.first {
                    self.detectedFontName = best.path + "|" + best.name
                    // Update the Current Font display
                    let scorePercent = Int(best.score * 100)

                    if let source = result["source"] as? String {
                        // Use accurate source label (e.g. "System Font (Name Match)")
                        self.detectedFont = "\(best.name) (\(source))"
                    } else {
                        // Fallback for purely visual matches
                        self.detectedFont = "\(best.name) (Visual Match: \(scorePercent)%)"
                    }
                    // Note: Do NOT overwrite originalDetectedFont - that contains the actual PDF font info
                }
                self.isSearchingFonts = false
                self.searchProgress = 1.0
                self.searchingFontName = "Complete"
            } else {
                // Handle failure - show error message if available
                if let result = result, let message = result["message"] as? String {
                    self.searchingFontName = "Error: \(message)"
                } else {
                    self.searchingFontName = "Search failed"
                }
                self.isSearchingFonts = false
                self.searchProgress = 0.0
            }

        } catch {
            logger.error("Interactive font search failed: \(error.localizedDescription)")
            self.searchingFontName = "Error: \(error.localizedDescription)"
            self.isSearchingFonts = false
            self.searchProgress = 0.0
        }
        } // End of fontSearchTask
    }
    
    /// Cancel an ongoing font search
    func cancelFontSearch() {
        fontSearchTask?.cancel()
        fontSearchTask = nil
        isSearchingFonts = false
        searchProgress = 0.0
        searchingFontName = ""
        print("[FontSearch] Search cancelled by user")
    }



    
    func replaceText(original: String, newText: String, pageIndex: Int) async {
        if isProcessing {
            LogManager.shared.log("replaceText: already processing, ignoring")
            return
        }
        isProcessing = true
        LogManager.shared.log("replaceText: starting replacement page=\(pageIndex), originalLength=\(original.count), replacementLength=\(newText.count)")


        // Wrap work in a task we can explicitly cancel via UI button
        let docIDSnapshot = selectedDocID
        self.processingTask = Task {
             defer {
                 // Only clear processing flag if we're still on the same document
                 if self.selectedDocID == docIDSnapshot {
                     LogManager.shared.log("replaceText: task defer - isProcessing=false, processingTask=nil")
                     self.isProcessing = false
                     self.processingTask = nil
                 } else {
                     LogManager.shared.log("replaceText: task defer - document changed, keeping processing state")
                 }
             }

             // Resolve document URL before calling replacement
             guard let docID = self.selectedDocID,
                   let doc = self.documents.first(where: { $0.id == docID }) else {
                 LogManager.shared.log("replaceText: document not found, aborting")
                 return
             }

             await self.performReplacement(
                inputURL: doc.currentURL,
                targetText: original,
                replacementText: newText,
                pageIndex: pageIndex,
                overrides: self.manualOverrides
             )
        }
    }
    
    private func performReplacement(
        inputURL: URL,
        targetText: String,
        replacementText: String,
        pageIndex: Int,
        overrides: ManualOverrides,
        showLoading: Bool = true,
        isPreview: Bool = false
    ) async {
        guard let id = selectedDocID, let _ = documents.firstIndex(where: { $0.id == id }) else { return }
        
        guard let runner = self.runner else {
            self.errorMessage = "Python runtime not initialized"
            return
        }
        
        do {
            // Generate distinct output URL to avoid file locking issues
            let uuid = UUID().uuidString.prefix(8)
            let outputDirectory: URL
            if CommandLine.arguments.contains("--run-ui-tests"),
               let testOutputDir = UserDefaults.standard.string(forKey: "uitest.outputDir") {
                outputDirectory = URL(fileURLWithPath: testOutputDir, isDirectory: true)
                try? FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
            } else {
                outputDirectory = FileManager.default.temporaryDirectory
            }
            let outputURL = outputDirectory.appendingPathComponent("marcedit_edit_\(uuid).pdf")

            // BUG #41 FIX: Ensure temp file is cleaned up on error paths
            // Track whether we successfully handed the temp file to the document
            var shouldCleanupTempFile = true
            defer {
                if shouldCleanupTempFile {
                    cleanupTempFile(outputURL)
                }
            }

            // Security-scoped access is only needed for user-selected files
            // Temp files (from previous edits/previews) don't need security scoping
            let isTempFile = inputURL.isTemporaryFile
            LogManager.shared.log("performReplacement: inputURL='\(inputURL.lastPathComponent)', isTempFile=\(isTempFile)")
            let hasAccess = isTempFile ? false : inputURL.startAccessingSecurityScopedResource()
            defer { if hasAccess { inputURL.stopAccessingSecurityScopedResource() } }
            LogManager.shared.log("performReplacement: hasAccess=\(hasAccess)")

            // For non-temp files, verify we have security-scoped access
            // For temp files, verify the file exists and is readable
            if !isTempFile && !hasAccess {
                LogManager.shared.log("performReplacement: ERROR - Cannot access non-temp file (no security scope)")
                self.errorMessage = "Cannot access file: permission denied"
                return
            }
            if isTempFile && !FileManager.default.isReadableFile(atPath: inputURL.path) {
                LogManager.shared.log("performReplacement: ERROR - Temp file not readable")
                self.errorMessage = "Cannot access temp file: file not found or not readable"
                return
            }
            LogManager.shared.log("performReplacement: Access OK, proceeding with replacement")
            
            let inputPath = inputURL.path
            let outputPath = outputURL.path
            let pageNum = pageIndex + 1 // 1-based for Python
            
            // Flags for font style matching
            var dict: [String: Any] = [:]
            dict["manual_size_delta"] = overrides.sizeDelta
            dict["manual_x_offset"] = overrides.xOffset
            dict["manual_y_offset"] = overrides.yOffset
            dict["manual_tracking_delta"] = overrides.trackingDelta
            if let j = overrides.justification { dict["justification"] = j }
            // Python reads "manual_font", not "font_name" — use the correct key.
            if let f = overrides.fontName { dict["manual_font"] = f }
            if overrides.isBold { dict["is_bold"] = true }
            if overrides.isItalic { dict["is_italic"] = true }
            if overrides.skipVisualMatching { dict["skip_visual_matching"] = true }
            if overrides.smartQuotes { dict["smart_quotes"] = true }
            if self.allowCollisionOverrun { dict["skip_collision"] = true }
            // Fill color for redaction (nil = transparent; UI picker in FontOverrideControls)
            if let fc = overrides.fillColor { dict["fill_color"] = fc }
            // Exhaustive font search: honour the global preference set in app Settings
            if UserDefaults.standard.bool(forKey: "exhaustiveFontSearch") { dict["exhaustive_search"] = true }

            // PERF: If Swift's background font search already identified the font, pass it
            // directly so Python can skip its own expensive visual-matching phase.
            // Only applies when the user hasn't manually chosen a different font.
            // detectedFontName format: "/path/to/font.ttf|PostScriptName" or "system|Name"
            // Python's manual_font format: "/path/to/font.ttf|PSName" or "helv"/"cour"/"tiro"
            if overrides.fontName == nil, let detected = self.detectedFontName, !detected.isEmpty {
                if detected.hasPrefix("system|") {
                    // Map common system font names to PyMuPDF built-in identifiers
                    let baseName = String(detected.dropFirst("system|".count))
                        .components(separatedBy: "-").first ?? ""
                    let builtins: [String: String] = [
                        "Helvetica": "helv", "Arial": "helv",
                        "Times": "tiro",
                        "Courier": "cour",
                        "Symbol": "symb",
                        "ZapfDingbats": "zadb"
                    ]
                    if let builtin = builtins[baseName] {
                        dict["manual_font"] = builtin
                    }
                } else if detected.contains("|") {
                    // "/path/to/font.ttf|PostScriptName" — Python accepts this format directly
                    dict["manual_font"] = detected
                }
            }

            // Run replacement via Python with timeout protection
            // Using Task.detached to avoid blocking UI during heavy PDF processing
            let result = try await withThrowingTaskGroup(of: (success: Bool, modified: Bool, message: String, appliedInfo: [String: Any]?, substitutionWarning: String?).self) { group in
                // Task 1: The actual replacement
                group.addTask {
                    return try await Task.detached {
                        try runner.replaceTextInPDF(
                            inputPath: inputPath,
                            outputPath: outputPath,
                            targetText: targetText,
                            replacementText: replacementText,
                            pageNumber: pageNum,
                            manualOverrides: dict.isEmpty ? nil : dict
                        )
                    }.value
                }

                // Task 2: Timeout watchdog (30 seconds)
                group.addTask {
                    try await Task.sleep(nanoseconds: 30_000_000_000)
                    logger.warning("Text replacement timed out after 30s")
                    return (success: false, modified: false, message: "Replacement timed out - text may be too complex", appliedInfo: nil, substitutionWarning: nil)
                }

                // Return the first one to complete
                guard let result = try await group.next() else {
                    throw NSError(domain: "TaskGroup", code: -1,
                                  userInfo: [NSLocalizedDescriptionKey: "TaskGroup returned no result"])
                }
                group.cancelAll()
                return result
            }
             
            // Check cancellation before applying
            if Task.isCancelled { return }

            await MainActor.run {
                // RACE CONDITION FIX: If this was a preview but preview mode was cancelled
                // while we were processing, DO NOT apply the result - it would overwrite the restored state.
                if isPreview && !self.isShowingPreview {
                    logger.info("performReplacement: Preview finished but mode was cancelled - discarding result")
                    return
                }
                
                if result.success {
                    LogManager.shared.log("Edit success - modified: \(result.modified)")

                    if isPreview {
                        self.previewStatus = .success(warnings: result.substitutionWarning)
                    }

                    // Update Document using map-based pattern to avoid index invalidation
                    if let id = self.selectedDocID {
                        LogManager.shared.log("performReplacement: Updating document with id=\(id)")

                        self.documents = self.documents.map { doc in
                            guard doc.id == id else { return doc }
                            var updatedDoc = doc
                            LogManager.shared.log("performReplacement: BEFORE update")

                            if updatedDoc.currentURL != updatedDoc.originalURL {
                                self.cleanupTempFile(updatedDoc.currentURL)
                            }
                            updatedDoc.currentURL = outputURL
                            updatedDoc.isDirty = true
                            // BUG #41 FIX: Temp file successfully handed to document - don't clean up
                            shouldCleanupTempFile = false
                            LogManager.shared.log("performReplacement: AFTER update")
                            return updatedDoc
                        }

                        // Add to undo stack for each replacement (including preview)
                        let item = EditHistoryItem(
                            inputURL: inputURL,
                            outputURL: outputURL,
                            targetText: targetText,
                            replacementText: replacementText,
                            pageIndex: pageIndex,
                            overrides: overrides,
                            originalFontInfo: self.originalDetectedFont
                        )

                        if isPreview {
                            // Preview mode: Add to undo stack immediately
                            // This allows undo to work one edit at a time during preview
                            self.appendUndoHistory(item)
                            self.clearRedoHistory()
                            logger.info("Preview mode: Added to undo stack, reloading PDF to show changes")
                            // Reload PDF to show changes (preserveState keeps dialog open)
                            self.selectFile(id, preserveState: true)

                            // NOTE: We do NOT update targetTextForReplacement here!
                            // It remains the original text for the entire edit session.
                            // This allows multiple preview toggles to work correctly.
                        } else {
                            // Normal mode: Add to undo stack and reload
                            self.appendUndoHistory(item)
                            self.clearRedoHistory()
                            logger.info("Replacement complete, reloading PDF with preserved state")
                            self.selectFile(id, preserveState: true)

                            // NOTE: targetTextForReplacement stays IMMUTABLE (the original PDF text).
                            // Nudge/kern/size re-do the replacement from scratch using lastEdit.inputURL
                            // (which contains the original text), so we MUST keep the original search text.
                        }
                    } else {
                        LogManager.shared.log("performReplacement: ERROR - could not find document with id=\(self.selectedDocID?.uuidString ?? "nil")")
                    }

                    // Update logs/info if needed
                    if let info = result.appliedInfo {
                         // Extract font source for inline display
                         if let source = info["font_source"] as? String {
                             self.fontSourceInfo = source
                         }
                         logger.info("Applied Info: \(info)")
                    }
                    
                } else {
                    // Build a user-facing error string. If a search diagnostic is available,
                    // append an actionable summary so the user knows *why* the text wasn't found.
                    var displayMessage = result.message

                    if let appliedInfo = result.appliedInfo,
                       let diagnostic = appliedInfo["diagnostic"] as? [String: Any] {

                        logger.warning("Search diagnostic available with \(diagnostic.keys.count) fields")
                        LogManager.shared.log("SEARCH DIAGNOSTIC:")

                        var hints: [String] = []

                        // Which strategies ran and whether any found it
                        if let strategies = diagnostic["strategies_tried"] as? [[String: String]] {
                            for strategy in strategies {
                                LogManager.shared.log("  - \(strategy["name"] ?? ""): \(strategy["result"] ?? "")")
                            }
                            let allFailed = strategies.allSatisfy { ($0["result"] ?? "").hasPrefix("NO") || ($0["result"] ?? "").hasPrefix("SKIP") }
                            if allFailed {
                                hints.append("All \(strategies.count) search strategies failed")
                            }
                        }

                        if let unicodeSummary = diagnostic["unicode_summary"] as? [String: Any] {
                            let nonASCII = unicodeSummary["non_ascii_count"] as? Int ?? 0
                            let invisible = unicodeSummary["invisible_count"] as? Int ?? 0
                            let softHyphen = unicodeSummary["soft_hyphen_count"] as? Int ?? 0
                            let ligatures = unicodeSummary["ligature_count"] as? Int ?? 0
                            LogManager.shared.log("  Unicode summary: nonASCII=\(nonASCII), invisible=\(invisible), softHyphen=\(softHyphen), ligatures=\(ligatures)")

                            if nonASCII > 0 || invisible > 0 || softHyphen > 0 || ligatures > 0 {
                                hints.append("Unusual character classes in selection: nonASCII=\(nonASCII), invisible=\(invisible), softHyphen=\(softHyphen), ligatures=\(ligatures)")
                            }
                        }

                        if !hints.isEmpty {
                            displayMessage += "\n\n" + hints.joined(separator: "\n")
                        }
                    }

                    if isPreview {
                        let msgLower = result.message.lowercased()
                        if msgLower.contains("collision") || msgLower.contains("overlap") {
                            let ratio: Double? = {
                                let pattern = #"(\d+\.?\d*)%"#
                                if let range = result.message.range(of: pattern, options: .regularExpression),
                                   let val = Double(result.message[range].dropLast()) {
                                    return val
                                }
                                return nil
                            }()
                            self.previewStatus = .collisionError(message: result.message, ratio: ratio)
                        } else {
                            self.previewStatus = .otherError(message: displayMessage)
                        }
                    } else {
                        self.errorMessage = "Edit failed: \(displayMessage)"
                    }
                }
            }

        } catch {
            if Task.isCancelled { return }
            let errorDetails = "\(error)"
            logger.error("Python error: \(errorDetails)")
            if isPreview {
                self.previewStatus = .otherError(message: "Edit failed: \(errorDetails)")
            } else {
                self.errorMessage = "Edit failed: \(errorDetails)"
            }
        }
    }
    private func performBlockReplacement(
        inputURL: URL,
        pageIndex: Int
    ) async {
        if isProcessing { return }
        isProcessing = true
        
        // Wrap in Task for cancellation support
        self.processingTask = Task {
             defer {
                 self.isProcessing = false
                 self.processingTask = nil
             }
            
            guard let runner = self.runner else {
                self.errorMessage = "Python runtime not initialized"
                return
            }
            
            do {
                // Generate distinct output URL
                let uuid = UUID().uuidString.prefix(8)
                let outputURL = FileManager.default.temporaryDirectory.appendingPathComponent("marcedit_block_\(uuid).pdf")

                // BUG #41 FIX: Ensure temp file is cleaned up on error paths
                var shouldCleanupTempFile = true
                defer {
                    if shouldCleanupTempFile {
                        cleanupTempFile(outputURL)
                    }
                }

                let isTempFile = inputURL.isTemporaryFile
                let hasAccess = isTempFile ? false : inputURL.startAccessingSecurityScopedResource()
                defer { if hasAccess { inputURL.stopAccessingSecurityScopedResource() } }

                if !isTempFile && !hasAccess {
                    self.errorMessage = "Cannot access file: permission denied"
                    return
                }
                if isTempFile && !FileManager.default.isReadableFile(atPath: inputURL.path) {
                    self.errorMessage = "Cannot access temp file: file not found"
                    return
                }

                let inputPath = inputURL.path
                let outputPath = outputURL.path
                let pageNum = pageIndex + 1
                
                // Prepare data for Python
                let blockBbox = self.blockBbox
                let spansDicts = self.editingSpans.map { span -> [String: Any] in
                    return [
                        "text": span.text,
                        "font": span.font,
                        "size": span.size,
                        "is_bold": span.isBold,
                        "is_italic": span.isItalic,
                        "color": span.color,
                        "bbox": span.bbox,
                        "line_index": span.lineIndex
                    ]
                }
                
                // Prepare overrides
                var overridesDict: [String: Any]? = nil
                var dict: [String: Any] = [:]
                dict["manual_size_delta"] = manualOverrides.sizeDelta
                dict["manual_x_offset"] = manualOverrides.xOffset
                dict["manual_y_offset"] = manualOverrides.yOffset
                dict["manual_tracking_delta"] = manualOverrides.trackingDelta
                if let j = manualOverrides.justification { dict["justification"] = j }
                if !dict.isEmpty { overridesDict = dict }

                // Check cancellation before expensive operation
                if Task.isCancelled { return }

                // Run replacement
                let result = try await Task.detached(priority: .userInitiated) {
                    return try runner.replaceBlockWithSpans(
                        inputPath: inputPath,
                        outputPath: outputPath,
                        pageNumber: pageNum,
                        blockBbox: blockBbox,
                        spans: spansDicts,
                        overrides: overridesDict
                    )
                }.value

                if Task.isCancelled { return }
                
                await MainActor.run {
                    if result.success {
                        LogManager.shared.log("Block Edit success: \(result.message)")
                        
                        // Update Document
                        if let id = self.selectedDocID, let idx = self.documents.firstIndex(where: { $0.id == id }) {
                            var doc = self.documents[idx]
                            if doc.currentURL != doc.originalURL {
                                self.cleanupTempFile(doc.currentURL)
                            }
                            doc.currentURL = outputURL
                            doc.isDirty = true
                            // BUG #41 FIX: Temp file successfully handed to document - don't clean up
                            shouldCleanupTempFile = false
                            self.documents[idx] = doc

                            // Directly reload PDF view to reflect changes
                            logger.info("Block replacement complete, reloading PDF with preserved state")
                            self.selectFile(id, preserveState: true)
                        }
                        
                        // Update History
                        let item = EditHistoryItem(
                            inputURL: inputURL,
                            outputURL: outputURL,
                            targetText: "Block Edit",
                            replacementText: "Block Edit",
                            pageIndex: pageIndex,
                            overrides: self.manualOverrides,
                            originalFontInfo: nil
                        )
                        self.appendUndoHistory(item)
                        self.clearRedoHistory()
                        
                    } else {
                        self.errorMessage = "Block edit failed: \(result.message)"
                    }
                }
            } catch {
                if !Task.isCancelled {
                    let errorDetails = "\(error)"
                    logger.error("Python error: \(errorDetails)")
                    self.errorMessage = "Edit failed: \(errorDetails)"
                }
            }
        }
    }
    
    // Apply overrides to currently selected text spans (Paragraph mode)
    func applyOverridesToSelection() {
        guard selectionMode == "paragraph", !editingSpans.isEmpty else { return }
        let selection = selectedTextRange
        if selection.length == 0 { return }
        
        var newSpans: [SpanInfo] = []
        var currentPos = 0
        
        for span in editingSpans {
            let nsText = span.text as NSString
            let spanLen = nsText.length
            let spanRange = NSRange(location: currentPos, length: spanLen)
            let intersection = NSIntersectionRange(selection, spanRange)
            
            if intersection.length > 0 {
                // Determine cut points relative to span
                // Intersection is in global coords. Convert to local.
                let relativeStart = intersection.location - currentPos
                let relativeLength = intersection.length
                
                // Parts
                var parts: [SpanInfo] = []
                
                // 1. Prefix (unchanged)
                if relativeStart > 0 {
                    let prefixRange = NSRange(location: 0, length: relativeStart)
                    var prefix = span
                    prefix.id = UUID()
                    prefix.text = nsText.substring(with: prefixRange)
                    parts.append(prefix)
                }
                
                // 2. Middle (modified)
                var middle = span
                middle.id = UUID()
                let middleRange = NSRange(location: relativeStart, length: relativeLength)
                middle.text = nsText.substring(with: middleRange)
                
                // Apply Overrides
                if let f = manualOverrides.fontName { middle.font = f }
                if let s = manualOverrides.fontStyle {
                    middle.isBold = s.contains("Bold")
                    middle.isItalic = s.contains("Italic")
                }
                // Reset bbox to flow
                middle.bbox = [0, 0, 0, 0]
                
                parts.append(middle)
                
                // 3. Suffix (unchanged)
                let relativeEnd = relativeStart + relativeLength
                if relativeEnd < spanLen {
                    let suffixRange = NSRange(location: relativeEnd, length: spanLen - relativeEnd)
                    var suffix = span
                    suffix.id = UUID()
                    suffix.text = nsText.substring(with: suffixRange)
                    // Reset bbox for suffix too (will flow after middle)
                    suffix.bbox = [0, 0, 0, 0]
                    parts.append(suffix)
                }
                
                newSpans.append(contentsOf: parts)
                
            } else {
                newSpans.append(span)
            }
            
            currentPos += spanLen
        }
        
        self.editingSpans = newSpans
        
        LogManager.shared.log("Applied overrides to selection: \(selection)")
    }
    
    // MARK: - Document Actions
    
    func flattenCurrentDocument() async {
        guard let id = selectedDocID, 
              let idx = documents.firstIndex(where: { $0.id == id }) else { return }
        
        let doc = documents[idx]
        guard let runner = self.runner else { 
            self.errorMessage = "Python runtime not ready"
            return 
        }
        
        if isProcessing { return }
        isProcessing = true
        
        // Create temp output path
        let tempOut = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString + "_flattened.pdf")
        
        self.processingTask = Task {
             defer { 
                 self.isProcessing = false
                 self.processingTask = nil
             }
             
            do {
                // Run flattening in background
                let result = try await Task.detached(priority: .userInitiated) {
                    return try runner.flattenDocument(inputPath: doc.currentURL.path, outputPath: tempOut.path)
                }.value
                
                if Task.isCancelled { return }
                
                if result.success {
                    // Log detailed output
                    for log in result.logs {
                        print("Flatten: \(LogManager.sanitizeForLogging(log))")
                    }
                    LogManager.shared.log("Flattened document successfully")
                    
                    // Update document to point to new flattened file
                    await MainActor.run {
                        if let newIdx = self.documents.firstIndex(where: { $0.id == id }) {
                            var updatedDoc = self.documents[newIdx]
                            
                            // Cleanup old temp file if needed
                            if updatedDoc.currentURL != updatedDoc.originalURL {
                                 // Only cleanup if not in history stack (safety check)
                                let isReferenced = self.undoStack.contains { $0.inputURL == updatedDoc.currentURL || $0.outputURL == updatedDoc.currentURL }
                                if !isReferenced {
                                    self.cleanupTempFile(updatedDoc.currentURL)
                                }
                            }
                            
                            updatedDoc.currentURL = tempOut
                            updatedDoc.isDirty = true
                            self.documents[newIdx] = updatedDoc
                            
                            // Reload UI
                            self.selectFile(id, preserveState: true)
                        }
                    }
                    
                } else {
                    await MainActor.run {
                        self.errorMessage = "Flatten failed: \(result.message)"
                    }
                    logger.error("Flatten failed: \(result.message)")
                }
            } catch {
                if !Task.isCancelled {
                    await MainActor.run {
                        self.errorMessage = "Flattening error: \(error.localizedDescription)"
                    }
                    logger.error("Flattening exception: \(error)")
                }
            }
        }
    }
    
    // MARK: - Metadata & Checksums
    
    func calculateChecksum(for docID: UUID) {
        guard let idx = documents.firstIndex(where: { $0.id == docID }) else { return }
        let url = documents[idx].currentURL
        
        Task.detached(priority: .utility) {
            do {
                let handle = try FileHandle(forReadingFrom: url)
                defer { try? handle.close() }
                var hasher = Insecure.MD5()

                // Read in chunks to be memory efficient
                while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty {
                    hasher.update(data: data)
                }
                
                let digest = hasher.finalize()
                let md5String = digest.map { String(format: "%02hhx", $0) }.joined()
                
                await MainActor.run {
                     if let newIdx = self.documents.firstIndex(where: { $0.id == docID }) {
                         self.documents[newIdx].md5Checksum = md5String
                         
                         // Force update selected document binding if needed
                         if self.selectedDocID == docID {
                             self.objectWillChange.send()
                         }
                     }
                }
            } catch {
                logger.error("Failed to calculate MD5 for \(url.lastPathComponent): \(error)")
            }
        }
    }
    
    /// View metadata for current document
    /// If a scrub report exists for this document, shows that (before/after comparison).
    /// Otherwise extracts and displays current metadata.
    func viewCurrentDocumentMetadata() async {
        guard let id = selectedDocID,
              let idx = documents.firstIndex(where: { $0.id == id }),
              let runner = self.runner else { return }
        
        let doc = documents[idx]
        
        // Check if there's a saved scrub report for this document
        if let savedReportURL = lastScrubReportURLs[id],
           FileManager.default.fileExists(atPath: savedReportURL.path) {
            // Show saved scrub report in separate window (movable/resizable)
            await MainActor.run {
                ReportWindowController.openReportWindow(for: savedReportURL)
            }
            return
        }
        
        if isProcessing { return }
        isProcessing = true
        
        self.processingTask = Task {
             defer {
                 self.isProcessing = false
                 self.processingTask = nil
             }
             
             // Task wrapped to avoid blocking main actor
             // Note: using detached task for python op
             // Task wrapped to avoid blocking main actor
             // Note: using detached task for python op
             let result = await Task.detached(priority: .userInitiated) {
                 return runner.extractMetadata(inputPath: doc.currentURL.path)
             }.value
             
             if Task.isCancelled { return }
             
             if result.success, let html = result.reportHTML {
                 // Save report next to the PDF (same as Scrub)
                 let pdfDir = doc.originalURL.deletingLastPathComponent()
                 let pdfBaseName = doc.originalURL.deletingPathExtension().lastPathComponent
                 let reportPath = pdfDir.appendingPathComponent("\(pdfBaseName)_metadata_report.html")
                 
                 do {
                     try html.write(to: reportPath, atomically: true, encoding: .utf8)
                     
                     await MainActor.run {
                         ReportWindowController.openReportWindow(for: reportPath)
                     }
                 } catch {
                     if !Task.isCancelled {
                         await MainActor.run {
                             self.errorMessage = "Failed to save metadata report: \(error.localizedDescription)"
                         }
                     }
                 }
             } else {
                 if !Task.isCancelled {
                     await MainActor.run {
                         self.errorMessage = "Failed to extract metadata: \(result.error ?? "Unknown error")"
                     }
                 }
             }
        }
    }
    
    func scrubCurrentDocument() async {
        guard let id = selectedDocID, 
              let idx = documents.firstIndex(where: { $0.id == id }),
              let runner = self.runner else { return }
        
        let doc = documents[idx]
        self.isProcessing = true

        // Set up paths — scrub artifacts go to Application Support, NOT alongside
        // the source PDF (which would deposit cleartext extracted data in iCloud/TM).
        let tempOut = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString + "_scrubbed.pdf")
        let pdfBaseName = doc.originalURL.deletingPathExtension().lastPathComponent

        let appSupportBase: URL = {
            let fm = FileManager.default
            if let dir = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first {
                let marcEditDir = dir.appendingPathComponent("Marcedit/ScrubReports", isDirectory: true)
                try? fm.createDirectory(at: marcEditDir, withIntermediateDirectories: true)
                return marcEditDir
            }
            return URL(fileURLWithPath: NSTemporaryDirectory())
        }()
        let sessionID = UUID().uuidString.prefix(8)
        let dataDir = appSupportBase.appendingPathComponent("\(pdfBaseName)_\(sessionID)_scrub_data")
        let reportPath = appSupportBase.appendingPathComponent("\(pdfBaseName)_\(sessionID)_scrub_report.html")

        self.processingTask = Task {
            defer {
                self.isProcessing = false
                self.processingTask = nil
            }

            // Task wrapped to avoid blocking main actor
            // Note: using detached task for python op
            let result = await Task.detached(priority: .userInitiated) {
                return runner.scrubMetadata(
                    inputPath: doc.currentURL.path,
                    outputPath: tempOut.path,
                    dataDir: dataDir.path
                )
            }.value

            if Task.isCancelled { return }

            if result.success {
                // Save HTML report
                if let html = result.reportHTML {
                    do {
                        try html.write(to: reportPath, atomically: true, encoding: .utf8)
                        LogManager.shared.log("Scrub report saved")
                    } catch {
                        LogManager.shared.log("Failed to save scrub report: \(error)")
                    }
                }

                await MainActor.run {
                    if let newIdx = self.documents.firstIndex(where: { $0.id == id }) {
                        var updatedDoc = self.documents[newIdx]

                        // Cleanup old temp
                        if updatedDoc.currentURL != updatedDoc.originalURL {
                            let isReferenced = self.undoStack.contains { $0.inputURL == updatedDoc.currentURL || $0.outputURL == updatedDoc.currentURL }
                            if !isReferenced {
                                self.cleanupTempFile(updatedDoc.currentURL)
                            }
                        }

                        updatedDoc.currentURL = tempOut
                        updatedDoc.isDirty = true
                        self.documents[newIdx] = updatedDoc

                        // Reload and Recalculate MD5
                        self.selectFile(id, preserveState: true)
                        self.calculateChecksum(for: id)

                        LogManager.shared.log("Metadata scrubbed successfully")

                        // Save report path for View button (don't auto-open)
                        self.lastScrubReportURLs[id] = reportPath
                        // Save data dir path so secureErase can find it regardless of session ID
                        self.lastScrubDataDirURLs[id] = dataDir

                        // Surface any non-fatal warnings from the scrub
                        if !result.warnings.isEmpty {
                            for w in result.warnings {
                                LogManager.shared.log("Scrub warning: \(w)")
                            }
                            self.scrubWarningMessage = "Scrub completed with warnings — see report for details."
                        }
                    }
                }
            } else {
                await MainActor.run {
                    self.errorMessage = "Scrub failed: \(result.message)"
                }
            }
        }
    }
    
    /// Erase all traces of the current document with best-effort multi-pass overwrite.
    /// Targets: original PDF, modified/temp PDF, scrub report + data dir, undo/redo history.
    func secureEraseCurrentDocument() async {
        guard let id = selectedDocID,
              let initialIdx = documents.firstIndex(where: { $0.id == id }) else { return }

        let doc = documents[initialIdx]

        // Secure erase is intentionally non-cancellable — destroying and overwriting files
        // is irreversible; partial completion would leave inconsistent state.
        // The Cancel button is suppressed while erasing (isErasureInProgress == true).
        // DO NOT assign to processingTask — that would make it cancellable via cancelProcessing().
        self.isProcessing = true
        self.isErasureInProgress = true

        // Snapshot undo/redo stacks before entering the task (they live on MainActor)
        let undoSnapshot = undoStack
        let redoSnapshot = redoStack

        // Use an unassigned local Task so it is never reachable via processingTask/cancelProcessing.
        Task {
            defer {
                self.isProcessing = false
                self.isErasureInProgress = false
            }

            var filesToErase: [URL] = []
            var directoriesToErase: [URL] = []

            // 1. Original PDF
            filesToErase.append(doc.originalURL)

            // 2. Current/modified PDF (if different from original)
            if doc.currentURL != doc.originalURL {
                filesToErase.append(doc.currentURL)
            }

            // 3. Scrub report
            if let reportURL = lastScrubReportURLs[id] {
                filesToErase.append(reportURL)
            }

            // 4. Scrub data directory (use the saved path so the session-ID suffix matches)
            if let dataDir = lastScrubDataDirURLs[id] {
                if FileManager.default.fileExists(atPath: dataDir.path) {
                    directoriesToErase.append(dataDir)
                }
            }

            // 5. All undo/redo history files for this document
            for item in undoSnapshot {
                if item.inputURL != doc.originalURL && item.inputURL != doc.currentURL {
                    filesToErase.append(item.inputURL)
                }
                if item.outputURL != doc.originalURL && item.outputURL != doc.currentURL {
                    filesToErase.append(item.outputURL)
                }
            }
            for item in redoSnapshot {
                if item.inputURL != doc.originalURL && item.inputURL != doc.currentURL {
                    filesToErase.append(item.inputURL)
                }
                if item.outputURL != doc.originalURL && item.outputURL != doc.currentURL {
                    filesToErase.append(item.outputURL)
                }
            }

            // Deduplicate
            let uniqueFiles = Array(Set(filesToErase))

            // Perform secure erase — runs to completion regardless of any cancel request.
            let (erasedCount, errorMessages) = await Task.detached(priority: .userInitiated) { [uniqueFiles, directoriesToErase] in
                var count = 0
                var errors: [String] = []

                // Erase files
                for url in uniqueFiles {
                    do {
                        if FileManager.default.fileExists(atPath: url.path) {
                            try await secureErase(at: url)
                            count += 1
                        }
                    } catch {
                        errors.append("Failed to erase \(url.lastPathComponent): \(error.localizedDescription)")
                    }
                }

                // Erase directories
                for dir in directoriesToErase {
                    do {
                        try await secureEraseDirectory(at: dir)
                        count += 1
                    } catch {
                        errors.append("Failed to erase directory \(dir.lastPathComponent): \(error.localizedDescription)")
                    }
                }

                return (count, errors)
            }.value

            // No Task.isCancelled check here — erase must always run to completion.

            await MainActor.run {
                // Clear history for this document
                self.undoStack.removeAll { $0.inputURL == doc.originalURL || $0.inputURL == doc.currentURL ||
                                            $0.outputURL == doc.originalURL || $0.outputURL == doc.currentURL }
                self.redoStack.removeAll { $0.inputURL == doc.originalURL || $0.inputURL == doc.currentURL ||
                                            $0.outputURL == doc.originalURL || $0.outputURL == doc.currentURL }

                // Remove scrub report and data dir references
                self.lastScrubReportURLs.removeValue(forKey: id)
                self.lastScrubDataDirURLs.removeValue(forKey: id)

                // Remove document from list (re-fetch index since array may have changed during await)
                if let currentIdx = self.documents.firstIndex(where: { $0.id == id }) {
                    self.documents.remove(at: currentIdx)
                }

                // Select next document or clear selection
                if let first = self.documents.first {
                    self.selectFile(first.id)
                } else {
                    self.selectedDocID = nil
                    self.selectedPDF = nil
                }

                if errorMessages.isEmpty {
                    LogManager.shared.log("Secure erase complete: \(erasedCount) items destroyed")
                } else {
                    self.errorMessage = "Some files could not be erased:\n\(errorMessages.joined(separator: "\n"))"
                }
            }
        }
    }
    
    func attemptToCloseApp() {
        if documents.contains(where: { $0.isDirty }) {
            self.pendingCloseAction = { NSApplication.shared.terminate(nil) }
            self.showUnsavedAlert = true
        } else {
            NSApplication.shared.terminate(nil)
        }
    }

    private func cleanupTempFile(_ url: URL) {
        // SAFETY: Don't delete if URL is still referenced in undo/redo history or current documents
        let isReferenced = undoStack.contains { $0.inputURL == url || $0.outputURL == url } ||
                           redoStack.contains { $0.inputURL == url || $0.outputURL == url } ||
                           documents.contains { $0.currentURL == url } ||
                           previewStashedURL == url
        
        guard !isReferenced else {
            logger.debug("Skipping cleanup of referenced temp file: \(url.lastPathComponent)")
            return
        }
        
        // Securely erase the file (overwrite with 0s) asynchronously
        Task {
            do {
                try await secureErase(at: url)
            } catch {
                logger.warning("Failed to securely erase temp file: \(error.localizedDescription)")
            }
        }
    }

    private func storeFontSearchResults(_ results: [FontSearchResult], for cacheKey: String) {
        guard !results.isEmpty else { return }
        fontSearchResults[cacheKey] = results

        let overflow = fontSearchResults.count - maxFontSearchCacheEntries
        guard overflow > 0 else { return }

        for key in fontSearchResults.keys.sorted().prefix(overflow) {
            fontSearchResults.removeValue(forKey: key)
        }
    }

    private func appendUndoHistory(_ item: EditHistoryItem) {
        undoStack.append(item)
        trimUndoHistoryIfNeeded()
    }

    private func appendRedoHistory(_ item: EditHistoryItem) {
        redoStack.append(item)
        trimRedoHistoryIfNeeded()
    }

    private func clearRedoHistory() {
        let removedItems = redoStack
        redoStack.removeAll()
        cleanupHistoryItems(removedItems)
    }

    private func clearEditHistory() {
        let removedItems = undoStack + redoStack
        undoStack.removeAll()
        redoStack.removeAll()
        cleanupHistoryItems(removedItems)
    }

    private func trimUndoHistoryIfNeeded() {
        let overflow = undoStack.count - maxEditHistoryItems
        guard overflow > 0 else { return }
        let removedItems = Array(undoStack.prefix(overflow))
        undoStack.removeFirst(overflow)
        cleanupHistoryItems(removedItems)
    }

    private func trimRedoHistoryIfNeeded() {
        let overflow = redoStack.count - maxEditHistoryItems
        guard overflow > 0 else { return }
        let removedItems = Array(redoStack.prefix(overflow))
        redoStack.removeFirst(overflow)
        cleanupHistoryItems(removedItems)
    }

    private func cleanupHistoryItems(_ items: [EditHistoryItem]) {
        guard !items.isEmpty else { return }

        for item in items {
            cleanupTempFile(item.inputURL)
            cleanupTempFile(item.outputURL)
        }
    }
    
    // MARK: - Undo/Redo
    
    func undo() {
        guard let item = undoStack.popLast() else { 
            logger.debug("Undo: Stack is empty")
            return 
        }
        
        // Validate the target URL exists before proceeding
        if !FileManager.default.fileExists(atPath: item.inputURL.path) {
            logger.error("Undo: Target file missing")
            errorMessage = "Cannot undo: Previous state file no longer exists"
            // Don't move to redo stack since it's invalid
            return
        }
        
        appendRedoHistory(item)
        applyHistoryState(url: item.inputURL)
        logger.info("Undo: Restored to \(item.inputURL.lastPathComponent)")
    }
    
    func redo() {
        guard let item = redoStack.popLast() else { 
            logger.debug("Redo: Stack is empty")
            return 
        }
        
        // Validate the target URL exists before proceeding
        if !FileManager.default.fileExists(atPath: item.outputURL.path) {
            logger.error("Redo: Target file missing")
            errorMessage = "Cannot redo: Target state file no longer exists"
            // Don't move to undo stack since it's invalid
            return
        }
        
        appendUndoHistory(item)
        applyHistoryState(url: item.outputURL)
        logger.info("Redo: Restored to \(item.outputURL.lastPathComponent)")
    }
    
    private func applyHistoryState(url: URL) {
        guard let id = selectedDocID else { return }

        // Use map-based pattern to avoid index invalidation
        documents = documents.map { doc in
            guard doc.id == id else { return doc }
            var updated = doc
            if FileManager.default.fileExists(atPath: url.path) {
                updated.currentURL = url
            } else {
                logger.warning("Undo/Redo file missing. Falling back to original.")
                updated.currentURL = doc.originalURL
            }
            updated.isDirty = true
            return updated
        }
        selectFile(id, preserveState: true) // Reload
    }
    
    // MARK: - Real Preview (runs actual replacement, cancel = restore)
    
    /// Start preview mode - stash current PDF URL for potential cancel
    func startPreview() {
        guard let id = selectedDocID,
              let idx = documents.firstIndex(where: { $0.id == id }) else {
            LogManager.shared.log("startPreview: FAILED - selectedDocID=\(selectedDocID?.uuidString ?? "nil")")
            return
        }

        // GUARD: Don't re-stash if already in preview mode
        // This prevents re-stashing during preview updates
        if isShowingPreview {
            LogManager.shared.log("startPreview: SKIPPED - already in preview mode")
            return
        }

        let currentURL = documents[idx].currentURL

        previewStashedURL = currentURL
        // NOTE: targetTextForReplacement is now immutable, so we don't need to stash it
        // We stash the current editingText so we can restore the text field on cancel
        previewStashedOriginalText = editingText
        isShowingPreview = true
        previewStatus = .idle
        allowCollisionOverrun = false
        LogManager.shared.log("startPreview: SUCCESS - stashed '\(self.previewStashedURL?.lastPathComponent ?? "nil")'")
        logger.info("Preview: Started, stashed \(self.previewStashedURL?.lastPathComponent ?? "nil")")
    }
    
    /// Run the actual replacement as a preview (debounced)
    func runPreviewReplacement(targetText: String, replacementText: String, pageIndex: Int, overrides: ManualOverrides) {
        // NOTE: We NO LONGER block preview while font search is active
        // Instead, we use the interim detected font for preview
        // When font search completes, it will trigger another preview update

        // Cancel any pending debounce
        previewDebounceTask?.cancel()
        previewDebounceTask = nil  // Prevent race with old task
        previewPendingText = replacementText
        // NOTE: allowCollisionOverrun is reset in EditLineView's .onChange(of: vm.editingText),
        // NOT here — resetting here would immediately undo the "Allow Overrun" button.

        // Debounce 300ms to avoid running on every keystroke
        previewDebounceTask = Task { @MainActor [weak self] in
            guard let self = self else { return }
            self.previewStatus = .running
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }

            // Run actual replacement using the STASHED (original) URL
            // CRITICAL FIX: With immutable targetTextForReplacement, we always search for
            // the ORIGINAL text. So we must always search in the ORIGINAL PDF (stashed),
            // not in the preview output (which has the replaced text).
            // This allows multiple preview toggles and re-previews to work correctly.
            let currentInputURL: URL
            if let stashed = self.previewStashedURL {
                // Always use stashed URL for preview - contains the original text to find
                currentInputURL = stashed
                LogManager.shared.log("runPreviewReplacement: Using stashed URL '\(stashed.lastPathComponent)'")
            } else if let docID = self.selectedDocID,
                      let doc = self.documents.first(where: { $0.id == docID }) {
                // Fallback to current doc if no stash (shouldn't happen if stashPreviewState was called)
                currentInputURL = doc.currentURL
                LogManager.shared.log("runPreviewReplacement: FALLBACK to currentURL '\(doc.currentURL.lastPathComponent)'")
            } else {
                LogManager.shared.log("runPreviewReplacement: ERROR - No valid input URL")
                logger.error("Preview: No valid input URL found")
                self.previewStatus = .otherError(message: "No valid input URL")
                return
            }

            LogManager.shared.log("runPreviewReplacement: page=\(pageIndex), targetLength=\(targetText.count), replacementLength=\(replacementText.count)")

            await self.performReplacement(
                inputURL: currentInputURL,
                targetText: targetText,
                replacementText: replacementText,
                pageIndex: pageIndex,
                overrides: overrides,
                showLoading: false,  // Don't show loading indicator for preview
                isPreview: true  // CRITICAL: Don't reload PDF to keep dialog open
            )
            LogManager.shared.log("Preview: Applied replacement from stashed original, replacementLength=\(replacementText.count)")
        }
    }
    
    /// Cancel preview - restore stashed URL
    func cancelPreview() {
        previewDebounceTask?.cancel()
        previewDebounceTask = nil

        guard let stashedURL = previewStashedURL else {
            // Clean up all preview state even if no stashed URL
            previewStashedOriginalText = nil
            previewPendingText = nil
            previewStatus = .idle
            allowCollisionOverrun = false
            isShowingPreview = false
            return
        }
        
        // Restore the stashed PDF using map pattern to avoid index invalidation
        if let id = selectedDocID {
            var cleanupURL: URL? = nil
            documents = documents.map { doc in
                guard doc.id == id else { return doc }
                // Track preview temp file for cleanup if different from stashed
                if doc.currentURL != stashedURL {
                    cleanupURL = doc.currentURL
                }
                var updated = doc
                updated.currentURL = stashedURL
                return updated
            }
            if let url = cleanupURL {
                cleanupTempFile(url)
            }
            
            // Reload with state preservation (selectFile posts prepare/didReload internally)
            selectFile(id, preserveState: true)

            // Restore the text field to its pre-preview state
            // NOTE: targetTextForReplacement remains unchanged (it's immutable)
            if let stashedText = previewStashedOriginalText {
                editingText = stashedText
            }
        }
        
        previewStashedURL = nil
        previewStashedOriginalText = nil
        previewPendingText = nil
        previewStatus = .idle
        allowCollisionOverrun = false
        isShowingPreview = false
        logger.info("Preview: Cancelled, restored stashed URL")
    }
    
    /// Confirm preview - keep the replacement, clear stashed state
    func confirmPreview() {
        // Capture document ID before async operations
        let docIDSnapshot = selectedDocID

        // Wait for any pending preview to complete before confirming
        let pendingTask = previewDebounceTask
        previewDebounceTask = nil

        // Clear stashed URL immediately to prevent race with cancel
        previewStashedURL = nil

        Task {
            // Ensure pending preview completes before confirming
            await pendingTask?.value

            await MainActor.run {
                // Verify we're still on the same document
                guard self.selectedDocID == docIDSnapshot else {
                    logger.warning("Preview: Confirm aborted - document changed during await")
                    return
                }
                // The replacement is already applied - undo items were created during preview
                // Just mark preview as confirmed (previewStashedURL already cleared above)
                // previewStashedURL = nil  // Already cleared before await
                previewStashedOriginalText = nil  // CRITICAL: Must clear to prevent stale restoration
                previewPendingText = nil
                self.previewStatus = .idle
                self.allowCollisionOverrun = false
                isShowingPreview = false

                // NOTE: targetTextForReplacement stays IMMUTABLE (the original PDF text).
                // Nudge/kern/size re-do the replacement from scratch using lastEdit.inputURL.

                // CRITICAL: Force PDF reload so text extraction shows NEW content, not cached old content
                // Without this, clicking on edited text would show the original text
                if let id = selectedDocID {
                    logger.info("Preview: Confirmed after pending preview completed")
                    selectFile(id, preserveState: true)
                } else {
                    logger.info("Preview: Confirmed (undo items already created during preview edits)")
                }
            }
        }
    }
}
