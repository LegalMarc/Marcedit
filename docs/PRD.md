# Marcedit Product Requirements Document (PRD)

**Version:** 1.0  
**Last Updated:** 2026-01-10  
**Status:** Comprehensive Feature Specification

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Overview](#2-product-overview)
3. [User Interface Layout](#3-user-interface-layout)
4. [Core Features](#4-core-features)
   - [4.1 Document Management](#41-document-management)
   - [4.2 Text Selection](#42-text-selection)
   - [4.3 Text Editing](#43-text-editing)
   - [4.4 Font Detection & Matching](#44-font-detection--matching)
   - [4.5 Preview Mode](#45-preview-mode)
   - [4.6 Text Controls (Nudge)](#46-text-controls-nudge)
   - [4.7 Undo/Redo System](#47-undoredo-system)
5. [Document Controls](#5-document-controls)
   - [5.1 Vector Flatten](#51-vector-flatten)
   - [5.2 Metadata Scrub](#52-metadata-scrub)
   - [5.3 MD5 Checksum](#53-md5-checksum)
6. [Settings](#6-settings)
7. [Technical Architecture](#7-technical-architecture)
8. [Keyboard Shortcuts](#8-keyboard-shortcuts)

---

## 1. Executive Summary

**Marcedit** is a specialized PDF text editor for macOS that enables users to edit text within existing PDFs while preserving the original visual appearance. Unlike traditional PDF editors that treat PDFs as static images, Marcedit intelligently analyzes and replaces text with proper font matching, positioning, and styling.

### Key Value Propositions

- **Non-destructive text editing** in existing PDFs
- **Automatic font detection and matching** to preserve document style
- **Pixel-perfect positioning controls** for fine-tuned adjustments
- **Preview mode** to validate changes before committing
- **Document cleanup tools** (flatten, metadata scrub)

---

## 2. Product Overview

### Target Users

- Legal professionals needing to correct errors in contracts
- Designers making minor text adjustments to client PDFs
- Administrative staff updating dated information in official documents
- Anyone needing to make small, precise text changes without recreating documents

### Platform Requirements

- **Operating System:** macOS 13.0+ (Ventura or later)
- **Architecture:** Apple Silicon (arm64) and Intel (x86_64)
- **Runtime:** Embedded Python 3.12 with PyMuPDF

---

## 3. User Interface Layout

### Main Window Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Marcedit (Title Bar)                       │
├───────────────────────────────┬─────────────────────────────────────┤
│  LEFT PANEL (Resizable)       │  RIGHT PANEL (PDF Preview)          │
│  ┌─────────────────────────┐  │                                     │
│  │  Documents Card          │  │    ┌─────────────────────────┐     │
│  │  - Open files list       │  │    │                         │     │
│  │  - Save/Export/Revert    │  │    │   Interactive PDF View  │     │
│  │  - Close buttons         │  │    │   - Hover highlighting  │     │
│  └─────────────────────────┘  │◄─►│   - Click to select      │     │
│  ┌─────────────────────────┐  │    │   - Double-click to edit │     │
│  │  Text Controls Card      │  │    │                         │     │
│  │  - Nudge arrows (↑↓←→)   │  │    └─────────────────────────┘     │
│  │  - Size adjustment       │  │                                     │
│  │  - Kerning adjustment    │  │    Status bar at bottom            │
│  └─────────────────────────┘  │                                     │
│  ┌─────────────────────────┐  │                                     │
│  │  Document Controls Card  │  │                                     │
│  │  - MD5 Checksum         │  │                                     │
│  │  - Vector Flatten       │  │                                     │
│  │  - Scrub Metadata       │  │                                     │
│  └─────────────────────────┘  │                                     │
├───────────────────────────────┴─────────────────────────────────────┤
```

### Left Panel Resizing

- **Minimum Width:** 220px (preserves nudge arrow layout)
- **Maximum Width:** 450px
- **Default Width:** 280px
- **Interaction:** Drag the vertical divider between panels
- **Cursor:** Changes to resize cursor on hover

---

## 4. Core Features

### 4.1 Document Management

#### 4.1.1 Opening Documents

| Method | Description |
|--------|-------------|
| Menu: File → Open | Standard file picker (Cmd+O) |
| Drag & Drop | Drop PDFs onto the window |
| File Importer Dialog | Multi-select capable |

**Supported Format:** PDF only (`.pdf` extension)

#### 4.1.2 Document List (Sidebar)

Each open document shows:
- **PDF icon** (blue when selected)
- **Filename** (wraps to up to 3 lines)
- **"Unsaved Changes"** badge (orange, when dirty)
- **Action buttons** (visible when selected or dirty):
  - **Save As** (arrow.up.doc) - Export to new file
  - **Save** (square.and.arrow.down) - Overwrite original (disabled if clean)
  - **Revert** (arrow.uturn.backward) - Restore original (disabled if clean)
  - **Reveal in Finder** (folder) - Open containing folder
  - **Close** (xmark.circle.fill) - Close document

#### 4.1.3 Save Operations

| Operation | Behavior |
|-----------|----------|
| **Save (Overwrite)** | Writes current state back to original file location |
| **Save As (Export)** | Opens save dialog to choose new location |
| **Revert** | Discards all edits, reloads original file |

#### 4.1.4 Unsaved Changes Protection

When closing a document with unsaved changes:
- Warning alert appears
- Options: "Save", "Discard", "Cancel"

When quitting the app with unsaved documents:
- Prevents quit
- Shows alert with list of unsaved documents
- Options: "Save All", "Discard All", "Cancel"

---

### 4.2 Text Selection

#### 4.2.1 Smart Selection Algorithm

The selection system uses **context-aware gap detection** to handle both flowing text and tabular content:

```
IF selection contains large character gaps (avgCharWidth > 10pt):
    → Word selection mode (for table cells)
ELSE:
    → Line selection mode (for flowing text)
```

#### 4.2.2 Selection Behavior

| Action | Result |
|--------|--------|
| **Hover** | Highlights selectable text with dotted outline |
| **Single Click** | Opens Edit Text dialogue, loads text, triggers font analysis, shows selection highlight |
| **Double Click** | No action|

#### 4.2.3 Gap Detection Thresholds

- **Normal text:** ~5-8pt average character width
- **Table cell trigger:** >10pt average character width
- **Must have:** >5 characters in selection to trigger gap detection

---

### 4.3 Text Editing

#### 4.3.1 Edit Text Dialog

Opens as a floating panel overlay on the PDF view.

**Header:**
- "Edit Text" title
- Original Font display (e.g., "AAAAAA+Calibri (Internal Embedded Font)")
- Current Font display (when using override)

**Text Editor:**
- Multi-line TextEditor control
- Uses system font for consistent UI
- Initial value: selected original text

**Font Override Controls:**
- **Override Font** dropdown (default: "Use Auto-Detected")
- **Override Style** dropdown (Auto, Regular, Bold, Italic, Bold Italic)
- Populated from font search results

**Footer Controls:**
- **Cancel** button - Closes dialog, discards changes
- **Preview** toggle - Shows live preview on PDF
- **Save** button (primary, Cmd+Enter) - Commits changes

#### 4.3.2 Edit Text Flow

```
1. User clicks text
2. Font detection runs async (shows "Analysing Fonts...")
3. Top 5 font matches displayed when ready if 
4. User modifies text content
5. User optionally toggles Preview
6. User clicks Save
7. Python backend:
   a. Searches for original text at location
   b. Redacts original text (removes from PDF)
   c. Inserts new text with matched/overridden font
8. PDF view updates with new content
9. Document marked as dirty
```

---

### 4.4 Font Detection & Matching

#### 4.4.1 Automatic Font Detection

When text is selected, the system:
1. Extracts font name from PDF text operators
2. Analyzes font flags (bold, italic, serif, etc.)
3. Gets font size, origin point, and metrics
4. Attempts to identify matching system fonts

**Display Format:** `FontName - Size (Source)`  
Example: `AAAAAA+Calibri - 12.0pt (Internal Embedded Font)`

#### 4.4.2 Font Matching Modes

| Mode | Description |
|------|-------------|
| **Common Fonts** (default) | Fast search of ~50 common fonts |
| **Exhaustive Search** | Complete scan of all system fonts (slower) |

#### 4.4.3 Font Source Types

| Source | Description |
|--------|-------------|
| **Internal (Embedded Font)** | Font embedded in PDF, no matching needed |
| **System Font** | Matched from macOS font library |
| **CoreText Match** | Found via CoreText font descriptor matching |
| **Fallback** | Using Helvetica as last resort |

#### 4.4.4 Manual Font Override

Users can override auto-detected fonts:
- Select from dropdown of matched fonts
- Choose style variant (Regular, Bold, Italic, Bold Italic)
- Override persists for subsequent edits until changed

---

### 4.5 Preview Mode

#### 4.5.1 Preview Toggle Behavior

| State | Behavior |
|-------|----------|
| **OFF → ON** | Stashes current document state, runs actual replacement |
| **ON (typing)** | Debounced (300ms) live updates to PDF |
| **ON → Save** | Confirms preview, adds to undo stack |
| **ON → Cancel** | Restores stashed document state |

#### 4.5.2 Preview Implementation

- **Not an overlay:** Runs actual PyMuPDF replacement
- **Stash/Restore:** Preserves original URL for cancel
- **Debounced:** Waits 300ms after typing stops before updating

---

### 4.6 Text Controls (Nudge)

#### 4.6.1 Position Nudge

Directional arrows to move replacement text after editing.

| Direction | Action |
|-----------|--------|
| ↑ Up | Move text up |
| ↓ Down | Move text down |
| ← Left | Move text left |
| → Right | Move text right |

**Increment:**
- **Normal click:** 0.1 pixels
- **Command (⌘) + click:** 1.0 pixels

#### 4.6.2 Size Adjustment

Increase/decrease font size of replacement text.

- **Increment:** ±0.1pt (or ±1.0pt with Cmd)
- **Display:** Shows current delta (e.g., "+0.5")

#### 4.6.3 Kerning Adjustment

Adjust character spacing of replacement text.

- **Increment:** ±0.05em (or ±0.5em with Cmd)
- **Display:** Shows current delta (e.g., "+0.10")

#### 4.6.4 Nudge Workflow

1. User makes initial text edit
2. Observes positioning in PDF
3. Uses nudge arrows to adjust
4. System re-runs replacement with offset applied
5. Repeat until satisfied

---

### 4.7 Undo/Redo System

#### 4.7.1 Stack Behavior

- **Undo Stack:** Maximum 10 levels
- **Redo Stack:** Cleared when new edit is made
- **State Stored:** Input URL, output URL, target text, replacement text, page index, overrides, original font info

#### 4.7.2 Shortcuts

| Action | Shortcut |
|--------|----------|
| Undo | Cmd+Z |
| Redo | Cmd+Shift+Z |

#### 4.7.3 Undo Behavior

1. Retrieves previous state from undo stack
2. Restores document to previous URL
3. Pushes current state to redo stack
4. Updates PDF view

---

## 5. Document Controls

### 5.1 Vector Flatten

**Purpose:** Converts all text in the document to vector outlines (shapes).

**Use Cases:**
- Preparing documents where fonts might not be available
- Creating print-ready PDFs
- Preventing text extraction/editing

**Behavior:**
1. User clicks "Vector Flatten" button
2. Confirmation dialog appears with warning
3. On confirm, Python backend converts all text to paths
4. Document updated with flattened version
5. **IRREVERSIBLE** - text can no longer be edited as text

**Warning Message:**
> "This will convert all text to vector outlines. The document will no longer be editable as text, but will look identical and be print-ready. This action cannot be undone."

---

### 5.2 Metadata Scrub

**Purpose:** Removes all identifying metadata from the PDF.

**Items Removed:**
- Title
- Author
- Creator
- Producer
- Creation Date
- Modification Date
- Subject
- Keywords
- XMP Metadata
- Other internal metadata streams

**Behavior:**
1. User clicks "Scrub Metadata" button
2. Confirmation dialog appears
3. On confirm, Python backend removes all metadata
4. Document updated with clean version
5. **IRREVERSIBLE**

**Warning Message:**
> "This will remove all standard metadata (Title, Author, etc.), XMP data, and perform a deep clean of the file structure. This action cannot be undone."

---

### 5.3 MD5 Checksum

**Purpose:** Displays cryptographic hash of current document state.

**Display:** `MD5: a1b2c3d4e5f6...`

**Features:**
- Updates when document changes
- Text selectable for copying
- Tooltip: "MD5 Checksum: Verify file integrity bit-for-bit"

**Use Cases:**
- Verify document hasn't been modified
- Compare before/after editing
- Chain of custody documentation

---

## 6. Settings

Accessed via menu: **Marcedit → Settings** (Cmd+,)

### 6.1 Appearance

| Setting | Options | Default |
|---------|---------|---------|
| Theme | Follow System, Light, Dark | Follow System |

### 6.2 File Handling

| Setting | Description | Default |
|---------|-------------|---------|
| Preserve All Metadata | Keeps original creation date and attributes when saving | OFF |

### 6.3 Font Replacement

| Setting | Description | Default |
|---------|-------------|---------|
| Exhaustive Font Search | Scan all system fonts instead of common fonts only | OFF |

### 6.4 Debug

| Setting | Description | Default |
|---------|-------------|---------|
| Enable Debug Logging | Writes verbose diagnostics for troubleshooting | OFF |
| Open App Log | Opens log file location | - |
| Clear Logs | Deletes current log file | - |

---

## 7. Technical Architecture

### 7.1 Technology Stack

| Layer | Technology |
|-------|------------|
| **UI Framework** | SwiftUI (macOS) |
| **PDF Rendering** | PDFKit (Apple) |
| **PDF Manipulation** | PyMuPDF (fitz) via embedded Python 3.12 |
| **Font Analysis** | CoreText + PyMuPDF font extraction |
| **Interop** | PythonKit (Swift-Python bridge) |

### 7.2 File Structure

```
Marcedit.app/
├── Contents/
│   ├── MacOS/
│   │   └── Marcedit (executable)
│   ├── Frameworks/
│   │   └── Python.framework/
│   └── Resources/
│       └── python_site/
│           └── editor_pkg/
│               ├── core.py (main PDF logic)
│               └── ...
```

### 7.3 Python Runtime

- **Isolated Environment:** Sanitizes PATH, PYTHONHOME, PYTHONPATH
- **GIL Management:** Worker thread with explicit GIL acquire/release
- **Thread Safety:** All Python calls dispatched to dedicated worker thread

### 7.4 Temporary Files

- **Location:** System temp directory (`/tmp/` or equivalent)
- **Naming:** `marcedit_<uuid>.pdf`
- **Cleanup:** On document close, app quit, undo stack overflow

---

## 8. Keyboard Shortcuts

### 8.1 Global Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+O | Open file |
| Cmd+S | Save current document |
| Cmd+Shift+S | Save As |
| Cmd+Z | Undo |
| Cmd+Shift+Z | Redo |
| Cmd+R | Revert to original |
| Cmd+, | Open Settings |
| Cmd+W | Close current document |
| Cmd+Q | Quit application |

### 8.2 Edit Dialog Shortcuts

| Shortcut | Action |
|----------|--------|
| Cmd+Enter | Save changes |
| Escape | Cancel/Close dialog |

### 8.3 Nudge Modifiers

| Modifier | Effect |
|----------|--------|
| (none) | 0.1px / 0.05em movement |
| Cmd | 1.0px / 0.5em movement |

### 8.4 PDF View Shortcuts

| Shortcut | Action |
|----------|--------|
| Arrow Keys | Nudge selected text (0.1px) |
| Cmd+Arrow Keys | Nudge selected text (1.0px) |

---

## Appendix A: Error Messages

| Error | Cause | Resolution |
|-------|-------|------------|
| "Cannot access file: permission denied" | Security scoped resource access failed | Re-open file through file picker |
| "Target text cannot be empty" | Empty selection passed to replacement | Select text before editing |
| "Invalid page number" | Page index out of bounds | Internal error, report bug |
| "Python runtime not initialized" | Embedded Python failed to load | Reinstall application |
| "Edit failed: [message]" | PyMuPDF operation error | Check file permissions, PDF integrity |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Embedded Font** | Font data included within the PDF file |
| **Subset Font** | Embedded font containing only used characters |
| **Origin** | Baseline coordinate where text drawing begins |
| **Redaction** | Permanent removal of content from PDF |
| **Span** | Contiguous run of text with same formatting |
| **Vector Flatten** | Converting text outlines to graphics paths |
| **Dirty State** | Document has unsaved changes |

---

*End of PRD*
