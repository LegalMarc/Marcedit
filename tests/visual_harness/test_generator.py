"""
Test Generator - Creates deterministic test cases from PDF analysis.

Generates test_manifest.json with TestCase objects covering:
- All required features from required_features.json
- One representative span per unique font
- Identity, Substitution, and Overflow edit types
"""

import os
import sys
import json
import random
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

# Ensure reproducible test generation
random.seed(42)

# Handle both module and standalone imports
try:
    from .feature_detector import FeatureDetector, TextSpan, PageAnalysis
except ImportError:
    from feature_detector import FeatureDetector, TextSpan, PageAnalysis


@dataclass
class TestCase:
    """A single test case for visual verification."""
    id: str
    file: str  # Relative path to PDF
    page: int
    target_text: str
    target_bbox: tuple[float, float, float, float]
    edit_type: str  # identity, substitution, overflow
    replacement: str
    features: list[str]
    original_font: str
    original_size: float


# Required features to ensure coverage
REQUIRED_FEATURES = {
    "location": ["header", "footer", "body", "table_cell", "sidebar"],
    "style": ["bold", "italic", "serif", "sans_serif", "large", "small", "colored"],
    "content": ["numeric", "currency", "date", "special_chars", "long_word"],
    "source": ["native", "ocr", "embedded_font", "system_font"]
}


class TestGenerator:
    """Generates test cases from PDF analysis."""
    
    def __init__(self, sample_dirs: list[str]):
        self.sample_dirs = sample_dirs
        self.test_cases: list[TestCase] = []
        self.coverage: dict[str, list[str]] = {}  # feature -> [test_ids]
        self.tc_counter = 0
    
    def generate_all(self) -> list[TestCase]:
        """Generate test cases for all PDFs in sample directories."""
        pdf_files = self._find_pdfs()
        
        for pdf_path in pdf_files:
            self._generate_for_pdf(pdf_path)
        
        self._ensure_coverage()
        return self.test_cases
    
    def _find_pdfs(self) -> list[str]:
        """Find all PDF files in sample directories."""
        pdfs = []
        for sample_dir in self.sample_dirs:
            if not os.path.isdir(sample_dir):
                continue
            for root, dirs, files in os.walk(sample_dir):
                for f in files:
                    if f.lower().endswith(".pdf") and not f.startswith("."):
                        pdfs.append(os.path.join(root, f))
        return sorted(pdfs)
    
    def _generate_for_pdf(self, pdf_path: str):
        """Generate test cases for a single PDF."""
        relative_path = self._make_relative(pdf_path)
        
        try:
            detector = FeatureDetector(pdf_path)
            analyses = detector.analyze_all_pages()
            
            for analysis in analyses:
                self._generate_for_page(relative_path, analysis)
            
            detector.close()
        except Exception as e:
            print(f"Warning: Could not analyze {pdf_path}: {e}")
    
    def _generate_for_page(self, pdf_path: str, analysis: PageAnalysis):
        """Generate test cases for a single page."""
        # Strategy 1: Feature-based probes (one per location type found)
        locations_covered = set()
        for span in analysis.spans:
            if span.location not in locations_covered and len(span.text) >= 5:
                self._create_test_case(pdf_path, span, "identity")
                locations_covered.add(span.location)
        
        # Strategy 2: Font variety probes (one per unique font, max 5)
        fonts_covered = set()
        for span in analysis.spans:
            font_key = f"{span.font_name}|{span.font_size:.0f}"
            if font_key not in fonts_covered and len(span.text) >= 5:
                # Alternate between edit types
                edit_type = ["identity", "substitution", "overflow"][len(fonts_covered) % 3]
                self._create_test_case(pdf_path, span, edit_type)
                fonts_covered.add(font_key)
                if len(fonts_covered) >= 5:
                    break
        
        # Strategy 3: Content-based probes (currency, dates, etc.)
        for span in analysis.spans:
            if "currency" in span.features and len(span.text) >= 4:
                self._create_test_case(pdf_path, span, "substitution")
                break
        
        for span in analysis.spans:
            if "date" in span.features and len(span.text) >= 4:
                self._create_test_case(pdf_path, span, "substitution")
                break
    
    def _create_test_case(self, pdf_path: str, span: TextSpan, edit_type: str) -> TestCase:
        """Create a test case from a span."""
        self.tc_counter += 1
        tc_id = f"TC-{self.tc_counter:04d}"
        
        # Generate replacement text based on edit type
        replacement = self._generate_replacement(span.text, edit_type)
        
        tc = TestCase(
            id=tc_id,
            file=pdf_path,
            page=span.page_num,
            target_text=span.text.strip(),
            target_bbox=span.bbox,
            edit_type=edit_type,
            replacement=replacement,
            features=span.features.copy(),
            original_font=span.font_name,
            original_size=span.font_size
        )
        
        self.test_cases.append(tc)
        
        # Track coverage
        for feature in span.features:
            if feature not in self.coverage:
                self.coverage[feature] = []
            self.coverage[feature].append(tc_id)
        
        return tc
    
    def _generate_replacement(self, original: str, edit_type: str) -> str:
        """Generate replacement text based on edit type."""
        if edit_type == "identity":
            return original
        
        elif edit_type == "substitution":
            # Smart substitutions
            import re
            
            # Replace years
            if re.search(r'\b20\d{2}\b', original):
                return re.sub(r'\b20\d{2}\b', '2025', original)
            
            # Replace currency amounts
            if re.search(r'\$[\d,]+', original):
                return re.sub(r'\$[\d,]+\.?\d*', '$9,999.99', original)
            
            # Replace percentages
            if re.search(r'\d+%', original):
                return re.sub(r'\d+%', '99%', original)
            
            # Default: change first word
            words = original.split()
            if words:
                words[0] = words[0].upper()
                return ' '.join(words)
            return original
        
        elif edit_type == "overflow":
            # Add text to test wrapping
            words = original.split()
            if len(words) >= 2:
                words.insert(1, "ADDITIONAL")
                return ' '.join(words)
            return original + " EXTENDED"
        
        return original
    
    def _ensure_coverage(self):
        """Check and report on feature coverage."""
        missing = []
        for category, features in REQUIRED_FEATURES.items():
            for feature in features:
                if feature not in self.coverage:
                    missing.append(f"{category}:{feature}")
        
        if missing:
            print(f"Warning: Missing coverage for features: {missing}")
            print("Consider adding PDFs that contain these features.")
    
    def _make_relative(self, path: str) -> str:
        """Convert absolute path to relative path from project root."""
        # Find project root (contains Package.swift or .git)
        current = os.path.dirname(os.path.abspath(path))
        for _ in range(10):  # Max 10 levels up
            if os.path.exists(os.path.join(current, "Package.swift")):
                return os.path.relpath(path, current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return path
    
    def get_coverage_report(self) -> dict:
        """Generate coverage report."""
        covered = {}
        uncovered = []
        
        for category, features in REQUIRED_FEATURES.items():
            covered[category] = {}
            for feature in features:
                if feature in self.coverage:
                    covered[category][feature] = len(self.coverage[feature])
                else:
                    uncovered.append(f"{category}:{feature}")
        
        return {
            "total_tests": len(self.test_cases),
            "covered_features": covered,
            "uncovered_features": uncovered,
            "generated_at": datetime.now().isoformat()
        }
    
    def save_manifest(self, output_path: str):
        """Save test manifest to JSON file."""
        manifest = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "test_cases": [asdict(tc) for tc in self.test_cases],
            "coverage": self.get_coverage_report()
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"Generated {len(self.test_cases)} test cases -> {output_path}")


def generate_tests(sample_dirs: list[str], output_path: str) -> list[TestCase]:
    """Convenience function to generate tests."""
    generator = TestGenerator(sample_dirs)
    tests = generator.generate_all()
    generator.save_manifest(output_path)
    return tests


if __name__ == "__main__":
    # Default sample directories
    sample_dirs = [
        "tests/visual_harness/samples",
        "ignored-resources/sample-files"
    ]
    
    output_path = "tests/visual_harness/output/test_manifest.json"
    
    tests = generate_tests(sample_dirs, output_path)
    print(f"\nGenerated {len(tests)} test cases")
