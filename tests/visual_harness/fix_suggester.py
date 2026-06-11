"""
Fix Suggester - Aggregates LLM evaluation issues and generates actionable fix recommendations.

Maps issue categories to likely code locations in the Marcedit codebase.
"""

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Handle both module and standalone imports
try:
    from .llm_evaluator import LLMEvaluation, LLMIssue, load_evaluations
except ImportError:
    from llm_evaluator import LLMEvaluation, LLMIssue, load_evaluations


# Map issue categories to likely code locations
CODE_LOCATION_MAP = {
    "FONT_MATCHING": [
        "Sources/Marcedit/python_site/editor_pkg/visual_matcher.py - Font matching logic",
        "Sources/Marcedit/python_site/editor_pkg/core.py:_get_span_font_info - Font extraction",
        "Sources/Marcedit/python_site/editor_pkg/core.py:_find_internal_font_name - Font lookup",
    ],
    "POSITIONING": [
        "Sources/Marcedit/python_site/editor_pkg/core.py:replace_text_in_pdf - Baseline calculation",
        "Sources/Marcedit/python_site/editor_pkg/reflow.py - Text positioning logic",
    ],
    "SIZE_MISMATCH": [
        "Sources/Marcedit/python_site/editor_pkg/core.py:_get_span_font_info - Size extraction",
        "Sources/Marcedit/python_site/editor_pkg/visual_matcher.py - Size matching",
    ],
    "COLOR_MISMATCH": [
        "Sources/Marcedit/python_site/editor_pkg/core.py - Color extraction and application",
    ],
    "REDACTION_VISIBLE": [
        "Sources/Marcedit/python_site/editor_pkg/core.py:_redact_text - Redaction rectangle",
        "Sources/Marcedit/python_site/editor_pkg/core.py - Redaction color/opacity",
    ],
    "ARTIFACTS": [
        "Sources/Marcedit/python_site/editor_pkg/core.py - PDF modification logic",
        "Sources/Marcedit/python_site/editor_pkg/reflow.py - Layout recalculation",
    ],
    "CONTEXT_DAMAGE": [
        "Sources/Marcedit/python_site/editor_pkg/core.py - Target area isolation",
        "Sources/Marcedit/python_site/editor_pkg/core.py:_redact_text - Redaction bounds",
    ],
    "TEXT_CORRUPTION": [
        "Sources/Marcedit/python_site/editor_pkg/core.py - Text insertion",
        "Sources/Marcedit/python_site/editor_pkg/core.py - Character encoding",
    ],
    "BASELINE": [
        "Sources/Marcedit/python_site/editor_pkg/core.py:replace_text_in_pdf - Baseline calculation",
        "Sources/Marcedit/python_site/editor_pkg/visual_matcher.py - Vertical alignment",
    ],
}


@dataclass
class IssueAggregate:
    """Aggregated information about a category of issues."""
    category: str
    count: int
    severity_distribution: dict[str, int]  # severity -> count
    example_test_ids: list[str]
    sample_descriptions: list[str]
    likely_code_locations: list[str]


class FixSuggester:
    """Aggregates issues and generates fix recommendations."""

    def __init__(self, evaluations: list[LLMEvaluation]):
        self.evaluations = evaluations
        self.aggregates: dict[str, IssueAggregate] = {}
        self._aggregate_issues()

    def _aggregate_issues(self):
        """Aggregate issues by category."""
        category_data = defaultdict(lambda: {
            "count": 0,
            "severities": defaultdict(int),
            "test_ids": [],
            "descriptions": []
        })

        for ev in self.evaluations:
            for issue in ev.issues:
                cat = issue.category
                data = category_data[cat]
                data["count"] += 1
                data["severities"][issue.severity] += 1
                if ev.test_id not in data["test_ids"]:
                    data["test_ids"].append(ev.test_id)
                if len(data["descriptions"]) < 5:  # Keep up to 5 examples
                    data["descriptions"].append(issue.description)

        # Build aggregates
        for cat, data in category_data.items():
            self.aggregates[cat] = IssueAggregate(
                category=cat,
                count=data["count"],
                severity_distribution=dict(data["severities"]),
                example_test_ids=data["test_ids"][:10],  # Limit to 10 examples
                sample_descriptions=data["descriptions"],
                likely_code_locations=CODE_LOCATION_MAP.get(cat, [
                    "Unknown - manual investigation required"
                ])
            )

    def get_priority_order(self) -> list[str]:
        """Get issue categories sorted by priority (high severity, high count)."""
        def priority_score(cat: str) -> tuple:
            agg = self.aggregates.get(cat)
            if not agg:
                return (0, 0, 0)
            # Score: high severity count, medium count, total count
            high = agg.severity_distribution.get("high", 0)
            medium = agg.severity_distribution.get("medium", 0)
            return (high, medium, agg.count)

        return sorted(
            self.aggregates.keys(),
            key=priority_score,
            reverse=True
        )

    def generate_markdown_report(self) -> str:
        """Generate a markdown report with fix suggestions."""
        lines = []

        # Header
        lines.append("# PDF Editing Fix Suggestions")
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(f"Based on LLM evaluation of {len(self.evaluations)} tests.")
        lines.append("")

        # Verdict summary
        verdicts = defaultdict(int)
        for ev in self.evaluations:
            verdicts[ev.verdict] += 1

        lines.append("## Evaluation Summary")
        lines.append("")
        lines.append("| Verdict | Count |")
        lines.append("|---------|-------|")
        for v in ["PERFECT", "ACCEPTABLE", "DEGRADED", "BROKEN", "ERROR"]:
            if v in verdicts:
                lines.append(f"| {v} | {verdicts[v]} |")
        lines.append("")

        # Priority order
        priority = self.get_priority_order()

        if not priority:
            lines.append("## No Issues Found")
            lines.append("")
            lines.append("All evaluated tests passed without issues.")
            return "\n".join(lines)

        lines.append("## Priority Order")
        lines.append("")
        for i, cat in enumerate(priority, 1):
            agg = self.aggregates[cat]
            high = agg.severity_distribution.get("high", 0)
            severity_note = f" ({high} high severity)" if high > 0 else ""
            lines.append(f"{i}. **{cat}** ({agg.count} occurrences){severity_note}")
        lines.append("")

        # Detailed sections for each category
        lines.append("## Issue Details")
        lines.append("")

        for cat in priority:
            agg = self.aggregates[cat]
            lines.extend(self._format_category_section(agg))

        # Suggested fixes from evaluations
        lines.append("## Individual Suggested Fixes")
        lines.append("")

        fix_count = 0
        for ev in self.evaluations:
            if ev.suggested_fixes and ev.verdict in ("DEGRADED", "BROKEN"):
                lines.append(f"### {ev.test_id} ({ev.verdict})")
                lines.append("")
                for fix in ev.suggested_fixes[:3]:
                    lines.append(f"- {fix}")
                lines.append("")
                fix_count += 1
                if fix_count >= 20:  # Limit to 20 tests
                    lines.append("*(Showing first 20 tests with suggestions)*")
                    break

        return "\n".join(lines)

    def _format_category_section(self, agg: IssueAggregate) -> list[str]:
        """Format a single category section."""
        lines = []

        # Header with severity indicator
        high = agg.severity_distribution.get("high", 0)
        severity_label = "HIGH" if high > 0 else "MEDIUM" if agg.severity_distribution.get("medium", 0) > 0 else "LOW"

        lines.append(f"### {agg.category} ({severity_label})")
        lines.append("")

        # Stats
        lines.append(f"**Occurrences:** {agg.count}")
        lines.append("")

        # Severity breakdown
        if len(agg.severity_distribution) > 1:
            sev_str = ", ".join(
                f"{s}: {c}" for s, c in sorted(agg.severity_distribution.items())
            )
            lines.append(f"**Severity Breakdown:** {sev_str}")
            lines.append("")

        # Example tests
        if agg.example_test_ids:
            test_str = ", ".join(agg.example_test_ids[:5])
            lines.append(f"**Example Tests:** {test_str}")
            lines.append("")

        # Sample descriptions
        if agg.sample_descriptions:
            lines.append("**Sample Issues:**")
            for desc in agg.sample_descriptions[:3]:
                lines.append(f"- {desc}")
            lines.append("")

        # Code locations
        if agg.likely_code_locations:
            lines.append("**Likely Code Locations:**")
            for loc in agg.likely_code_locations:
                lines.append(f"- `{loc}`")
            lines.append("")

        lines.append("---")
        lines.append("")

        return lines


def generate_fix_report(
    evaluations_path: str,
    output_path: str
) -> str:
    """Load evaluations and generate fix report."""
    evaluations = load_evaluations(evaluations_path)

    suggester = FixSuggester(evaluations)
    report = suggester.generate_markdown_report()

    with open(output_path, 'w') as f:
        f.write(report)

    print(f"\nFix suggestions saved to: {output_path}")
    return report


def generate_fix_report_from_evaluations(
    evaluations: list[LLMEvaluation],
    output_path: str
) -> str:
    """Generate fix report directly from evaluation objects."""
    suggester = FixSuggester(evaluations)
    report = suggester.generate_markdown_report()

    with open(output_path, 'w') as f:
        f.write(report)

    print(f"\nFix suggestions saved to: {output_path}")
    return report


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fix_suggester.py <evaluations.json> [output.md]")
        sys.exit(1)

    evaluations_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "fix_suggestions.md"

    generate_fix_report(evaluations_path, output_path)
