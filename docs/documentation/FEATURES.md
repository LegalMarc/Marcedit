# Marcedit — Complete Feature List

## Core PDF Text Editing
- **Click-to-select** individual text lines in a PDF
- **Double-click to edit** selected text in a modal dialog
- **Drag-select** multiple lines
- **Word selection** via Option+Click
- **Paragraph/block editing** — expand a line to its full text block, edit with per-span styling
- **Live preview** of replacement text overlaid on the PDF (toggleable)
- **Smart text normalization** — handles Unicode, ligatures, special characters, invisible chars
- **Collision detection** — warns when replacement text visually overlaps existing content (pixmap-based comparison)

## Font Control
- **Auto-detect fonts** from selected text (family, weight, width, style, size)
- **Font search** — quick (common fonts) or exhaustive (all system fonts) with progress bar
- **Smart font matching** with confidence scoring (auto-selects at 0.85+)
- **Font substitution** via system fonts or bundled fonts
- **CJK font weight support** (w0–w9 variants)
- **PostScript font name** support
- **TTC extraction** (TrueType Collection fonts)

## Text Positioning & Sizing (Nudge Controls)
- **Nudge position** — up/down/left/right (±0.1pt, ±1pt with Cmd)
- **Adjust text size** (±0.1pt, ±1pt with Cmd)
- **Adjust kerning/tracking** (±0.05pt, ±0.5pt with Cmd)
- Real-time visual feedback during all adjustments

## Text Decoration & Styling
- **Text color/fill color** detection and editing
- **Simulated bold** injection (for fonts lacking a bold variant)
- **Italic slant** injection
- **Underline** detection and injection
- **Strikethrough** detection and injection
- **Text alignment** detection (left, center, right, justified)
- **Smart quotes** toggle

## Document Management
- **Open multiple PDFs** simultaneously
- **Drag & drop** PDFs to open
- **Save** (overwrite), **Save As** (export copy), **Revert** (undo all changes)
- **Close** individual documents with unsaved-changes confirmation
- **MD5 checksum** display for file integrity
- **Sidebar** listing all open PDFs with dirty-state indicator (orange dot)
- Quick-action buttons per file: Revert, Save, Save As, Close

## Document-Level Operations
- **Vector Flatten** — convert all text to vector shapes (irreversible, for finalization)
- **View Metadata** — inspect all PDF metadata + XMP metadata
- **Scrub Metadata** — remove all metadata with detailed HTML report of what was removed
- **Secure Erase** — DOD 5220.22-M compliant 3-pass file deletion (zeros, 0xFF, random)

## Zoom & View
- **Zoom In/Out** (Cmd++/Cmd+-)
- **Fit to Window** (Cmd+0)
- Zoom percentage display
- **Persistent zoom & scroll position** per document
- **PDF dark mode** — independent of app theme (Follow System / Light / Dark)
- **Sidebar toggle** (Cmd+B) with animation
- Resizable left panel via drag divider

## Undo/Redo
- **Undo** (Cmd+Z) and **Redo** (Cmd+Y / Shift+Cmd+Z)
- Per-document edit history stack, preserved across document switches

## Layout & Analysis
- **Layout detection** — columns, tables, reading order
- **Text rotation** detection
- **Character metrics** extraction (x-height, cap-height)
- **Ligature** detection and decomposition
- **Line structure analysis** with character-level splitting
- **Regex-based text replacement**
- **Batch replacement** across multiple pages

## Settings & Preferences
- **App theme**: Follow System / Light / Dark
- **PDF appearance**: Follow System / Light / Dark
- **Exhaustive Font Search** toggle
- **Preserve All Metadata** toggle (keep original creation date on save)
- **Debug logging** toggle + open/clear log files

## UI/UX
- **Toast notifications** — success (green), error (red, auto-dismiss), info; tap-to-dismiss
- **Processing overlay** with cancel button (Esc)
- **Status indicators** — ready badge, last-saved timestamp
- **Help & Shortcuts** dialog (Cmd+/)
- **Tooltips** on all interactive elements
- **Accessibility identifiers** on every element; keyboard-navigable

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Cmd+O | Open PDF |
| Cmd+S | Save |
| Cmd+W | Close Document |
| Cmd+Z | Undo |
| Cmd+Y / Shift+Cmd+Z | Redo |
| Cmd+B | Toggle Sidebar |
| Cmd++/- /0 | Zoom In/Out/Fit |
| Cmd+/ | Help & Shortcuts |
| Arrow keys | Nudge text (Cmd for 10x step) |
| Escape | Cancel edit / clear selection |

## Performance
- **Font cache** (60 entries, LRU)
- **Pixmap cache** for collision detection (200 entries, LRU)
- **Normalization caches** (Unicode, text matching, special chars)
- **Debounced preview** updates

## Privacy & Security
- **Fully offline** — no internet connection, all processing local
- Secure metadata scrubbing (3-pass overwrite before deletion)
- DOD-compliant secure file erasure
