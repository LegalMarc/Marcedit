//
//  EditorViewModelV2.swift
//  Marcedit
//
//  Compatibility bridge: forwards all UI-facing operations to EditorViewModel.
//  All @Published state is owned by the embedded EditorViewModel; V2 propagates
//  its objectWillChange so SwiftUI views that hold an EditorViewModelV2 observe
//  changes correctly.
//
//  Created: 2026-01-23
//

import Foundation
import PDFKit
import Combine
import OSLog

private let logger = Logger(subsystem: "com.marclaw.Marcedit", category: "EditorViewModelV2")

@MainActor
class EditorViewModelV2: ObservableObject {

    // MARK: - Legacy backing store

    private(set) var legacyVM: EditorViewModel

    private var cancellables = Set<AnyCancellable>()

    // MARK: - Initialization

    init() {
        let vm = EditorViewModel()
        self.legacyVM = vm

        // Propagate V1's state changes through V2's objectWillChange so that
        // SwiftUI views subscribed to EditorViewModelV2 re-render on V1 mutations.
        vm.objectWillChange
            .sink { [weak self] in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    // MARK: - Published property forwarding
    // Computed vars that proxy V1 @Published state. Because objectWillChange is
    // forwarded above, SwiftUI sees the willChange notification then reads the
    // updated value through these getters in the next render cycle.

    var documents: [DocumentFile] {
        get { legacyVM.documents }
        set { legacyVM.documents = newValue }
    }

    var selectedDocID: UUID? {
        get { legacyVM.selectedDocID }
        set { legacyVM.selectedDocID = newValue }
    }

    var selectedDocument: DocumentFile? {
        get { legacyVM.selectedDocument }
        set { legacyVM.selectedDocument = newValue }
    }

    var selectedPDF: PDFDocument? {
        get { legacyVM.selectedPDF }
        set { legacyVM.selectedPDF = newValue }
    }

    var showEditSheet: Bool {
        get { legacyVM.showEditSheet }
        set { legacyVM.showEditSheet = newValue }
    }

    var editingText: String {
        get { legacyVM.editingText }
        set { legacyVM.editingText = newValue }
    }

    var targetTextForReplacement: String {
        get { legacyVM.targetTextForReplacement }
        set { legacyVM.targetTextForReplacement = newValue }
    }

    var editingOriginalText: String { legacyVM.editingOriginalText }

    var editingPageIndex: Int {
        get { legacyVM.editingPageIndex }
        set { legacyVM.editingPageIndex = newValue }
    }

    var detectedFont: String? {
        get { legacyVM.detectedFont }
        set { legacyVM.detectedFont = newValue }
    }

    var detectedFontName: String? {
        get { legacyVM.detectedFontName }
        set { legacyVM.detectedFontName = newValue }
    }

    var detectedFontFlags: Int {
        get { legacyVM.detectedFontFlags }
        set { legacyVM.detectedFontFlags = newValue }
    }

    var originalDetectedFont: String? {
        get { legacyVM.originalDetectedFont }
        set { legacyVM.originalDetectedFont = newValue }
    }

    var detectedIsItalic: Bool { legacyVM.detectedIsItalic }
    var detectedIsBold: Bool { legacyVM.detectedIsBold }

    var isSearchingFonts: Bool {
        get { legacyVM.isSearchingFonts }
        set { legacyVM.isSearchingFonts = newValue }
    }

    var searchProgress: Double {
        get { legacyVM.searchProgress }
        set { legacyVM.searchProgress = newValue }
    }

    var searchingFontName: String {
        get { legacyVM.searchingFontName }
        set { legacyVM.searchingFontName = newValue }
    }

    var fontSearchResults: [String: [FontSearchResult]] {
        get { legacyVM.fontSearchResults }
        set { legacyVM.fontSearchResults = newValue }
    }

    var manualOverrides: ManualOverrides {
        get { legacyVM.manualOverrides }
        set { legacyVM.manualOverrides = newValue }
    }

    var isProcessing: Bool {
        get { legacyVM.isProcessing }
        set { legacyVM.isProcessing = newValue }
    }

    var errorMessage: String? {
        get { legacyVM.errorMessage }
        set { legacyVM.errorMessage = newValue }
    }

    var showFileImporter: Bool {
        get { legacyVM.showFileImporter }
        set { legacyVM.showFileImporter = newValue }
    }

    var showUnsavedAlert: Bool {
        get { legacyVM.showUnsavedAlert }
        set { legacyVM.showUnsavedAlert = newValue }
    }

    var closeActionType: CloseActionType {
        get { legacyVM.closeActionType }
        set { legacyVM.closeActionType = newValue }
    }

    var pendingCloseAction: (() -> Void)? {
        get { legacyVM.pendingCloseAction }
        set { legacyVM.pendingCloseAction = newValue }
    }

    var pdfViewID: UUID {
        get { legacyVM.pdfViewID }
        set { legacyVM.pdfViewID = newValue }
    }

    var currentScaleFactor: CGFloat {
        get { legacyVM.currentScaleFactor }
        set { legacyVM.currentScaleFactor = newValue }
    }

    var currentDestination: PDFDestination? {
        get { legacyVM.currentDestination }
        set { legacyVM.currentDestination = newValue }
    }

    var lastSavedTime: Date? {
        get { legacyVM.lastSavedTime }
        set { legacyVM.lastSavedTime = newValue }
    }

    var fontSourceInfo: String? {
        get { legacyVM.fontSourceInfo }
        set { legacyVM.fontSourceInfo = newValue }
    }

    var selectionMode: String {
        get { legacyVM.selectionMode }
        set { legacyVM.selectionMode = newValue }
    }

    var editingSpans: [SpanInfo] {
        get { legacyVM.editingSpans }
        set { legacyVM.editingSpans = newValue }
    }

    var blockBbox: [Double] {
        get { legacyVM.blockBbox }
        set { legacyVM.blockBbox = newValue }
    }

    var selectedTextRange: NSRange {
        get { legacyVM.selectedTextRange }
        set { legacyVM.selectedTextRange = newValue }
    }

    var availableFonts: [[String: String]] {
        get { legacyVM.availableFonts }
        set { legacyVM.availableFonts = newValue }
    }

    var undoStack: [EditHistoryItem] {
        get { legacyVM.undoStack }
        set { legacyVM.undoStack = newValue }
    }

    var redoStack: [EditHistoryItem] {
        get { legacyVM.redoStack }
        set { legacyVM.redoStack = newValue }
    }

    var lastEdit: EditHistoryItem? { legacyVM.lastEdit }

    var allowCollisionOverrun: Bool {
        get { legacyVM.allowCollisionOverrun }
        set { legacyVM.allowCollisionOverrun = newValue }
    }

    var previewStatus: EditorViewModel.PreviewStatus {
        get { legacyVM.previewStatus }
        set { legacyVM.previewStatus = newValue }
    }

    var isShowingPreview: Bool {
        get { legacyVM.isShowingPreview }
        set { legacyVM.isShowingPreview = newValue }
    }

    var previewStashedURL: URL? {
        get { legacyVM.previewStashedURL }
        set { legacyVM.previewStashedURL = newValue }
    }

    var previewPendingText: String? {
        get { legacyVM.previewPendingText }
        set { legacyVM.previewPendingText = newValue }
    }

    var showScrubReport: Bool {
        get { legacyVM.showScrubReport }
        set { legacyVM.showScrubReport = newValue }
    }

    var scrubReportURL: URL? {
        get { legacyVM.scrubReportURL }
        set { legacyVM.scrubReportURL = newValue }
    }

    var scrubWarningMessage: String? {
        get { legacyVM.scrubWarningMessage }
        set { legacyVM.scrubWarningMessage = newValue }
    }

    var isErasureInProgress: Bool { legacyVM.isErasureInProgress }

    var formattedManualFontName: String? { legacyVM.formattedManualFontName }

    // MARK: - Forwarded methods

    @discardableResult
    func handleDrop(providers: [NSItemProvider]) -> Bool {
        legacyVM.handleDrop(providers: providers)
    }

    func add(urls: [URL]) {
        legacyVM.add(urls: urls)
    }

    func selectFile(_ id: UUID, preserveState: Bool = false) {
        legacyVM.selectFile(id, preserveState: preserveState)
    }

    func handleLineSelection(text: String, pageIndex: Int) {
        legacyVM.handleLineSelection(text: text, pageIndex: pageIndex)
    }

    func nudge(direction: String, amount: Double) {
        legacyVM.nudge(direction: direction, amount: amount)
    }

    func registerTerminationHandler() {
        legacyVM.registerTerminationHandler()
    }

    func quitAnyway() {
        legacyVM.quitAnyway()
    }

    func requestCloseDocument() {
        legacyVM.requestCloseDocument()
    }

    func cancelProcessing() {
        legacyVM.cancelProcessing()
    }

    func saveFile(_ id: UUID) {
        legacyVM.saveFile(id)
    }

    func revertFile(_ id: UUID) {
        legacyVM.revertFile(id)
    }

    func closeFile(_ id: UUID) {
        legacyVM.closeFile(id)
    }

    func exportFile(_ id: UUID) {
        legacyVM.exportFile(id)
    }

    func revealInFinder(_ id: UUID) {
        legacyVM.revealInFinder(id)
    }

    func cancelFontSearch() {
        legacyVM.cancelFontSearch()
    }

    func undo() {
        legacyVM.undo()
    }

    func redo() {
        legacyVM.redo()
    }

    func replaceText(original: String, newText: String, pageIndex: Int) async {
        await legacyVM.replaceText(original: original, newText: newText, pageIndex: pageIndex)
    }

    func startPreview() {
        legacyVM.startPreview()
    }

    func runPreviewReplacement(targetText: String, replacementText: String, pageIndex: Int, overrides: ManualOverrides) {
        legacyVM.runPreviewReplacement(targetText: targetText, replacementText: replacementText, pageIndex: pageIndex, overrides: overrides)
    }

    func cancelPreview() {
        legacyVM.cancelPreview()
    }

    func confirmPreview() {
        legacyVM.confirmPreview()
    }

    func flattenCurrentDocument() async {
        await legacyVM.flattenCurrentDocument()
    }

    func viewCurrentDocumentMetadata() async {
        await legacyVM.viewCurrentDocumentMetadata()
    }

    func scrubCurrentDocument() async {
        await legacyVM.scrubCurrentDocument()
    }

    func secureEraseCurrentDocument() async {
        await legacyVM.secureEraseCurrentDocument()
    }
}
