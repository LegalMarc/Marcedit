# Marcedit Visual Verification Battery - Implementation Plan v2

## 1. Ultimate Goal
Achieve **100% confidence** that the text editing engine produces visually faithful output across all PDF feature combinations before App Store deployment. Enable rapid iteration: run hundreds of tests, review consolidated results, provide structured feedback, repeat.

---

## 2. Feature Coverage Matrix
To guarantee no blind spots, we define an explicit matrix of features to test. Each cell = a required test case.

### 2.1. Text Location Features
| Feature | Description | Detection Method |
|---------|-------------|------------------|
| **Header** | Top 10% of page (titles, running heads) | Y-coordinate < 0.1 * page_height |
| **Footer** | Bottom 10% of page (page numbers, disclaimers) | Y-coordinate > 0.9 * page_height |
| **Body** | Main content area | Everything else |
| **Sidebar/Margin** | Text in left/right 15% gutters | X-coordinate checks |
| **Table Cell** | Text aligned in grid patterns | Detect via line clustering (shared X or Y with neighbors) |
| **Form Field** | Near form widgets or labeled pairs ("Name: ____") | Proximity to AcroForm objects or ": " patterns |
| **Multi-Column** | Page has 2+ distinct text columns | Gap detection in X-axis text distribution |

### 2.2. Text Style Features
| Feature | Description | Detection Method |
|---------|-------------|------------------|
| **Bold** | flags & 16 | Span flags |
| **Italic** | flags & 2 | Span flags |
| **Serif** | flags & 4 | Span flags |
| **Sans-Serif** | !(flags & 4) | Span flags |
| **Monospace** | flags & 8 | Span flags |
| **Large (>18pt)** | Headlines, titles | Span size |
| **Small (<8pt)** | Fine print, footnotes | Span size |
| **Colored** | Non-black text | Span color != 0 |

### 2.3. Text Content Features
| Feature | Description | Detection Method |
|---------|-------------|------------------|
| **Numeric** | Dates, amounts, percentages | Regex: `\d+`, `\$`, `%` |
| **Currency** | Dollar amounts | Regex: `\$[\d,]+` |
| **Special Chars** | ©, ™, §, bullets | Unicode ranges |
| **Long Words** | Tests kerning/overflow | Word length > 12 chars |
| **Short Words** | Tests precision | Word length < 4 chars |
| **Mixed Case** | CamelCase, ALLCAPS | Pattern detection |

### 2.4. PDF Source Features
| Feature | Description | Detection Method |
|---------|-------------|------------------|
| **Native Text** | Clean vector text | No `/Subtype /Image` overlays |
| **OCR Layer** | Text over scanned image | Invisible text (render mode 3) or image behind |
| **Embedded Font** | Font subset in PDF | Font name has `+` prefix |
| **System Font** | Standard font reference | Font name is known system font |
| **Subset Font** | Partial character set | `+` prefix + limited glyphs |

---

## 3. Deterministic Test Generation

### 3.1. The Feature Requirement File
Instead of random probing, we maintain `tests/visual_harness/required_features.json`:
```json
{
  "location": ["header", "footer", "body", "table_cell", "sidebar"],
  "style": ["bold", "italic", "serif", "large", "small", "colored"],
  "content": ["numeric", "currency", "special_chars", "long_word"],
  "source": ["native", "ocr", "embedded_font", "subset_font"]
}
```

### 3.2. Coverage Tracker
The generator scans all PDFs and builds a **Coverage Matrix**:
- For each feature combination, find ONE representative text span
- Mark that span as a test case
- Track which features have NO coverage (prompts adding more sample PDFs)

### 3.3. Output: `test_manifest.json`
A deterministic, version-controlled list of all test cases:
```json
[
  {
    "id": "TC-001",
    "file": "samples/invoice.pdf",
    "page": 0,
    "target_text": "$1,250.00",
    "features": ["table_cell", "currency", "bold", "native"],
    "edit_type": "substitution",
    "replacement": "$9,999.99"
  },
  ...
]
```

---

## 4. Execution Engine

### 4.1. For Each Test Case:
1. Open PDF
2. Render "Before" image of target region (with margin context)
3. Execute `core.redact_and_replace()` with automatic font matching
4. Render "After" image of same region
5. Compute metrics (see §5)
6. Emit result to `results.json`

### 4.2. Isolation
Each test operates on a **fresh copy** of the PDF to avoid state leakage.

---

## 5. Automated Analysis & Pass/Fail Criteria

### 5.1. Metrics Computed
| Metric | Description | Threshold |
|--------|-------------|-----------|
| `pixel_diff_pct` | % of pixels changed in bounding box | Identity: <1%, Subst: <15% |
| `structural_similarity` | SSIM score (0-1) | >0.95 = PASS |
| `font_preserved` | Original font == Result font | Boolean |
| `baseline_shift_px` | Vertical movement of text baseline | <2px |
| `width_overflow_pct` | How much wider than original bbox | <5% |

### 5.2. Explanation Logic (Pseudo-code)
```python
def generate_explanation(tc, metrics):
    reasons = []
    verdict = "PASS"
    
    if tc.edit_type == "identity" and metrics.pixel_diff_pct > 1.0:
        reasons.append(f"Pixel diff {metrics.pixel_diff_pct:.1f}% exceeds 1% for identity edit")
        verdict = "FAIL"
    
    if not metrics.font_preserved:
        reasons.append(f"Font changed: {tc.original_font} → {metrics.result_font}")
        verdict = "WARN" if verdict != "FAIL" else "FAIL"
    
    if metrics.baseline_shift_px > 2:
        reasons.append(f"Baseline shifted {metrics.baseline_shift_px}px")
        verdict = "FAIL"
    
    if verdict == "PASS":
        reasons.append(f"All metrics within tolerance (SSIM={metrics.ssim:.2f})")
    
    return verdict, "; ".join(reasons)
```

---

## 6. Feedback Loop & Baseline Management

### 6.1. The Review Workflow (Chat-Based)
1. **Run:** `python run_tests.py` → generates `Visual_Regression_Report.pdf` + `results.json`
2. **Review:** You scroll through the PDF, noting test IDs (e.g., TC-001, TC-042)
3. **Provide Feedback in Chat:** You paste a paragraph like:
   ```
   TC-001 through TC-010 all look good.
   TC-011 bug: text is way too small.
   TC-012 known issue: this PDF always uses fallback font.
   TC-015 bug: baseline shifted, text overlaps border.
   TC-020 to TC-030 accept.
   ```
4. **I Parse & Apply:** I read your feedback, update `feedback.json` programmatically, and report back what I understood
5. **Update Baseline:** I run `python update_baseline.py` to mark accepted tests as expected
6. **Fix & Re-run:** For bugs, I investigate and fix. Then re-run only affected tests.

### 6.2. Feedback Syntax (Flexible)
The parser understands natural patterns:
- `TC-001 ok` / `TC-001 accept` / `TC-001 looks good` → Accept
- `TC-002 bug: [reason]` / `TC-002 fail: [reason]` → Bug requiring fix
- `TC-003 known` / `TC-003 known issue` / `TC-003 expected` → Known limitation
- `TC-004 skip` / `TC-004 ignore` → Exclude from future runs
- Ranges: `TC-010 to TC-020 accept` / `TC-010-TC-020 ok`

### 6.3. Baseline Storage
- `baselines/` directory contains per-test-case expected images
- Committed to git (or LFS for large files)
- Allows detecting regressions: "This USED to pass, now it fails"

### 6.4. Iterative Cycle
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Run Tests  │ ──► │ Review PDF  │ ──► │ Chat Feedback│
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                       │
       │            ┌─────────────┐            │
       └────────────│  Fix Bugs   │◄───────────┘
                    └─────────────┘
```

---

## 7. Report Format (PDF)

### 7.1. Summary Page
- **Run Date/Time**
- **Total Tests:** 247
- **PASS:** 230 | **WARN:** 10 | **FAIL:** 7
- **Critical Failures:** (list of TC-IDs with "bug" feedback)
- **Coverage Gaps:** (features with no test cases)

### 7.2. Detail Pages (1 per test)
```
┌─────────────────────────────────────────────────────────┐
│ TC-042: invoice.pdf | Page 1 | Table Cell | Currency   │
│ Edit: "$1,250.00" → "$9,999.99"                         │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│ │   BEFORE    │  │    AFTER    │  │    DIFF     │       │
│ │  [image]    │  │   [image]   │  │  [red px]   │       │
│ └─────────────┘  └─────────────┘  └─────────────┘       │
├─────────────────────────────────────────────────────────┤
│ VERDICT: ✅ PASS                                        │
│ Explanation: All metrics within tolerance (SSIM=0.98).  │
│ Font preserved: TimesNewRoman. Baseline shift: 0px.     │
├─────────────────────────────────────────────────────────┤
│ Your Feedback: [accept] [known_issue] [bug] [skip]      │
│ Notes: ________________________________________         │
└─────────────────────────────────────────────────────────┘
```

---

## 8. Sample Data Strategy

### 8.1. Required Sample Coverage
We need PDFs that collectively cover all matrix cells. Minimum set:
- `clean_invoice.pdf` - Tables, currency, numbers, native text
- `legal_contract.pdf` - Body text, headers, footers, fine print, serif fonts
- `scanned_form.pdf` - OCR layer, form fields
- `brochure.pdf` - Multi-column, colored text, large headlines, images
- `spreadsheet_export.pdf` - Dense tables, monospace, small text

### 8.2. Locations
- **Public:** `tests/visual_harness/samples/` - Synthetic/safe-to-share PDFs
- **Private:** `ignored-resources/sample-files/` - Real-world files (gitignored)

---

## 9. Implementation Phases

### Phase 1: Foundation
- [ ] Create directory structure
- [ ] Implement `feature_detector.py` (analyze page structure)
- [ ] Implement `test_generator.py` (produce `test_manifest.json`)
- [ ] Implement `test_runner.py` (execute tests, emit `results.json`)

### Phase 2: Reporting
- [ ] Implement `report_builder.py` (generate PDF report)
- [ ] Implement `feedback_processor.py` (parse your annotations)

### Phase 3: Baseline Management
- [ ] Implement `baseline_manager.py` (store/compare expected images)
- [ ] Implement regression detection logic

### Phase 4: CI Integration (Future)
- [ ] GitHub Actions workflow to run on PR
- [ ] Auto-comment with failure summary
