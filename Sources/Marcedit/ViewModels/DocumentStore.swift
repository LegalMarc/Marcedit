//
//  DocumentStore.swift
//  Marcedit
//
//  One of three focused stores the EditorViewModel coordinator composes
//  (Candidate D). DocumentStore owns the open-document set, the current
//  selection, and the PDF-view display state. Cross-cutting orchestration
//  (open/save/close/reload) stays in the coordinator, which observes this
//  store and re-emits its changes.
//

import Foundation
import PDFKit

@MainActor
final class DocumentStore: ObservableObject {
    @Published var documents: [DocumentFile] = []
    @Published var selectedDocID: UUID?

    /// The PDFDocument currently rendered in the viewer.
    @Published var selectedPDF: PDFDocument?
    /// Bumped to force the PDFView to rebuild.
    @Published var pdfViewID = UUID()

    // Zoom & scroll persistence (bound to the PDFView).
    @Published var currentScaleFactor: CGFloat = 1.0
    @Published var currentDestination: PDFDestination? = nil

    /// The selected document, derived from `documents` + `selectedDocID`.
    var selectedDocument: DocumentFile? {
        get { documents.first(where: { $0.id == selectedDocID }) }
        set {
            if let val = newValue {
                documents = documents.map { $0.id == val.id ? val : $0 }
            }
        }
    }
}
