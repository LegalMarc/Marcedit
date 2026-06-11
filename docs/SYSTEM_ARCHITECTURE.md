# Marcedit System Architecture

## High-Level Overview

Marcedit is a hybrid macOS application that combines native Swift UI (SwiftUI) with a powerful Python backend for PDF manipulation (PyMuPDF).

### Core Components

1.  **Frontend (Swift)**: Visuals, User Interaction, State Management.
2.  **Coordinator (Swift Actor)**: Central point of truth for document state.
3.  **Bridge (PythonKit)**: Communication layer between Swift and Python.
4.  **Backend (Python)**: logical core for PDF analysis and editing.

---

## Swift Architecture

### The DocumentCoordinator
Located in `Sources/Marcedit/Architecture/DocumentCoordinator.swift`.

The `DocumentCoordinator` is a Swift Actor that manages:
- **Document Integrity**: Ensures one source of truth for open documents.
- **Edit Sessions**: Tracks active edits to prevent race conditions.
- **Font Search**: Manages background tasks for finding suitable replacement fonts.
- **Undo/Redo Stack**: Centralized history management.

**Why an Actor?**
PDF editing is asynchronous and resource-intensive. Using an actor ensures thread safety when updating the document model or performing IO operations, preventing data corruption.

---

## Python Backend Architecture

The Python core is located in `Sources/Marcedit/python_site/editor_pkg/`.

### Key Modules

#### `core.py`
The API entry point called by Swift. It exposes high-level functions like:
- `replace_text_in_pdf()`
- `get_pdf_text_map()`
- `analyze_font_at_location()`

#### `reflow.py`
The "brain" of the text replacement. It handles:
- **Line Breaking**: Analyzes existing text visual flow.
- **Expansion/Contraction**: Adjusts character spacing if replacement text length differs.
- **Visual Safety**: Checks for collisions with surrounding elements.

#### `synthesizer.py`
Responsible for **Font Synthesis**. If the original font is not fully embedded or is a subset:
- It attempts to synthesize a matching font from system fonts.
- It matches metrics (width, weight, x-height) to blend seamlessly.

---

## Data Flow

1.  **User Action**: User selects text and types replacement in SwiftUI.
2.  **Coordinator**: `DocumentCoordinator` receives intent, locks document state.
3.  **Bridge**: Calls `editor_pkg.core.replace_text_in_pdf()` via PythonKit.
4.  **Backend Processing**:
    - `harvester.py` extracts original font metrics.
    - `synthesizer.py` selects best matching font.
    - `reflow.py` calculates new glyph positions.
    - `PyMuPDF` (muPDF) writes low-level PDF stream.
5.  **Result**: New PDF blob returned to Swift.
6.  **Refresh**: View updates with new PDF data.

---

## Directory Structure (Refactored)

- `DOCS/`: Developer documentation.
- `Sources/`: Swift application code & Python packages.
- `Scripts/`: Utility scripts for build/debug.
- `tests/`: Python unit tests.
- `Artifacts/`: Build logs and test outputs (git-ignored).
- `ignored-resources/`: Sensitive test documents (git-ignored).
