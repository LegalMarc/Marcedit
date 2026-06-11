# Marcedit Compatibility & Limitation Notes

This document outlines current capabilities, verified features, and known limitations of the Marcedit PDF editing engine.

## ✅ Verified Features

### Text Editing
- **Identity Replacement**: Replacing text with identical content preserves the original font (via Smart Reuse) with >95% visual fidelity (SSIM > 0.95).
- **Simple Substitution**: Replacing text with new content using the same font works correctly for standard TrueType and OpenType fonts.
- **Font Fallback**: Automatic fallback to system fonts (Helvetica, Times, Courier) if the original font cannot be reused or matched.
- **Color Preservation**: Original text color is correctly detected and applied to replacement text.

### Visual Rendering
- **Live Preview**: Real-time preview of edits matches final PDF output closely.
- **Rendering Engine**: Uses PyMuPDF (MuPDF) for high-quality text placement and rendering.

## ⚠️ Known Limitations

### Font Support
- **Complex Font Subsets**: Some PDF files use non-standard "Identity-H" encodings or custom CID maps (Type 0/Type 1 fonts) that prevent extraction. Marcedit will fallback to a system font in these cases, which may alter the visual appearance (weight/spacing).
- **Font Extraction**: Fonts legally protected or obfuscated by the PDF creator cannot be extracted.
- **Smart Reuse**: Requires the original PDF to contain a valid embedded font stream. If the font is not embedded, substitution results depend on available system fonts.

### Text Layout & Direction
- **RTL Support**: Right-to-Left languages (Arabic, Hebrew) are **not currently supported** for re-flow. Text selection may behave unpredictably in RTL documents.
- **Vertical Text**: Vertical text layout is not supported.
- **Justification**: Fully justified text (aligned to both left and right margins) may lose its strict justification upon editing, reverting to Left or Center alignment depending on the best match.

### Rendering Differences
- **Pixel-Perfect Fidelity**: Due to differences between PDF rendering engines (e.g., Apple Preview vs. MuPDF), extremely minor pixel shifts (<1-2%) may occur even in identity edits. This is often due to anti-aliasing differences and not actual content shifts.

## 🐛 Troubleshooting

| Issue | Cause | Workaround |
|-------|-------|------------|
| **Text looks slightly thinner/thicker** | The original font was a specific weight (e.g., Book) but the nearest system match is Regular. | Use the Font Control Panel to manually select a specific weight if auto-detection fails. |
| **"Unknown" characters (rectangles)** | The font does not support the characters in your replacement text. | Choose a universal font like Arial or Helvetica for the replacement. |
| **Selection boxes are misaligned** | The PDF contains complex transforms or rotation. | Marcedit attempts to normalize coordinates, but heavily rotated text may have selection drift. |
