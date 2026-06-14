//
//  PreviewSession.swift
//  Marcedit
//
//  One of three focused stores the EditorViewModel coordinator composes
//  (Candidate D). PreviewSession owns the live-preview state (the
//  preview = a real replacement; cancel = restore the stashed original).
//  The preview pipeline interleaves with the replacement orchestration, so
//  start/run/cancel/confirm stay in the coordinator, which observes this
//  store and re-emits its changes. The PreviewStatus enum remains nested on
//  EditorViewModel so existing references are unaffected.
//

import Foundation

@MainActor
final class PreviewSession: ObservableObject {
    @Published var previewStatus: EditorViewModel.PreviewStatus = .idle
    @Published var isShowingPreview: Bool = false
    @Published var previewStashedURL: URL? = nil   // URL to restore on Cancel
    @Published var previewPendingText: String? = nil // Text for debounced preview
}
