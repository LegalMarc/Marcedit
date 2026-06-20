//
//  EditSession.swift
//  Marcedit
//
//  One of three focused stores the EditorViewModel coordinator composes
//  (Candidate D). EditSession owns the active edit-dialog state plus all
//  font-detection / font-search state and the manual overrides. The
//  orchestration that drives replacement and font search stays in the
//  coordinator, which observes this store and re-emits its changes.
//

import Foundation

@MainActor
final class EditSession: ObservableObject {
    // Edit dialog
    @Published var showEditSheet = false
    /// Selection mode: "line" for a single line, "paragraph" for a block/cell.
    @Published var selectionMode: String = "line"
    /// Block editing: styled spans when in paragraph mode.
    @Published var editingSpans: [SpanInfo] = []
    @Published var blockBbox: [Double] = []
    @Published var selectedTextRange: NSRange = NSRange(location: 0, length: 0)

    /// Text to search for in the PDF — never mutated during an edit session.
    @Published var targetTextForReplacement: String = ""
    /// The user's current edited text (may differ from the target).
    @Published var editingText: String = ""
    @Published var editingPageIndex: Int = 0
    /// 0-based index of the clicked occurrence among same-text matches on the page.
    /// nil when unknown (e.g. selection came from a code path that cannot derive it),
    /// which preserves the existing "replace all on page" behaviour.
    @Published var editingOccurrenceIndex: Int? = nil

    // Font detection
    @Published var detectedFont: String? = nil
    @Published var detectedFontName: String? = nil
    @Published var detectedFontFlags: Int = 0
    @Published var originalDetectedFont: String? = nil
    @Published var isSearchingFonts: Bool = false

    // Font search
    @Published var searchProgress: Double = 0.0
    @Published var searchingFontName: String = ""
    @Published var fontSearchResults: [String: [FontSearchResult]] = [:] // key: originalText

    // Font & manual controls
    @Published var availableFonts: [[String: String]] = []
    @Published var manualOverrides = ManualOverrides()
    @Published var allowCollisionOverrun: Bool = false

    /// Alias for ContentView compatibility (same value as targetTextForReplacement).
    var editingOriginalText: String { targetTextForReplacement }
    var detectedIsItalic: Bool { (detectedFontFlags & 2) != 0 }
    var detectedIsBold: Bool { (detectedFontFlags & 16) != 0 }
}
