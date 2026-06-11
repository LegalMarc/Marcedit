# Marcedit — Visual Glitch Bug List

_Compiled 2026-03-06 via manual review of `visual_edit_harness_report/` before/after PNGs._
_Source: 91 successful edits across 10 PDFs at 150 DPI. Approximately 40–50% show at least one visible defect._

---

## BUG-1 · All Instances Replaced When Only One Was Intended

**Severity: HIGH**
**Category: Semantic correctness**

### Description
When the target text is a short, common word or phrase that appears multiple times in a document, every occurrence is replaced — not just the one the user intended to edit.

### Evidence
| Edit | Target | Result |
|------|--------|--------|
| LexisNexis Edit 3 | `Number` | Every instance of "Number" became "March": "Customer **March**", "Invoice **March**", "Account **March**", "REGISTRATION **MARCH**…" in both body and header. Elapsed: 4033 ms (many instances) |
| SimpleTire Edit 6 | `Total` | Both the column header **and** the summary row "Total | $737.06" became "Three". Two replacements visible. |
| Redline Edit 1 | `INC.` | Replaced in main body title AND in footer watermark. |

### Root Cause
`replace_text_in_pdf()` calls `_robust_search()` which returns every rectangle matching the target text, then loops over all of them. There is no mechanism for the caller to specify "replace only the Nth occurrence" or "replace only the instance on page X near coordinate Y".

### Relevant Code
- `core.py` ~line 3945: `_robust_search()` → returns all matching rects
- `core.py` ~line 4137: per-instance loop operates on every result with no count limit

### Proposed Fix
Add `occurrence_index: int | None = None` parameter to `replace_text_in_pdf`. When set, skip all instances except the Nth match (0-based). Default `None` = replace all (preserves current behavior). The UI should pass the specific instance the user clicked on.

---

## BUG-2 · Gap Left After Shorter Replacement (Suffix Not Closed)

**Severity: HIGH**
**Category: Layout / spacing**

### Description
When the replacement text is shorter than the original, the suffix that was preserved on the same line is not moved leftward to fill the gap. A wide blank area remains between the replacement and the suffix.

### Evidence
| Edit | Target | Replacement | Symptom |
|------|--------|-------------|---------|
| SimpleTire Edit 10 | `275/45R20` (8 chars, ~52 pt wide) | `INC` (3 chars, ~20 pt wide) | Third product line reads "- INC        - V (68.58 lbs)" with ~32 pt of dead space |

### Root Cause
The reflow engine records the suffix start-x from the original span position and inserts it there unchanged. When the replacement is shorter, the suffix stays at its original x-coordinate rather than being moved left to `replacement_end_x + word_space`. The warning "suffix preserved (not redacted)" confirms the suffix is placed at its old position.

### Relevant Code
- `core.py` reflow engine: suffix preservation section (lines ~4053–4131)
- The suffix start rect is never adjusted by `(original_width - replacement_width)`

### Proposed Fix
After inserting replacement text, compute `gap = original_end_x - replacement_end_x`. If `gap > font_size * 0.3` (i.e., more than ~30% of a character width), move the suffix insertion point left by `gap` so it immediately follows the replacement. This requires reflowing or reinserting the suffix span at the new x-position.

---

## BUG-3 · Text Overflow When Replacement Is Wider (Collision Not Blocked)

**Severity: HIGH**
**Category: Layout / collision**

### Description
When the replacement text is wider than the original, the WARNING is logged but the edit is allowed to proceed. The replacement text overflows its cell or column boundary, colliding with adjacent content.

### Evidence
| Edit | Warning | Symptom |
|------|---------|---------|
| SimpleTire Edit 6 | (none logged) | "Three" overflows the right border of the "Total" column header cell, "e" visually clipped |
| Boarding Pass Edit 10 | (none logged) | "Three" (replacing "Seat" label) overflows its fixed-width box; "T r e" rendering with expanded spacing |
| LexisNexis Edit 6 | +26 pt wider | "Beta Amount" overflows into "Total" column cell; table header alignment broken |
| LexisNexis Edit 5 | +51 pt wider | "Solutions Number" overflows "Customer Number" column |
| 660-25 Edit 2 | +35 pt wider | "january" (in wrong font) overflows suffix |
| Omnibus Edit 4 | +54 pt wider | "EXOS HOLDINGS ARIZONA, LLC" (suffix on next line so no visible overflow — false positive warning) |

### Root Cause
The visual collision check (`optical.detect_visual_collision()`) uses an exclusion rect based on the *replacement* bounding box, not the *original* bounding box. If the replacement grows rightward outside the original rect, the collision detector may not see it as colliding. The "reflow trust" override (line ~4749) also suppresses collision failures when reflow reports success.

### Proposed Fix
1. Before inserting, measure the rendered width of the replacement text using the chosen font/size.
2. If `replacement_width > original_width + tolerance` (suggest tolerance = `font_size * 0.5`), check whether the region `[original_end_x, original_end_x + overflow]` contains any non-background pixels in the before-state pixmap. If yes, treat as COLLISION FAIL and return `success: False` with message "Replacement text too wide for available space".
3. Downgrade WARNING to conditional fail; don't rely solely on pixel collision after the fact.

---

## BUG-4 · Font Synthesis Fallback Produces Wrong Visual Style

**Severity: HIGH**
**Category: Font/style**

### Description
When glyph synthesis is incomplete (any glyph missing from the PDF's embedded font), the entire replacement falls back to Helvetica (`helv`). The resulting text has visibly different weight, style, and metrics from the surrounding text.

### Evidence
| Edit | Missing Glyphs | Symptom |
|------|---------------|---------|
| Boarding Pass Edit 3 | `R` | "CORP" in thin helv next to bold condensed "14B" original font |
| Boarding Pass Edit 6 | `y` | "New york" label field uses wrong font weight |
| Boarding Pass Edit 8 | `s` | "Solutions" label visibly lighter font |
| Boarding Pass Edit 9 | `E`, `S` | "JONES" in wrong font, different weight from "KOZGYO" |
| 660-25 Edit 2 | `j` | "january" in wrong font mid-sentence; surrounding text unchanged |

The boarding pass uses a custom condensed sans-serif. All synthesized fallback edits produce full-weight Helvetica — noticeably wider and lighter.

### Root Cause
When synthesis reports `missing {'R'}` (even one glyph), the whole replacement is routed to the generic insertion path using `helv`. The fallback doesn't attempt: (a) using the embedded font for glyphs it does have, (b) matching weight/style via system font lookup, or (c) flagging that the visual result will be wrong.

### Relevant Code
- `core.py` line ~4186–4196: synthesis incomplete → `Falling back to generic font.`
- The fallback path uses `helv` unconditionally

### Proposed Fix
1. When synthesis is incomplete due to missing glyphs, attempt a **visual weight match** via the existing font scoring mechanism (already implemented at line ~4200 for other paths).
2. If the visual match score is < 0.65 and synthesis failed, **return failure** rather than silently using a wrong font. Let the caller know: `{"success": False, "message": "Cannot match font — glyph 'R' not available and no visual match above threshold"}`.
3. Alternatively, implement a partial synthesis: use embedded font glyphs for characters present, and fallback only for the specific missing glyph (e.g., use a space-width placeholder and note it).

---

## BUG-5 · Special Characters Dropped on Font Fallback

**Severity: MEDIUM**
**Category: Data integrity**

### Description
When synthesis falls back to a generic font that lacks special characters (€, ©, accented letters, etc.), those characters are silently dropped from the rendered output.

### Evidence
| Edit | Target | Result |
|------|--------|--------|
| 660-25 Edit 2 | `1 h 42 min (390 €/h)` | After: `1 h january min (390   h)` — the `€` is missing, replaced by whitespace |

The Euro sign is part of the preserved suffix `(390 €/h)` but `helv` (or the rendered fallback path) doesn't contain it.

### Root Cause
The suffix `(390 €/h)` is re-inserted using the fallback font for the new text. `helv` doesn't map U+20AC (€). The character is silently dropped rather than raising an error.

### Proposed Fix
Before committing to a fallback font, check that all characters in the replacement (including preserved prefix/suffix context) are available in the chosen font. If not, collect the missing character set and return failure with details. At minimum, log the missing characters in `debug_log` as an error-level entry.

---

## BUG-6 · Multi-Context Replacement (Same Text in Body + Footer/Watermark)

**Severity: MEDIUM**
**Category: Semantic correctness**

### Description
Text that appears identically in both the main body and a footer/header/watermark region is replaced in all contexts. This is a variant of BUG-1 specific to document chrome vs. content.

### Evidence
| Edit | Context 1 | Context 2 | Defect |
|------|-----------|-----------|--------|
| Redline Edit 1 | Body: "ENERGIZE HOLDINGS, **INC.**" → "ENERGIZE HOLDINGS, MIAMI" ✓ | Footer: "[ENERGIZE HOLDINGS, **INC.**" → "[ENERGIZE HOLDINGS, MIAMI" | Footer now reads "MIAMI-" (missing space before hyphen) |

The space before " - MANAGEMENT RIGHTS LETTER" was part of the same span as "INC." in the footer, so when "INC." (with its trailing span) was redacted, the space before the hyphen was lost.

### Root Cause
Same as BUG-1 (all instances replaced). The secondary defect (missing space) is a suffix-boundary issue: the period in "INC." was used as a span boundary, and the space preceding " - " was attached to a redacted span rather than the preserved suffix.

### Proposed Fix
Same as BUG-1 fix (occurrence index selection). Additionally, improve span boundary detection: when redacting the target span, preserve any leading whitespace from the adjacent suffix span rather than relying on the redacted span to carry it.

---

## BUG-7 · Trailing Punctuation Spacing Lost After Replacement

**Severity: MEDIUM**
**Category: Layout / typography**

### Description
When the original text ends with punctuation (period, comma, colon) and the replacement text does not, the space that was associated with the punctuation character's span is lost, causing the suffix to abut directly against the replacement with no space.

### Evidence
| Edit | Before | After |
|------|--------|-------|
| Redline Edit 1 | "ENERGIZE HOLDINGS, INC. - MANAGEMENT RIGHTS LETTER" | "ENERGIZE HOLDINGS, MIAMI- MANAGEMENT RIGHTS LETTER" (no space before hyphen) |

### Root Cause
The "." in "INC." and the space " " after it may be in the same span as "INC." If the redaction covers that whole span, the space is lost. Alternatively, the space is in a separate span but the suffix detection includes it as trailing whitespace of the target rather than leading whitespace of the suffix.

### Proposed Fix
When identifying suffix spans for preservation, check that the first character of the first suffix span is not whitespace that logically belongs to the gap between replacement and suffix. If the gap between replacement end-x and suffix start-x is ≤ word_space, insert a single word-space character before the suffix.

---

## BUG-8 · Very Short Replacement of Long String Leaves Visible Artifacts

**Severity: MEDIUM**
**Category: Rendering / cleanup**

### Description
When a very long string (e.g., 54-char barcode) is replaced with a very short string (4 chars), "relaxed collision detection" is triggered and the edit may not fully clean up leftover character rendering artifacts at the bottom of the page.

### Evidence
| Edit | Target (54 chars) | Replacement | Symptom |
|------|------------------|-------------|---------|
| LexisNexis Edit 4 | `00A00000958404256WN2QJ22025053130958179640000001005270` | `2026` | After image shows `2026` plus apparent artifact characters below it |

### Root Cause
The `>80% shorter` detection relaxes collision detection (line ~4702). If the barcode string spans multiple content streams or is rendered as a single bitmap-like text element, the redaction may not cover all rendering artifacts from the original.

### Proposed Fix
For large-delta replacements (>80% shorter), apply a larger redaction rectangle (not just the text bounding box) to cover any rendering bleed, and perform the post-edit optical verification on a wider region. Do not relax collision checking — instead, widen the exclusion zone.

---

## Summary Table

| Bug | Severity | Category | Status | Fix Location |
|-----|----------|----------|--------|-------------|
| BUG-1: All instances replaced | HIGH | Semantic | **FIXED** | `core.py` — `occurrence_index` parameter |
| BUG-2: Suffix gap after shrink | HIGH | Layout | **FIXED** | `reflow.py` — suffix shift-left logic |
| BUG-3: Text overflow (wider) | HIGH | Collision | **FIXED** | `reflow.py` — overflow pre-check |
| BUG-4: Font synthesis fallback | HIGH | Font/style | **FIXED** | `reflow.py` — return failure instead of silent helv fallback |
| BUG-5: Special chars dropped | MEDIUM | Data integrity | OPEN | |
| BUG-6: Multi-context replace | MEDIUM | Semantic | **FIXED** | Subset of BUG-1 fix |
| BUG-7: Trailing punct spacing | MEDIUM | Typography | OPEN | |
| BUG-8: Artifact after big shrink | MEDIUM | Rendering | OPEN | |

---

## Notes on Clean Edits

The following edit types generally produce correct output:
- Body text replacements in paragraph flow (legal docs: Omnibus, Umbrella Policy)
- Address field replacements where font is Helvetica (`helv`) — synthesis not needed
- Single-occurrence short phrases in non-tabular context
- Replacements where target and replacement are similar length (< 15% width delta)
