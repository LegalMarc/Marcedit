"""
Feature Detector - Analyzes PDF pages to classify text regions and features.

Detects:
- Location features: header, footer, body, sidebar, table_cell
- Style features: bold, italic, serif, large, small, colored
- Content features: numeric, currency, special_chars
- Source features: native, ocr, embedded_font
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional
import re

# Add project root to path for core.py imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Sources", "Marcedit", "python_site"))

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF (fitz) required. Install with: pip install pymupdf")
    sys.exit(1)


@dataclass
class TextSpan:
    """Represents a single text span with all detected features."""
    text: str
    page_num: int
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    font_name: str
    font_size: float
    flags: int
    color: int
    
    # Detected features
    location: str = ""  # header, footer, body, sidebar, table_cell
    features: list[str] = field(default_factory=list)
    
    @property
    def is_bold(self) -> bool:
        return (self.flags & 16) != 0
    
    @property
    def is_italic(self) -> bool:
        return (self.flags & 2) != 0
    
    @property
    def is_serif(self) -> bool:
        return (self.flags & 4) != 0
    
    @property
    def is_monospace(self) -> bool:
        return (self.flags & 8) != 0


@dataclass
class PageAnalysis:
    """Analysis results for a single page."""
    page_num: int
    width: float
    height: float
    spans: list[TextSpan] = field(default_factory=list)
    font_palette: set[str] = field(default_factory=set)  # Unique font+size combos
    has_tables: bool = False
    has_ocr: bool = False
    column_count: int = 1


class FeatureDetector:
    """Analyzes PDF pages to detect text features and structure."""
    
    # Content detection patterns
    CURRENCY_PATTERN = re.compile(r'[\$€£¥]\s*[\d,]+\.?\d*')
    NUMERIC_PATTERN = re.compile(r'\d+')
    DATE_PATTERN = re.compile(r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{4}')
    SPECIAL_CHARS = set('©®™§¶•–—''""…†‡°±×÷')
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.analyses: list[PageAnalysis] = []
    
    def analyze_all_pages(self) -> list[PageAnalysis]:
        """Analyze all pages in the document."""
        self.analyses = []
        for page_num in range(len(self.doc)):
            analysis = self.analyze_page(page_num)
            self.analyses.append(analysis)
        return self.analyses
    
    def analyze_page(self, page_num: int) -> PageAnalysis:
        """Analyze a single page for features."""
        page = self.doc[page_num]
        rect = page.rect
        
        analysis = PageAnalysis(
            page_num=page_num,
            width=rect.width,
            height=rect.height
        )
        
        # Build set of embedded fonts from page.get_fonts()
        # Format: (xref, ext, type, basefont, name, encoding)
        # Embedded/subset fonts have '+' in basefont
        embedded_font_basenames = set()
        for font_info in page.get_fonts():
            basefont = font_info[3] if len(font_info) > 3 else ""
            if '+' in basefont:
                # Extract basename after the + (e.g., "BLUVWU+TimesNewRoman" -> "TimesNewRoman")
                basename = basefont.split('+', 1)[-1]
                embedded_font_basenames.add(basename)
                # Also add without comma suffix for matching
                if ',' in basename:
                    embedded_font_basenames.add(basename.split(',')[0])
        
        # Extract all text spans
        blocks = page.get_text("dict")["blocks"]
        all_spans = []
        
        for block in blocks:
            if block.get("type") != 0:  # Skip non-text blocks
                continue
            for line in block.get("lines", []):
                for span_data in line.get("spans", []):
                    span = self._create_span(span_data, page_num, rect)
                    if span and span.text.strip():
                        all_spans.append(span)
        
        # Detect page-level features
        analysis.has_tables = self._detect_tables(all_spans)
        analysis.has_ocr = self._detect_ocr(page)
        analysis.column_count = self._detect_columns(all_spans, rect.width)
        
        # Classify each span
        for span in all_spans:
            self._classify_location(span, rect, all_spans)
            self._classify_style(span)
            self._classify_content(span)
            self._classify_source(span, analysis.has_ocr, embedded_font_basenames)
            
            # Add to font palette
            font_key = f"{span.font_name}|{span.font_size:.1f}"
            analysis.font_palette.add(font_key)
        
        analysis.spans = all_spans
        return analysis
    
    def _create_span(self, span_data: dict, page_num: int, page_rect) -> Optional[TextSpan]:
        """Create a TextSpan from raw span data."""
        text = span_data.get("text", "")
        if not text:
            return None
        
        bbox = span_data.get("bbox", (0, 0, 0, 0))
        
        return TextSpan(
            text=text,
            page_num=page_num,
            bbox=tuple(bbox),
            font_name=span_data.get("font", "Unknown"),
            font_size=span_data.get("size", 12.0),
            flags=span_data.get("flags", 0),
            color=span_data.get("color", 0)
        )
    
    def _classify_location(self, span: TextSpan, page_rect, all_spans: list[TextSpan]):
        """Classify span location on page."""
        y_center = (span.bbox[1] + span.bbox[3]) / 2
        x_center = (span.bbox[0] + span.bbox[2]) / 2
        
        header_threshold = page_rect.height * 0.10
        footer_threshold = page_rect.height * 0.90
        sidebar_threshold = page_rect.width * 0.15
        
        # Check table membership
        if self._is_in_table(span, all_spans):
            span.location = "table_cell"
            span.features.append("table_cell")
        elif y_center < header_threshold:
            span.location = "header"
            span.features.append("header")
        elif y_center > footer_threshold:
            span.location = "footer"
            span.features.append("footer")
        elif x_center < sidebar_threshold or x_center > page_rect.width - sidebar_threshold:
            span.location = "sidebar"
            span.features.append("sidebar")
        else:
            span.location = "body"
            span.features.append("body")
    
    def _classify_style(self, span: TextSpan):
        """Classify style features."""
        if span.is_bold:
            span.features.append("bold")
        if span.is_italic:
            span.features.append("italic")
        if span.is_serif:
            span.features.append("serif")
        else:
            span.features.append("sans_serif")
        if span.is_monospace:
            span.features.append("monospace")
        
        if span.font_size >= 18:
            span.features.append("large")
        elif span.font_size <= 8:
            span.features.append("small")
        
        if span.color != 0:
            span.features.append("colored")
    
    def _classify_content(self, span: TextSpan):
        """Classify content features."""
        text = span.text
        
        if self.CURRENCY_PATTERN.search(text):
            span.features.append("currency")
        if self.DATE_PATTERN.search(text):
            span.features.append("date")
        if self.NUMERIC_PATTERN.search(text):
            span.features.append("numeric")
        
        if any(c in self.SPECIAL_CHARS for c in text):
            span.features.append("special_chars")
        
        words = text.split()
        if any(len(w) > 12 for w in words):
            span.features.append("long_word")
        if any(len(w) < 4 for w in words if w.isalpha()):
            span.features.append("short_word")
    
    def _classify_source(self, span: TextSpan, page_has_ocr: bool, embedded_font_basenames: set = None):
        """Classify source features."""
        font_name = span.font_name
        
        # Check if this font is embedded (detected from page.get_fonts())
        is_embedded = False
        if embedded_font_basenames:
            # Check exact match or prefix match
            if font_name in embedded_font_basenames:
                is_embedded = True
            else:
                # Also try without style suffix (e.g., "TimesNewRoman,Bold" -> check "TimesNewRoman")
                base_name = font_name.split(',')[0] if ',' in font_name else font_name
                if base_name in embedded_font_basenames:
                    is_embedded = True
        
        # Fallback: check for '+' in name (though get_text usually strips this)
        if not is_embedded and '+' in font_name:
            is_embedded = True
        
        if is_embedded:
            span.features.append("embedded_font")
            span.features.append("subset_font")
        else:
            span.features.append("system_font")
        
        if page_has_ocr:
            span.features.append("ocr")
        else:
            span.features.append("native")
    
    def _detect_tables(self, spans: list[TextSpan]) -> bool:
        """Detect if page has table-like structures."""
        if len(spans) < 4:
            return False
        
        # Look for Y-alignment clusters (rows)
        y_coords = [s.bbox[1] for s in spans]
        y_clusters = self._cluster_values(y_coords, threshold=5.0)
        
        # Look for X-alignment clusters (columns)
        x_coords = [s.bbox[0] for s in spans]
        x_clusters = self._cluster_values(x_coords, threshold=10.0)
        
        # Table if we have multiple aligned rows AND columns
        return len(y_clusters) >= 3 and len(x_clusters) >= 2
    
    def _is_in_table(self, span: TextSpan, all_spans: list[TextSpan]) -> bool:
        """Check if a span is part of a table structure."""
        y_tolerance = 5.0
        x_tolerance = 10.0
        
        # Count spans on same row
        same_row = [s for s in all_spans 
                    if abs(s.bbox[1] - span.bbox[1]) < y_tolerance and s != span]
        
        # If 2+ other items on same row with different X positions, likely table
        if len(same_row) >= 2:
            x_positions = set(round(s.bbox[0] / x_tolerance) for s in same_row)
            if len(x_positions) >= 2:
                return True
        
        return False
    
    def _detect_ocr(self, page) -> bool:
        """Detect if page has OCR layer (invisible text over image)."""
        # Check for render mode 3 (invisible text)
        content = page.get_text("rawdict")
        
        # Also check if page has large images
        images = page.get_images()
        if images:
            # If there's a large image and text on same page, might be OCR
            for img in images:
                xref = img[0]
                try:
                    pix = fitz.Pixmap(self.doc, xref)
                    # Large image covering most of page suggests scanned doc
                    if pix.width > page.rect.width * 0.8:
                        return True
                except:
                    pass
        
        return False
    
    def _detect_columns(self, spans: list[TextSpan], page_width: float) -> int:
        """Detect number of text columns on page."""
        if len(spans) < 10:
            return 1
        
        # Look for gap in X-distribution of text
        x_starts = sorted([s.bbox[0] for s in spans])
        
        # Find large gaps
        gaps = []
        for i in range(1, len(x_starts)):
            gap = x_starts[i] - x_starts[i-1]
            if gap > page_width * 0.1:  # Gap > 10% of page width
                gaps.append(x_starts[i])
        
        return len(gaps) + 1
    
    def _cluster_values(self, values: list[float], threshold: float) -> list[list[float]]:
        """Cluster nearby values together."""
        if not values:
            return []
        
        sorted_vals = sorted(values)
        clusters = [[sorted_vals[0]]]
        
        for val in sorted_vals[1:]:
            if val - clusters[-1][-1] < threshold:
                clusters[-1].append(val)
            else:
                clusters.append([val])
        
        return clusters
    
    def get_coverage_summary(self) -> dict:
        """Get summary of feature coverage across all pages."""
        all_features = set()
        feature_counts = {}
        
        for analysis in self.analyses:
            for span in analysis.spans:
                for feature in span.features:
                    all_features.add(feature)
                    feature_counts[feature] = feature_counts.get(feature, 0) + 1
        
        return {
            "total_pages": len(self.analyses),
            "total_spans": sum(len(a.spans) for a in self.analyses),
            "unique_features": sorted(all_features),
            "feature_counts": feature_counts,
            "font_palette": self._get_all_fonts()
        }
    
    def _get_all_fonts(self) -> list[str]:
        """Get all unique fonts across document."""
        fonts = set()
        for analysis in self.analyses:
            fonts.update(analysis.font_palette)
        return sorted(fonts)
    
    def close(self):
        """Close the document."""
        self.doc.close()


def analyze_pdf(pdf_path: str) -> dict:
    """Convenience function to analyze a PDF and return summary."""
    detector = FeatureDetector(pdf_path)
    detector.analyze_all_pages()
    summary = detector.get_coverage_summary()
    detector.close()
    return summary


if __name__ == "__main__":
    # Test with a sample file
    import json
    
    # Look for sample files
    sample_dirs = [
        "tests/visual_harness/samples",
        "ignored-resources/sample-files"
    ]
    
    for sample_dir in sample_dirs:
        if os.path.isdir(sample_dir):
            for filename in os.listdir(sample_dir):
                if filename.endswith(".pdf"):
                    pdf_path = os.path.join(sample_dir, filename)
                    print(f"\nAnalyzing: {pdf_path}")
                    try:
                        summary = analyze_pdf(pdf_path)
                        print(json.dumps(summary, indent=2))
                    except Exception as e:
                        print(f"  Error: {e}")
