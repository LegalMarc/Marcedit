"""
Prompt templates for LLM-based visual evaluation.

Defines:
- System prompt with quality dimensions
- Evaluation prompt template
- Edit-type specific guidance
"""

SYSTEM_PROMPT = """You are a visual quality assurance expert analyzing PDF text editing results.

Your task is to compare BEFORE and AFTER images of PDF text edits and assess the quality of the edit.

## Quality Dimensions to Evaluate

1. **Text Fidelity**: Is the replacement text rendered correctly? No missing characters, correct spelling?

2. **Font Matching**: Does the replacement text use the same (or visually similar) font as the original?
   - Check serif vs sans-serif consistency
   - Check weight (bold/regular) consistency
   - Check italic/oblique consistency

3. **Positioning**: Is the text in the correct location?
   - Baseline alignment with surrounding text
   - Horizontal alignment (left/right margins)
   - No unexpected overlaps with other content

4. **Size Matching**: Is the font size visually consistent with the original?

5. **Color Matching**: Is the text color correct (especially for non-black text)?

6. **Context Preservation**: Is surrounding content undamaged?
   - No artifacts or visual noise
   - No unintended changes to nearby text
   - Original layout preserved

## Verdict Categories

- **PERFECT**: Edit is visually indistinguishable from original (for identity edits) or looks completely natural
- **ACCEPTABLE**: Minor visual differences that most users wouldn't notice
- **DEGRADED**: Noticeable quality issues but still readable and functional
- **BROKEN**: Severe issues - text unreadable, major visual artifacts, or content damage

## Issue Categories

When reporting issues, use these categories:
- FONT_MATCHING: Wrong font family, weight, or style
- POSITIONING: Baseline shift, alignment issues
- SIZE_MISMATCH: Text size doesn't match original
- COLOR_MISMATCH: Text color incorrect
- REDACTION_VISIBLE: Original text still partially visible
- ARTIFACTS: Visual noise, rendering glitches
- CONTEXT_DAMAGE: Surrounding content affected
- TEXT_CORRUPTION: Characters missing or garbled
"""


def get_evaluation_prompt(test_context: dict) -> str:
    """Generate the evaluation prompt with test context."""
    edit_type = test_context.get("edit_type", "unknown")
    target_text = test_context.get("target_text", "")
    replacement_text = test_context.get("replacement_text", "")
    original_font = test_context.get("original_font", "Unknown")
    pixel_diff_pct = test_context.get("pixel_diff_pct", 0)
    ssim_score = test_context.get("ssim_score", 0)

    edit_guidance = EDIT_TYPE_GUIDANCE.get(edit_type, "")

    return f"""## Test Information

**Edit Type**: {edit_type}
**Original Text**: "{target_text}"
**Replacement Text**: "{replacement_text}"
**Original Font**: {original_font}
**Automated Metrics**: {pixel_diff_pct:.1f}% pixel diff, SSIM={ssim_score:.3f}

{edit_guidance}

## Your Task

Analyze the three images provided:
1. **BEFORE**: The original PDF region before editing
2. **AFTER**: The same region after the edit was applied
3. **DIFF**: Red highlights showing changed pixels

Based on your analysis, provide a JSON response with this exact structure:

```json
{{
  "verdict": "PERFECT|ACCEPTABLE|DEGRADED|BROKEN",
  "confidence": 0.0-1.0,
  "issues": [
    {{
      "category": "FONT_MATCHING|POSITIONING|SIZE_MISMATCH|COLOR_MISMATCH|REDACTION_VISIBLE|ARTIFACTS|CONTEXT_DAMAGE|TEXT_CORRUPTION",
      "severity": "low|medium|high",
      "description": "Brief description of the issue"
    }}
  ],
  "suggested_fixes": [
    "Specific suggestion for fixing the issue"
  ],
  "summary": "One sentence summary of your assessment"
}}
```

Respond ONLY with the JSON object, no additional text."""


EDIT_TYPE_GUIDANCE = {
    "identity": """## Identity Edit Guidance

This is an **identity edit** - the replacement text is identical to the original.
The expected result is that the AFTER image should be visually identical to BEFORE.

Any visual difference indicates a problem with the editing system.
- Font substitution issues will show even though text content is unchanged
- Baseline or positioning drift will be visible
- Size or weight changes indicate font matching problems

For identity edits, even small differences are significant failures.""",

    "substitution": """## Substitution Edit Guidance

This is a **substitution edit** - the text content is changed.

Expect some visual difference since the text itself is different.
Focus on:
- Does the NEW text render with the correct font style?
- Is the baseline aligned with surrounding text?
- Is the font size consistent?
- Are there any artifacts from the redaction process?

Small alignment differences may be acceptable if the overall appearance is clean.""",

    "overflow": """## Overflow Edit Guidance

This is an **overflow edit** - the replacement text is LONGER than the original.

The editing system must handle text that doesn't fit in the original bounding box.
Look for:
- Text truncation (cut off characters)
- Overlap with adjacent content
- Awkward line breaks
- Font size reduction to fit

Some visual difference from the original layout is expected and acceptable
if the text remains readable and doesn't corrupt surrounding content."""
}


def get_batch_summary_prompt(evaluations: list[dict]) -> str:
    """Generate prompt for summarizing batch evaluation results."""
    return f"""You have evaluated {len(evaluations)} PDF text edit tests.

Here is a summary of the evaluations:

{_format_evaluations_summary(evaluations)}

Please provide a brief executive summary (2-3 paragraphs) covering:
1. Overall quality assessment
2. Most common issues found
3. Priority areas for improvement

Keep the summary concise and actionable."""


def _format_evaluations_summary(evaluations: list[dict]) -> str:
    """Format evaluations for summary prompt."""
    verdicts = {}
    issues = {}

    for ev in evaluations:
        v = ev.get("verdict", "UNKNOWN")
        verdicts[v] = verdicts.get(v, 0) + 1

        for issue in ev.get("issues", []):
            cat = issue.get("category", "UNKNOWN")
            issues[cat] = issues.get(cat, 0) + 1

    lines = ["Verdict Distribution:"]
    for v, count in sorted(verdicts.items()):
        lines.append(f"  {v}: {count}")

    lines.append("\nIssue Categories:")
    for cat, count in sorted(issues.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}: {count}")

    return "\n".join(lines)
