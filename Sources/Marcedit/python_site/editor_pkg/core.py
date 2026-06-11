"""
Marcedit PDF Editor - Core Python Module
Called from Swift via PythonKit

Uses PyMuPDF (fitz) for text replacement with font preservation.
"""
import fitz  # PyMuPDF
import os
import atexit
import gc
import threading
from functools import lru_cache
from fontTools.ttLib import TTFont
from fontTools.ttLib import TTCollection
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools import subset
import io
import glob
import tempfile
import unicodedata
from . import optical
from . import reflow
from .logging_utils import get_logger, monitor_performance

_log = get_logger("core")

# ── Font-object cache (Week 7 Day 1) ─────────────────────────────────────────
# Maps font_path → fitz.Font so the same font file is loaded from disk only
# once per session.  The cache is bounded to avoid unbounded memory growth.
_font_object_cache: dict[str, object] = {}
_FONT_OBJECT_CACHE_MAX = 60  # max distinct font files to keep in memory
_font_object_cache_lock = threading.Lock()


def _get_cached_font(font_path: str) -> object | None:
    """Return a cached fitz.Font for *font_path*, loading it on first access."""
    with _font_object_cache_lock:
        if font_path in _font_object_cache:
            return _font_object_cache[font_path]
    # Load outside the lock — fitz.Font() may do disk I/O.
    try:
        font = fitz.Font(fontfile=font_path)
    except Exception:
        return None
    with _font_object_cache_lock:
        # Another thread may have loaded the same font while we did; that's fine.
        if font_path not in _font_object_cache:
            if len(_font_object_cache) >= _FONT_OBJECT_CACHE_MAX:
                _font_object_cache.pop(next(iter(_font_object_cache)))
            _font_object_cache[font_path] = font
        return _font_object_cache[font_path]


# ── Pixmap cache (Week 8) ─────────────────────────────────────────────────────
# Caches the "before" pixmap captures used by collision detection.  Only the
# before-state snapshot is cached; the after-state is always freshly rendered
# because the page content has just changed.
#
# Key: (normalised_file_path, page_index, x0r, y0r, x1r, y1r, zoom)
# where x*r / y*r are the rect coordinates rounded to one decimal place to
# absorb floating-point noise without conflating distinct rects.
#
# Memory: a typical text-span clip at zoom=2 is ≈200 × 24 px ≈ 20 KB.
# 200 entries therefore uses ≈ 4 MB — well within budget.
_pixmap_cache: dict[tuple, object] = {}
_PIXMAP_CACHE_MAX = 200
_pixmap_cache_lock = threading.Lock()


def _pixmap_cache_key(file_path: str, page_index: int, rect, zoom: float) -> tuple:
    """Build a hashable cache key for a pixmap capture."""
    return (
        os.path.normpath(file_path),
        page_index,
        round(rect.x0, 1), round(rect.y0, 1),
        round(rect.x1, 1), round(rect.y1, 1),
        zoom,
    )


def _get_cached_pixmap(file_path: str, page_index: int, rect, zoom: float) -> object | None:
    """Return a cached before-state pixmap, or *None* on cache miss."""
    with _pixmap_cache_lock:
        return _pixmap_cache.get(_pixmap_cache_key(file_path, page_index, rect, zoom))


def _store_cached_pixmap(file_path: str, page_index: int, rect, zoom: float, pix) -> None:
    """Insert *pix* into the bounded pixmap cache, evicting the oldest entry if full."""
    with _pixmap_cache_lock:
        if len(_pixmap_cache) >= _PIXMAP_CACHE_MAX:
            _pixmap_cache.pop(next(iter(_pixmap_cache)))
        _pixmap_cache[_pixmap_cache_key(file_path, page_index, rect, zoom)] = pix


def _invalidate_file_pixmaps(file_path: str) -> int:
    """
    Remove all cached pixmaps whose source path matches *file_path*.

    Call this after writing to *file_path* so that subsequent reads of that
    file will capture a fresh before-state pixmap rather than the stale one.

    Returns the number of entries removed.
    """
    norm = os.path.normpath(file_path)
    with _pixmap_cache_lock:
        to_delete = [k for k in _pixmap_cache if k[0] == norm]
        for k in to_delete:
            del _pixmap_cache[k]
    return len(to_delete)


def get_cache_stats() -> dict:
    """Return a snapshot of the in-process performance cache state."""
    with _font_object_cache_lock:
        font_obj_size = len(_font_object_cache)
    with _pixmap_cache_lock:
        pixmap_size = len(_pixmap_cache)
    with _system_font_cache_lock:
        sys_font_size = len(_system_font_cache)
    return {
        "font_object_cache_size": font_obj_size,
        "font_object_cache_max":  _FONT_OBJECT_CACHE_MAX,
        "pixmap_cache_size":      pixmap_size,
        "pixmap_cache_max":       _PIXMAP_CACHE_MAX,
        "system_font_cache_size": sys_font_size,
        "system_font_cache_max":  _SYSTEM_FONT_CACHE_MAX,
        "normalize_unicode_cache":        normalize_unicode.cache_info()._asdict()
            if hasattr(normalize_unicode, "cache_info") else {},
        "normalize_text_for_matching_cache": normalize_text_for_matching.cache_info()._asdict()
            if hasattr(normalize_text_for_matching, "cache_info") else {},
        "normalize_special_chars_cache":  normalize_special_chars.cache_info()._asdict()
            if hasattr(normalize_special_chars, "cache_info") else {},
    }


class SearchDiagnostic:
    """Captures non-content diagnostics when text search fails."""

    def __init__(self, target_text: str, page_number: int):
        self.target_text = target_text
        self.page_number = page_number
        self.strategies_tried = []
        self.page_text_sample = ""
        self.unicode_summary = {}

    def add_strategy(self, name: str, result: str):
        """Record a search strategy that was tried."""
        self.strategies_tried.append({"name": name, "result": result})

    def capture_page_text(self, page_text: str, max_chars: int = 500):
        """Record only text length so diagnostics do not expose PDF content."""
        self.page_text_sample = ""
        self.page_text_length = len(page_text) if page_text else 0

    def capture_unicode(self):
        """Capture aggregate Unicode classes without storing reconstructive text."""
        sample = self.target_text[:50]
        self.unicode_summary = {
            "sample_length": len(sample),
            "non_ascii_count": sum(1 for c in sample if ord(c) > 127),
            "invisible_count": sum(1 for c in sample if ord(c) in {0x200b, 0x200c, 0x200d, 0xfeff}),
            "soft_hyphen_count": sum(1 for c in sample if ord(c) == 0x00ad),
            "ligature_count": sum(1 for c in sample if 0xfb00 <= ord(c) <= 0xfb06),
            "category_counts": {},
        }
        for c in sample:
            category = unicodedata.category(c)
            self.unicode_summary["category_counts"][category] = (
                self.unicode_summary["category_counts"].get(category, 0) + 1
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "target_length": len(self.target_text),
            "page_number": self.page_number,
            "strategies_tried": self.strategies_tried,
            "unicode_summary": getattr(self, "unicode_summary", {}),
            "page_text_length": getattr(self, "page_text_length", 0),
        }


def _safe_unicode_name(char: str) -> str:
    """Get Unicode name for a character safely."""
    import unicodedata
    try:
        return unicodedata.name(char, "UNKNOWN")
    except ValueError:
        return "UNKNOWN"


def _is_ttc_file(file_path: str) -> bool:
    """Check if a font file is a TrueType Collection (TTC) by reading magic bytes."""
    try:
        with open(file_path, 'rb') as f:
            magic = f.read(4)
            return magic == b'ttcf'
    except Exception:
        return False


def _extract_font_from_ttc(ttc_path: str, ps_name: str = None, font_index: int = 0) -> bytes:
    """
    Extract a single font from a TTC file.
    
    Args:
        ttc_path: Path to the TTC file
        ps_name: PostScript name to match (optional, preferred)
        font_index: Index to use if ps_name not found (default 0)
        
    Returns:
        bytes: The extracted font as TTF bytes
    """
    ttc = None
    try:
        ttc = TTCollection(ttc_path)
        
        # If PostScript name provided, search for it
        if ps_name:
            ps_target = ps_name.replace('-', '').replace(' ', '').lower()
            
            for i, ttf in enumerate(ttc):
                try:
                    name_table = ttf.get('name')
                    font_ps_name = None
                    if name_table:
                        for record in name_table.names:
                            if record.nameID == 6:  # PostScript name
                                font_ps_name = str(record)
                                break
                    
                    if font_ps_name:
                        tf_name = font_ps_name.replace('-', '').replace(' ', '').lower()
                        if tf_name == ps_target:
                            # Found it! Extract to buffer
                            buf = io.BytesIO()
                            ttf.save(buf)
                            return buf.getvalue()
                except Exception:
                    continue
        
        # Fallback: use specified index (or 0)
        if font_index < len(ttc):
            buf = io.BytesIO()
            ttc[font_index].save(buf)
            return buf.getvalue()
        else:
            # Index out of range, use first font
            buf = io.BytesIO()
            ttc[0].save(buf)
            return buf.getvalue()
            
    finally:
        if ttc:
            ttc.close()


def subset_font_buffer(font_buffer: bytes, text: str) -> bytes:
    """
    Subset a font buffer (TTF/OTF) to include only the specified characters.
    Reduces file size by removing unused glyphs.

    Note: This function does NOT handle TTC files. Use subset_font_from_path for TTC support.

    Args:
        font_buffer: The source font file bytes (TTF/OTF only, not TTC)
        text: The string of characters to keep in the subset

    Returns:
        bytes: The subsetted font file
    """
    font = None
    try:
        # Load font from buffer
        in_stream = io.BytesIO(font_buffer)
        font = TTFont(in_stream)

        # Configure subsetter with optimized options
        options = subset.Options()

        # Keep essential layout features for proper rendering
        # Reduce verbosity by only keeping critical features
        options.layout_features = ['*']  # Keep all layout features
        options.name_IDs = ['*']  # Keep all name IDs

        # Drop non-essential tables to reduce size and warnings
        # These tables are not required for basic text rendering
        options.drop_tables = [
            'DSIG',  # Digital signature (not needed in subset)
        ]

        # Suppress verbose warnings about advanced typography tables
        # that fontTools doesn't know how to subset
        import logging
        fonttools_logger = logging.getLogger('fontTools.subset')
        old_level = fonttools_logger.level
        fonttools_logger.setLevel(logging.ERROR)

        try:
            subsetter = subset.Subsetter(options=options)
            subsetter.populate(text=text)
            subsetter.subset(font)
        finally:
            # Restore logging level
            fonttools_logger.setLevel(old_level)

        # Save to buffer
        out_stream = io.BytesIO()
        font.save(out_stream)
        return out_stream.getvalue()

    except Exception as e:
        # BUG #59 FIX: Proper error logging for font subsetting failures
        import sys
        error_msg = f"[Core] WARNING: Font subsetting failed: {e}. Using original font."
        print(error_msg, file=sys.stderr)  # Log to stderr for visibility
        # Also log the exception type and details for debugging
        print(f"[Core] Exception type: {type(e).__name__}", file=sys.stderr)
        print(f"[Core] Font buffer size: {len(font_buffer) if font_buffer else 0} bytes", file=sys.stderr)
        # Fallback: return original buffer (unsubsetted font)
        return font_buffer
    finally:
        if font:
            font.close()


def subset_font_from_path(font_path: str, text: str, ps_name: str = None) -> bytes:
    """
    Subset a font file (TTF, OTF, or TTC) to include only the specified characters.
    Handles TrueType Collections by extracting the correct font first.
    
    Args:
        font_path: Path to the font file
        text: The string of characters to keep in the subset
        ps_name: PostScript name for TTC files (to identify which font to extract)
        
    Returns:
        bytes: The subsetted font file
    """
    try:
        if _is_ttc_file(font_path):
            # Extract specific font from TTC first
            print(f"TTC detected: extracting font (hasPostScriptName={bool(ps_name)})")
            font_buffer = _extract_font_from_ttc(font_path, ps_name=ps_name)
            print(f"Extracted {len(font_buffer)} bytes from TTC")
        else:
            # Regular font file - read directly
            with open(font_path, 'rb') as f:
                font_buffer = f.read()
        
        # Now subset the extracted/read font
        return subset_font_buffer(font_buffer, text)
        
    except Exception as e:
        print(f"subset_font_from_path failed: {type(e).__name__}")
        # Fallback: read and return original file
        with open(font_path, 'rb') as f:
            return f.read()

def get_precise_metrics(font_path: str) -> dict:
    """
    Read precise vertical metrics from font tables (OS/2, hhea).
    Used for pixel-perfect vertical alignment.
    
    Returns dict with:
        ascender_ratio: ascent / units_per_em
        descender_ratio: descent / units_per_em (positive)
        line_gap_ratio: line_gap / units_per_em
        cap_height_ratio: cap_height / units_per_em
    """
    font = None
    try:
        font = TTFont(font_path)
        
        if 'head' not in font or 'hhea' not in font:
            return {'success': False}
        head = font['head']
        hhea = font['hhea']
        os2 = font.get('OS/2')  # Not all fonts have OS/2 table
        
        upm = head.unitsPerEm
        if not upm or upm <= 0:
            return {'success': False}

        # Prefer sTypoAscender/Descender from OS/2 if valid (USE_TYPO_METRICS flag)
        # But for PDF rendering, hhea values often match better.
        # Let's get both and prioritize hhea for PyMuPDF context usually.

        ascent = hhea.ascent
        descent = abs(hhea.descent)
        line_gap = hhea.lineGap

        # OS/2 overrides
        if os2 and os2.version >= 2:
             # Check if we should use typo metrics?
             # For now, let's grab cap height which is critical and missing in hhea
             cap_height = os2.sCapHeight
        else:
             cap_height = ascent * 0.7 # Fallback

        return {
            'ascent_ratio': ascent / upm,
            'descent_ratio': descent / upm,
            'line_gap_ratio': line_gap / upm,
            'cap_height_ratio': cap_height / upm,
            'success': True
        }
        
    except Exception as e:
        print(f"Precise metrics failed: {e}")
        return {'success': False}
    finally:
        if font:
            font.close()

from .visual_matcher import VisualFontMatcher

# Track extracted preview fonts for cleanup
_temp_preview_fonts: set[str] = set()

def _cleanup_temp_fonts():
    """Cleanup temporary preview font files on exit."""
    for path in _temp_preview_fonts:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    _temp_preview_fonts.clear()

atexit.register(_cleanup_temp_fonts)


def _startup_cleanup():
    """Clean up stale preview fonts from previous sessions."""
    try:
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, "marcedit_preview_*")
        files = glob.glob(pattern)
        if files:
            print(f"[Core] Cleaning up {len(files)} stale preview font files...")
            for path in files:
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Core] Startup cleanup failed: {e}")

# Run cleanup on import
_startup_cleanup()


def _get_span_font_info(page, target_text: str, search_rect) -> dict:
    """
    Extract detailed font information from the text span at the given location.
    Returns font properties needed to recreate the text with the same appearance.
    
    Critical for exact font matching:
    - origin: The exact baseline starting point of the text
    - fontsize: The exact size from the PDF
    - bbox: The bounding box for precise positioning
    - ascender/descender: Font metrics for baseline calculation
    """
    defaults = {
        'fontname': 'helv',
        'fontsize': 11.0,
        'color': (0, 0, 0),
        'flags': 0,
        'origin': None,
        'bbox': None,
        'ascender': 0.8,  # Default ratio
        'descender': 0.2,
        'span_text': '',  # Prevent KeyError in _get_reference_char_metrics
        'found': False
    }
    
    try:
        # Get text as dictionary with full font details
        # Expand search rect slightly to catch edge cases
        expanded_rect = search_rect + (-2, -2, 2, 2)
        blocks = page.get_text("dict", clip=expanded_rect).get("blocks", [])

        best_match = None
        best_overlap = 0
        
        for block in blocks:
            if block.get("type") != 0:  # text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    if not span_text:
                        continue
                    
                    # Calculate overlap between target and span text
                    # This handles partial matches better
                    span_clean = span_text.strip()
                    target_clean = target_text.strip()
                    
                    # Check for exact match first
                    if span_clean == target_clean:
                        overlap = len(target_clean)
                    # Check if target contains span (multi-span text)
                    elif span_clean in target_clean:
                        overlap = len(span_clean)
                    # Check if span contains target
                    elif target_clean in span_clean:
                        overlap = len(target_clean)
                    # Check first N characters match
                    elif len(span_clean) >= 3 and len(target_clean) >= 3:
                        if span_clean[:3] == target_clean[:3]:
                            overlap = 3
                        else:
                            overlap = 0
                    else:
                        overlap = 0
                    
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_match = span
                    elif overlap == best_overlap and overlap > 0:
                        # Tie-breaker: Prefer non-generic fonts (AVOID OCR Helvetica)
                        # or prefer fonts with '+' (subsets are usually vector)
                        current_font = best_match.get("font", "").lower()
                        new_font = span.get("font", "").lower()
                        
                        current_is_generic = "helv" in current_font or "arial" in current_font
                        new_is_generic = "helv" in new_font or "arial" in new_font
                        
                        if current_is_generic and not new_is_generic:
                            best_match = span
                        elif "+" in new_font and "+" not in current_font:
                            # Subsets are almost always the REAL vector text
                            best_match = span
        
        if best_match:
            font_name = best_match.get("font", "helv")
            font_size = best_match.get("size", 11.0)
            color_int = best_match.get("color", 0)
            origin = best_match.get("origin", None)
            flags = best_match.get("flags", 0)
            bbox = best_match.get("bbox", None)
            ascender = best_match.get("ascender", 0.8)
            descender = best_match.get("descender", 0.2)
            
            # Convert packed color to RGB tuple
            if isinstance(color_int, int):
                r = ((color_int >> 16) & 0xFF) / 255.0
                g = ((color_int >> 8) & 0xFF) / 255.0
                b = (color_int & 0xFF) / 255.0
                color = (r, g, b)

                # DIAGNOSTIC: Log color extraction (helps debug red text issue)
                import sys
                print(f"[DIAGNOSTIC] _get_span_font_info: Extracted color RGB{color} (int: {color_int}) from span length={len(best_match.get('text', ''))}", file=sys.stderr)

                # Validate color is not pure black unless it's actually black
                # This catches cases where color extraction might fail
                if color_int == 0:
                    # Could be actual black, or could be error - log for debugging
                    pass
            elif isinstance(color_int, (tuple, list)) and len(color_int) >= 3:
                # Color already in tuple format (rare but possible)
                color = (color_int[0], color_int[1], color_int[2])
            else:
                color = (0, 0, 0)
            
            return {
                'fontname': font_name,
                'fontsize': font_size,
                'color': color,
                'flags': flags,
                'origin': origin,
                'bbox': bbox,
                'ascender': ascender if ascender else 0.8,
                'descender': descender if descender else 0.2,
                'span_text': best_match.get("text", ""), # return original text for width calc
                'found': True
            }
        
        return defaults
    except Exception:
        return defaults


def _parse_palette_color(color_id: str) -> tuple | None:
    """
    Parse a color ID from the 144-color macOS-style palette.
    
    Color IDs are in format "huename_row" where:
    - huename: red, orange, yellow, chartreuse, green, spring, cyan, azure, blue, purple, magenta, rose
    - row: 0-11 (0=darkest, 11=lightest)
    
    Returns RGB tuple (r, g, b) with values 0.0-1.0, or None if invalid.
    """
    # Parse "huename_row" format
    parts = color_id.split('_')
    if len(parts) != 2:
        return None
    
    hue_name = parts[0]
    try:
        row = int(parts[1])
    except ValueError:
        return None
    
    if row < 0 or row > 11:
        print(f"[Core] Invalid color row: '{row}' in '{color_id}'")
        return None
    
    # Hue mapping (degrees)
    hue_map = {
        'red': 0.0,
        'orange': 30.0,
        'yellow': 55.0,
        'chartreuse': 80.0,
        'green': 120.0,
        'spring': 150.0,
        'cyan': 180.0,
        'azure': 210.0,
        'blue': 240.0,
        'purple': 270.0,
        'magenta': 300.0,
        'rose': 330.0,
    }
    
    if hue_name not in hue_map:
        print(f"[Core] Invalid hue name: '{hue_name}' in '{color_id}'")
        return None
    
    hue = hue_map[hue_name] / 360.0
    
    # Saturation and brightness for each row (matching Swift)
    sb_map = {
        0: (1.0, 0.4),
        1: (1.0, 0.5),
        2: (1.0, 0.6),
        3: (1.0, 0.7),
        4: (1.0, 0.8),
        5: (1.0, 0.9),
        6: (0.8, 0.95),
        7: (0.6, 0.95),
        8: (0.4, 0.95),
        9: (0.25, 0.98),
        10: (0.12, 1.0),
        11: (0.05, 1.0),
    }
    
    s, b = sb_map[row]
    
    # Convert HSB to RGB
    return _hsb_to_rgb(hue, s, b)


def _hsb_to_rgb(h: float, s: float, b: float) -> tuple:
    """Convert HSB (hue 0-1, saturation 0-1, brightness 0-1) to RGB tuple."""
    c = b * s
    x = c * (1 - abs((h * 6) % 2 - 1))
    m = b - c
    
    segment = int(h * 6) % 6
    if segment == 0:
        r, g, bb = c, x, 0
    elif segment == 1:
        r, g, bb = x, c, 0
    elif segment == 2:
        r, g, bb = 0, c, x
    elif segment == 3:
        r, g, bb = 0, x, c
    elif segment == 4:
        r, g, bb = x, 0, c
    else:
        r, g, bb = c, 0, x
    
    return (r + m, g + m, bb + m)


def _get_all_spans_in_selection(page, target_text: str, search_rect) -> list:
    """
    Find ALL individual text spans that contribute to the selected text.
    
    This is critical for cross-column selections where text like "07/05/2026 $342.24"
    is actually stored as two separate text objects in different table columns.
    
    IMPORTANT: We must be VERY strict about matching - only return spans that
    together form the EXACT target text, not just contain substrings.
    
    LIMITATION: This logic assumes Left-to-Right text direction for sorting (sorted by x0).
    RTL languages (Arabic/Hebrew) or vertical text will not be correctly reconstructed.
    
    Returns list of dicts with 'text', 'bbox', 'origin' for each span.
    """
    spans_found = []
    
    try:
        # CRITICAL: For cross-column text, the search_rect only covers the first column.
        # We need to search the ENTIRE page width at the same vertical level.
        # But keep Y bounds VERY tight to avoid matching other rows.
        page_rect = page.rect
        y_center = (search_rect.y0 + search_rect.y1) / 2
        y_tolerance = (search_rect.y1 - search_rect.y0) / 2 + 2  # Half height + small margin
        
        expanded_rect = fitz.Rect(
            page_rect.x0,                # Full page left
            y_center - y_tolerance,      # Tight Y bound
            page_rect.x1,                # Full page right  
            y_center + y_tolerance       # Tight Y bound
        )
        
        print(f"[SpanSearch] Target text length={len(target_text)}")
        print(f"[SpanSearch] Original rect: {search_rect}")
        print(f"[SpanSearch] Expanded rect: {expanded_rect}")
        
        blocks = page.get_text("dict", clip=expanded_rect).get("blocks", [])

        # BUG #48 FIX: Use consistent normalization order
        # Apply same normalization as other search strategies for consistency
        target_clean = target_text.strip()
        target_normalized = normalize_special_chars(normalize_text_for_matching(target_clean, preserve_case=False))
        
        # Collect ALL spans in the horizontal band first
        candidate_spans = []
        for block in blocks:
            if block.get("type") != 0:  # text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    if not span_text.strip():
                        continue
                    span_bbox = span.get("bbox")
                    if span_bbox:
                        # BUG #48 FIX: Use consistent normalization
                        span_normalized = normalize_special_chars(normalize_text_for_matching(span_text, preserve_case=False))
                        candidate_spans.append({
                            'text': span_text,
                            'text_clean': span_text.strip(),  # Keep original for display
                            'text_normalized': span_normalized,  # Add normalized version for matching
                            'bbox': fitz.Rect(span_bbox),
                            'origin': span.get("origin"),
                            'fontname': span.get("font", "helv"),
                            'fontsize': span.get("size", 11.0)
                        })
        
        # Sort candidates left-to-right
        candidate_spans.sort(key=lambda s: s['bbox'].x0)
        
        print(f"[SpanSearch] Found {len(candidate_spans)} candidate spans in band:")
        for i, s in enumerate(candidate_spans):
            print(f"  {i}: textLength={len(s['text_clean'])} at x={s['bbox'].x0:.1f}")
        
        # Strategy: Find consecutive spans that together form the target text
        # Try all starting positions
        for start_idx in range(len(candidate_spans)):
            concatenated = ""
            concat_normalized = ""
            matched_spans = []

            for idx in range(start_idx, len(candidate_spans)):
                span = candidate_spans[idx]
                if concatenated:
                    concatenated += " "  # Add space between spans for display
                    concat_normalized += " "  # Add space for normalized version
                concatenated += span['text_clean']
                concat_normalized += span['text_normalized']
                matched_spans.append(span)

                # BUG #48 FIX: Use pre-normalized text for comparison (already normalized above)
                
                # Check for exact match
                if concat_normalized == target_normalized:
                    print(f"[SpanSearch] EXACT MATCH found with {len(matched_spans)} spans")
                    spans_found = matched_spans.copy()
                    break
                
                # If we've exceeded the target length, stop trying from this start
                if len(concat_normalized) > len(target_normalized) + 5:
                    break
            
            if spans_found:
                break
        
        target_clean = target_text.strip()
        target_lower = target_clean.lower()
        
        if not spans_found:
            for span in candidate_spans:
                span_text = span['text_clean']
                span_lower = span_text.lower()
                
                if target_lower in span_lower:
                    start_pos = span_lower.find(target_lower)
                    # For simplicity in redaction, if it's a substring we currently treat it as a prefix
                    # if it's at the start, or we'd need more complex 'partial_prefix' logic.
                    # Given the current architecture, let's at least handle the prefix/exact inside a span.
                    
                    if start_pos == 0:
                        # Use len(target_lower) since the match was done on lowercased text
                        # This is safe because lowercasing preserves length for most scripts
                        # (except rare cases like German ß→ss which won't be a prefix match anyway)
                        suffix = span_text[len(target_lower):]
                        print(f"[SpanSearch] SUBSTRING PREFIX MATCH: targetLength={len(target_clean)} in spanLength={len(span_text)}")
                        span['partial_suffix'] = suffix
                        spans_found = [span]
                        break
                    else:
                        # Full containment - this is trickier because we'd need to split the span.
                        # For now, let's at least mark it found so we redact the WHOLE span if we have to,
                        # or better, just return it and let the user know.
                        print(f"[SpanSearch] FULL CONTAINMENT MATCH: targetLength={len(target_clean)} inside spanLength={len(span_text)}")
                        spans_found = [span]
                        break
        
        # Clean up internal tracking fields
        for span in spans_found:
            if 'text_clean' in span:
                del span['text_clean']
            if 'text_normalized' in span:
                del span['text_normalized']
        
        print(f"[SpanSearch] Final spans to redact: {len(spans_found)}")
        for s in spans_found:
            suffix_info = f" (suffixLength={len(s.get('partial_suffix', ''))})" if s.get('partial_suffix') else ""
            print(f"  -> textLength={len(s.get('text', ''))} at {s.get('bbox', '?')}{suffix_info}")
        
    except Exception as e:
        print(f"_get_all_spans_in_selection error: {e}")
        import traceback
        traceback.print_exc()
        # Ensure we don't just fail silently if something critical broke
        # But returning empty list is the safest fallback to prevent crash
    
    return spans_found


def _find_font_via_coretext(font_name: str) -> str | None:
    """
    Use Core Text to find a system-registered font.
    This is App Store safe and works in sandboxed apps.
    Returns the font file path, or None if not found.
    """
    try:
        from CoreText import (
            CTFontDescriptorCreateWithNameAndSize,
            CTFontDescriptorCopyAttribute,
            kCTFontURLAttribute,
        )
        from Foundation import NSURL
        
        # Extract base font name (remove subset prefix like "ABCDEF+")
        base_name = font_name.split('+')[-1] if '+' in font_name else font_name
        
        # Create a font descriptor for the font name
        descriptor = CTFontDescriptorCreateWithNameAndSize(base_name, 0.0)
        if not descriptor:
            return None
        
        # Get the font file URL
        url = CTFontDescriptorCopyAttribute(descriptor, kCTFontURLAttribute)
        if url and isinstance(url, NSURL):
            return url.path()
        
        return None
    except ImportError:
        # PyObjC not available
        return None
    except Exception:
        return None


def _normalize_font_name(font_name: str) -> str:
    """
    Normalize font name by removing subset tags and standardizing separators.
    Example: 'AAAAAB+Calibri,Italic' -> 'Calibri-Italic'
    """
    if not font_name:
        return ""

    # Remove subset tag (6 chars + +)
    base_name = font_name.split('+')[-1] if '+' in font_name else font_name

    # Replace common separators with hyphen
    base_name = base_name.replace(',', '-')
    base_name = base_name.replace(' ', '-')

    return base_name


# ============================================================================
# Unicode Normalization Functions (Week 6 Day 3)
# ============================================================================

@lru_cache(maxsize=4000)
def normalize_unicode(text: str, form: str = 'NFC') -> str:
    """
    Normalize Unicode text using specified normalization form.

    Args:
        text: Text to normalize
        form: Normalization form - 'NFC', 'NFD', 'NFKC', or 'NFKD'
            - NFC: Canonical Composition (default, preserves ligatures)
            - NFD: Canonical Decomposition (separates combining marks)
            - NFKC: Compatibility Composition (decomposes ligatures)
            - NFKD: Compatibility Decomposition (maximum decomposition)

    Returns:
        Normalized text

    Examples:
        >>> normalize_unicode("café", "NFC")   # é as single codepoint
        'café'
        >>> normalize_unicode("café", "NFD")   # e + combining accent
        'café'
        >>> normalize_unicode("ﬁnd", "NFKC")  # ligature → fi
        'find'
    """
    import unicodedata

    if not text:
        return text

    valid_forms = ['NFC', 'NFD', 'NFKC', 'NFKD']
    if form not in valid_forms:
        raise ValueError(f"Invalid normalization form '{form}'. Must be one of {valid_forms}")

    return unicodedata.normalize(form, text)


def strip_invisible_chars(text: str, strip_zwsp: bool = True, strip_control: bool = True) -> str:
    """
    Remove invisible and zero-width characters from text.

    Args:
        text: Text to process
        strip_zwsp: Strip zero-width spaces and joiners (default True)
        strip_control: Strip control characters (default True)

    Returns:
        Text with invisible characters removed

    Removes:
        - Zero-width space (U+200B)
        - Zero-width non-joiner (U+200C)
        - Zero-width joiner (U+200D)
        - Zero-width no-break space / BOM (U+FEFF)
        - Word joiner (U+2060)
        - Control characters (U+0000-U+001F, U+007F-U+009F) if strip_control=True
    """
    if not text:
        return text

    result = text

    # Strip zero-width characters
    if strip_zwsp:
        zero_width_chars = [
            '\u200B',  # Zero-width space
            '\u200C',  # Zero-width non-joiner
            '\u200D',  # Zero-width joiner
            '\uFEFF',  # Zero-width no-break space (BOM)
            '\u2060',  # Word joiner
        ]
        for char in zero_width_chars:
            result = result.replace(char, '')

    # Strip control characters (but preserve \n, \r, \t)
    if strip_control:
        import unicodedata
        result = ''.join(
            char for char in result
            if unicodedata.category(char) != 'Cc' or char in '\n\r\t'
        )

    return result


# Common ligatures mapping (ligature → decomposed form)
LIGATURE_MAP = {
    # Latin ligatures
    'ﬁ': 'fi',
    'ﬂ': 'fl',
    'ﬀ': 'ff',
    'ﬃ': 'ffi',
    'ﬄ': 'ffl',
    'ﬅ': 'ft',  # Long s + t
    'ﬆ': 'st',
    # IJ ligatures
    'Ĳ': 'IJ',
    'ĳ': 'ij',
    # Æ/Œ ligatures
    'Æ': 'AE',
    'æ': 'ae',
    'Œ': 'OE',
    'œ': 'oe',
    # Armenian ligatures
    'ﬓ': 'մն',
    'ﬔ': 'մե',
    'ﬕ': 'մի',
    'ﬖ': 'վն',
    'ﬗ': 'մխ',
}

# Reverse mapping for restoration
LIGATURE_REVERSE_MAP = {v: k for k, v in LIGATURE_MAP.items()}


def detect_ligatures(text: str) -> dict:
    """
    Detect ligatures in text and return mapping.

    Args:
        text: Text to analyze

    Returns:
        dict with keys:
        - positions: list of (start, end, ligature, decomposed)
        - has_ligatures: bool
        - count: int

    Example:
        >>> detect_ligatures("ﬁnd the ﬁle")
        {
            'positions': [(0, 1, 'ﬁ', 'fi'), (9, 10, 'ﬁ', 'fi')],
            'has_ligatures': True,
            'count': 2
        }
    """
    if not text:
        return {'positions': [], 'has_ligatures': False, 'count': 0}

    positions = []

    for i, char in enumerate(text):
        if char in LIGATURE_MAP:
            decomposed = LIGATURE_MAP[char]
            positions.append((i, i + 1, char, decomposed))

    return {
        'positions': positions,
        'has_ligatures': len(positions) > 0,
        'count': len(positions)
    }


def decompose_ligatures(text: str) -> tuple[str, dict]:
    """
    Decompose ligatures and return both decomposed text and ligature map.

    Args:
        text: Text with potential ligatures

    Returns:
        (decomposed_text, ligature_info)

    Example:
        >>> decompose_ligatures("ﬁnd")
        ('find', {'positions': [(0, 1, 'ﬁ', 'fi')], ...})
    """
    if not text:
        return text, {'positions': [], 'has_ligatures': False, 'count': 0}

    # Detect ligatures first
    ligature_info = detect_ligatures(text)

    # Decompose
    result = text
    for ligature, decomposed in LIGATURE_MAP.items():
        result = result.replace(ligature, decomposed)

    return result, ligature_info


def restore_ligatures(text: str, ligature_info: dict) -> str:
    """
    Restore ligatures in text based on ligature map from original.

    This attempts to restore ligatures in replacement text if the original
    text had ligatures in similar positions.

    Args:
        text: Replacement text (decomposed)
        ligature_info: Ligature info from detect_ligatures() on original

    Returns:
        Text with ligatures restored where possible

    Example:
        >>> original_info = detect_ligatures("ﬁnd")
        >>> restore_ligatures("finding", original_info)
        'ﬁnding'  # Ligature restored at start
    """
    if not text or not ligature_info.get('has_ligatures'):
        return text

    result = text

    # Try to restore ligatures at each position
    # Strategy: If the decomposed form appears in the replacement text,
    # restore the ligature
    for pos, end, ligature, decomposed in ligature_info['positions']:
        # Simple restoration: replace all occurrences
        # More sophisticated: only replace at similar positions
        result = result.replace(decomposed, ligature, 1)  # Replace first occurrence

    return result


@lru_cache(maxsize=2000)
def normalize_text_for_matching(text: str, preserve_case: bool = False) -> str:
    """
    Normalize text for matching (aggressive normalization).

    Used when searching for text to find. More aggressive than replacement.

    Args:
        text: Text to normalize
        preserve_case: Keep original case (default False = lowercase)

    Returns:
        Normalized text suitable for matching

    Applies:
        - NFKC normalization (decomposes ligatures, converts compatibility chars)
        - Strips zero-width characters
        - Normalizes whitespace
        - Optionally lowercases
    """
    if not text:
        return text

    # Apply NFKC (compatibility composition)
    # This converts ligatures: "ﬁ" → "fi"
    result = normalize_unicode(text, form='NFKC')

    # Strip invisible characters
    result = strip_invisible_chars(result)

    # BUG #49 FIX: Preserve whitespace patterns while normalizing
    # Instead of aggressively collapsing all whitespace to single spaces,
    # preserve intentional spacing (double/triple spaces for formatting)
    # Only normalize truly excessive runs (4+ consecutive spaces)
    import re
    # Replace 4+ spaces with 2 spaces (preserve some spacing intent)
    # This handles tables, indentation, justified text, etc.
    result = re.sub(r' {4,}', '  ', result)
    # Normalize line endings to single newline
    result = re.sub(r'\n+', '\n', result)
    # Trim leading/trailing whitespace per line (not entire string)
    result = '\n'.join(line.rstrip() for line in result.split('\n'))

    # Lowercase for case-insensitive matching
    if not preserve_case:
        result = result.lower()

    return result


def normalize_text_for_replacement(text: str, preserve_ligatures: bool = True) -> str:
    """
    Normalize text for replacement (conservative normalization).

    Used when inserting replacement text. More conservative than matching.

    Args:
        text: Replacement text
        preserve_ligatures: Try to preserve ligatures (default True)

    Returns:
        Normalized text suitable for PDF insertion

    Applies:
        - NFC normalization (composes combining characters, preserves ligatures)
        - Does NOT strip zero-width chars (may be intentional)
        - Does NOT normalize whitespace (preserve user formatting)
    """
    if not text:
        return text

    # Apply NFC (canonical composition)
    # This preserves ligatures like "ﬁ" but composes "e + ́" → "é"
    result = normalize_unicode(text, form='NFC' if preserve_ligatures else 'NFKC')

    return result


@lru_cache(maxsize=2000)
def normalize_special_chars(text: str) -> str:
    """
    Normalize special characters for robust text matching.

    Converts various Unicode characters to their ASCII equivalents for comparison.
    This handles:
    - Smart quotes → straight quotes
    - Various dashes → hyphen-minus
    - Ligatures → component letters
    - Special whitespace → regular space
    - Currency symbols → abbreviated names

    Args:
        text: Text to normalize

    Returns:
        Text with special characters normalized to ASCII equivalents
    """
    if not text:
        return text

    # Comprehensive character normalization map
    replacements = {
        # Whitespace
        '\u00a0': ' ',    # Non-breaking space -> regular space
        '\u2003': ' ',    # Em space
        '\u2002': ' ',    # En space
        '\u2009': ' ',    # Thin space
        '\u200a': ' ',    # Hair space
        '\u200b': '',     # Zero-width space (remove)
        '\ufeff': '',     # BOM / zero-width no-break space (remove)

        # Quotes - smart quotes to straight
        '\u2018': "'",    # Left single quote
        '\u2019': "'",    # Right single quote / apostrophe
        '\u201a': "'",    # Single low-9 quote
        '\u201b': "'",    # Single high-reversed-9 quote
        '\u2032': "'",    # Prime
        '\u2035': "'",    # Reversed prime
        '\u2033': '"',    # Double prime
        '\u2036': '"',    # Reversed double prime
        '\u201c': '"',    # Left double quote
        '\u201d': '"',    # Right double quote
        '\u201e': '"',    # Double low-9 quote
        '\u201f': '"',    # Double high-reversed-9 quote
        '\u00ab': '"',    # Left guillemet
        '\u00bb': '"',    # Right guillemet
        '\u2039': "'",    # Single left guillemet
        '\u203a': "'",    # Single right guillemet

        # Dashes and hyphens
        '\u2212': '-',    # Minus sign -> hyphen
        '\u2013': '-',    # En-dash -> hyphen
        '\u2014': '-',    # Em-dash -> hyphen
        '\u2015': '-',    # Horizontal bar
        '\u2010': '-',    # Hyphen
        '\u2011': '-',    # Non-breaking hyphen
        '\u2012': '-',    # Figure dash
        '\u00ad': '',     # Soft hyphen (remove)

        # Ligatures (common ones that NFKC might miss)
        '\ufb00': 'ff',   # ff ligature
        '\ufb01': 'fi',   # fi ligature
        '\ufb02': 'fl',   # fl ligature
        '\ufb03': 'ffi',  # ffi ligature
        '\ufb04': 'ffl',  # ffl ligature
        '\ufb05': 'st',   # st ligature (long s + t)
        '\ufb06': 'st',   # st ligature

        # Currency and symbols
        '\uff04': '$',    # Fullwidth dollar
        '\u20ac': 'EUR',  # Euro symbol
        '\u00a3': 'GBP',  # Pound symbol
        '\u00a5': 'JPY',  # Yen symbol

        # Ellipsis and dots
        '\u2026': '...',  # Horizontal ellipsis
        '\u22ef': '...',  # Midline horizontal ellipsis

        # Other common substitutions
        '\u00b7': '.',    # Middle dot
        '\u2022': '*',    # Bullet
        '\u2219': '*',    # Bullet operator
        '\u00d7': 'x',    # Multiplication sign
        '\u00f7': '/',    # Division sign
    }

    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


# Font family equivalence groups for intelligent fallback
FONT_FAMILY_GROUPS = {
    'sans': ['arial', 'helvetica', 'calibri', 'carlito', 'verdana', 'tahoma', 
             'segoe', 'trebuchet', 'liberation sans', 'noto sans', 'roboto'],
    'serif': ['times', 'georgia', 'cambria', 'garamond', 'palatino', 'book antiqua',
              'liberation serif', 'noto serif', 'charter'],
    'mono': ['courier', 'consolas', 'menlo', 'monaco', 'lucida console', 
             'liberation mono', 'noto mono', 'sf mono', 'source code'],
}


def _get_font_family_group(font_name: str) -> str | None:
    """Determine which family group a font belongs to."""
    fn_lower = font_name.lower()
    for group, fonts in FONT_FAMILY_GROUPS.items():
        for font in fonts:
            if font in fn_lower:
                return group
    return None


def _extract_font_style(font_name: str) -> tuple[bool, bool]:
    """Extract bold and italic flags from font name."""
    fn_lower = font_name.lower()
    is_bold = any(x in fn_lower for x in ['bold', 'black', 'heavy', 'semibold', 'demi'])
    is_italic = any(x in fn_lower for x in ['italic', 'oblique', 'slant'])
    return (is_bold, is_italic)


def _score_font_match(source_name: str, candidate_name: str, src_is_bold: bool = None, src_is_italic: bool = None, src_is_serif: bool = None) -> int:
    """
    Score how well a candidate font matches the source font.
    Higher score = better match.
    
    Scoring:
    - Exact name match: 100
    - Family (base) name match: 80
    - Same family group (sans/serif/mono): 40
    - Style match (bold): +15
    - Style match (italic): +15
    - Serif/sans-serif match: +20 (mismatch: -50)
    """
    score = 0
    src_lower = source_name.lower()
    cand_lower = candidate_name.lower()
    
    # Normalize names (remove subset prefix, standardize separators)
    src_norm = _normalize_font_name(source_name).lower()
    cand_norm = _normalize_font_name(candidate_name).lower()
    
    # Extract base family name (remove style suffixes)
    src_base = src_norm.split('-')[0].split(' ')[0]
    cand_base = cand_norm.split('-')[0].split(' ')[0]
    
    # Exact match
    if src_norm == cand_norm:
        score += 100
    # Base family match
    elif src_base == cand_base:
        score += 80
    # Same family group
    else:
        src_group = _get_font_family_group(source_name)
        cand_group = _get_font_family_group(candidate_name)
        if src_group and src_group == cand_group:
            score += 40
    
    # Style matching
    # If explicit flags provided (from PDF structure), use them. 
    # Otherwise fallback to name parsing.
    if src_is_bold is None or src_is_italic is None:
        name_bold, name_italic = _extract_font_style(source_name)
        if src_is_bold is None: src_is_bold = name_bold
        if src_is_italic is None: src_is_italic = name_italic
        
    cand_bold, cand_italic = _extract_font_style(candidate_name)
    
    if src_is_bold == cand_bold:
        score += 15
    if src_is_italic == cand_italic:
        score += 15
    
    # Serif/sans-serif matching (critical for visual fidelity)
    # Determine if candidate is serif by looking at the font name
    cand_is_serif = _is_font_serif(candidate_name)
    
    if src_is_serif is not None and cand_is_serif is not None:
        if src_is_serif == cand_is_serif:
            score += 20  # Good match
        else:
            score -= 50  # Major penalty for serif/sans mismatch
    
    return score


def _is_font_serif(font_name: str) -> bool | None:
    """Determine if a font is serif based on its name. Returns None if unknown."""
    fn_lower = font_name.lower()
    
    # Known serif fonts
    serif_fonts = ['times', 'georgia', 'garamond', 'palatino', 'cambria', 
                   'baskerville', 'book', 'roman', 'charter', 'century', 
                   'bodoni', 'didot', 'caslon', 'minion', 'cochin', 'hoefler']
    
    # Known sans-serif fonts
    sans_fonts = ['arial', 'helvetica', 'verdana', 'tahoma', 'calibri', 
                  'segoe', 'gothic', 'sans', 'gill', 'futura', 'avenir',
                  'roboto', 'open sans', 'lato', 'montserrat', 'nunito',
                  'source sans', 'ubuntu', 'noto sans']
    
    for font in serif_fonts:
        if font in fn_lower:
            return True
    
    for font in sans_fonts:
        if font in fn_lower:
            return False
    
    return None  # Unknown


def _is_font_name_suspicious(font_name: str) -> bool:
    """
    Detect if a font name appears to be obfuscated/suspicious.
    
    Obfuscated PDFs often use garbage font names like "AllAndNone" or 
    random strings to hide the actual fonts used. These should trigger
    visual serif detection as the PDF flags may also be incorrect.
    
    Returns True if the font name seems suspicious/obfuscated.
    """
    if not font_name:
        return True  # No name = suspicious
    
    fn_lower = font_name.lower()
    
    # Remove subset prefix (e.g., "AAAAAA+FontName" -> "fontname")
    if '+' in font_name:
        fn_lower = font_name.split('+')[-1].lower()
    
    # Known legitimate font families (partial matches are fine)
    known_fonts = [
        # Serif
        'times', 'georgia', 'garamond', 'palatino', 'cambria', 'baskerville',
        'book', 'roman', 'charter', 'century', 'bodoni', 'didot', 'caslon',
        'minion', 'cochin', 'hoefler', 'new york', 'rockwell', 'clarendon',
        # Sans-serif
        'arial', 'helvetica', 'verdana', 'tahoma', 'calibri', 'segoe', 
        'gothic', 'sans', 'gill', 'futura', 'avenir', 'roboto', 'lato',
        'montserrat', 'nunito', 'ubuntu', 'noto', 'open', 'source',
        'franklin', 'trade', 'myriad', 'frutiger', 'optima', 'trebuchet',
        # Monospace
        'courier', 'mono', 'consolas', 'menlo', 'monaco', 'source code',
        # Others
        'symbol', 'wingding', 'dingbat', 'zapf'
    ]
    
    # Check if font name contains any known font family
    for known in known_fonts:
        if known in fn_lower:
            return False  # Matches known font, not suspicious
    
    # Check for common font naming patterns (e.g., "-Bold", "-Italic", "Regular")
    common_suffixes = ['bold', 'italic', 'regular', 'light', 'medium', 'black', 'thin']
    for suffix in common_suffixes:
        if suffix in fn_lower:
            # Has a style suffix but no known font base = might still be valid
            # Only flag as suspicious if the name is very short or random-looking
            pass
    
    # Short gibberish names are suspicious
    base_name = fn_lower.replace('-', '').replace('_', '').replace(' ', '')
    if len(base_name) < 4:
        return True  # Too short to be a real font name
    
    # Names that don't contain common letters/patterns are suspicious
    # (e.g., "AllAndNone" is valid syntax but not a real font)
    if base_name in ['allandnone', 'none', 'unknown', 'default', 'base']:
        return True
    
    # If we got here, it's an unknown font but might be legitimate
    # Be conservative - don't flag as suspicious unless clearly bogus
    return False


def _generate_font_name_variants(font_name: str) -> list[str]:
    """
    Generate comprehensive list of font name variations to handle:
    - Subset prefixes: "AAAAAA+Calibri" -> "Calibri"
    - PostScript suffixes: "Arial-BoldMT" -> "Arial Bold", "Arial-Bold"
    - Separator styles: commas, hyphens, spaces, none
    - Style keywords: Bold, Italic, Regular, etc.
    
    Returns list of unique variants ordered from most to least specific.
    """
    if not font_name:
        return []
    
    variants = set()
    
    # Step 1: Remove subset prefix (e.g., "AAAAAA+Calibri" -> "Calibri")
    clean_name = font_name.split('+')[-1] if '+' in font_name else font_name
    variants.add(clean_name)
    
    # Step 2: Remove common PostScript suffixes
    ps_suffixes = ['MT', 'PS', 'PSMT', '-Regular', 'Regular']
    for suffix in ps_suffixes:
        if clean_name.endswith(suffix):
            without_suffix = clean_name[:-len(suffix)].rstrip('-')
            variants.add(without_suffix)
            clean_name = without_suffix  # Continue processing without suffix
    
    # Step 3: Generate separator variations
    # Common patterns: "Arial-Bold", "Arial Bold", "Arial,Bold", "ArialBold"
    for base in list(variants):
        # Replace hyphens with spaces
        if '-' in base:
            variants.add(base.replace('-', ' '))
            variants.add(base.replace('-', ''))
        # Replace commas with spaces
        if ',' in base:
            variants.add(base.replace(',', ' '))
            variants.add(base.replace(',', '-'))
            variants.add(base.replace(',', ''))
        # Replace spaces with hyphens
        if ' ' in base:
            variants.add(base.replace(' ', '-'))
            variants.add(base.replace(' ', ''))
    
    # Step 4: Extract family and style, try combinations
    # Handle patterns like "Arial Bold" -> try "Arial" + "Bold" separately
    style_keywords = ['Bold', 'Italic', 'Light', 'Medium', 'Regular', 'Thin', 
                      'Black', 'Heavy', 'Semibold', 'SemiBold', 'ExtraBold', 
                      'UltraLight', 'Narrow', 'Condensed', 'Expanded']
    
    for base in list(variants):
        for style in style_keywords:
            # Check various joining patterns
            patterns = [
                f"{style}",           # Just the style
                f" {style}",          # Space before
                f"-{style}",          # Hyphen before  
                f",{style}",          # Comma before
            ]
            for pattern in patterns:
                if base.endswith(pattern):
                    family = base[:-len(pattern)]
                    if family:
                        # Add family + style with different separators
                        variants.add(f"{family} {style}")
                        variants.add(f"{family}-{style}")
                        variants.add(f"{family}{style}")
    
    # Step 5: Add title case and preserve case variants
    final_variants = set()
    for v in variants:
        final_variants.add(v)
        # Try title case if not already
        if v != v.title():
            final_variants.add(v.title())
    
    # Return as sorted list (longer/more specific names first)
    return sorted(final_variants, key=lambda x: (-len(x), x))


def _find_bundled_font(font_name: str) -> str | None:
    """
    Check for bundled OSS replacement fonts in the app bundle.
    Uses font_map.json to map proprietary fonts to OSS equivalents.
    """
    import os
    import json
    
    if not font_name:
        return None
    
    # Normalize the font name
    base_name = _normalize_font_name(font_name)
    
    # Find the bundle's fonts directory
    # This file is at: .../python_site/editor_pkg/core.py
    # Fonts are at: .../fonts/
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        bundle_root = os.path.dirname(os.path.dirname(current_dir))  # Up from editor_pkg to bundle
        fonts_dir = os.path.join(bundle_root, "fonts")
        font_map_path = os.path.join(fonts_dir, "font_map.json")
        
        if not os.path.isfile(font_map_path):
            return None
        
        with open(font_map_path, 'r') as f:
            font_map = json.load(f)
        
        mappings = font_map.get("mappings", {})
        
        # Try exact match first
        if base_name in mappings:
            font_file = os.path.join(fonts_dir, mappings[base_name])
            if os.path.isfile(font_file):
                return font_file
        
        # Try case-insensitive match
        base_lower = base_name.lower()
        for prop_font, oss_font in mappings.items():
            if prop_font.lower() == base_lower:
                font_file = os.path.join(fonts_dir, oss_font)
                if os.path.isfile(font_file):
                    return font_file
        
        # Try fallback for specific families if exact match not found
        # e.g. "Calibri" -> "Carlito-Regular"
        if "calibri" in base_lower:
            style_suffix = ""
            if "bold" in base_lower: style_suffix += "-Bold"
            if "italic" in base_lower: style_suffix += "Italic"
            
            # Map simplified style to file
            # If no style, assume regular
            if not style_suffix: style_suffix = "-Regular"
            
            candidate = f"Carlito/Carlito{style_suffix}.ttf"
            font_file = os.path.join(fonts_dir, candidate)
            if os.path.isfile(font_file):
                return font_file
            
        return None
    except Exception:
        return None


# Cache for system font lookups (cleared on module reload)
_system_font_cache: dict[str, str | None] = {}
_SYSTEM_FONT_CACHE_MAX = 200  # max distinct lookups to keep in memory
_system_font_cache_lock = threading.Lock()


def _find_system_font(font_name: str, flags: int = None) -> str | None:
    """
    Try to find the actual font file on the system using weighted scoring.

    Strategy (enhanced with scoring):
    1. Fast-path for common PDF fonts (instant lookup)
    2. Collect candidates from Core Text, file system, and bundled fonts
    3. Score each candidate based on name match, family, and style
    4. Return the highest-scoring candidate

    Returns the path to the best matching font file, or None if not found.
    """
    import os
    import sys

    if not font_name:
        return None

    # Check cache first (under lock — concurrent font searches are common)
    cache_key = font_name.lower() + (f"_{flags}" if flags else "")
    with _system_font_cache_lock:
        if cache_key in _system_font_cache:
            return _system_font_cache[cache_key]

    # LOG: What font are we searching for?
    print(f"[FONT SEARCH] Looking for: '{font_name}' (flags={flags})", file=sys.stderr, flush=True)

    # FAST PATH: Common PDF fonts (instant lookup without CoreText overhead)
    # This dramatically speeds up font detection for standard documents
    font_name_clean = font_name.lower()
    if '+' in font_name_clean:
        font_name_clean = font_name_clean.split('+')[-1]  # Remove subset prefix
    # Remove common separators for matching
    font_name_normalized = font_name_clean.replace(',', '').replace('-', '').replace(' ', '')

    # Map common PDF font names to macOS system font paths
    # These are guaranteed to exist on macOS 11+ systems
    # Order matters: check specific variants before base fonts
    common_fonts = {
        'timesnewromanbolditalic': '/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf',
        'timesnewromanpsbolditalicmt': '/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf',
        'timesnewromanbold': '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf',
        'timesnewromanpsboldmt': '/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf',
        'timesnewromanitalic': '/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf',
        'timesnewromanpsitalicmt': '/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf',
        'timesnewromanpsmt': '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
        'timesnewroman': '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
        'timesroman': '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
        'times': '/System/Library/Fonts/Times.ttc',
        # Helvetica variants (TTC file contains all variants)
        'helveticaneue': '/System/Library/Fonts/Helvetica.ttc',
        'helveticaneuebold': '/System/Library/Fonts/Helvetica.ttc',
        'helveticaboldoblique': '/System/Library/Fonts/Helvetica.ttc',
        'helveticaoblique': '/System/Library/Fonts/Helvetica.ttc',
        'helveticabold': '/System/Library/Fonts/Helvetica.ttc',
        'helvetica': '/System/Library/Fonts/Helvetica.ttc',
        # Arial variants
        'arialbolditalic': '/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf',
        'arialitalic': '/System/Library/Fonts/Supplemental/Arial Italic.ttf',
        'arialbold': '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        'arialboldmt': '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        'arial': '/System/Library/Fonts/Supplemental/Arial.ttf',
        'arialmt': '/System/Library/Fonts/Supplemental/Arial.ttf',
        # Courier
        'courierbold': '/System/Library/Fonts/Courier.dfont',
        'courier': '/System/Library/Fonts/Courier.dfont',
        # Calibri (Microsoft Office)
        'calibribold': '/Library/Fonts/Microsoft/Calibri Bold.ttf',
        'calibri': '/Library/Fonts/Microsoft/Calibri.ttf',
    }

    # Check if this is a common font (exact match on normalized name)
    if font_name_normalized in common_fonts:
        path = common_fonts[font_name_normalized]
        if os.path.isfile(path):
            print("[FONT SEARCH] Fast-path match", file=sys.stderr, flush=True)
            with _system_font_cache_lock:
                if len(_system_font_cache) >= _SYSTEM_FONT_CACHE_MAX:
                    _system_font_cache.pop(next(iter(_system_font_cache)))
                _system_font_cache[cache_key] = path
            return path
        else:
            print("[FONT SEARCH] Fast-path found but file missing", file=sys.stderr, flush=True)

    print(f"[FONT SEARCH] No fast-path match, trying full search (normalized: '{font_name_normalized}')", file=sys.stderr, flush=True)

    candidates = []  # List of (path, score) tuples

    # Determine source style from flags if available
    src_is_bold = None
    src_is_italic = None
    src_is_serif = None
    if flags is not None:
        # bit 0: Superscript
        # bit 1: Italic
        # bit 2: Serif
        # bit 3: Monospaced
        # bit 4: Bold
        src_is_italic = (flags & 2) != 0
        src_is_serif = (flags & 4) != 0
        src_is_bold = (flags & 16) != 0

    # --- Strategy 1: Core Text lookup ---
    variants = [font_name]
    if "," in font_name:
        variants.append(font_name.replace(",", " "))
        variants.append(font_name.replace(",", "-"))
        variants.append(font_name.replace(",", ""))
    
    if "+" in font_name:
        clean = font_name.split("+")[-1]
        if clean not in variants: variants.append(clean)
        if "," in clean:
            variants.append(clean.replace(",", " "))
            variants.append(clean.replace(",", "-"))

    for variant in variants:
        coretext_path = _find_font_via_coretext(variant)
        if coretext_path and os.path.isfile(coretext_path):
            score = _score_font_match(font_name, variant, src_is_bold=src_is_bold, src_is_italic=src_is_italic, src_is_serif=src_is_serif)
            candidates.append((coretext_path, score, f"CoreText:{variant}"))
    
    # --- Strategy 2: Direct file lookup ---
    file_variants = _generate_font_name_variants(font_name)
    
    font_dirs = [
        "/Library/Fonts",
        os.path.expanduser("~/Library/Fonts"),
        "/System/Library/Fonts",
        "/System/Library/Fonts/Supplemental",
        "/Applications/Microsoft Word.app/Contents/Resources/DFonts",
        "/Applications/Microsoft Excel.app/Contents/Resources/DFonts",
        "/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts",
    ]
    
    extensions = ['.ttf', '.otf', '.ttc', '.TTF', '.OTF', '.TTC']
    
    for font_dir in font_dirs:
        if not os.path.isdir(font_dir):
            continue
        for variant in file_variants:
            for ext in extensions:
                font_path = os.path.join(font_dir, variant + ext)
                if os.path.isfile(font_path):
                    score = _score_font_match(font_name, variant, src_is_bold=src_is_bold, src_is_italic=src_is_italic, src_is_serif=src_is_serif)
                    candidates.append((font_path, score, f"File:{variant}"))
    
    # --- Strategy 3: Bundled OSS fonts ---
    bundled_path = _find_bundled_font(font_name)
    if bundled_path:
        # Bundled fonts get a bonus as they're guaranteed available
        score = _score_font_match(font_name, os.path.basename(bundled_path), src_is_bold=src_is_bold, src_is_italic=src_is_italic, src_is_serif=src_is_serif) + 5
        candidates.append((bundled_path, score, "Bundled"))
    
    # --- Pick best candidate ---
    if candidates:
        # Sort by score descending, pick highest
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_path, best_score, source = candidates[0]
        print(f"[FONT SEARCH] Found via {source} (score={best_score:.2f})", file=sys.stderr, flush=True)
        with _system_font_cache_lock:
            if len(_system_font_cache) >= _SYSTEM_FONT_CACHE_MAX:
                _system_font_cache.pop(next(iter(_system_font_cache)))
            _system_font_cache[cache_key] = best_path
        return best_path

    print(f"[FONT SEARCH] ✗ Not found, returning None", file=sys.stderr, flush=True)
    with _system_font_cache_lock:
        if len(_system_font_cache) >= _SYSTEM_FONT_CACHE_MAX:
            _system_font_cache.pop(next(iter(_system_font_cache)))
        _system_font_cache[cache_key] = None
    return None


def _is_standard_pdf_font(font_name: str, flags: int = None) -> tuple[bool, str]:
    """
    Check if a font is a standard PDF Base-14 font or close equivalent.

    The PDF Base-14 fonts are guaranteed to be available in all PDF readers
    and PyMuPDF has built-in versions that match them exactly. Using these
    built-in fonts gives pixel-perfect results compared to system TrueType fonts.

    Args:
        font_name: Font name from PDF (may include subset prefix like 'AAAAAA+')
        flags: Font flags from PDF (bit 4 = bold, bit 1 = italic)

    Returns:
        Tuple of (is_standard: bool, builtin_name: str or None)
        builtin_name is the PyMuPDF built-in font name if is_standard is True
    """
    if not font_name:
        return (False, None)

    # Normalize font name
    fn = font_name.split('+')[-1].lower() if '+' in font_name else font_name.lower()
    fn_normalized = fn.replace('-', '').replace(' ', '').replace(',', '')

    # Extract style from name
    is_bold = 'bold' in fn
    is_italic = 'italic' in fn or 'oblique' in fn

    # Override with flags if available (more reliable than name parsing)
    if flags is not None:
        is_bold = (flags & 16) != 0  # bit 4
        is_italic = (flags & 2) != 0   # bit 1

    # Map font families to built-in names
    # Helvetica family (includes Arial which is metrically compatible)
    helvetica_variants = ['helvetica', 'arial', 'arialmt', 'helveticaneue']
    if any(v in fn_normalized for v in helvetica_variants):
        if is_bold and is_italic:
            return (True, "hebi")
        elif is_bold:
            return (True, "hebo")
        elif is_italic:
            return (True, "heit")
        else:
            return (True, "helv")

    # Times family
    times_variants = ['times', 'timesnewroman', 'timesroman', 'timesnewromanps']
    if any(v in fn_normalized for v in times_variants):
        if is_bold and is_italic:
            return (True, "tibi")
        elif is_bold:
            return (True, "tibo")
        elif is_italic:
            return (True, "tiit")
        else:
            return (True, "tiro")

    # Courier family
    courier_variants = ['courier', 'couriernew', 'couriernewps']
    if any(v in fn_normalized for v in courier_variants):
        if is_bold and is_italic:
            return (True, "cobi")
        elif is_bold:
            return (True, "cobo")
        elif is_italic:
            return (True, "coit")
        else:
            return (True, "cour")

    # Symbol and ZapfDingbats
    if 'symbol' in fn_normalized:
        return (True, "symb")
    if 'zapfdingbats' in fn_normalized or 'dingbats' in fn_normalized:
        return (True, "zadb")

    return (False, None)


def _map_to_builtin_font(font_name: str) -> str:
    """
    Map PDF font names to PyMuPDF built-in fonts with style support.
    Used as fallback when system font is not available.
    """
    if not font_name:
        return "helv"
    
    fn_lower = font_name.lower()
    is_bold = 'bold' in fn_lower
    is_italic = 'italic' in fn_lower or 'oblique' in fn_lower
    
    # Determine base family
    base = "helv"
    if any(x in fn_lower for x in ['calibri', 'arial', 'helv', 'sans', 'segoe', 'verdana', 'tahoma', 'trebuchet']):
        base = "helv"
    elif any(x in fn_lower for x in ['times', 'serif', 'georgia', 'cambria', 'garamond', 'palatino', 'book']):
        base = "tiro"
    elif any(x in fn_lower for x in ['courier', 'mono', 'consolas', 'menlo', 'lucida console', 'fixed']):
        base = "cour"
    
    # Apply styles
    if base == "helv":
        if is_bold and is_italic: return "hebi"
        if is_bold: return "hebo"
        if is_italic: return "heit"
        return "helv"
    elif base == "tiro":
        if is_bold and is_italic: return "tibi"
        if is_bold: return "tibo"
        if is_italic: return "tiit"
        return "tiro"
    elif base == "cour":
        if is_bold and is_italic: return "cobi"
        if is_bold: return "cobo"
        if is_italic: return "coit"
        return "cour"
        
    return "helv"


def _get_base14_fontname(font_name: str, is_bold: bool = False, is_italic: bool = False) -> str:
    """
    Map font name to PyMuPDF Base-14 font with explicit style flags.
    
    Unlike _map_to_builtin_font which derives style from font name,
    this function accepts explicit bold/italic flags from span data.
    """
    if not font_name:
        font_name = "Helvetica"
    
    fn_lower = font_name.lower()
    
    # Determine base family
    base = "helv"
    if any(x in fn_lower for x in ['times', 'serif', 'georgia', 'cambria', 'garamond', 'palatino', 'book']):
        base = "tiro"
    elif any(x in fn_lower for x in ['courier', 'mono', 'consolas', 'menlo', 'fixed']):
        base = "cour"
    
    # Apply styles
    if base == "helv":
        if is_bold and is_italic: return "hebi"
        if is_bold: return "hebo"
        if is_italic: return "heit"
        return "helv"
    elif base == "tiro":
        if is_bold and is_italic: return "tibi"
        if is_bold: return "tibo"
        if is_italic: return "tiit"
        return "tiro"
    elif base == "cour":
        if is_bold and is_italic: return "cobi"
        if is_bold: return "cobo"
        if is_italic: return "coit"
        return "cour"
        
    return "helv"


def _find_internal_font_name(doc, page, font_name: str, replacement_text: str, search_text: str) -> tuple:
    """
    Find the internal font name (e.g., 'F1') for an embedded font and check glyph coverage.
    
    Args:
        doc: The fitz document
        page: The fitz page
        font_name: The font name to find (may include subset prefix like 'AAAAAA+')
        replacement_text: The text that will replace the original
        search_text: The original text being replaced (used for subset character validation)
    
    Returns:
        Tuple of (internal_name, all_glyphs_present, reuse_buffer):
        - internal_name: Font name if safe to reuse (e.g., 'Calibri'), or None
        - all_glyphs_present: True if matched font has all required glyphs
        - reuse_buffer: Bytes of font data for re-registration, or None
    """
    try:
        # Normalize font name for matching (handle subset prefixes like "AAAAAA+")
        # Keep the full name including style suffixes (e.g., ",BoldItalic")
        target_full = font_name.split('+')[-1].lower() if '+' in font_name else font_name.lower()
        # Also extract just the family name for fallback matching
        target_family = target_full.split(',')[0] if ',' in target_full else target_full
        
        fonts = page.get_fonts()
        exact_match = None  # Prefer exact match
        family_match = None  # Fallback to family-only match
        
        for f in fonts:
            xref, ext, type_, basefont, internal_name, enc = f
            
            # Check if this font matches (handling subset prefix)
            font_full = basefont.split('+')[-1].lower() if '+' in basefont else basefont.lower()
            font_family = font_full.split(',')[0] if ',' in font_full else font_full
            
            is_subset = '+' in basefont
            
            # EXACT MATCH: Full name including style suffix (e.g., "TimesNewRoman,BoldItalic")
            if font_full == target_full:
                exact_match = (xref, ext, type_, basefont, internal_name, enc, is_subset)
                break  # Exact match - use this one
            
            # FAMILY MATCH: Same family but potentially different style (less preferred)
            elif font_family == target_family and family_match is None:
                family_match = (xref, ext, type_, basefont, internal_name, enc, is_subset)
        
        # Use exact match if found, otherwise fall back to family match
        match = exact_match or family_match
        if match:
            xref, ext, type_, basefont, internal_name, enc, is_subset = match
            
            # Log which match type we used
            if exact_match:
                pass  # Exact match - best case
            else:
                # Family-only match - warn about potential style mismatch
                import logging
                logging.debug(f"Font variant mismatch: wanted '{target_full}' but only found '{basefont.split('+')[-1].lower()}'")
                
            # Found matching font - check if it has all required glyphs
            font_data = doc.extract_font(xref)
            if font_data and len(font_data) >= 4 and font_data[3]:
                buffer = font_data[3]
                
                # Check font type - CID/Type0 fonts have unreliable glyph checks
                # because they use Identity-H encoding where has_glyph() returns 0
                # for all codepoints even though the font renders correctly.
                is_cid_font = type_ == 'Type0' or ext == 'cid'
                
                if is_cid_font:
                    # For CID fonts, check buffer size first
                    if len(buffer) < 1000:
                        return (None, False, None)
                    # Proceed to check glyphs below using the extracted buffer
                
                try:
                    temp_font = fitz.Font(fontbuffer=buffer)
                    
                    all_glyphs_present = True
                    missing_chars = []
                    for char in replacement_text:
                        if char.strip():  # Skip whitespace
                            gid = temp_font.has_glyph(ord(char))
                            if not gid:
                                all_glyphs_present = False
                                missing_chars.append(char)
                            else:
                                # Check if the glyph has width (is not invisible)
                                # Some subsets keep CMAP but map to empty glyphs
                                try:
                                    width = temp_font.text_length(char, fontsize=1000)
                                    if width == 0:
                                        all_glyphs_present = False
                                        missing_chars.append(char)
                                except Exception:
                                    # If metric check fails, assume unsafe
                                    all_glyphs_present = False
                                    missing_chars.append(char)
                    
                    if all_glyphs_present:
                        # PARANOID CHECK FOR SUBSETS:
                        # If it's a subset using the "+" prefix, AND we are introducing characters
                        # that were not in the target_text (the original span), we should NOT assume
                        # the subset has them, even if has_glyph says yes (it often lies for GID 0 or blanks).
                        # We force fallback to system font in this case to be safe.
                        if is_subset and search_text:
                            orig_set = set(search_text)
                            repl_set = set(replacement_text)
                            # Ignore whitespace differences
                            orig_set.discard(' ')
                            repl_set.discard(' ')
                            if not repl_set.issubset(orig_set):
                                # New characters introduced - unsafe to reuse subset
                                # But check if we're just changing case? No, font handles that.
                                # Fallback to system font
                                return (None, False, None)

                        # SMART REUSE: Reuse the BUFFER for all verified fonts
                        # Return basefont (e.g. "Calibri") as the name
                        return (basefont, True, buffer)
                    
                    # Glyph check failed - but for CID fonts, has_glyph() may be broken
                    # Check if has_glyph returns 0 for EVERYTHING including original text
                    if is_cid_font and search_text:
                        # Test if has_glyph is broken by checking original chars
                        original_chars_work = False
                        for char in search_text:
                            if char.strip() and temp_font.has_glyph(ord(char)):
                                original_chars_work = True
                                break
                        
                        if not original_chars_work:
                            # has_glyph is broken for this font (returns 0 for everything)
                            # Fall back to character set comparison:
                            # If all replacement chars exist in original text, font can render them
                            # Note: Using case-sensitive comparison (fonts distinguish A vs a)
                            original_charset = set(search_text)
                            replacement_charset = set(replacement_text)
                            
                            # Check if replacement is subset of original (ignoring whitespace)
                            original_charset.discard(' ')
                            replacement_charset.discard(' ')
                            
                            if replacement_charset.issubset(original_charset):
                                # All replacement chars exist in original - safe to reuse
                                return (None, True, buffer)
                    
                    # Missing glyphs - fall back to system font
                    return (None, False, None)
                except Exception as e:
                    # Failed to load/check font - unsafe to reuse
                    return (None, False, None)
                    
            else:
                # Font matched but no extractable buffer (e.g., Standard 14 reference)
                # Cannot reuse safely - trigger fallback
                return (None, False, None)
                    
        return (None, False, None)
    except Exception:
        return (None, False, None)


def _check_synthesis_feasibility(doc, page, font_name: str, replacement_text: str) -> tuple[bool, float]:
    """
    Check if glyph synthesis is feasible for the replacement text.
    
    This function probes the document to see if we can harvest glyphs from
    existing text to synthesize the replacement, avoiding system font fallback.
    
    Args:
        doc: fitz.Document
        page: fitz.Page (used to determine current page for priority)
        font_name: Original font name from the PDF (may include subset prefix)
        replacement_text: The text that will be inserted
    
    Returns:
        Tuple of (is_feasible: bool, coverage: float)
        - is_feasible: True if synthesis can produce acceptable results
        - coverage: Percentage of glyphs that can be harvested (0.0-1.0)
    """
    from . import harvester
    
    try:
        # Get unique non-whitespace characters needed
        needed_chars = set(c for c in replacement_text if not c.isspace())
        if not needed_chars:
            return (True, 1.0)  # Empty or whitespace-only - trivially synthesizable
        
        # Quick harvest check with limited page scan
        glyph_map, missing = harvester.harvest_glyphs(
            doc, needed_chars, font_name,
            target_color=None,  # Accept any color for feasibility check
            page_limit=10  # Check first 10 pages (fast)
        )
        
        coverage = len(glyph_map) / len(needed_chars) if needed_chars else 0.0
        
        # Synthesis is feasible if we found at least 80% of needed glyphs
        # (remaining can use similar-char substitution or spacing)
        is_feasible = coverage >= 0.8
        
        return (is_feasible, coverage)
        
    except Exception:
        return (False, 0.0)


def _get_page_font_metrics(page, font_name: str) -> tuple[float, float] | None:
    """
    Find font on page matching font_name and return (ascender, descender).
    """
    try:
        fonts = page.get_fonts()
        matching_xref = None
        doc = page.parent

        for f in fonts:
            xref, _, _, basefont, name, _ = f

            # Check if basefont contains our font name (handling subsets)
            if font_name in basefont or basefont in font_name:
                matching_xref = xref
                break

            # Fallback: check normalized
            try:
                norm_base = basefont.split('+')[-1]
                if norm_base.lower() == font_name.lower():
                    matching_xref = xref
                    break
            except Exception:
                pass

        if matching_xref is not None:
            # Try loading font
            try:
                # Attempt 1: Direct from doc/xref (works in recent PyMuPDF)
                font = fitz.Font(doc, matching_xref)
                return (font.ascender, font.descender)
            except Exception:
                pass
                
            try:
                # Attempt 2: Extract buffer (works for embedded subsets)
                # extract_font returns (name, ext, flags, buffer)
                font_data = doc.extract_font(matching_xref)
                if font_data and len(font_data) >= 4:
                    buffer = font_data[3]
                    font = fitz.Font(fontbuffer=buffer)
                    return (font.ascender, font.descender)
            except Exception:
                pass
            
    except Exception:
        pass
        
    return None



def _get_reference_char_metrics(page, search_rect, target_text: str) -> tuple[str, float, float] | None:
    """
    Find a representative character from the target text (PDF) and measure its exact width and height.
    Uses multiple reference characters to calculate accurate average visual size.
    Returns (char, width, height) or None.

    Character categories:
    - x-height: x, a, e, o, u, n, r, s, c, v, z (no ascenders/descenders)
    - cap-height: H, M, T, Z, I (uppercase, no descenders)
    - ascender: b, d, f, h, k, l, t (extend above x-height)
    - descender: g, j, p, q, y (extend below baseline)
    """
    # Input validation
    if page is None:
        print("[Core] WARNING: _get_reference_char_metrics called with None page")
        return None
    if search_rect is None or search_rect.is_empty:
        print("[Core] WARNING: _get_reference_char_metrics called with invalid rect")
        return None
    if not target_text or not isinstance(target_text, str):
        print("[Core] WARNING: _get_reference_char_metrics called with invalid target_text")
        return None

    try:
        # Expand rect slightly
        clip = search_rect + (-2, -2, 2, 2)
        raw = page.get_text("rawdict", clip=clip)

        # Categorize reference characters
        x_height_chars = "xaeocuvz"  # Pure x-height (no ascenders/descenders)
        cap_height_chars = "MHZITN"  # Cap height
        ascender_chars = "bdfhkt"    # Have ascenders
        descender_chars = "gjpqy"    # Have descenders

        # Organize candidates by category
        candidates = {
            'x_height': [],
            'cap_height': [],
            'ascender': [],
            'descender': [],
            'other': []
        }

        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_origin = span.get('origin')
                    baseline = span_origin[1] if span_origin and len(span_origin) >= 2 else None

                    for char in span.get("chars", []):
                        c = char.get("c")
                        if c not in target_text or not c.strip():
                            continue

                        bbox = char.get('bbox')
                        if not bbox or len(bbox) < 4:
                            continue
                        w = bbox[2] - bbox[0]
                        h = bbox[3] - bbox[1]

                        # Calculate metrics relative to baseline if available
                        metrics = {
                            'char': c,
                            'width': w,
                            'height': h,
                            'bbox': bbox
                        }

                        if baseline:
                            metrics['baseline_y'] = baseline
                            # Distance from baseline to top (positive for ascenders)
                            metrics['ascender_dist'] = baseline - bbox[1]
                            # Distance from baseline to bottom (positive for descenders)
                            metrics['descender_dist'] = bbox[3] - baseline

                        # Categorize
                        if c in x_height_chars:
                            candidates['x_height'].append(metrics)
                        elif c in cap_height_chars:
                            candidates['cap_height'].append(metrics)
                        elif c in ascender_chars:
                            candidates['ascender'].append(metrics)
                        elif c in descender_chars:
                            candidates['descender'].append(metrics)
                        else:
                            candidates['other'].append(metrics)

        # Strategy: Use multiple characters for better accuracy
        # Priority 1: Average of 3+ x-height characters (most reliable for visual size)
        if len(candidates['x_height']) >= 3:
            heights = [c['height'] for c in candidates['x_height']]
            widths = [c['width'] for c in candidates['x_height']]
            chars = [c['char'] for c in candidates['x_height']]
            avg_h = sum(heights) / len(heights)
            avg_w = sum(widths) / len(widths)
            # Return first char as representative, but with averaged metrics
            return (chars[0], avg_w, avg_h)

        # Priority 2: Single x-height character
        if candidates['x_height']:
            c = candidates['x_height'][0]
            return (c['char'], c['width'], c['height'])

        # Priority 3: Cap-height character (uppercase)
        if candidates['cap_height']:
            c = candidates['cap_height'][0]
            # Cap height is typically 1.2-1.5x x-height, so we normalize
            # This is a heuristic - we'll adjust in scaling
            return (c['char'], c['width'], c['height'])

        # Priority 4: Mix of ascender and descender to infer x-height
        if candidates['ascender'] and candidates['descender']:
            # Ascenders extend ~0.7x x-height above baseline
            # Descenders extend ~0.3x x-height below baseline
            # We can estimate x-height from these
            a = candidates['ascender'][0]
            d = candidates['descender'][0]

            if 'ascender_dist' in a and 'descender_dist' in d:
                # Validate distances are positive (baseline could be outside bbox in rare cases)
                if a['ascender_dist'] > 0 and d['descender_dist'] > 0:
                    # Estimate x-height from ascender and descender distances
                    # Ascenders typically extend ~0.7x x-height above baseline
                    # Descenders typically extend ~0.3x x-height below baseline
                    est_x_height_from_asc = a['ascender_dist'] / 0.7
                    est_x_height_from_desc = d['descender_dist'] / 0.3
                    # Use the smaller (more conservative) estimate
                    est_x_height = min(est_x_height_from_asc, est_x_height_from_desc)

                    return (a['char'], a['width'], est_x_height)

        # Priority 5: Any available character (least reliable)
        for category in ['ascender', 'descender', 'other']:
            if candidates[category]:
                c = candidates[category][0]
                return (c['char'], c['width'], c['height'])

    except Exception:
        pass
    return None

def list_available_fonts() -> list[dict]:
    """
    Returns a list of available fonts for the UI picker.
    Uses Core Text to enumerate all system-registered fonts.
    """
    fonts = []
    
    # 1. Built-in PyMuPDF fonts (always available)
    fonts.append({"name": "System Helvetica", "id": "helv", "type": "builtin"})
    fonts.append({"name": "System Times", "id": "tiro", "type": "builtin"})
    fonts.append({"name": "System Courier", "id": "cour", "type": "builtin"})
    
    # 2. Enumerate all system fonts via Core Text (App Store safe)
    try:
        from CoreText import (
            CTFontCollectionCreateFromAvailableFonts,
            CTFontCollectionCreateMatchingFontDescriptors,
            CTFontDescriptorCopyAttribute,
            kCTFontDisplayNameAttribute,
            kCTFontFamilyNameAttribute,
            kCTFontStyleNameAttribute,
            kCTFontURLAttribute,
            kCTFontNameAttribute,
        )
        from Foundation import NSDictionary
        
        # Get all available font descriptors
        collection = CTFontCollectionCreateFromAvailableFonts(None)
        descriptors = CTFontCollectionCreateMatchingFontDescriptors(collection)
        
        seen_names = set()
        
        if descriptors:
            for descriptor in descriptors:
                try:
                    display_name = CTFontDescriptorCopyAttribute(descriptor, kCTFontDisplayNameAttribute)
                    family_name = CTFontDescriptorCopyAttribute(descriptor, kCTFontFamilyNameAttribute)
                    style_name = CTFontDescriptorCopyAttribute(descriptor, kCTFontStyleNameAttribute)
                    font_url = CTFontDescriptorCopyAttribute(descriptor, kCTFontURLAttribute)
                    ps_name = CTFontDescriptorCopyAttribute(descriptor, kCTFontNameAttribute)
                    
                    if display_name and font_url:
                        display_str = str(display_name)
                        
                        # Skip duplicates based on display name
                        if display_str in seen_names:
                            continue
                        seen_names.add(display_str)
                        
                        font_path = font_url.path() if hasattr(font_url, 'path') else str(font_url)
                        ps_name_str = str(ps_name) if ps_name else ""
                        
                        # Use pipe to separate path and PS name for unique ID
                        # If PS Name is missing, fallback to just path
                        font_id = f"{font_path}|{ps_name_str}" if ps_name_str else font_path
                        
                        fonts.append({
                            "name": display_str,
                            "id": font_id,
                            "family": str(family_name) if family_name else "",
                            "style": str(style_name) if style_name else "",
                            "type": "system"
                        })
                except Exception:
                    continue
                    
    except ImportError:
        # Fallback: PyObjC not available, use hardcoded paths
        system_paths = [
            ("/System/Library/Fonts/Helvetica.ttc", "Helvetica"),
            ("/Library/Fonts/Arial.ttf", "Arial"),
            ("/Applications/Microsoft Word.app/Contents/Resources/DFonts/Calibri.ttf", "Calibri"),
            ("/System/Library/Fonts/Times.ttc", "Times New Roman"),
            ("/System/Library/Fonts/SFNS.ttf", "San Francisco")
        ]
        for path, name in system_paths:
            if os.path.exists(path):
                fonts.append({"name": f"{name} (System)", "id": path, "type": "system"})
    except Exception:
        pass  # Silently fail if Core Text enumeration fails
    
    # Sort fonts alphabetically by name (builtins first)
    fonts.sort(key=lambda f: (0 if f["type"] == "builtin" else 1, f["name"].lower()))
            
    return fonts


def _measure_glyph_visual_metrics(font_obj, char: str) -> tuple[float, float] | None:
    """
    Render a single character at 100pt to a temporary page to measure its visual bbox.
    Returns (normalized_width, normalized_height) at 1pt scale.
    """
    temp_doc = None
    try:
        # Create temp doc
        temp_doc = fitz.open()
        page = temp_doc.new_page()

        # Use TextWriter to render with specific font object
        tw = fitz.TextWriter(page.rect)
        tw.append(fitz.Point(100, 100), char, font=font_obj, fontsize=100)
        tw.write_text(page)

        # Measure
        # Clip to area around insertion
        raw = page.get_text("rawdict", clip=fitz.Rect(90, 80, 210, 210))

        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for c in span.get("chars", []):
                        if c.get("c") == char:
                            c_bbox = c.get("bbox")
                            if not c_bbox:
                                continue
                            bbox = fitz.Rect(c_bbox)
                            return (bbox.width / 100.0, bbox.height / 100.0)
    except Exception:
        pass
    finally:
        if temp_doc:
            temp_doc.close()
    return None



def _calculate_precise_redaction_rect(page, target_rect: fitz.Rect, target_text: str) -> fitz.Rect:
    """
    Calculate a precise redaction rectangle that fully covers all text.
    Expands the rectangle based on character-level metrics to prevent
    artifacts and hairlines from incomplete redaction.

    Handles substring matches where target is part of a larger span.

    Args:
        page: fitz.Page
        target_rect: Original rect from search
        target_text: The text being replaced

    Returns:
        fitz.Rect: Expanded rect guaranteed to cover all text
    """
    # Input validation
    if page is None:
        print("[Core] WARNING: _calculate_precise_redaction_rect called with None page")
        return target_rect if target_rect else fitz.Rect(0, 0, 0, 0)
    if target_rect is None or target_rect.is_empty or target_rect.is_infinite:
        print("[Core] WARNING: _calculate_precise_redaction_rect called with invalid rect")
        return target_rect if target_rect else fitz.Rect(0, 0, 0, 0)
    if not target_text or not isinstance(target_text, str):
        print("[Core] WARNING: _calculate_precise_redaction_rect called with invalid target_text")
        return target_rect

    try:
        # Expand rect to catch all characters
        clip = target_rect + (-3, -3, 3, 3)
        raw = page.get_text("rawdict", clip=clip)

        # Collect all character bboxes that match our target
        char_bboxes = []
        target_chars = set(target_text.replace(' ', ''))  # Ignore spaces for matching

        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "")

                    # Check if this span overlaps with our target
                    span_bbox = fitz.Rect(span.get("bbox", (0,0,0,0)))
                    if not span_bbox.intersects(target_rect):
                        continue

                    # Check if we need to handle substring matching
                    # Find where our target text starts in this span
                    target_clean = target_text.strip()
                    span_clean = span_text.strip()

                    # Only redact the characters that match our target
                    chars_to_redact = []
                    span_chars = span.get("chars", [])

                    # Build character list — include all chars within the target rect
                    # (spatial check is the authoritative filter, not string membership)
                    for i, char_obj in enumerate(span_chars):
                        char_bbox_raw = char_obj.get("bbox")
                        if not char_bbox_raw:
                            continue
                        char_bbox = fitz.Rect(char_bbox_raw)
                        if char_bbox.intersects(target_rect):
                            chars_to_redact.append(char_obj)

                    # Add the bboxes of characters to redact
                    for char_obj in chars_to_redact:
                        char_bboxes.append(fitz.Rect(char_obj.get("bbox", (0,0,0,0))))

        if not char_bboxes:
            # Fallback: expand original rect conservatively
            return target_rect + (-0.5, -1.0, 0.5, 1.0)

        # Calculate union of all character bboxes
        precise_rect = fitz.Rect(char_bboxes[0])
        for bbox in char_bboxes[1:]:
            precise_rect |= bbox

        # Add safety margin for anti-aliasing and hairlines
        # - Vertical: more margin for ascenders/descenders
        # - Horizontal: less margin, just for anti-aliasing
        safety_margin = fitz.Rect(-0.3, -0.8, 0.3, 0.8)

        return precise_rect + safety_margin

    except Exception:
        # If anything fails, use conservative expansion
        return target_rect + (-1.0, -2.0, 1.0, 2.0)


def _robust_search(page, target_text: str, return_all: bool = False, diagnostic: SearchDiagnostic = None):
    """
    Robust text search that handles invisible characters, whitespace differences,
    and encoding mismatches better than standard page.search_for().
    Returns the first matching fitz.Rect (or list of Rects if return_all=True) or None.

    Args:
        page: PyMuPDF page object
        target_text: Text to search for
        return_all: If True, return all matching rects; otherwise return first match
        diagnostic: Optional SearchDiagnostic to capture debug info on failure
    """
    if not target_text:
        if diagnostic:
            diagnostic.add_strategy("Empty target", "SKIPPED")
        return [] if return_all else None

    # Use module-level normalize_text_for_matching with preserve_case=True
    # (we handle lowercasing separately where needed)
    def normalize_text(text: str) -> str:
        return normalize_text_for_matching(text, preserve_case=True)

    # Use module-level normalize_special_chars function

    found_rects = []
    
    # Deduplication Helper
    def add_unique(rects):
        for r in rects:
            is_duplicate = False
            for fr in found_rects:
                overlap_area = (r & fr).get_area()
                if overlap_area > 0:
                    if overlap_area > r.get_area() * 0.5 or overlap_area > fr.get_area() * 0.5:
                        is_duplicate = True
                        break
            if not is_duplicate:
                found_rects.append(r)

    # Strategy 1: Exact search (Fastest, most accurate)
    hits = page.search_for(target_text)
    if hits:
        if diagnostic:
            diagnostic.add_strategy("Strategy 1: Exact search", f"FOUND {len(hits)} hits")
        if not return_all: return hits[0]
        add_unique(hits)
    elif diagnostic:
        diagnostic.add_strategy("Strategy 1: Exact search", "NO MATCH")

    # Strategy 2: Quads search (Handles some layout oddities)
    if not found_rects or return_all:
        hits = page.search_for(target_text, quads=True)
        if hits:
            rects = [h.rect for h in hits]
            if diagnostic:
                diagnostic.add_strategy("Strategy 2: Quads search", f"FOUND {len(rects)} hits")
            if not return_all: return rects[0]
            add_unique(rects)
        elif diagnostic:
            diagnostic.add_strategy("Strategy 2: Quads search", "NO MATCH")
    
    # Strategy 2.5: Block-level scan (Optimization)
    target_norm = normalize_special_chars(normalize_text(target_text)).lower()
    if not target_norm:
        return found_rects if return_all else None

    # Instead of parsing full dict (SLOW for large pages), scan blocks first
    candidate_rects = []
    try:
        # get_text("blocks") is much faster than "dict"
        blocks_simple = page.get_text("blocks")
        for b in blocks_simple:
            # b is (x0, y0, x1, y1, text, block_no, block_type)
            if len(b) >= 7 and b[6] == 0: # Text block (block_type at index 6: 0=text, 1=image)
                block_text = b[4]
                # BUG #57 FIX: Use word-boundary aware containment check
                # Simple substring matching is too loose ("cat" matches "category")
                norm_block = normalize_special_chars(normalize_text(block_text)).lower()

                # For single words, require word boundaries
                # For phrases, allow substring match (multi-word targets often span formatting)
                if ' ' in target_norm:
                    # Multi-word target: use substring (handles line breaks, formatting)
                    is_match = target_norm in norm_block
                else:
                    # Single word: require word boundaries to avoid false matches
                    # Use simple word boundary check (not regex for performance)
                    import re
                    pattern = r'\b' + re.escape(target_norm) + r'\b'
                    is_match = bool(re.search(pattern, norm_block))

                if is_match:
                    candidate_rects.append(fitz.Rect(b[0], b[1], b[2], b[3]))

        if diagnostic:
            if candidate_rects:
                diagnostic.add_strategy("Strategy 2.5: Block scan", f"FOUND {len(candidate_rects)} candidate blocks")
            else:
                diagnostic.add_strategy("Strategy 2.5: Block scan", "NO MATCH in any block")

        # If no blocks contain the text, Strategy 3 is futile (unless normalization weirdness)
        if not candidate_rects and not (" " in target_text) and not found_rects:
             # If target is single word, block check is reliable.
             return [] if return_all else None

    except Exception as e:
        if diagnostic:
            diagnostic.add_strategy("Strategy 2.5: Block scan", f"ERROR: {e}")
        pass # Fallback to full scan if blocks fail
        
    strategy3_found = 0
    try:
        # Strategy 3: Detailed Dict Scan (Targeted or Full)
        # If we have candidates, only scan those areas!
        if candidate_rects:
            blocks = []
            for rect in candidate_rects:
                 # Expand rect slightly to ensure full chars included, but clip to page bounds
                 expanded = rect + (-5, -5, 5, 5)
                 clip = expanded & page.rect  # Intersect with page bounds to prevent out-of-bounds
                 blocks.extend(page.get_text("dict", clip=clip).get("blocks", []))
        else:
            # Fallback to full page if optimization skipped (e.g. error)
            blocks = page.get_text("dict").get("blocks", [])

        for block in blocks:
            if block.get("type") != 0: continue
            for line in block.get("lines", []):
                # Reconstruct line text from spans
                line_plain = "".join([s.get("text", "") for s in line.get("spans", [])])
                line_norm = normalize_special_chars(normalize_text(line_plain)).lower()

                # Check for match
                if target_norm in line_norm:
                    line_bbox = line.get("bbox")
                    if not line_bbox:
                        continue
                    found_line_rect = fitz.Rect(line_bbox)

                    # Exact or substantial match?
                    if target_norm == line_norm or len(target_norm) > 0.8 * len(line_norm):
                        strategy3_found += 1
                        if not return_all: return found_line_rect
                        add_unique([found_line_rect])
                        continue

                    # Look for exact span matches within the line
                    for span in line.get("spans", []):
                        span_norm = normalize_special_chars(normalize_text(span.get("text", ""))).lower()
                        if target_norm == span_norm:
                            span_bbox = span.get("bbox")
                            if not span_bbox:
                                continue
                            found_span_rect = fitz.Rect(span_bbox)
                            strategy3_found += 1
                            if not return_all: return found_span_rect
                            add_unique([found_span_rect])

        if diagnostic:
            if strategy3_found > 0:
                diagnostic.add_strategy("Strategy 3: Dict scan", f"FOUND {strategy3_found} matches")
            else:
                diagnostic.add_strategy("Strategy 3: Dict scan", "NO MATCH")

    except Exception as e:
        if diagnostic:
            diagnostic.add_strategy("Strategy 3: Dict scan", f"ERROR: {e}")
    
    if found_rects and return_all:
        return found_rects

    # Strategy 4: Strip leading bullet/dash characters and retry
    bullet_chars = ['-', '•', '–', '—', '·', '*', '‣', '◦', '○', '●']
    stripped_text = target_text.lstrip()
    strategy4_found = False

    for bullet in bullet_chars:
        if stripped_text.startswith(bullet):
            cleaned = stripped_text[len(bullet):].lstrip()
            if cleaned:
                # Find hits for cleaned text
                clean_hits = page.search_for(cleaned)
                if not clean_hits:
                    clean_hits = [h.rect for h in page.search_for(cleaned, quads=True)]

                if clean_hits:
                    processed_rects = []
                    for main_rect in clean_hits:
                        # Try to find the bullet character in the same horizontal band
                        bullet_hits = page.search_for(bullet)
                        found_combined = False
                        for bullet_rect in bullet_hits:
                            if (abs(bullet_rect.y0 - main_rect.y0) < 5 and bullet_rect.x0 < main_rect.x0):
                                combined = fitz.Rect(
                                    bullet_rect.x0,
                                    min(bullet_rect.y0, main_rect.y0),
                                    main_rect.x1,
                                    max(bullet_rect.y1, main_rect.y1)
                                )
                                processed_rects.append(combined)
                                found_combined = True
                                break
                        if not found_combined:
                            processed_rects.append(main_rect)

                    strategy4_found = True
                    if diagnostic:
                        diagnostic.add_strategy(f"Strategy 4: Bullet strip ('{bullet}')", f"FOUND {len(processed_rects)} hits")

                    if not return_all:
                        return processed_rects[0]
                    else:
                        # Avoid duplicates
                        for r in processed_rects:
                             if not any(r.intersects(fr) and r.get_area() > fr.get_area()*0.9 for fr in found_rects):
                                 found_rects.append(r)
            break

    if diagnostic and not strategy4_found and any(stripped_text.startswith(b) for b in bullet_chars):
        diagnostic.add_strategy("Strategy 4: Bullet strip", "NO MATCH after stripping")

    # Strategy 5: Flexible whitespace matching for justified text
    # Justified text has variable spacing that can break exact matching
    if not found_rects or return_all:
        import re
        # Build a regex pattern that treats whitespace flexibly
        # Replace any whitespace sequence with a flexible match pattern
        words = target_text.split()
        strategy5_found = 0
        if len(words) > 1:
            # Create pattern: word1 + flexible space + word2 + ...
            # This handles justified text where spaces may be different widths
            escaped_words = [re.escape(w) for w in words]
            flex_pattern = r'\s+'.join(escaped_words)

            try:
                page_text_full = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                matches = list(re.finditer(flex_pattern, page_text_full, re.IGNORECASE))

                for match in matches:
                    matched_text = match.group(0)
                    # Search for this specific matched text
                    match_rects = page.search_for(matched_text)
                    if match_rects:
                        strategy5_found += len(match_rects)
                        if not return_all:
                            if diagnostic:
                                diagnostic.add_strategy("Strategy 5: Flex whitespace", f"FOUND {len(match_rects)} hits")
                            return match_rects[0]
                        add_unique(match_rects)

                if diagnostic:
                    if strategy5_found > 0:
                        diagnostic.add_strategy("Strategy 5: Flex whitespace", f"FOUND {strategy5_found} hits")
                    else:
                        diagnostic.add_strategy("Strategy 5: Flex whitespace", "NO MATCH")

            except Exception as e:
                if diagnostic:
                    diagnostic.add_strategy("Strategy 5: Flex whitespace", f"ERROR: {e}")

    # Strategy 6: Multi-line text matching with normalization
    # When user selects text spanning multiple PDF lines, the target contains newlines
    # but PDF stores each line separately. Match lines individually and combine rects.
    # Uses normalized matching to handle special characters (smart quotes, ligatures, etc.)
    if not found_rects or return_all:
        # Check if target contains line breaks (newlines or explicit line-break patterns)
        lines = target_text.split('\n')
        if len(lines) > 1:
            # Filter out empty lines
            lines = [l.strip() for l in lines if l.strip()]

            if len(lines) >= 2:
                # Helper to find a line rect with normalization fallback
                def find_line_rect(search_line):
                    """Find rect for a line, with normalized fallback."""
                    # Try exact search first
                    rects = page.search_for(search_line)
                    if rects:
                        return rects

                    # Fallback: search with normalized comparison
                    search_norm = normalize_special_chars(normalize_text(search_line)).lower()
                    try:
                        for block in page.get_text("dict").get("blocks", []):
                            if block.get("type") != 0:
                                continue
                            for line in block.get("lines", []):
                                line_text = "".join(s.get("text", "") for s in line.get("spans", []))
                                line_norm = normalize_special_chars(normalize_text(line_text)).lower()
                                # Check if normalized texts match (exact match only to avoid false positives)
                                if search_norm == line_norm:
                                    l_bbox = line.get("bbox")
                                    if l_bbox:
                                        return [fitz.Rect(l_bbox)]
                    except Exception:
                        pass
                    return []

                # Search for first line
                first_line_rects = find_line_rect(lines[0])

                if first_line_rects:
                    for first_rect in first_line_rects:
                        # Try to find subsequent lines below this one
                        matched_lines = [first_rect]
                        current_y = first_rect.y1  # Bottom of first line
                        all_matched = True

                        for line in lines[1:]:
                            # Search for this line with normalization
                            line_rects = find_line_rect(line)

                            # Find a rect that is directly below current position
                            found_below = None
                            for lr in line_rects:
                                # Check if this line is below current and reasonably aligned
                                # Allow 50pt vertical gap (typical line spacing)
                                # and check x-alignment (left edge within 100pt)
                                if (lr.y0 >= current_y - 2 and
                                    lr.y0 <= current_y + 50 and
                                    abs(lr.x0 - first_rect.x0) < 100):
                                    found_below = lr
                                    break

                            if found_below:
                                matched_lines.append(found_below)
                                current_y = found_below.y1
                            else:
                                all_matched = False
                                break

                        if all_matched and len(matched_lines) == len(lines):
                            # Combine all matched rects into one
                            combined = fitz.Rect(
                                min(r.x0 for r in matched_lines),
                                min(r.y0 for r in matched_lines),
                                max(r.x1 for r in matched_lines),
                                max(r.y1 for r in matched_lines)
                            )
                            if diagnostic:
                                diagnostic.add_strategy(
                                    f"Strategy 6: Multi-line ({len(lines)} lines)",
                                    f"FOUND combined rect"
                                )
                            if not return_all:
                                return combined
                            add_unique([combined])
                            break  # Found a match, stop looking

                if diagnostic and not found_rects:
                    diagnostic.add_strategy(
                        f"Strategy 6: Multi-line ({len(lines)} lines)",
                        "NO MATCH - lines not found in sequence"
                    )

    return found_rects if return_all else (found_rects[0] if found_rects else None)



def _inject_simulated_bold(page, stroke_width: float = 0.28):
    """
    HACK: Inject PDF operators to simulate bolding (Fill+Stroke) for the last inserted text.
    This is needed when reusing 'Regular' embedded fonts that were originally rendered 
    with '2 Tr' (simulated bold).
    
    Args:
        page: fitz.Page object
        stroke_width: The line width for the stroke (default 0.28 for ~11pt text)
                     Logic: width ~= 0.025 * fontsize
    """
    try:
        # DO NOT use clean_contents() here as it can interfere with redaction transparency
        # Instead, we look at the last content stream since that's where new text is usually appended
        
        contents_xrefs = page.get_contents()
        if not contents_xrefs: return
        
        # Check streams in reverse order (newest first)
        found_and_injected = False
        import re
        
        # We look for the Tf operator: "/F[0-9]+ [0-9.]+ Tf"
        tf_pattern = rb'(/[a-zA-Z0-9_]+ [0-9\.]+ Tf)'
        
        for xref in reversed(contents_xrefs):
            stream = page.parent.xref_stream(xref)
            
            matches = list(re.finditer(tf_pattern, stream))
            if matches:
                # Found the font selection in this stream
                last_match = matches[-1]
                idx = last_match.start()
                
                # Inject "w 2 Tr" before the font selection
                w_str = f"{stroke_width:.2f}".encode('ascii')
                injection = b' ' + w_str + b' w 2 Tr '
                
                prefix = stream[:idx]
                suffix = stream[idx:]
                
                new_stream = prefix + injection + suffix
                
                # Update stream
                page.parent.update_stream(xref, new_stream)
                found_and_injected = True
                break
        
        if not found_and_injected:
            # Fallback: if we couldn't find where to inject, log it
            # print("Warning: Could not find font selection to inject bold")
            pass
            
    except Exception as e:
        print(f"Bolding injection failed: {e}")


def _detect_text_decorations(page, rect: fitz.Rect) -> dict:
    """
    Detect text decorations (underline, strikethrough) by analyzing drawing operations.

    PDF text decorations are implemented as line drawing operations, not font attributes.
    We look for horizontal lines near the text baseline.

    IMPORTANT: Color filtering is applied to reject red decorations (redline markup).
    Only BLACK decorations are detected to avoid false positives from redline strikethrough.

    Returns dict with:
        - underline: bool
        - strikethrough: bool
        - detected: bool
    """
    result = {
        'underline': False,
        'strikethrough': False,
        'detected': False
    }

    try:
        # Get drawing operations in the text area
        # Do NOT expand rect - use exact bounds only to avoid false positives
        search_rect = rect

        # Get the page's drawing instructions
        paths = page.get_cdrawings()

        for path in paths:
            items = path.get("items", [])
            if not items:
                continue

            # COLOR FILTERING: Reject red decorations (redline strikethrough)
            # Path color from get_cdrawings() is a tuple of floats (0-1), e.g. (1.0, 0.0, 0.0)
            path_color = path.get("color")
            if path_color is None:
                r, g, b = 0.0, 0.0, 0.0  # Default to black
            elif isinstance(path_color, (tuple, list)):
                r = path_color[0] if len(path_color) > 0 else 0.0
                g = path_color[1] if len(path_color) > 1 else 0.0
                b = path_color[2] if len(path_color) > 2 else 0.0
            else:
                r, g, b = 0.0, 0.0, 0.0

            # Skip red decorations (R > 0.5, G < 0.3, B < 0.3)
            # This prevents redline strikethrough from being detected
            if r > 0.5 and g < 0.3 and b < 0.3:
                continue  # Skip red decoration

            # Extract line segments from drawing items
            # get_cdrawings() items are tuples: ("l", p1, p2) for lines
            for item in items:
                if len(item) < 3 or item[0] != "l":
                    continue  # Only process line segments
                p0 = item[1]  # Start point
                p1 = item[2]  # End point

                # Check if it's a horizontal line (y coordinates nearly equal)
                y0 = p0[1] if hasattr(p0, '__getitem__') else getattr(p0, 'y', 0)
                y1 = p1[1] if hasattr(p1, '__getitem__') else getattr(p1, 'y', 0)
                if abs(y0 - y1) < 2:  # Nearly horizontal
                    line_y = (y0 + y1) / 2
                    text_baseline = rect.y0 + (rect.y1 - rect.y0) * 0.85

                    # Check line width
                    line_width = path.get("width", 1.0)

                    # Underline: typically below baseline, close to text
                    # Strikethrough: through middle of text

                    text_height = rect.y1 - rect.y0
                    text_middle = rect.y0 + text_height / 2

                    # Allow some tolerance
                    underline_y = text_baseline + text_height * 0.15
                    if abs(line_y - underline_y) < text_height * 0.1 and line_width < 2:
                        result['underline'] = True
                        result['detected'] = True

                    if abs(line_y - text_middle) < text_height * 0.1 and line_width < 2:
                        result['strikethrough'] = True
                        result['detected'] = True

    except Exception as e:
        print(f"Decoration detection failed: {e}")

    return result


def _inject_text_underline(page, rect: fitz.Rect, color=(0, 0, 0)):
    """
    Draw an underline below text at the given rect.

    Args:
        page: fitz.Page object
        rect: fitz.Rect of the text
        color: RGB tuple for underline color
    """
    try:
        # Calculate underline position (typically below baseline)
        text_height = rect.y1 - rect.y0
        baseline_y = rect.y0 + text_height * 0.85
        underline_y = baseline_y + text_height * 0.15

        # Draw line
        underline_rect = fitz.Rect(rect.x0, underline_y, rect.x1, underline_y + 0.5)

        page.draw_line(underline_rect.bl, underline_rect.br, color=color, width=0.5)

    except Exception as e:
        print(f"Underline injection failed: {e}")


def _inject_text_strikethrough(page, rect: fitz.Rect, color=(0, 0, 0)):
    """
    Draw a strikethrough line through text at the given rect.

    Args:
        page: fitz.Page object
        rect: fitz.Rect of the text
        color: RGB tuple (floats 0-1) for strikethrough color
    """
    try:
        # Calculate strikethrough position (middle of text)
        text_height = rect.y1 - rect.y0
        mid_y = rect.y0 + text_height / 2

        # Draw line
        strike_rect = fitz.Rect(rect.x0, mid_y, rect.x1, mid_y + 0.5)

        page.draw_line(strike_rect.bl, strike_rect.br, color=color, width=0.5)

    except Exception as e:
        print(f"Strikethrough injection failed: {e}")


def _inject_simulated_italic(page):
    """
    HACK: Inject PDF operators to simulate italic (oblique transform) for the last inserted text.
    This is needed when the replacement font doesn't have a native italic variant.

    We apply a horizontal skew transformation matrix [1 0 0.2 1 0 0] which:
    - Keeps x coordinates unchanged
    - Skews y coordinates by 20% to the right
    - This creates the characteristic slant of italic text

    Args:
        page: fitz.Page object
    """
    try:
        # We need to find the last text insertion and apply a transformation matrix
        # The matrix [1 0 0.2 1 0 0] will skew the text horizontally

        contents_xrefs = page.get_contents()
        if not contents_xrefs: return

        # Check streams in reverse order (newest first)
        found_and_injected = False
        import re

        # Look for the Tf operator: "/F[0-9]+ [0-9.]+ Tf"
        tf_pattern = rb'(/[a-zA-Z0-9_]+ [0-9\.]+ Tf)'

        for xref in reversed(contents_xrefs):
            stream = page.parent.xref_stream(xref)

            matches = list(re.finditer(tf_pattern, stream))
            if matches:
                # Found the font selection in this stream
                last_match = matches[-1]
                idx = last_match.start()

                # Inject a transformation matrix before the font selection
                # [1 0 0.2 1 0 0] cm - 20% horizontal skew (italic simulation)
                injection = b' 1 0 0.2 1 0 0 cm '

                prefix = stream[:idx]
                suffix = stream[idx:]

                new_stream = prefix + injection + suffix

                # Update stream
                page.parent.update_stream(xref, new_stream)
                found_and_injected = True
                break

        if not found_and_injected:
            # Fallback: if we couldn't find where to inject, log it
            pass

    except Exception as e:
        print(f"Italic injection failed: {e}")


def detect_text_alignment(page, rect: fitz.Rect, line_rect: fitz.Rect = None, debug_log: list = None) -> str:
    """
    Unified text alignment detection function.

    Analyzes text position relative to margins and word spacing to determine:
    - "left": Text aligned to left margin
    - "center": Text centered in column
    - "right": Text aligned to right margin
    - "justified": Text spans full width with distributed spacing

    Args:
        page: fitz.Page object
        rect: Target rect containing the text
        line_rect: Optional line rect for better context (from reflow)
        debug_log: Optional list for debug messages

    Returns:
        str: One of "left", "center", "right", "justified"
    """
    if debug_log is None:
        debug_log = []

    try:
        # BUG #51 FIX: Calculate margins dynamically from actual page content
        # instead of assuming fixed 7.5% margins
        page_rect = page.rect
        page_width = page_rect.width

        # Sample page content to find actual text boundaries
        # Get all text blocks on the page (not just in target rect)
        all_blocks = page.get_text("dict").get("blocks", [])
        text_left_edges = []
        text_right_edges = []

        for block in all_blocks:
            if block.get("type") != 0: continue  # Skip non-text blocks
            bbox = block.get("bbox")
            if bbox:
                text_left_edges.append(bbox[0])
                text_right_edges.append(bbox[2])

        # Calculate margins from content boundaries
        if text_left_edges and text_right_edges:
            # Use 10th percentile for left (ignore outliers/page numbers)
            # Use 90th percentile for right (ignore outliers)
            text_left_edges.sort()
            text_right_edges.sort()
            left_margin = text_left_edges[max(0, len(text_left_edges) // 10)]
            right_margin = text_right_edges[min(len(text_right_edges) - 1, len(text_right_edges) * 9 // 10)]
        else:
            # Fallback to standard margins if no content found
            left_margin = page_width * 0.075
            right_margin = page_width * 0.925

        content_width = right_margin - left_margin
        if content_width <= 0:
            content_width = page_width * 0.85  # Fallback to 85% of page width
        content_center = (left_margin + right_margin) / 2

        debug_log.append(f"Dynamic margins: left={left_margin:.1f}, right={right_margin:.1f} (content_width={content_width:.1f})")

        # Use line_rect for better context if available
        ref_rect = line_rect if line_rect else rect

        # Get text blocks for word spacing analysis
        blocks = page.get_text("dict", clip=rect).get("blocks", [])

        for block in blocks:
            if block.get("type") != 0: continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans: continue

                # Get line boundaries
                line_bbox_raw = line.get("bbox")
                if line_bbox_raw:
                    line_x0 = line_bbox_raw[0]
                    line_x1 = line_bbox_raw[2]
                else:
                    line_x0 = rect.x0
                    line_x1 = rect.x1
                line_width = line_x1 - line_x0

                # Get text content
                text = "".join(s.get("text", "") for s in spans)
                words = text.split()

                # Check if text spans full width (justified)
                # Must have multiple words and span >90% of content area
                if line_width > content_width * 0.90 and len(words) >= 3:
                    # Additional check: analyze word spacing variation
                    if len(spans) > 1:
                        gaps = []
                        for i in range(1, len(spans)):
                            cur_bbox = spans[i].get("bbox")
                            prev_bbox = spans[i-1].get("bbox")
                            if not cur_bbox or not prev_bbox:
                                continue
                            gap = cur_bbox[0] - prev_bbox[2]
                            if gap > 0:
                                gaps.append(gap)

                        if gaps and len(gaps) >= 2 and max(gaps) > 2 * min(gaps):
                            debug_log.append(f"Alignment: JUSTIFIED (full width, variable spacing)")
                            return "justified"

                    debug_log.append(f"Alignment: JUSTIFIED (spans {line_width/content_width*100:.0f}% of content width)" if content_width > 0 else "Alignment: JUSTIFIED")
                    return "justified"

        # Position-based alignment detection using reference rect
        text_center = (ref_rect.x0 + ref_rect.x1) / 2
        text_left = ref_rect.x0
        text_right = ref_rect.x1
        text_width = ref_rect.width

        # Calculate distances from alignment positions
        dist_from_center = abs(text_center - content_center)
        dist_from_left = abs(text_left - left_margin)
        dist_from_right = abs(text_right - right_margin)

        # Tolerance for alignment detection
        # Use percentage-based tolerance for center (5% of content width)
        # Use fixed tolerance for edges (20 points)
        center_tolerance = content_width * 0.05
        edge_tolerance = 20

        # Check for centered text first (strongest indicator)
        if dist_from_center < center_tolerance:
            # Additional check: text should not span full width
            if text_width < content_width * 0.9:
                debug_log.append(f"Alignment: CENTER (center dist: {dist_from_center:.1f}pt, tol: {center_tolerance:.1f}pt)")
                return "center"

        # Check for right-aligned text
        if dist_from_right < edge_tolerance and dist_from_left > edge_tolerance * 2:
            debug_log.append(f"Alignment: RIGHT (right dist: {dist_from_right:.1f}pt, left dist: {dist_from_left:.1f}pt)")
            return "right"

        # Default to left-aligned
        debug_log.append(f"Alignment: LEFT (default - left dist: {dist_from_left:.1f}pt)")
        return "left"

    except Exception as e:
        debug_log.append(f"Alignment detection error: {e}")
        return "left"


def _detect_justification(page, rect: fitz.Rect) -> str:
    """
    Legacy wrapper for detect_text_alignment for backwards compatibility.

    Returns:
        str: One of "left", "center", "right", "justified"
    """
    return detect_text_alignment(page, rect)


# ──────────────────────────────────────────────────────────────────────────────
# Layout Detection  (Week 7 Day 2)
# ──────────────────────────────────────────────────────────────────────────────

def detect_columns(page) -> list:
    """
    Detect column regions on a page by clustering text-span X positions.

    PyMuPDF merges same-Y text into single wide blocks, so block-level X
    positions are unreliable for multi-column layouts.  This function clusters
    at the span level, which preserves each run's true X position.

    Returns:
        list of fitz.Rect – one rect per detected column, sorted left-to-right.
        Empty list for single-column pages or pages with no text.
    """
    try:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
        page_width = page.rect.width

        # Collect (x_center, bbox) for each span; skip very narrow fragments
        centers = []
        for b in blocks:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span["bbox"]
                    w = bbox[2] - bbox[0]
                    if w < 20:
                        continue
                    centers.append((bbox[0] + w / 2.0, bbox))

        if len(centers) < 3:
            return []

        centers.sort(key=lambda t: t[0])

        # Cluster: group X centres within 15 % of page width
        cluster_gap = page_width * 0.15
        clusters = []
        current = [centers[0][1]]
        current_cx = centers[0][0]

        for cx, bbox in centers[1:]:
            if cx - current_cx > cluster_gap:
                clusters.append(current)
                current = [bbox]
                current_cx = cx
            else:
                current.append(bbox)
                current_cx = (current_cx + cx) / 2.0

        clusters.append(current)

        if len(clusters) < 2:
            return []  # single column

        column_rects = []
        for group in clusters:
            x0 = min(b[0] for b in group)
            y0 = min(b[1] for b in group)
            x1 = max(b[2] for b in group)
            y1 = max(b[3] for b in group)
            column_rects.append(fitz.Rect(x0, y0, x1, y1))

        column_rects.sort(key=lambda r: r.x0)
        return column_rects

    except Exception as e:
        print(f"[Layout] detect_columns error: {e}")
        return []


def get_text_rotation(span: dict) -> int:
    """
    Extract the rotation angle from a text span's "dir" direction vector.

    Args:
        span: A span dict from page.get_text("dict"); must have "dir" key
              (cos θ, sin θ) representing the text baseline direction.

    Returns:
        Rotation in degrees: 0, 90, 180, or 270.
    """
    try:
        import math
        direction = span.get("dir")
        if direction is None:
            return 0
        cos_a, sin_a = direction
        angle_deg = math.degrees(math.atan2(sin_a, cos_a)) % 360
        return int(round(angle_deg / 90) * 90) % 360
    except Exception as e:
        print(f"[Layout] get_text_rotation error: {e}")
        return 0


def detect_tables(page) -> list:
    """
    Detect table regions from page drawing paths (horizontal/vertical lines).

    Returns:
        list of dict, each with:
          - "rect":  fitz.Rect – bounding box of the table
          - "rows":  int        – estimated row count
          - "cols":  int        – estimated column count
          - "cells": list of fitz.Rect – individual cell rects
    """
    try:
        drawings = page.get_drawings()
        if not drawings:
            return []

        h_lines = []
        v_lines = []

        for path in drawings:
            for item in path.get("items", []):
                if item[0] != "l":
                    continue
                p1, p2 = item[1], item[2]
                dx = abs(p2.x - p1.x)
                dy = abs(p2.y - p1.y)
                if dy < 2 and dx > 20:      # horizontal
                    h_lines.append((p1.y + p2.y) / 2.0)
                elif dx < 2 and dy > 20:    # vertical
                    v_lines.append((p1.x + p2.x) / 2.0)

        if len(h_lines) < 2 or len(v_lines) < 2:
            return []

        def cluster_lines(coords, gap=3.0):
            coords = sorted(set(round(c, 1) for c in coords))
            clusters = []
            current = [coords[0]]
            for c in coords[1:]:
                if c - current[-1] <= gap:
                    current.append(c)
                else:
                    clusters.append(sum(current) / len(current))
                    current = [c]
            clusters.append(sum(current) / len(current))
            return clusters

        h_unique = cluster_lines(h_lines)
        v_unique = cluster_lines(v_lines)

        if len(h_unique) < 2 or len(v_unique) < 2:
            return []

        rows = len(h_unique) - 1
        cols = len(v_unique) - 1
        table_rect = fitz.Rect(v_unique[0], h_unique[0], v_unique[-1], h_unique[-1])

        cells = []
        for r in range(rows):
            for c in range(cols):
                cells.append(fitz.Rect(v_unique[c], h_unique[r],
                                       v_unique[c + 1], h_unique[r + 1]))

        return [{"rect": table_rect, "rows": rows, "cols": cols, "cells": cells}]

    except Exception as e:
        print(f"[Layout] detect_tables error: {e}")
        return []


def get_reading_order(page, blocks: list = None) -> list:
    """
    Return text blocks sorted in natural reading order (column-aware).

    For multi-column pages blocks are grouped by column first, then sorted
    top-to-bottom within each column.  Single-column pages fall back to a
    simple top-to-bottom, left-to-right sort.

    Args:
        page:   fitz.Page object
        blocks: Optional pre-fetched block list from page.get_text("dict").
                If None, fetched internally.

    Returns:
        list of block dicts (type == 0 only) in reading order.
    """
    try:
        if blocks is None:
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])

        text_blocks = [b for b in blocks if b.get("type") == 0]
        if not text_blocks:
            return []

        columns = detect_columns(page)

        if not columns:
            return sorted(text_blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        col_centres = [(c.x0 + c.x1) / 2.0 for c in columns]

        def column_index(bbox):
            cx = (bbox[0] + bbox[2]) / 2.0
            for i, col in enumerate(columns):
                if col.x0 <= cx <= col.x1:
                    return i
            return min(range(len(col_centres)), key=lambda i: abs(col_centres[i] - cx))

        return sorted(text_blocks, key=lambda b: (column_index(b["bbox"]), b["bbox"][1]))

    except Exception as e:
        print(f"[Layout] get_reading_order error: {e}")
        return blocks if blocks else []


def detect_layout_context(page, rect: fitz.Rect = None) -> dict:
    """
    Master layout analysis for a page and optional focus rect.

    Args:
        page: fitz.Page object
        rect: Optional fitz.Rect of the text region of interest.

    Returns:
        dict with:
          - "layout_type":       str  – "single_column" | "multi_column" |
                                        "table" | "rotated" | "mixed"
          - "columns":           list – column rects as fitz.Rect
          - "column_count":      int
          - "tables":            list – table dicts from detect_tables()
          - "has_tables":        bool
          - "dominant_rotation": int  – 0 | 90 | 180 | 270
          - "has_rotated_text":  bool
          - "column_index":      int | None – which column rect falls in
          - "rect_rotation":     int | None – rotation of text at rect
    """
    _default = {
        "layout_type": "single_column",
        "columns": [],
        "column_count": 1,
        "tables": [],
        "has_tables": False,
        "dominant_rotation": 0,
        "has_rotated_text": False,
        "column_index": None,
        "rect_rotation": None,
    }
    try:
        result = dict(_default)

        columns = detect_columns(page)
        result["columns"] = columns
        result["column_count"] = max(1, len(columns))

        tables = detect_tables(page)
        result["tables"] = tables
        result["has_tables"] = bool(tables)

        # Dominant rotation across all spans (weighted by character count)
        raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        rotation_votes = {}
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    angle = get_text_rotation(span)
                    rotation_votes[angle] = rotation_votes.get(angle, 0) + len(span.get("text", ""))

        if rotation_votes:
            dominant = max(rotation_votes, key=rotation_votes.get)
            result["dominant_rotation"] = dominant
            result["has_rotated_text"] = any(a != 0 for a in rotation_votes)

        # Layout type
        flags = []
        if len(columns) >= 2:
            flags.append("multi_column")
        if tables:
            flags.append("table")
        if result["has_rotated_text"] and result["dominant_rotation"] != 0:
            flags.append("rotated")

        result["layout_type"] = (
            "single_column" if not flags
            else flags[0] if len(flags) == 1
            else "mixed"
        )

        # Focus rect context
        if rect is not None and columns:
            cx = (rect.x0 + rect.x1) / 2.0
            col_centres = [(c.x0 + c.x1) / 2.0 for c in columns]
            for i, col in enumerate(columns):
                if col.x0 <= cx <= col.x1:
                    result["column_index"] = i
                    break
            if result["column_index"] is None:
                result["column_index"] = min(range(len(col_centres)),
                                             key=lambda i: abs(col_centres[i] - cx))

        if rect is not None:
            for block in raw.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    if not fitz.Rect(line["bbox"]).intersects(rect):
                        continue
                    for span in line.get("spans", []):
                        if fitz.Rect(span["bbox"]).intersects(rect):
                            result["rect_rotation"] = get_text_rotation(span)
                            break
                    if result["rect_rotation"] is not None:
                        break
                if result["rect_rotation"] is not None:
                    break

        return result

    except Exception as e:
        print(f"[Layout] detect_layout_context error: {e}")
        return _default


def _insert_justified_text(page, pos, text, fontname, fontsize, color, available_width, debug_log=None):
    """Insert text with justified alignment by distributing space between words."""
    words = text.split(' ')
    if len(words) <= 1:
        # Single word - just left-align
        page.insert_text(pos, text, fontname=fontname, fontsize=fontsize, color=color)
        return

    # Measure each word
    try:
        font = fitz.Font(fontname)
        word_widths = [font.text_length(w, fontsize=fontsize) for w in words]
    except Exception:
        word_widths = [len(w) * fontsize * 0.5 for w in words]

    total_word_width = sum(word_widths)
    num_gaps = len(words) - 1
    remaining = available_width - total_word_width

    # Sanity check: don't justify if text is too short or gaps too wide
    normal_space = fontsize * 0.25
    space_per_gap = remaining / num_gaps if num_gaps > 0 else 0
    if space_per_gap > normal_space * 4 or space_per_gap < 0:
        page.insert_text(pos, text, fontname=fontname, fontsize=fontsize, color=color)
        return

    # Insert word by word
    x, y = pos
    for i, word in enumerate(words):
        page.insert_text((x, y), word, fontname=fontname, fontsize=fontsize, color=color)
        x += word_widths[i]
        if i < num_gaps:
            x += space_per_gap


def _insert_tracked_text(page, pos, text, fontname, fontsize, color, tracking_delta, debug_log=None):
    """Insert text with adjusted tracking/letter-spacing."""
    if not tracking_delta or tracking_delta == 0:
        page.insert_text(pos, text, fontname=fontname, fontsize=fontsize, color=color)
        return

    try:
        font = fitz.Font(fontname)
    except Exception:
        font = None

    x, y = pos
    for char in text:
        page.insert_text((x, y), char, fontname=fontname, fontsize=fontsize, color=color)
        if font:
            char_width = font.text_length(char, fontsize=fontsize)
        else:
            char_width = fontsize * 0.5
        x += char_width + tracking_delta


def _handle_multiline_replacement(page, target_text: str, replacement_text: str, rect: fitz.Rect, font_info: dict, repl_font, use_internal_fontname, adjusted_fontsize, debug_log: list, manual_overrides: dict = None) -> tuple[bool, fitz.Rect | None]:
    """
    Handle replacement of multi-line text blocks, preserving line breaks and vertical spacing.

    Args:
        page: fitz.Page to modify
        target_text: Original text (may contain newlines)
        replacement_text: New text (may contain newlines)
        rect: Bounding rect of the target text
        font_info: Font information dict
        repl_font: Replacement font object
        use_internal_fontname: Internal font name to use (or None)
        adjusted_fontsize: Font size to use
        debug_log: List to append debug messages
        manual_overrides: Optional manual overrides dict

    Returns:
        tuple: (success: bool, final_rect: fitz.Rect | None)
    """
    debug_log.append("[MultiLine] Detected multi-line text replacement")

    # Split into lines
    target_lines = target_text.split('\n')
    replacement_lines = replacement_text.split('\n')

    debug_log.append(f"[MultiLine] Target has {len(target_lines)} lines, replacement has {len(replacement_lines)} lines")

    # Get the text structure to find line positions
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception as e:
        debug_log.append(f"[MultiLine] ERROR: Failed to get text structure: {e}")
        return False, None

    # Find all lines within the target rect
    line_rects = []
    for block in blocks:
        if block.get("type") != 0:  # Skip non-text blocks
            continue

        for line in block.get("lines", []):
            raw_bbox = line.get("bbox")
            if not raw_bbox:
                continue
            line_bbox = fitz.Rect(raw_bbox)
            # Check if this line overlaps with our target rect
            if rect.intersects(line_bbox):
                line_text = "".join(span.get("text", "") for span in line.get("spans", []))
                # Capture actual baseline from first span's origin
                line_baseline = None
                spans = line.get("spans", [])
                if spans:
                    origin = spans[0].get("origin")
                    if origin and len(origin) >= 2:
                        line_baseline = origin[1]
                line_rects.append((line_bbox, line_text, line_baseline))

    debug_log.append(f"[MultiLine] Found {len(line_rects)} lines in target rect")

    if not line_rects:
        debug_log.append("[MultiLine] ERROR: Could not find line structure")
        return False, None

    # Sort lines by vertical position (top to bottom)
    line_rects.sort(key=lambda x: x[0].y0)

    # Calculate average line height and spacing
    if len(line_rects) > 1:
        line_heights = [r[0].height for r in line_rects]
        avg_line_height = sum(line_heights) / len(line_heights)

        # Calculate spacing between lines (from bottom of one to top of next)
        spacings = []
        for i in range(len(line_rects) - 1):
            spacing = line_rects[i+1][0].y0 - line_rects[i][0].y1
            spacings.append(spacing)
        avg_spacing = sum(spacings) / len(spacings) if spacings else avg_line_height * 0.2
    else:
        avg_line_height = line_rects[0][0].height
        avg_spacing = avg_line_height * 0.2  # 20% of line height as default spacing

    debug_log.append(f"[MultiLine] Avg line height: {avg_line_height:.2f}, spacing: {avg_spacing:.2f}")

    # Redact each line individually for precise removal
    # Using per-line redaction prevents accidentally removing adjacent content
    redact_fill = _parse_palette_color(manual_overrides['fill_color'].lower()) if manual_overrides and manual_overrides.get('fill_color') else None
    tracking_delta = float(manual_overrides.get('manual_tracking_delta', 0)) if manual_overrides else 0

    for line_rect, line_text in line_rects:
        # Shrink slightly to avoid catching adjacent text, but only if rect is large enough
        if line_rect.width > 1.0 and line_rect.height > 1.0:
            precise_rect = fitz.Rect(
                line_rect.x0 + 0.5,
                line_rect.y0 + 0.5,
                line_rect.x1 - 0.5,
                line_rect.y1 - 0.5
            )
        else:
            precise_rect = line_rect
        page.add_redact_annot(precise_rect, fill=redact_fill)

    # Apply all redactions at once - preserve images and graphics
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    debug_log.append(f"[MultiLine] Redacted {len(line_rects)} line regions")

    # Insert replacement text line by line
    start_y = line_rects[0][0].y0  # Top of first line
    start_x = min(r[0].x0 for r in line_rects)   # Leftmost edge across all lines
    end_x = max(r[0].x1 for r in line_rects)      # Rightmost edge across all lines

    # Check for manual justification override, otherwise auto-detect
    if manual_overrides and manual_overrides.get('justification'):
        alignment = manual_overrides['justification']
        debug_log.append(f"[MultiLine] Using manual alignment: {alignment}")
    else:
        alignment = _detect_justification(page, rect)
        debug_log.append(f"[MultiLine] Auto-detected alignment: {alignment}")

    # Register font if needed (defense-in-depth: also pre-registered before branching)
    if use_internal_fontname and repl_font and hasattr(repl_font, 'buffer'):
        try:
            page.insert_font(fontname=use_internal_fontname, fontbuffer=repl_font.buffer)
        except Exception as e:
            debug_log.append(f"[MultiLine] Font registration failed: {e}")
    elif not use_internal_fontname and repl_font and hasattr(repl_font, 'buffer'):
        try:
            page.insert_font(fontname="R0", fontbuffer=repl_font.buffer)
        except Exception as e:
            debug_log.append(f"[MultiLine] Font registration failed: {e}")

    fontname = use_internal_fontname if use_internal_fontname else "R0"
    # Use manual color override if set, otherwise preserve original text color.
    # Note: for redline documents, user should set force_black_text override.
    if manual_overrides and manual_overrides.get('force_black_text'):
        color = (0, 0, 0)
    elif manual_overrides and manual_overrides.get('color'):
        color = manual_overrides['color']
    else:
        color = font_info.get('color', (0, 0, 0))

    # Insert each replacement line
    final_rect = None
    # Use actual baseline from first line's span origin if available, else estimate
    first_baseline = line_rects[0][2] if len(line_rects[0]) > 2 and line_rects[0][2] is not None else None
    current_y = first_baseline if first_baseline else start_y + avg_line_height * 0.85

    for i, line_text in enumerate(replacement_lines):
        if not line_text:  # Skip empty lines but maintain spacing
            current_y += avg_line_height + avg_spacing
            continue

        # Insert this line with alignment-aware positioning
        try:
            # Calculate line width for alignment
            try:
                # Try actual font first, fall back to helv for estimation
                try:
                    est_font = fitz.Font(fontname)
                except Exception:
                    est_font = fitz.Font("helv")
                line_width = est_font.text_length(line_text, fontsize=adjusted_fontsize)
            except Exception:
                line_width = len(line_text) * adjusted_fontsize * 0.5  # Rough estimate

            # Calculate x position based on alignment
            if alignment == "center":
                # Center in the original text area
                original_center = (start_x + end_x) / 2
                pos_x = original_center - (line_width / 2)
            elif alignment == "right":
                # Align to right edge
                pos_x = end_x - line_width
            else:  # "left" or "justified" - start at left edge
                pos_x = start_x

            # DIAGNOSTIC: Log multiline insertion parameters
            import sys
            print(f"[DIAGNOSTIC] Multiline insert_text line {i+1}: color={color}, fontsize={adjusted_fontsize:.1f}, fontname={fontname}, align={alignment}, pos_x={pos_x:.2f}", file=sys.stderr)

            is_last_line = (i == len(replacement_lines) - 1)
            if alignment == "justified" and not is_last_line:
                _insert_justified_text(
                    page, (pos_x, current_y), line_text,
                    fontname=fontname, fontsize=adjusted_fontsize,
                    color=color, available_width=end_x - start_x,
                    debug_log=debug_log
                )
                text_rect = fitz.Rect(pos_x, current_y - adjusted_fontsize, end_x, current_y)
            elif tracking_delta:
                _insert_tracked_text(
                    page, (pos_x, current_y), line_text,
                    fontname=fontname, fontsize=adjusted_fontsize,
                    color=color, tracking_delta=tracking_delta,
                    debug_log=debug_log
                )
                text_rect = fitz.Rect(pos_x, current_y - adjusted_fontsize, pos_x + line_width, current_y)
            else:
                page.insert_text(
                    (pos_x, current_y),
                    line_text,
                    fontname=fontname,
                    fontsize=adjusted_fontsize,
                    color=color
                )
                # insert_text returns float (text height), not Rect — build rect manually
                text_rect = fitz.Rect(pos_x, current_y - adjusted_fontsize, pos_x + line_width, current_y)

            if text_rect:
                if final_rect is None:
                    final_rect = text_rect
                else:
                    final_rect |= text_rect  # Union with previous lines

                debug_log.append(f"[MultiLine] Inserted line {i+1}/{len(replacement_lines)}: length={len(line_text)} at y={current_y:.2f}")

        except Exception as e:
            debug_log.append(f"[MultiLine] ERROR inserting line {i+1}: {e}")
            return False, None

        # Move to next line position
        current_y += avg_line_height + avg_spacing

    if final_rect:
        debug_log.append(f"[MultiLine] Success! Final rect: {final_rect}")
        return True, final_rect
    else:
        debug_log.append("[MultiLine] ERROR: No text was inserted")
        return False, None


@monitor_performance("replace_text_in_pdf")
def replace_text_in_pdf(input_path: str, output_path: str, target_text: str, replacement_text: str, page_number: int = 1, manual_overrides: dict = None, skip_collision: bool = False, occurrence_index: int | None = None) -> dict:
    """Replace text in a PDF while preserving original font appearance."""
    debug_log = []
    applied_info = {}
    # Extract skip_collision and occurrence_index from manual_overrides if passed via Swift bridge
    if manual_overrides and manual_overrides.get('skip_collision'):
        skip_collision = True
    if manual_overrides and manual_overrides.get('occurrence_index') is not None:
        occurrence_index = int(manual_overrides['occurrence_index'])
    try:
        if not target_text:
            return {'success': False, 'modified': False, 'message': 'Target text empty', 'debug_log': debug_log}

        # 0. Smart Quotes - only when explicitly requested via manual_overrides
        # Previously ran unconditionally, which destroyed foot/inch marks (5’10”),
        # code literals, and apostrophes in names (O’Brien → O’Brien).
        if manual_overrides and manual_overrides.get('smart_quotes') and ('"' in replacement_text or "'" in replacement_text):
            def smarten(text):
                res, open_d = [], True
                for char in text:
                    if char == '"': res.append('\u201c' if open_d else '\u201d'); open_d = not open_d
                    elif char == "'": res.append('\u2019' if res and res[-1].isalnum() else '\u2018')
                    else: res.append(char)
                return "".join(res)
            replacement_text = smarten(replacement_text)

        with fitz.open(input_path) as doc:
            if len(doc) == 0:
                return {'success': False, 'message': 'PDF has no pages'}
            if page_number < 1 or page_number > len(doc):
                return {'success': False, 'message': f'Invalid page {page_number}'}
            page = doc[page_number - 1]

            # Create diagnostic object to capture search details on failure
            diagnostic = SearchDiagnostic(target_text, page_number)
            diagnostic.capture_unicode()

            all_rects = _robust_search(page, target_text, return_all=True, diagnostic=diagnostic)
            if not all_rects:
                # Capture page text sample for debugging
                page_text = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
                diagnostic.capture_page_text(page_text)
                return {
                    'success': False,
                    'modified': False,
                    'message': 'Text not found',
                    'diagnostic': diagnostic.to_dict()
                }

            # MULTI-LINE CONSOLIDATION: When target contains newlines and we found multiple
            # rects (one per line), consolidate into a single combined rect to avoid
            # processing each line separately which causes duplicate replacements.
            # Only combine rects that are vertically contiguous (within line spacing).
            is_multiline_target = '\n' in target_text or '\n' in replacement_text
            if is_multiline_target and len(all_rects) > 1:
                # Sort rects by vertical position (top to bottom)
                sorted_rects = sorted(all_rects, key=lambda r: r.y0)

                # Group vertically contiguous rects
                groups = []
                current_group = [sorted_rects[0]]

                for rect in sorted_rects[1:]:
                    prev_rect = current_group[-1]
                    # Check if vertically adjacent (within 2x the height of previous rect)
                    vertical_gap = rect.y0 - prev_rect.y1
                    max_gap = prev_rect.height * 2

                    if vertical_gap < max_gap:
                        current_group.append(rect)
                    else:
                        groups.append(current_group)
                        current_group = [rect]

                groups.append(current_group)

                # Combine rects within each group
                all_rects = []
                for group in groups:
                    if len(group) > 1:
                        combined = fitz.Rect(
                            min(r.x0 for r in group),
                            min(r.y0 for r in group),
                            max(r.x1 for r in group),
                            max(r.y1 for r in group)
                        )
                        all_rects.append(combined)
                    else:
                        all_rects.extend(group)

                debug_log.append(f"Multi-line: consolidated into {len(all_rects)} contiguous groups")

            # SAME-LINE CONSOLIDATION: When search returns multiple rects for a single
            # text instance (common with small caps, mixed font sizes, or styled text),
            # merge horizontally-adjacent rects on the same line into one combined rect.
            # Without this, each span rect would trigger a separate full replacement.
            #
            # Implementation note: small-caps text produces rects that interleave at TWO
            # slightly different y0 positions (e.g., large-caps glyphs at y0=743.52 and
            # small-caps glyphs at y0=745.98).  If we sort by (y0, x0), all large-caps
            # rects come before all small-caps rects, creating artificial 34-pt gaps that
            # the adjacency check cannot bridge.  The fix is to group by VISUAL LINE first
            # (rects whose y-ranges overlap or are within ½ line-height of each other),
            # then sort within each visual line by x0.  This interleaves the two glyph
            # series correctly and allows the adjacency check to work.
            needs_fragment_consolidation = any(ch.isspace() for ch in target_text.strip())

            if needs_fragment_consolidation and len(all_rects) > 1:
                # ── Step 1: group rects into visual lines ──────────────────────────
                # Sort by y0 to walk top-to-bottom.
                by_y0 = sorted(all_rects, key=lambda r: r.y0)
                vline_groups = []
                vline_cur = [by_y0[0]]
                vline_y1  = by_y0[0].y1

                for r in by_y0[1:]:
                    line_h = max(r.height, vline_cur[0].height)
                    # Belongs to same visual line if it starts before the current
                    # group's bottom edge + ½ line height (handles rects at two
                    # closely-spaced y-positions as well as tight line spacing).
                    if r.y0 < vline_y1 + line_h * 0.5:
                        vline_cur.append(r)
                        vline_y1 = max(vline_y1, r.y1)
                    else:
                        vline_groups.append(vline_cur)
                        vline_cur = [r]
                        vline_y1 = r.y1
                vline_groups.append(vline_cur)

                # ── Step 2: within each visual line, sort by x0 and merge ─────────
                consolidated = []
                for vline in vline_groups:
                    vline_sorted = sorted(vline, key=lambda r: r.x0)
                    current_group = [vline_sorted[0]]

                    for rect_c in vline_sorted[1:]:
                        prev_rect = current_group[-1]
                        # Same line: vertical centers within half a line height
                        same_line = (abs(rect_c.y0 - prev_rect.y0) <
                                     max(prev_rect.height, rect_c.height) * 0.5)
                        # Horizontally adjacent: gap less than 0.5x line height.
                        # Use the group's combined right edge (not just the last
                        # rect's x1) so that an earlier wide rect keeps subsequent
                        # rects within its span adjacent to the group.
                        group_x1  = max(r.x1 for r in current_group)
                        h_gap     = rect_c.x0 - group_x1
                        adjacent  = h_gap < max(prev_rect.height, rect_c.height) * 0.5

                        if same_line and adjacent:
                            current_group.append(rect_c)
                        else:
                            if len(current_group) > 1:
                                consolidated.append(fitz.Rect(
                                    min(r.x0 for r in current_group),
                                    min(r.y0 for r in current_group),
                                    max(r.x1 for r in current_group),
                                    max(r.y1 for r in current_group)
                                ))
                            else:
                                consolidated.extend(current_group)
                            current_group = [rect_c]

                    # Flush final group for this visual line
                    if len(current_group) > 1:
                        consolidated.append(fitz.Rect(
                            min(r.x0 for r in current_group),
                            min(r.y0 for r in current_group),
                            max(r.x1 for r in current_group),
                            max(r.y1 for r in current_group)
                        ))
                    else:
                        consolidated.extend(current_group)

                if len(consolidated) < len(all_rects):
                    debug_log.append(f"Same-line consolidation: {len(all_rects)} rects → {len(consolidated)} instances")
                    all_rects = consolidated

            # CROSS-LINE CONSOLIDATION: When search_for() finds a text phrase
            # that wraps across two lines it returns one rect *per line fragment*
            # instead of one rect for the whole match.  Without this pass every
            # fragment would independently receive the full replacement text,
            # producing duplicate / garbled output.
            #
            # A cross-line pair is detected when:
            #   1. Two consecutive rects (sorted by y0) are on adjacent lines
            #      — the vertical gap between them is ≤ 1.5× the line height.
            #   2. The second rect starts further LEFT than the first by at
            #      least one line-height worth of space — the classic "the text
            #      ran to the end of line N and wrapped to the left margin of
            #      line N+1" pattern.
            #
            # When a pair is found ONLY THE FIRST rect is kept for replacement.
            # The second (continuation) rect is dropped.  Merging both into one
            # tall rect is avoided because _get_line_structure() uses the rect
            # height to compute vertical-tolerance, and a double-height rect
            # triggers a strict tolerance that misses both original lines.
            if needs_fragment_consolidation and len(all_rects) > 1:
                sorted_rects = sorted(all_rects, key=lambda r: r.y0)
                merged = []
                i = 0
                while i < len(sorted_rects):
                    rect = sorted_rects[i]
                    if i + 1 < len(sorted_rects):
                        next_rect = sorted_rects[i + 1]
                        y_gap = next_rect.y0 - rect.y1
                        line_height = max(rect.height, next_rect.height)
                        # Adjacent lines AND next rect's left edge is
                        # significantly more to the left (line-wrap signature).
                        # Require y_gap >= 0: overlapping rects (same visual line
                        # with different y0 heights) must NOT be treated as a
                        # cross-line pair — they should have been merged by the
                        # same-line consolidation pass above.
                        if (y_gap >= 0 and y_gap <= line_height * 1.5 and
                                next_rect.x0 < rect.x0 - line_height):
                            # Keep the first fragment (line-end portion) and
                            # drop the second (line-start continuation).
                            merged.append(rect)
                            i += 2  # consume both, but only keep first
                            continue
                    merged.append(rect)
                    i += 1
                if len(merged) < len(all_rects):
                    debug_log.append(
                        f"Cross-line consolidation: {len(all_rects)} rects → {len(merged)} instances"
                    )
                    all_rects = merged

            debug_log.append(f"Found {len(all_rects)} instances of target text length={len(target_text)}")
            if occurrence_index is not None:
                debug_log.append(f"occurrence_index={occurrence_index}: targeting instance {occurrence_index+1} of {len(all_rects)}")
            success_count = 0

            # Single loop over all instances found
            for inst_idx, rect in enumerate(all_rects):
                if occurrence_index is not None and inst_idx != occurrence_index:
                    debug_log.append(f"Skipping instance {inst_idx+1} (occurrence_index={occurrence_index})")
                    continue
                debug_log.append(f"\n--- Instance {inst_idx+1}/{len(all_rects)} ---")
                
                # --- OPTICAL VERIFICATION PREP ---
                # Capture 'before' snapshot of the area we are about to touch
                # Estimate the region based on target text rect
                # This is imperfect because we don't know the full extent of the NEW text yet,
                # but we can guess it won't be massively larger than 2x original width usually.
                verify_rect_est = rect + (-20, -10, rect.width * 2 + 20, 10)
                verify_rect_est = verify_rect_est & page.rect
                _pix_zoom = 2.0
                try:
                    before_pix = _get_cached_pixmap(
                        input_path, page_number - 1, verify_rect_est, _pix_zoom)
                    if before_pix is None:
                        before_pix = optical.capture_region(
                            page, verify_rect_est, zoom=_pix_zoom)
                        if before_pix is not None:
                            _store_cached_pixmap(
                                input_path, page_number - 1, verify_rect_est, _pix_zoom,
                                before_pix)
                except Exception as e:
                    debug_log.append(f"Optical capture failed: {e}")
                    before_pix = None
                
                font_info = _get_span_font_info(page, target_text, rect)

                # Font Detection
                repl_font, use_internal_fontname, smart_reuse_buffer = None, None, None
                matched_system_font_path = None
                using_matched_system_font = False  # Track whether we found a matching font

                if manual_overrides and manual_overrides.get('manual_font'):
                    m_font = manual_overrides['manual_font']
                    font_path, ps_name = m_font.split("|", 1) if "|" in m_font else (m_font, None)
                    if font_path in {"helv", "tiro", "cour", "symb", "zadb"}:
                        use_internal_fontname = font_path
                    elif font_path == "internal" or "marcedit_preview" in font_path:
                        if os.path.exists(font_path):
                            try: repl_font = _get_cached_font(font_path)
                            except Exception as e:
                                print(f"[WARNING] Failed to load manual font: {type(e).__name__}", file=sys.stderr)
                        if not repl_font:
                            internal_font_name, _, reuse_buffer = _find_internal_font_name(doc, page, font_info['fontname'], replacement_text, target_text)
                            if internal_font_name:
                                use_internal_fontname, smart_reuse_buffer = internal_font_name, reuse_buffer
                            else:
                                system_font_path = _find_system_font(font_info['fontname'], flags=font_info.get('flags'))
                        if system_font_path:
                            try:
                                subset_data = subset_font_from_path(system_font_path, replacement_text, ps_name=font_info.get('fontname', ''))
                                repl_font = fitz.Font(fontbuffer=subset_data)
                                matched_system_font_path = system_font_path
                            except Exception as e:
                                print(f"[WARNING] Font subsetting failed: {e}", file=sys.stderr)
                    elif os.path.exists(font_path):
                        try:
                            repl_font = _get_cached_font(font_path)
                            matched_system_font_path = font_path
                        except Exception as e:
                            print(f"[WARNING] Font loading exception: {e}", file=sys.stderr)
                    else:
                        try: repl_font = fitz.Font(m_font)
                        except Exception as e:
                            print(f"[WARNING] Font loading exception: {e}", file=sys.stderr)
                else:
                    # Auto Font - HYBRID APPROACH for best quality
                    # Priority order:
                    # 1. Standard PDF fonts → use PyMuPDF built-in (pixel-perfect match)
                    # 2. Embedded font with full coverage → reuse buffer (exact same font)
                    # 3. System font for non-standard fonts → TrueType from system
                    # 4. Synthesis for custom fonts → harvest glyphs from PDF
                    # 5. Visual matcher → find closest system font
                    # 6. Fallback → built-in font as last resort

                    # Step 1: Check if it's a standard PDF font (Helvetica, Times, Courier, etc.)
                    is_standard, builtin_name = _is_standard_pdf_font(
                        font_info['fontname'], flags=font_info.get('flags')
                    )

                    if is_standard and builtin_name:
                        # Use PyMuPDF built-in font for pixel-perfect match
                        use_internal_fontname = builtin_name
                        using_matched_system_font = True  # Built-in fonts match original metrics
                        debug_log.append(f"Using built-in font '{builtin_name}' for standard font '{font_info['fontname']}'")
                    else:
                        # Step 2: Try to reuse embedded font buffer
                        internal_font_name, _, reuse_buffer = _find_internal_font_name(
                            doc, page, font_info['fontname'], replacement_text, target_text
                        )
                        if reuse_buffer:
                            import binascii
                            use_internal_fontname = f"subset_{binascii.hexlify(os.urandom(4)).decode()}"
                            smart_reuse_buffer = reuse_buffer
                            try:
                                repl_font = fitz.Font(fontbuffer=reuse_buffer)
                                using_matched_system_font = True  # Reused font matches original
                                debug_log.append(f"Reusing embedded font buffer")
                            except Exception:
                                pass

                    # Step 3: If not standard and no embedded font, try system fonts
                    if not use_internal_fontname and not repl_font:
                        system_font_found = False
                        for finder in [_find_system_font, _find_bundled_font]:
                            p = finder(font_info['fontname'], flags=font_info.get('flags')) if finder == _find_system_font else finder(font_info['fontname'])
                            if p:
                                try:
                                    subset_data = subset_font_from_path(p, replacement_text, ps_name=font_info.get('fontname', ''))
                                    repl_font = fitz.Font(fontbuffer=subset_data)
                                    matched_system_font_path = p
                                    system_font_found = True
                                    using_matched_system_font = True
                                    debug_log.append(f"Using system font: {p}")
                                    break
                                except Exception as e:
                                    debug_log.append(f"System font subset failed: {e}")

                        # Step 4: If no system font, try synthesis for custom/embedded fonts
                        if not system_font_found and not repl_font:
                            synthesis_viable, synthesis_coverage = _check_synthesis_feasibility(
                                doc, page, font_info['fontname'], replacement_text
                            )

                            if synthesis_viable:
                                font_info['use_synthesis_mode'] = True
                                font_info['synthesis_coverage'] = synthesis_coverage
                                font_info['original_fontname'] = font_info.get('fontname', '')
                                debug_log.append(f"Synthesis viable ({synthesis_coverage*100:.0f}% coverage) - using for custom font")
                    
                    if (not use_internal_fontname and not repl_font and not font_info.get('use_synthesis_mode')
                            and not (manual_overrides and manual_overrides.get('skip_visual_matching'))):
                        try:
                            from .visual_matcher import find_matching_font
                            mp, mn, ms = find_matching_font(page, target_text, font_info['fontname'], exhaustive=manual_overrides.get('exhaustive_search') if manual_overrides else False, src_is_serif=(font_info['flags']&4)!=0 if font_info.get('flags') else None)

                            # DIAGNOSTIC: Log visual matcher results
                            import sys
                            print(f"[DIAGNOSTIC] Visual matcher: score={ms:.3f}, font='{mn}', hasPath={bool(mp)}", file=sys.stderr)

                            # PHASE 4 FIX: Raised threshold from 0.50 to 0.65 for better quality
                            if mp and ms > 0.65:
                                try:
                                    subset_data = subset_font_from_path(mp, replacement_text, ps_name=mn)
                                    repl_font = fitz.Font(fontbuffer=subset_data)
                                    matched_system_font_path = mp
                                    print(f"[DIAGNOSTIC] Using visual match: {mn} (score: {ms:.3f})", file=sys.stderr)
                                except Exception:
                                    repl_font = _get_cached_font(mp)
                                    matched_system_font_path = mp
                        except Exception as e:
                            print(f"[WARNING] Font loading exception: {e}", file=sys.stderr)
                    
                    if not use_internal_fontname and not repl_font and not font_info.get('use_synthesis_mode'):
                        use_internal_fontname = _map_to_builtin_font(font_info['fontname'])

                # Scaling
                adjusted_fontsize = font_info['fontsize']

                # FONT SCALING FIX: Skip scaling when using matched system font
                # When _find_system_font successfully finds the original font (e.g., Helvetica.ttc
                # for Helvetica-Bold), we should use the original fontsize without scaling.
                # The fonts have identical metrics, so no adjustment needed.
                # Only apply scaling when using a DIFFERENT font (visual match, synthesis, etc.)

                if using_matched_system_font:
                    # System font matches original - use original fontsize directly
                    debug_log.append(f"Using matched system font, skipping scaling (fontsize={adjusted_fontsize})")
                else:
                    # Different font - apply scaling to match visual appearance
                    try:
                        ref_text = font_info.get('span_text', '') or target_text
                        ref_char_data = _get_reference_char_metrics(page, rect, ref_text)
                        if ref_char_data and repl_font and not isinstance(repl_font, dict):
                            ref_char, ref_w_orig, ref_h_orig = ref_char_data
                            repl_metrics = _measure_glyph_visual_metrics(repl_font, ref_char)
                            if repl_metrics:
                                repl_w, repl_h = repl_metrics
                                is_cap_char = ref_char.isupper() and ref_char in "MHZITN"
                                ref_h_normalized = ref_h_orig / 1.25 if is_cap_char else ref_h_orig
                                nom_h = repl_h * font_info['fontsize']

                                if nom_h > 0:
                                    scale_factor = ref_h_normalized / nom_h
                                    scale_factor = min(max(scale_factor, 0.75), 1.35)
                                    if scale_factor < 0.8 or scale_factor > 1.2:
                                        debug_log.append(f"Font scaling: {scale_factor:.2f}x (reference height: {ref_h_orig:.2f})")
                                    adjusted_fontsize *= scale_factor
                    except Exception as e:
                        debug_log.append(f"Font scaling failed: {e}")

                if manual_overrides and manual_overrides.get('manual_size_delta'):
                    adjusted_fontsize += float(manual_overrides['manual_size_delta'])

                tracking_delta = float(manual_overrides.get('manual_tracking_delta', 0)) if manual_overrides else 0

                # Register font on page for ALL insertion paths (multiline, reflow, legacy)
                # Previously, font was only registered in the legacy path, causing
                # reflow/multiline to use an unregistered fontname and silently fall back
                # to Helvetica with wrong metrics.
                if use_internal_fontname and smart_reuse_buffer:
                    try:
                        page.insert_font(fontname=use_internal_fontname, fontbuffer=smart_reuse_buffer)
                        debug_log.append(f"Pre-registered embedded font: {use_internal_fontname}")
                    except Exception as e:
                        debug_log.append(f"Font pre-registration failed: {e}")
                elif not use_internal_fontname and repl_font and hasattr(repl_font, 'buffer'):
                    try:
                        page.insert_font(fontname="R0", fontbuffer=repl_font.buffer)
                        debug_log.append(f"Pre-registered replacement font as R0")
                    except Exception as e:
                        debug_log.append(f"Font pre-registration failed: {e}")

                # Redaction & Expansion
                redact_fill = _parse_palette_color(manual_overrides['fill_color'].lower()) if manual_overrides and manual_overrides.get('fill_color') else None
                
                # Capture 'before' snapshot again if needed? 
                # (Logic merged from previous inner loop)
                # Removed redundant instance logging and optical prep
                
                try:
                    # --- MULTI-LINE DETECTION ---
                    # Check if target or replacement contains newlines
                    is_multiline = '\n' in target_text or '\n' in replacement_text
                    multiline_success = False
                    multiline_rect = None
                    reflow_rect = None

                    if is_multiline:
                        debug_log.append("Multi-line text detected - using multi-line handler")
                        try:
                            multiline_success, multiline_rect = _handle_multiline_replacement(
                                page, target_text, replacement_text, rect, font_info,
                                repl_font, use_internal_fontname, adjusted_fontsize,
                                debug_log, manual_overrides
                            )
                            if multiline_success:
                                reflow_rect = multiline_rect
                                debug_log.append("Multi-line replacement successful!")
                        except Exception as e:
                            debug_log.append(f"Multi-line handler exception: {e}")
                            multiline_success = False

                    # --- REFLOW ENGINE ATTEMPT (single-line only) ---
                    reflow_success = False
                    reflow_attempted = False  # tracks whether reflow ran (and may have modified the page)

                    if not is_multiline and not multiline_success:
                        r_fontname = use_internal_fontname if use_internal_fontname else "R0"
                        # Use original text color for visual consistency
                        r_color = font_info.get('color', (0, 0, 0))

                        # DIAGNOSTIC: Log reflow parameters
                        import sys
                        print(f"[DIAGNOSTIC] Reflow: color={r_color}, fontsize={adjusted_fontsize:.1f}, fontname={r_fontname}", file=sys.stderr)

                        try:
                            # Font already pre-registered before branching

                            r_info = {
                                'fontname': r_fontname,
                                'fontsize': adjusted_fontsize,
                                'color': r_color,
                                'use_synthesis_mode': font_info.get('use_synthesis_mode', False),
                                'original_fontname': font_info.get('original_fontname', font_info.get('fontname', '')),
                            }
                            if matched_system_font_path:
                                r_info['fontfile'] = matched_system_font_path
                            # Forward user-specified fill_color so reflow can use it as
                            # the redaction fill instead of (or overriding) the sampled bg.
                            if manual_overrides and manual_overrides.get('fill_color'):
                                parsed_bg = _parse_palette_color(manual_overrides['fill_color'].lower())
                                if parsed_bg:
                                    r_info['bg_fill'] = parsed_bg
                            if manual_overrides and manual_overrides.get('justification'):
                                r_info['justification'] = manual_overrides['justification']

                            debug_log.append(f"Attempting Reflow on {rect}...")
                            reflow_attempted = True  # reflow will apply its own redaction before returning
                            r_success, r_rect = reflow.reflow_line(page, rect, replacement_text, r_info, debug_log, font_buffer=repl_font.buffer if hasattr(repl_font, 'buffer') else None)
                            if r_success:
                                reflow_success = True
                                reflow_rect = r_rect
                                debug_log.append("Reflow Success!")
                            else:
                                debug_log.append("Reflow Failed (returned False)")
                        except Exception as e:
                            debug_log.append(f"Reflow Exception: {e}")
                    
                    # --- FALLBACK: LEGACY LOGIC ---
                    if not reflow_success and not multiline_success:
                        debug_log.append("Falling back to Legacy Insertion...")

                        # Calculate precise redaction rect to prevent blooming/artifacts
                        precise_rect = _calculate_precise_redaction_rect(page, rect, target_text)
                        debug_log.append(f"Precise redaction rect: {precise_rect} (original: {rect})")

                        # REDACTION - When reflow was attempted, it already applied its own redaction
                        # using PDF_REDACT_LINE_ART_NONE (preserving vector graphics).
                        # In that case we must NOT use PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED for the
                        # second redaction pass — doing so would remove vector border lines that reflow
                        # intentionally preserved, causing a visible regression.
                        # Only use REMOVE_IF_TOUCHED for fresh legacy runs (no prior reflow redaction).
                        legacy_graphics_mode = (
                            fitz.PDF_REDACT_LINE_ART_NONE
                            if reflow_attempted
                            else fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
                        )
                        page.add_redact_annot(precise_rect, fill=redact_fill)
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=legacy_graphics_mode)
                        debug_log.append(f"Legacy redaction: graphics_mode={'LINE_ART_NONE (reflow-safe)' if reflow_attempted else 'LINE_ART_REMOVE_IF_TOUCHED'}")
                        
                        # CALC POSITION - Use proper baseline positioning
                        # First, determine alignment from manual override or auto-detect
                        if manual_overrides and manual_overrides.get('justification'):
                            legacy_alignment = manual_overrides['justification']
                            debug_log.append(f"Legacy: Using manual alignment: {legacy_alignment}")
                        else:
                            legacy_alignment = _detect_justification(page, rect)
                            debug_log.append(f"Legacy: Auto-detected alignment: {legacy_alignment}")

                        # Calculate text width for alignment
                        try:
                            # Use actual font for width estimation when available
                            _est_fontname = use_internal_fontname or fallback_fontname or "helv"
                            legacy_font = fitz.Font(_est_fontname)
                            legacy_text_width = legacy_font.text_length(replacement_text, fontsize=adjusted_fontsize)
                        except Exception:
                            try:
                                legacy_font = fitz.Font("helv")
                                legacy_text_width = legacy_font.text_length(replacement_text, fontsize=adjusted_fontsize)
                            except Exception:
                                legacy_text_width = len(replacement_text) * adjusted_fontsize * 0.5

                        # Calculate ins_x based on alignment
                        if legacy_alignment == "center":
                            original_center = (rect.x0 + rect.x1) / 2
                            ins_x = original_center - (legacy_text_width / 2)
                            debug_log.append(f"Legacy: Center-aligned at x={ins_x:.2f}")
                        elif legacy_alignment == "right":
                            ins_x = rect.x1 - legacy_text_width
                            debug_log.append(f"Legacy: Right-aligned at x={ins_x:.2f}")
                        elif legacy_alignment == "justified":
                            ins_x = rect.x0
                            debug_log.append(f"Legacy: Justified at x={ins_x:.2f}")
                        else:  # "left"
                            ins_x = rect.x0
                            debug_log.append(f"Legacy: Left-aligned at x={ins_x:.2f}")

                        # CRITICAL: Use actual baseline, not rect bottom
                        # rect.y1 is the bottom of the bounding box, not the baseline
                        # For text with descenders (g, j, p, q, y), the baseline is ABOVE rect.y1
                        origin = font_info.get('origin')
                        if origin and len(origin) >= 2 and origin[1] is not None:
                            # Use the actual baseline from the original text
                            ins_y = origin[1]
                            debug_log.append(f"Using actual baseline: {ins_y:.2f}")
                        else:
                            # Fallback: Estimate baseline from rect
                            # For text with descenders, baseline is typically 85% down from rect top
                            # For text without descenders, baseline is ~90% down
                            # We use a conservative estimate that works for both
                            rect_height = rect.y1 - rect.y0
                            ins_y = rect.y0 + rect_height * 0.85  # 85% down from top (NOT y1 + offset!)
                            debug_log.append(f"Using estimated baseline: {ins_y:.2f} (rect.y0: {rect.y0:.2f}, rect.y1: {rect.y1:.2f})")

                        if manual_overrides:
                            ins_x += float(manual_overrides.get('manual_x_offset', 0))
                            ins_y += float(manual_overrides.get('manual_y_offset', 0))

                        # Extract style flags from manual_overrides or font_info
                        # Priority: manual_overrides > font_info flags
                        is_bold = False
                        is_italic = False
                        has_underline = False
                        has_strikethrough = False

                        if manual_overrides:
                            # Check manual overrides first (user-specified style)
                            if manual_overrides.get('is_bold'):
                                is_bold = True
                                debug_log.append("Using manual bold override")
                            if manual_overrides.get('is_italic'):
                                is_italic = True
                                debug_log.append("Using manual italic override")
                            if manual_overrides.get('underline'):
                                has_underline = True
                                debug_log.append("Using manual underline override")
                            if manual_overrides.get('strikethrough'):
                                has_strikethrough = True
                                debug_log.append("Using manual strikethrough override")

                        # If no manual override, check font_info flags and detect decorations
                        if not (is_bold or is_italic or has_underline or has_strikethrough):
                            if font_info.get('flags'):
                                flags = font_info['flags']
                                # bit 1 (2): Italic, bit 4 (16): Bold, bit 0 (1): Superscript
                                if flags & 2:
                                    is_italic = True
                                    debug_log.append("Detected italic from font flags")
                                if flags & 16:
                                    is_bold = True
                                    debug_log.append("Detected bold from font flags")

                            # Detect text decorations (underline, strikethrough) from drawing operations
                            decorations = _detect_text_decorations(page, rect)
                            if decorations.get('detected'):
                                if decorations.get('underline'):
                                    has_underline = True
                                    debug_log.append("Detected underline from drawing operations")
                                if decorations.get('strikethrough'):
                                    has_strikethrough = True
                                    debug_log.append("Detected strikethrough from drawing operations")

                        # INSERTION
                        # Preserve original color unless force_black_text override is set
                        if manual_overrides and manual_overrides.get('force_black_text'):
                            color = (0, 0, 0)
                        else:
                            color = font_info.get('color', (0, 0, 0))

                        # DIAGNOSTIC: Log insertion parameters
                        import sys
                        print(f"[DIAGNOSTIC] Legacy insert_text: color={color}, fontsize={adjusted_fontsize:.1f}, fontname={use_internal_fontname or 'R0'}", file=sys.stderr)

                        if use_internal_fontname:
                            try:
                                page.insert_font(fontname=use_internal_fontname, fontbuffer=smart_reuse_buffer)
                            except Exception as e:
                                print(f"[WARNING] Font loading exception: {e}", file=sys.stderr)
                            if legacy_alignment == "justified":
                                _insert_justified_text(
                                    page, (ins_x, ins_y), replacement_text,
                                    fontname=use_internal_fontname, fontsize=adjusted_fontsize,
                                    color=color, available_width=rect.width,
                                    debug_log=debug_log
                                )
                            elif tracking_delta:
                                _insert_tracked_text(
                                    page, (ins_x, ins_y), replacement_text,
                                    fontname=use_internal_fontname, fontsize=adjusted_fontsize,
                                    color=color, tracking_delta=tracking_delta,
                                    debug_log=debug_log
                                )
                            else:
                                page.insert_text((ins_x, ins_y), replacement_text, fontname=use_internal_fontname, fontsize=adjusted_fontsize, color=color)
                        else:
                            # Select styled built-in font based on detected weight/style
                            fallback_fontname = _get_base14_fontname(
                                font_info.get('fontname', 'Helvetica'),
                                is_bold=is_bold,
                                is_italic=is_italic
                            )
                            # Try custom font buffer first
                            if repl_font and hasattr(repl_font, 'buffer'):
                                try:
                                    page.insert_font(fontname="R0", fontbuffer=repl_font.buffer)
                                    if legacy_alignment == "justified":
                                        _insert_justified_text(
                                            page, (ins_x, ins_y), replacement_text,
                                            fontname="R0", fontsize=adjusted_fontsize,
                                            color=color, available_width=rect.width,
                                            debug_log=debug_log
                                        )
                                    elif tracking_delta:
                                        _insert_tracked_text(
                                            page, (ins_x, ins_y), replacement_text,
                                            fontname="R0", fontsize=adjusted_fontsize,
                                            color=color, tracking_delta=tracking_delta,
                                            debug_log=debug_log
                                        )
                                    else:
                                        page.insert_text((ins_x, ins_y), replacement_text, fontname="R0", fontsize=adjusted_fontsize, color=color)
                                except Exception:
                                    if legacy_alignment == "justified":
                                        _insert_justified_text(
                                            page, (ins_x, ins_y), replacement_text,
                                            fontname=fallback_fontname, fontsize=adjusted_fontsize,
                                            color=color, available_width=rect.width,
                                            debug_log=debug_log
                                        )
                                    elif tracking_delta:
                                        _insert_tracked_text(
                                            page, (ins_x, ins_y), replacement_text,
                                            fontname=fallback_fontname, fontsize=adjusted_fontsize,
                                            color=color, tracking_delta=tracking_delta,
                                            debug_log=debug_log
                                        )
                                    else:
                                        page.insert_text((ins_x, ins_y), replacement_text, fontname=fallback_fontname, fontsize=adjusted_fontsize, color=color)
                            else:
                                if legacy_alignment == "justified":
                                    _insert_justified_text(
                                        page, (ins_x, ins_y), replacement_text,
                                        fontname=fallback_fontname, fontsize=adjusted_fontsize,
                                        color=color, available_width=rect.width,
                                        debug_log=debug_log
                                    )
                                elif tracking_delta:
                                    _insert_tracked_text(
                                        page, (ins_x, ins_y), replacement_text,
                                        fontname=fallback_fontname, fontsize=adjusted_fontsize,
                                        color=color, tracking_delta=tracking_delta,
                                        debug_log=debug_log
                                    )
                                else:
                                    page.insert_text((ins_x, ins_y), replacement_text, fontname=fallback_fontname, fontsize=adjusted_fontsize, color=color)

                        # Apply style simulation after text insertion
                        # This is critical for preserving bold/italic/decorations when the replacement font
                        # doesn't have native variants or when decorations need to be redrawn
                        if is_bold:
                            try:
                                # Calculate stroke width based on font size (typically 2-3% of font size)
                                stroke_width = max(0.2, adjusted_fontsize * 0.025)
                                _inject_simulated_bold(page, stroke_width=stroke_width)
                                debug_log.append(f"Applied simulated bold (stroke_width={stroke_width:.2f})")
                            except Exception as e:
                                debug_log.append(f"Failed to apply simulated bold: {e}")

                        if is_italic:
                            try:
                                # For italic, we need to apply a transformation matrix to skew the text
                                # This is a bit tricky in PyMuPDF, so we'll use a content stream hack
                                # Get the last text insertion and apply an italic transform
                                _inject_simulated_italic(page)
                                debug_log.append("Applied simulated italic")
                            except Exception as e:
                                debug_log.append(f"Failed to apply simulated italic: {e}")

                        # Apply text decorations (underline, strikethrough)
                        # These need to be drawn after text insertion so they appear on top
                        if has_underline:
                            try:
                                # Measure actual text width for decoration positioning
                                try:
                                    _dec_font = fitz.Font(use_internal_fontname or fallback_fontname or "helv")
                                    _dec_width = _dec_font.text_length(replacement_text, fontsize=adjusted_fontsize)
                                except Exception:
                                    _dec_width = len(replacement_text) * adjusted_fontsize * 0.5
                                text_rect = fitz.Rect(ins_x, rect.y0, ins_x + _dec_width, rect.y1)
                                _inject_text_underline(page, text_rect, color=color)
                                debug_log.append("Applied underline decoration")
                            except Exception as e:
                                debug_log.append(f"Failed to apply underline: {e}")

                        if has_strikethrough:
                            try:
                                # Measure actual text width for decoration positioning
                                try:
                                    _dec_font = fitz.Font(use_internal_fontname or fallback_fontname or "helv")
                                    _dec_width = _dec_font.text_length(replacement_text, fontsize=adjusted_fontsize)
                                except Exception:
                                    _dec_width = len(replacement_text) * adjusted_fontsize * 0.5
                                text_rect = fitz.Rect(ins_x, rect.y0, ins_x + _dec_width, rect.y1)
                                _inject_text_strikethrough(page, text_rect, color=color)
                                debug_log.append("Applied strikethrough decoration")
                            except Exception as e:
                                debug_log.append(f"Failed to apply strikethrough: {e}")
                    
                    # --- OPTICAL VERIFICATION ---
                    if 'before_pix' in locals() and before_pix:
                        try:
                            # Re-capture 'after' state
                            after_pix = optical.capture_region(page, verify_rect_est)

                            # BUG #58 FIX: Clear deletion detection logic
                            # Explicit check for empty replacement (full deletion)
                            # or replacement much shorter than original (>80% reduction)
                            replacement_stripped = replacement_text.strip()
                            target_stripped = target_text.strip()

                            is_full_deletion = len(replacement_stripped) == 0
                            is_deletion = is_full_deletion or (len(replacement_stripped) < len(target_stripped) * 0.2)

                            if is_deletion:
                                deletion_type = "full" if is_full_deletion else "partial"
                                debug_log.append(f"{deletion_type.capitalize()} deletion detected (replacement {len(replacement_text)} chars vs original {len(target_text)} chars) - relaxing collision detection")

                            # Calculate exclusion rect
                            zoom = 2.0
                            # Use multiline_rect if available, otherwise reflow_rect, otherwise rect
                            if multiline_success and multiline_rect is not None:
                                target_excl = multiline_rect
                            elif reflow_success and reflow_rect is not None:
                                target_excl = reflow_rect
                            else:
                                target_excl = rect

                            # For deletions, expand exclusion rect to be more generous
                            if is_deletion:
                                # Expand by 50% on all sides for deletions
                                expansion = target_excl.width * 0.5
                                target_excl = target_excl + (-expansion, -expansion, expansion, expansion)

                            rel_x0 = (target_excl.x0 - verify_rect_est.x0) * zoom
                            rel_y0 = (target_excl.y0 - verify_rect_est.y0) * zoom
                            rel_x1 = (target_excl.x1 - verify_rect_est.x0) * zoom
                            rel_y1 = (target_excl.y1 - verify_rect_est.y0) * zoom
                            excl_rect = fitz.Rect(rel_x0, rel_y0, rel_x1, rel_y1)

                            if skip_collision:
                                has_collision = False
                                msg = "Collision check skipped (user allowed overrun)"
                                debug_log.append(msg)
                            else:
                                has_collision, msg = optical.detect_visual_collision(
                                    before_pix, after_pix,
                                    exclusion_rect=excl_rect,
                                    allow_warning=True       # Allow moderate collisions (5-15%) - common in dense layouts
                                )

                            # GHOST EDIT HANDLING: Some edits legitimately produce minimal visual changes
                            # and should not be flagged as failures:
                            # 1. Identity edits: replacing text with itself
                            # 2. Shrink edits where replacement is a prefix of original (e.g., "Philadelphia" → "Phila")
                            # 3. Same-start edits where both texts start the same way
                            # In these cases, the visual pixels overlap significantly and diff detection fails

                            is_identity_edit = target_text.strip() == replacement_text.strip()
                            is_prefix_shrink = (
                                target_text.strip().startswith(replacement_text.strip()) or
                                replacement_text.strip().startswith(target_text.strip())
                            )
                            # Also allow if reflow reported success (trust the lower-level operation)
                            reflow_confirmed = reflow_success or multiline_success

                            if "Ghost Edit" in msg and (is_identity_edit or is_prefix_shrink or reflow_confirmed):
                                if is_identity_edit:
                                    debug_log.append(f"Identity edit detected - 'Ghost Edit' is expected behavior")
                                elif is_prefix_shrink:
                                    debug_log.append(f"Prefix shrink detected - 'Ghost Edit' acceptable for overlapping text")
                                else:
                                    debug_log.append(f"Reflow succeeded - trusting result despite Ghost Edit detection")
                                has_collision = False

                            # REFLOW TRUST: For edits where reflow succeeded, trust the operation
                            # even if optical collision is detected. Reflow has already handled
                            # the layout properly, and collision detection can have false positives
                            # when dealing with font substitution, shrink operations, or tight layouts.
                            if has_collision and reflow_confirmed:
                                if is_identity_edit:
                                    debug_log.append(f"Identity edit with reflow success - trusting result despite collision ({msg})")
                                elif is_prefix_shrink:
                                    debug_log.append(f"Shrink edit with reflow success - trusting result despite collision ({msg})")
                                else:
                                    debug_log.append(f"Edit with reflow success - trusting result despite collision ({msg})")
                                has_collision = False

                            if has_collision:
                                 debug_log.append(f"Visual Verification FAILED: {msg}")
                                 return {'success': False, 'message': f"Visual Collision: {msg}", 'debug_log': debug_log}
                            else:
                                 debug_log.append(f"Visual Verification PASSED")
                                 
                        except Exception as e:
                            debug_log.append(f"Visual Verify Exception: {e}")
                            
                    success_count += 1
                except Exception as e:
                    debug_log.append(f"Err: {e}")

            if success_count > 0:
                doc.save(output_path, garbage=4, deflate=True, clean=True)
                # Invalidate any cached before-state pixmaps for output_path: the
                # file content has just changed so stale entries must not be reused.
                _invalidate_file_pixmaps(output_path)
                return {'success': True, 'modified': True, 'count': success_count, 'debug_log': debug_log}
            else:
                return {'success': False, 'message': "No occurrences found or all failed.", 'debug_log': debug_log}
    except Exception as e:
        import traceback
        debug_log.append(traceback.format_exc())
        return {'success': False, 'message': str(e), 'debug_log': debug_log}


def _extract_font_to_temp(doc, page, font_name: str) -> str | None:
    """
    Extract the embedded font matching font_name to a temporary file.
    Returns the path to the temporary file, or None if failed.
    """
    try:
        import tempfile
        
        # Normalize target name (remove subset prefix like BLUVWU+)
        target_clean = font_name.split('+')[-1].lower() if '+' in font_name else font_name.lower()
        
        # First pass: Look for EXACT match only (prevents BoldItalic matching when Regular wanted)
        for f in page.get_fonts():
            xref, ext, type_, basefont, internal_name, enc = f
            base_clean = basefont.split('+')[-1].lower() if '+' in basefont else basefont.lower()
            
            # EXACT match only
            if base_clean == target_clean:
                font_data = doc.extract_font(xref)
                
                if font_data and len(font_data) >= 4 and font_data[3]:
                    ext_str = ext if ext else "ttf"
                    if ext_str == "n/a" or not ext_str: ext_str = "ttf"
                    # Security: strip non-alphanumeric chars to prevent path traversal
                    ext_str = (''.join(c for c in ext_str if c.isalnum()) or "ttf")[:10]

                    _fd, path = tempfile.mkstemp(suffix=f".{ext_str}", prefix="marcedit_preview_")
                    os.close(_fd)
                    with open(path, "wb") as f_out:
                        f_out.write(font_data[3])

                    _temp_preview_fonts.add(path)
                    print(f"[FontExtract] Exact match: '{basefont}' (xref={xref})")
                    return path
        
        # Second pass: If no exact match, try substring (for cases like "TimesNewRoman" matching "TimesNewRoman-Regular")
        # Comprehensive list of font style/weight markers to exclude from fuzzy matching
        STYLE_MARKERS = [
            # Weight variations
            ',bold', '-bold', 'bold',
            ',light', '-light', 'light',
            ',medium', '-medium', 'medium',
            ',heavy', '-heavy', 'heavy', 
            ',black', '-black', 'black',
            ',thin', '-thin', 'thin',
            ',semibold', '-semibold', 'semibold',
            ',demibold', '-demibold', 'demibold',
            ',extrabold', '-extrabold', 'extrabold',
            ',ultralight', '-ultralight', 'ultralight',
            # Style variations
            ',italic', '-italic', 'italic',
            ',oblique', '-oblique', 'oblique',
            # Width variations
            ',condensed', '-condensed', 'condensed',
            ',narrow', '-narrow', 'narrow',
            ',extended', '-extended', 'extended',
            ',wide', '-wide', 'wide',
        ]
        
        for f in page.get_fonts():
            xref, ext, type_, basefont, internal_name, enc = f
            base_clean = basefont.split('+')[-1].lower() if '+' in basefont else basefont.lower()
            
            # Substring match - but only if base doesn't have style markers that target lacks
            # e.g. "timesnewroman" should NOT match "timesnewroman,bolditalic"
            # but "timesnewroman-reg" SHOULD match "timesnewroman-regular"
            if target_clean in base_clean:
                # Check if base has any style marker that target doesn't have
                has_unwanted_style = any(
                    marker in base_clean 
                    for marker in STYLE_MARKERS 
                    if marker not in target_clean
                )
                if not has_unwanted_style:
                    font_data = doc.extract_font(xref)
                    
                    if font_data and len(font_data) >= 4 and font_data[3]:
                        ext_str = ext if ext else "ttf"
                        if ext_str == "n/a" or not ext_str: ext_str = "ttf"
                        # Security: strip non-alphanumeric chars to prevent path traversal
                        ext_str = (''.join(c for c in ext_str if c.isalnum()) or "ttf")[:10]

                        _fd, path = tempfile.mkstemp(suffix=f".{ext_str}", prefix="marcedit_preview_")
                        os.close(_fd)
                        with open(path, "wb") as f_out:
                            f_out.write(font_data[3])

                        _temp_preview_fonts.add(path)
                        print(f"[FontExtract] Substring match: '{basefont}' (xref={xref})")
                        return path
    except Exception as e:
        print(f"Font extraction failed: {e}")
    return None


@monitor_performance("identify_font")
def identify_font(input_path: str, page_number: int, target_text: str) -> dict:
    """
    Identify the font of the FIRST occurrence of target_text on the page.
    Returns dict with keys: success, fontname, fontsize, etc.

    For OCR/scanned documents, returns is_ocr=True when page has no text layer.
    """
    try:
        with fitz.open(input_path) as doc:
            if page_number < 1 or page_number > len(doc):
                return {
                    'success': False,
                    'message': f'Invalid page number {page_number}',
                    'fontname': None,
                    'fontsize': None
                }
            page = doc[page_number - 1]

            # OCR Detection: Check if page has any text content at all
            page_text = page.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            if not page_text or len(page_text.strip()) < 10:
                # Page has no/minimal text - likely scanned/OCR document
                return {
                    'success': False,
                    'message': 'Text not found on page (possible OCR/scanned document)',
                    'fontname': None,
                    'fontsize': None,
                    'is_ocr': True
                }

            # Use Robust Search
            rect = _robust_search(page, target_text)

            if not rect:
                return {
                    'success': False,
                    'message': 'Text not found on page',
                    'fontname': None,
                    'fontsize': None
                }
                
            # Reuse _get_span_font_info
            info = _get_span_font_info(page, target_text, rect)
            
            # Debug logging for font detection
            print(f"[FontDetect] identify_font: Found fontname='{info.get('fontname')}', size={info.get('fontsize')}, found={info.get('found')}")
            
            # Try to extract native font for perfect preview
            if info.get('found') and info.get('fontname'):
                preview_path = _extract_font_to_temp(doc, page, info['fontname'])
                if preview_path:
                    info['preview_font_path'] = preview_path
                    
                    # Calculate visual size adjustment to match PDF rendering
                    # This ensures the preview is scaled correctly (e.g. if PDF font is 11pt but rendered as 13pt)
                    try:
                        repl_font = _get_cached_font(preview_path)
                        # We need helper functions from earlier in file
                        # Assuming _get_reference_char_metrics and _measure_glyph_visual_metrics are available
                        
                        ref_char_data = _get_reference_char_metrics(page, rect, info.get('span_text', target_text))
                        if ref_char_data:
                            ref_char, ref_w_orig, ref_h_orig = ref_char_data
                            repl_metrics = _measure_glyph_visual_metrics(repl_font, ref_char)
                            
                            if repl_metrics:
                                _, ref_h_repl = repl_metrics
                                nominal_repl_h = ref_h_repl * info['fontsize']
                                
                                if nominal_repl_h > 0:
                                    h_factor = ref_h_orig / nominal_repl_h
                                    
                                    # Use same scaling logic as replace_text_in_pdf
                                    scale_factor = h_factor
                                    scale_factor = max(0.7, scale_factor)
                                    scale_factor = min(1.3, scale_factor)
                                    
                                    old_size = info['fontsize']
                                    new_size = old_size * scale_factor
                                    info['fontsize'] = new_size # Update to visual size
                                    
                                    # Log this for debug
                                    print(f"Identify Font Sizing: {old_size:.2f} -> {new_size:.2f} (Factor: {scale_factor:.3f})")
                    except Exception as e:
                        print(f"Identify font sizing calc failed: {e}")
            
            # Add success flag to info
            info['success'] = True
            info['message'] = 'Font identified successfully'
            return info
    except Exception as e:
        return {
            'success': False,
            'message': str(e),
            'fontname': None,
            'fontsize': None
        }


def expand_to_paragraph(input_path: str, page_number: int, span_text: str) -> dict:
    """
    Expand a text span to include adjacent text spans in the same paragraph/block.
    
    This looks for text lines that are:
    - On the same or adjacent Y coordinates (same vertical position ± font height)
    - Within the same horizontal extent (left/right bounds)
    
    Args:
        input_path: Path to PDF file
        page_number: 1-indexed page number
        span_text: The initially selected text span
        
    Returns:
        dict with 'expanded_text' containing the full paragraph text
    """
    try:
        with fitz.open(input_path) as doc:
            if page_number < 1 or page_number > len(doc):
                return {'expanded_text': span_text, 'message': 'Invalid page number'}
            
            page = doc[page_number - 1]
            
            # Find the clicked span's rect
            rect = _robust_search(page, span_text)
            if not rect:
                return {'expanded_text': span_text, 'message': 'Span not found'}
            
            # Get all text blocks on the page
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            
            # Find the block containing our span
            containing_block = None
            for block in blocks:
                if block.get("type") != 0:  # Skip non-text blocks
                    continue
                    
                block_rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
                if block_rect.intersects(rect):
                    containing_block = block
                    break
            
            if not containing_block:
                return {'expanded_text': span_text, 'message': 'Block not found'}
            
            # Extract all text from the block's lines
            paragraph_text = []
            for line in containing_block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                if line_text.strip():
                    paragraph_text.append(line_text.strip())
            
            # Join lines with spaces (preserving paragraph flow)
            expanded = " ".join(paragraph_text)
            
            return {
                'expanded_text': expanded,
                'message': f'Expanded from {len(span_text)} to {len(expanded)} chars'
            }
            
    except Exception as e:
        return {'expanded_text': span_text, 'message': str(e)}


def get_block_spans(input_path: str, page_number: int, span_text: str) -> dict:
    """
    Extract all spans from the text block containing the given span.
    
    Returns comprehensive styling info for each span to enable rich text editing.
    
    Args:
        input_path: Path to PDF file
        page_number: 1-indexed page number
        span_text: Any text span within the target block
        
    Returns:
        {
            "success": True/False,
            "block_bbox": [x0, y0, x1, y1],
            "spans": [
                {
                    "text": "Hello ",
                    "font": "Helvetica-Bold",
                    "size": 12.0,
                    "flags": 20,
                    "is_bold": True,
                    "is_italic": False,
                    "color": [0.0, 0.0, 0.0],
                    "bbox": [x0, y0, x1, y1],
                    "line_index": 0
                },
                ...
            ],
            "message": "..."
        }
    """
    try:
        with fitz.open(input_path) as doc:
            if page_number < 1 or page_number > len(doc):
                return {'success': False, 'spans': [], 'message': 'Invalid page number'}
            
            page = doc[page_number - 1]
            
            # Find the clicked span's rect using robust search
            target_rect = _robust_search(page, span_text)
            if not target_rect:
                return {'success': False, 'spans': [], 'message': 'Span not found'}
            
            # Get all text blocks on the page
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            
            # Find the block containing our span
            containing_block = None
            for block in blocks:
                if block.get("type") != 0:  # Skip non-text blocks
                    continue
                    
                block_rect = fitz.Rect(block.get("bbox", (0, 0, 0, 0)))
                if block_rect.intersects(target_rect):
                    containing_block = block
                    break
            
            if not containing_block:
                return {'success': False, 'spans': [], 'message': 'Block not found'}
            
            # Extract all spans from the block with full styling
            # BUG #54 FIX: Validate bbox structure before unpacking
            raw_block_bbox = containing_block.get("bbox", [0, 0, 0, 0])
            if isinstance(raw_block_bbox, (list, tuple)) and len(raw_block_bbox) >= 4:
                block_bbox = list(raw_block_bbox[:4])  # Take first 4 elements
            else:
                block_bbox = [0, 0, 0, 0]  # Fallback for malformed bbox

            spans_data = []

            for line_idx, line in enumerate(containing_block.get("lines", [])):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:  # Skip empty spans
                        continue

                    font = span.get("font", "")
                    size = span.get("size", 12.0)
                    flags = span.get("flags", 0)
                    color_int = span.get("color", 0)

                    # Validate span bbox structure
                    raw_bbox = span.get("bbox", [0, 0, 0, 0])
                    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
                        bbox = list(raw_bbox[:4])
                    else:
                        bbox = [0, 0, 0, 0]
                    
                    # Parse flags: 1=superscript, 2=italic, 4=serifed, 8=monospaced, 16=bold
                    is_bold = bool(flags & 16)
                    is_italic = bool(flags & 2)
                    
                    # Convert color integer to RGB (0-1 range)
                    # Color is packed as 0xRRGGBB
                    r = ((color_int >> 16) & 0xFF) / 255.0
                    g = ((color_int >> 8) & 0xFF) / 255.0
                    b = (color_int & 0xFF) / 255.0
                    
                    spans_data.append({
                        "text": text,
                        "font": font,
                        "size": size,
                        "flags": flags,
                        "is_bold": is_bold,
                        "is_italic": is_italic,
                        "color": [r, g, b],
                        "bbox": bbox,
                        "line_index": line_idx
                    })
            
            return {
                'success': True,
                'block_bbox': block_bbox,
                'spans': spans_data,
                'span_count': len(spans_data),
                'message': f'Found {len(spans_data)} spans in block'
            }
            
    except Exception as e:
        return {'success': False, 'spans': [], 'message': str(e)}


def replace_block_with_spans(
    input_path: str,
    output_path: str,
    page_number: int,
    block_bbox: list,
    spans: list,
    manual_overrides: dict = None
) -> dict:
    """
    Replace a text block with styled spans.
    
    This function:
    1. Redacts/covers the original block area with white
    2. Inserts each span with its styling (font, size, color, bold/italic)
    
    Args:
        input_path: Path to source PDF
        output_path: Path for output PDF
        page_number: 1-indexed page number
        block_bbox: [x0, y0, x1, y1] of the original block
        spans: Array of span dicts with: text, font, size, is_bold, is_italic, color, bbox, line_index
        manual_overrides: Optional overrides to apply
        
    Returns:
        {success, modified, message, debug_log}
    """
    debug_log = []
    doc = None
    try:
        doc = fitz.open(input_path)

        # BUG #53 FIX: Add complete page validation (empty doc check)
        if len(doc) == 0:
            return {'success': False, 'modified': False, 'message': 'PDF has no pages', 'debug_log': debug_log}

        if page_number < 1 or page_number > len(doc):
            return {'success': False, 'modified': False, 'message': f'Invalid page number: {page_number} (doc has {len(doc)} pages)', 'debug_log': debug_log}
        
        page = doc[page_number - 1]
        
        # Step 1: Redact/cover the original block area
        block_rect = fitz.Rect(block_bbox)
        # Add padding to ensure complete coverage
        block_rect.x0 -= 2
        block_rect.y0 -= 2
        block_rect.x1 += 2
        block_rect.y1 += 2

        debug_log.append(f"Block rect: {block_rect}")

        # Use proper redaction instead of just white fill
        # This ensures text is actually removed, not just covered
        page.add_redact_annot(block_rect, text="", fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

        debug_log.append(f"Redacted block area")
        
        # Step 2: Group spans by line and determine line positions
        lines = {}
        for span in spans:
            line_idx = span.get('line_index', 0)
            if line_idx not in lines:
                lines[line_idx] = []
            lines[line_idx].append(span)
        
        debug_log.append(f"Found {len(lines)} lines with {len(spans)} spans total")
        
        # Step 3: Insert each span with styling
        # Use TextWriter for proper text rendering
        tw = fitz.TextWriter(page.rect)
        
        # Calculate line heights and positions
        if spans:
            first_span = spans[0]
            base_size = first_span.get('size', 12.0)
            line_height = base_size * 1.2  # Standard line height ratio
            
            # Parse overrides
            manual_overrides = manual_overrides or {}
            size_delta = manual_overrides.get('manual_size_delta', 0.0)
            x_offset = manual_overrides.get('manual_x_offset', 0.0)
            y_offset = manual_overrides.get('manual_y_offset', 0.0)
            justification = manual_overrides.get('justification', 'Left')
            
            # Group spans by line index
            lines = {}
            for span in spans:
                idx = span.get('line_index', 0)
                if idx not in lines: lines[idx] = []
                lines[idx].append(span)
            
            sorted_lines = sorted(lines.keys())
            
            # Initialize TextWriter state
            current_tw_color = None
            tw = fitz.TextWriter(page.rect)
            
            # Y Position (adjust for offsets)
            # We base Y on the first line (baseline from top) plus overrides
            current_y = block_rect.y0 + base_size + y_offset
            previous_line_idx = sorted_lines[0] if sorted_lines else 0
            
            for line_idx in sorted_lines:
                line_spans = lines[line_idx]
                
                # Update Y position based on line gaps
                if line_idx > previous_line_idx:
                    current_y += line_height * (line_idx - previous_line_idx)
                previous_line_idx = line_idx
                
                # Pass 1: Measure Line Width & Load Fonts
                measured_spans = []
                line_width = 0.0
                
                for span in line_spans:
                    text = span.get('text', '')
                    if not text: continue
                    
                    font_name = span.get('font', '')
                    base_span_size = span.get('size', 12.0)
                    size = base_span_size + size_delta # Apply size override
                    
                    is_bold = span.get('is_bold', False)
                    is_italic = span.get('is_italic', False)
                    color = span.get('color', [0, 0, 0])
                    
                    # Font Loading Logic
                    internal_name, can_reuse, buffer = _find_internal_font_name(doc, page, font_name, text, "")
                    span_font = None
                    
                    if can_reuse and buffer:
                        try:
                            # Use memory stream for font
                            span_font = fitz.Font(fontbuffer=buffer)
                        except Exception:
                            span_font = fitz.Font("helv")
                    else:
                        base14 = _get_base14_fontname(font_name, is_bold, is_italic)
                        span_font = fitz.Font(base14)
                        
                    length = span_font.text_length(text, fontsize=size)
                    line_width += length
                    measured_spans.append((span, span_font, size, length, text, color))
                
                # Determine Start X based on Justification
                start_x = block_rect.x0 + x_offset
                if justification == 'Center':
                    start_x += (block_rect.width - line_width) / 2
                elif justification == 'Right':
                    start_x = block_rect.x1 + x_offset - line_width
                    
                current_x = start_x
                
                # Pass 2: Draw
                for (span, span_font, size, length, text, color) in measured_spans:
                    color_tuple = tuple(color[:3]) if len(color) >= 3 else (0, 0, 0)
                    
                    # Handle Color Change (Flash batch)
                    if current_tw_color is None:
                        current_tw_color = color_tuple
                    elif color_tuple != current_tw_color:
                        tw.write_text(page, color=current_tw_color)
                        tw = fitz.TextWriter(page.rect)
                        current_tw_color = color_tuple
                    
                    point = fitz.Point(current_x, current_y)
                    try:
                        tw.append(point, text, font=span_font, fontsize=size)
                        debug_log.append(f"Inserted span length={len(text)} at {point} (w={length:.1f})")
                    except Exception as e:
                        debug_log.append(f"Insertion error: {e}")
                        
                    current_x += length
            
            # Final flush
            if current_tw_color is not None:
                tw.write_text(page, color=current_tw_color)
        
        debug_log.append("TextWriter completed")
        
        # Step 4: Save document
        doc.save(output_path, garbage=4, deflate=True)

        debug_log.append("Saved block replacement output")

        return {
            'success': True,
            'modified': True,
            'message': f'Replaced block with {len(spans)} spans',
            'debug_log': debug_log
        }

    except Exception as e:
        return {
            'success': False,
            'modified': False,
            'message': str(e),
            'debug_log': debug_log
        }
    finally:
        if doc:
            doc.close()


def find_font_interactive(input_path: str, page_index: int, target_text: str, exhaustive: bool = False):
    """
    Find best font match with progress feedback (Generator version).
    
    Priority order (deterministic first, visual as fallback):
    1. Internal font name from PDF (embedded font)
    2. System font matching by name
    3. Bundled font matching by name
    4. Visual font matching (last resort)
    
    Args:
        input_path: Path to the PDF document
        page_index: Zero-based page index
        target_text: Text to find font for
        exhaustive: If True, search all system fonts
        
    Yields dicts: {'type': 'progress'|'complete'|'error', ...}
    """
    if not input_path:
        yield {'type': 'error', 'message': 'No document path provided'}
        return

    doc = None
    try:
        doc = fitz.open(input_path)
        if page_index < 0 or page_index >= len(doc):
            yield {'type': 'error', 'message': 'Invalid page index'}
            return
            
        page = doc[page_index]
        
        # Find text rect first
        rect = _robust_search(page, target_text)
        if not rect:
            yield {'type': 'error', 'message': 'Text not found'}
            return
            
        # Get font info
        font_info = _get_span_font_info(page, target_text, rect)
        font_name = font_info.get('fontname', '')
        font_size = font_info.get('fontsize', 12.0)
        
        # Check for suspicious/obfuscated fonts and apply visual serif detection
        src_is_serif = None  # Will be set if we can determine serif/sans
        if _is_font_name_suspicious(font_name):
            yield {'type': 'progress', 'message': 'Detecting font type visually...', 'progress': 0.03}
            try:
                from .visual_matcher import VisualFontMatcher
                matcher = VisualFontMatcher()
                visual_serif = matcher.detect_serif_visually(page, target_text, font_name)
                if visual_serif is not None:
                    src_is_serif = visual_serif
                    # Also update font_info flags for consistency
                    old_flags = font_info.get('flags', 0)
                    if visual_serif:
                        font_info['flags'] = old_flags | 4  # Set serif bit
                    else:
                        font_info['flags'] = old_flags & ~4  # Clear serif bit
            except Exception:
                pass  # Continue without visual detection
        else:
            # Not suspicious - trust PDF flags
            flags = font_info.get('flags', 0)
            src_is_serif = (flags & 4) != 0 if flags else None
        
        # --- DETERMINISTIC MATCHING (Priority 1-3) ---
        yield {'type': 'progress', 'message': 'Checking deterministic matches...', 'progress': 0.05}
        
        # Priority 1: Try to find internal font name (exact embedded font)
        # We pass target_text as replacement_text to check if the font supports the characters we found
        internal_font_name, has_all_glyphs, reuse_buffer = _find_internal_font_name(
            doc, page, font_name, target_text, target_text
        )
        if internal_font_name and has_all_glyphs:
            yield {'type': 'progress', 'message': f'Found internal font: {internal_font_name}', 'progress': 0.1}
            
            # Extract for preview
            preview_path = _extract_font_to_temp(doc, page, font_name)
            path_val = preview_path if preview_path else 'internal'
            
            yield {
                'type': 'complete',
                'success': True, 
                'best_match': {
                    'name': internal_font_name,
                    'path': path_val,  # Pass temp path so preview can load it
                    'score': 1.0  # Perfect match - it's the exact font
                },
                'candidates': [{'name': internal_font_name, 'path': path_val, 'score': 1.0}],
                'source': 'Embedded Font',
                'src_is_serif': src_is_serif  # Pass through for display
            }
            return
            
        # Priority 2: Try system font lookup by name
        yield {'type': 'progress', 'message': f'Searching system fonts for: {font_name}', 'progress': 0.15}
        
        system_font_path = _find_system_font(font_name, flags=font_info.get('flags'))
        if system_font_path:
            font_display_name = os.path.splitext(os.path.basename(system_font_path))[0]
            yield {
                'type': 'complete',
                'success': True,
                'best_match': {
                    'name': font_display_name,
                    'path': system_font_path,
                    'score': 0.95  # High score for name match
                },
                'candidates': [{'name': font_display_name, 'path': system_font_path, 'score': 0.95}],
                'source': 'System Font',
                'src_is_serif': src_is_serif
            }
            return
        
        # Priority 3: Try bundled fonts
        yield {'type': 'progress', 'message': 'Checking bundled fonts...', 'progress': 0.2}
        
        bundled_path = _find_bundled_font(font_name)
        if bundled_path:
            try:
                font_display_name = os.path.splitext(os.path.basename(bundled_path))[0]
                yield {
                    'type': 'complete',
                    'success': True,
                    'best_match': {
                        'name': font_display_name,
                        'path': bundled_path,
                        'score': 0.9  # Good score for bundled match
                    },
                    'candidates': [{'name': font_display_name, 'path': bundled_path, 'score': 0.9}],
                    'source': 'Bundled Font',
                    'src_is_serif': src_is_serif
                }
                return
            except Exception:
                pass  # Fall through to visual matching
        
        # --- VISUAL MATCHING (Priority 4 - Last Resort) ---
        yield {'type': 'progress', 'message': 'Starting visual font matching...', 'progress': 0.25}
        
        # Run visual matcher generator with serif/sans preference
        matcher = VisualFontMatcher(exhaustive=exhaustive)
        yield from matcher.find_best_match_gen(page, target_text, font_name, src_is_serif=src_is_serif)
        
    except Exception as e:
        yield {'type': 'error', 'message': str(e)}
    finally:
        if doc:
            doc.close()


def flatten_document_to_outlines(input_path: str, output_path: str) -> dict:
    """
    Convert all text in the document to vector paths (outlines).
    This makes the text uneditable while preserving visual appearance.
    
    Uses PyMuPDF's get_svg_image(text_as_path=True) to render text as vectors,
    then converts back to PDF.
    """
    debug_log = []
    debug_log.append("Starting vector flattening")
    doc = None
    out_doc = None
    try:
        doc = fitz.open(input_path)
        page_count = len(doc)
        debug_log.append(f"Document has {page_count} pages")

        # Create a new document to hold the flattened pages
        out_doc = fitz.open()

        for i, page in enumerate(doc):
            debug_log.append(f"Processing page {i+1}/{page_count}...")

            # 1. Convert page to SVG with text_as_path=True
            # This converts all text characters to vector drawing commands
            svg_data = page.get_svg_image(text_as_path=True)

            # 2. Convert SVG back to PDF page
            # We open the SVG data as a document (requires bytes)
            src = fitz.open("svg", svg_data.encode("utf-8"))
            try:
                # 3. Convert SVG doc to PDF blob
                pdf_bytes = src.convert_to_pdf()

                # 4. Open PDF blob as document
                page_doc = fitz.open("pdf", pdf_bytes)
                try:
                    # 5. Insert this flattened page into our output document
                    out_doc.insert_pdf(page_doc)
                finally:
                    page_doc.close()
            finally:
                src.close()

            debug_log.append(f"  Page {i+1} flattened successfully")

        # Save the result
        debug_log.append("Saving flattened document")
        out_doc.save(output_path, garbage=4, deflate=True)

        return {"success": True, "log": debug_log}

    except Exception as e:
        debug_log.append(f"Error: {e}")
        import traceback
        debug_log.append(traceback.format_exc())
        return {"success": False, "error": str(e), "log": debug_log}
    finally:
        if out_doc:
            out_doc.close()
        if doc:
            doc.close()


def extract_all_metadata(input_path: str) -> dict:
    """
    Extract ALL metadata from a PDF document without modification.
    
    Returns comprehensive metadata including:
    - Standard DocumentInfo fields
    - XMP metadata (parsed from XML)
    - Embedded files/attachments info
    - Document structure info
    """
    doc = None
    try:
        import os
        import hashlib
        from datetime import datetime
        
        # Calculate MD5 hash — streamed in 1 MiB chunks to avoid loading large PDFs into RAM.
        md5_hash = ""
        try:
            h = hashlib.md5()
            with open(input_path, 'rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
            md5_hash = h.hexdigest()
        except Exception:
            pass
        
        # Get macOS filesystem metadata - ALL Finder Get Info fields
        filesystem_meta = {}
        try:
            import subprocess
            stat_info = os.stat(input_path)
            
            # Basic file info
            filesystem_meta['file_size'] = stat_info.st_size
            filesystem_meta['file_size_human'] = _format_file_size(stat_info.st_size)
            filesystem_meta['created'] = datetime.fromtimestamp(stat_info.st_birthtime).isoformat()
            filesystem_meta['created_human'] = datetime.fromtimestamp(stat_info.st_birthtime).strftime('%B %d, %Y at %I:%M %p')
            filesystem_meta['modified'] = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
            filesystem_meta['modified_human'] = datetime.fromtimestamp(stat_info.st_mtime).strftime('%B %d, %Y at %I:%M %p')
            filesystem_meta['accessed'] = datetime.fromtimestamp(stat_info.st_atime).isoformat()
            filesystem_meta['accessed_human'] = datetime.fromtimestamp(stat_info.st_atime).strftime('%B %d, %Y at %I:%M %p')
            
            # Finder "Where" field - parent directory
            filesystem_meta['where'] = os.path.dirname(input_path)
            
            # File flags (Locked, Stationery pad)
            import stat as stat_module
            flags = stat_info.st_flags
            filesystem_meta['locked'] = 'Yes' if (flags & stat_module.UF_IMMUTABLE) else 'No'
            # Note: Stationery pad is stored differently in resource fork, harder to detect
            filesystem_meta['stationery_pad'] = 'No'  # Default - would need resource fork check
            
            # Permissions (Sharing & Permissions)
            mode = stat_info.st_mode
            owner_perms = []
            if mode & stat_module.S_IRUSR: owner_perms.append('Read')
            if mode & stat_module.S_IWUSR: owner_perms.append('Write')
            filesystem_meta['permissions'] = ' & '.join(owner_perms) if owner_perms else 'None'
            
            # Get Spotlight metadata (Kind, Comments, etc.)
            try:
                mdls_result = subprocess.run(['mdls', '-plist', '-', input_path], 
                                            capture_output=True, timeout=5)
                if mdls_result.returncode == 0:
                    import plistlib
                    mdls_data = plistlib.loads(mdls_result.stdout)
                    
                    # Kind (e.g., "PDF Document", "JPEG image")
                    kind = mdls_data.get('kMDItemKind', '')
                    filesystem_meta['kind'] = kind if kind else ''
                    
                    # Content type (UTI)
                    content_type = mdls_data.get('kMDItemContentType', '')
                    filesystem_meta['content_type'] = content_type if content_type else ''
                    
                    # Finder comment
                    comment = mdls_data.get('kMDItemFinderComment', '')
                    filesystem_meta['comment'] = comment if comment else ''
                    
                    # Where from (download source)
                    where_from = mdls_data.get('kMDItemWhereFroms', [])
                    filesystem_meta['where_from'] = where_from if where_from else []
                    
                    # Copyright
                    copyright_info = mdls_data.get('kMDItemCopyright', '')
                    filesystem_meta['copyright'] = copyright_info if copyright_info else ''
                    
                    # Download date
                    download_date = mdls_data.get('kMDItemDownloadedDate', [])
                    if download_date and len(download_date) > 0:
                        filesystem_meta['downloaded'] = download_date[0].isoformat() if hasattr(download_date[0], 'isoformat') else str(download_date[0])
                    else:
                        filesystem_meta['downloaded'] = ''
            except Exception:
                pass  # Spotlight not available or timeout

            
            # Extended attributes (macOS-specific)
            try:
                import subprocess
                import plistlib
                import re

                # Use xattr command line since module might be missing
                # -l lists attributes
                result = subprocess.run(['xattr', '-l', input_path], capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    attrs_list = []
                    
                    # Parse output lines "key: value"
                    # For complex types (like WhereFroms), we need to extract raw data
                    for line in result.stdout.splitlines():
                        if ": " in line:
                            k, v = line.split(": ", 1)
                            
                            # Handle specific binary plist attributes
                            if k in ["com.apple.metadata:kMDItemWhereFroms", "com.apple.metadata:kMDItemDownloadedDate", "com.apple.quarantine"]:
                                try:
                                    # Get hex output for binary decoding
                                    hex_res = subprocess.run(['xattr', '-p', '-x', k, input_path], capture_output=True, text=True)
                                    if hex_res.returncode == 0:
                                        # Convert hex to bytes
                                        hex_str = hex_res.stdout.replace(' ', '').replace('\n', '')
                                        data = bytes.fromhex(hex_str)
                                        
                                        # Decode plist if applicable
                                        if k == "com.apple.metadata:kMDItemWhereFroms":
                                            try:
                                                pl = plistlib.loads(data)
                                                v = f"{pl}" # Convert list to string representation
                                            except Exception:
                                                pass
                                        elif k == "com.apple.metadata:kMDItemDownloadedDate":
                                             try:
                                                pl = plistlib.loads(data)
                                                v = f"{pl}"
                                             except Exception:
                                                pass
                                except Exception:
                                    pass
                            
                            attrs_list.append(f"{k}: {v}")
                    
                    if attrs_list:
                        filesystem_meta['extended_attrs'] = attrs_list
            except Exception as e:
                filesystem_meta['extended_attrs_error'] = str(e)
        except Exception as e:
            filesystem_meta['_error'] = str(e)
        
        doc = fitz.open(input_path)

        result = {
            "success": True,
            "md5": md5_hash,
            "filesystem_metadata": filesystem_meta,
            "document_info": {},
            "xmp_metadata": {},
            "embedded_files": [],
            "structure_info": {}
        }
        
        # 1. Standard DocumentInfo - ALL 11 fields from PDF spec + PyMuPDF
        metadata = doc.metadata or {}
        for key in ['title', 'author', 'subject', 'keywords', 'creator', 
                    'producer', 'creationDate', 'modDate', 'format', 'encryption', 'trapped']:
            val = metadata.get(key, '')
            # Always include all standard fields, even if empty
            result['document_info'][key] = val if val else ''
        
        # 2. XMP Metadata extraction
        try:
            xmp_bytes = doc.xref_xml_metadata()
            if xmp_bytes:
                xmp_str = xmp_bytes if isinstance(xmp_bytes, str) else xmp_bytes.decode('utf-8', errors='replace')
                result['xmp_metadata'] = _parse_xmp_metadata(xmp_str)
        except Exception as e:
            result['xmp_metadata']['_error'] = f"XMP parsing failed: {e}"
        
        # 3. Embedded files / attachments
        try:
            embfile_count = doc.embfile_count()
            for i in range(embfile_count):
                info = doc.embfile_info(i)
                file_entry = {
                    'name': info.get('name', f'file_{i}'),
                    'filename': info.get('filename', ''),
                    'size': info.get('size', 0),
                    'creation_date': info.get('creationDate', ''),
                    'modification_date': info.get('modDate', ''),
                    'description': info.get('desc', ''),
                    'checksum': info.get('checksum', ''),
                    'can_extract': True
                }
                result['embedded_files'].append(file_entry)
        except Exception as e:
            result['embedded_files'] = [{'_error': f"Embedded file extraction failed: {e}"}]
        
        # 4. Document structure info
        try:
            page_count = len(doc)
            page_sizes = []
            for i in range(min(page_count, 10)):  # Sample first 10 pages
                page = doc[i]
                rect = page.rect
                width_pts = rect.width
                height_pts = rect.height
                # Convert to common paper size name if applicable
                size_name = _identify_page_size(width_pts, height_pts)
                page_sizes.append(f"{width_pts:.0f}x{height_pts:.0f} ({size_name})")
            
            if page_count > 10:
                page_sizes.append(f"... and {page_count - 10} more pages")
            
            # Use get_toc() for safe bookmark counting (avoids crash with outline traversal)
            toc = doc.get_toc() if hasattr(doc, 'get_toc') else []
            bookmark_count = len(toc) if toc else 0
            
            result['structure_info'] = {
                'page_count': page_count,
                'page_sizes': page_sizes,
                'has_bookmarks': bookmark_count > 0,
                'bookmark_count': bookmark_count,
                'has_annotations': any(len(doc[i].annots() or []) > 0 for i in range(min(page_count, 5))),
                'has_forms': doc.is_form_pdf,
                'has_signatures': _has_signatures(doc),
            }
        except Exception as e:
            result['structure_info']['_error'] = f"Structure analysis failed: {e}"
        
        # 5. Binary Resources Detection - ALL embedded binary content
        binary_resources = {
            'icc_profiles': [],
            'digital_signatures': [],
            'thumbnails': [],
            'embedded_fonts': [],
            'embedded_images': [],
            'javascript': [],
            'form_fields': [],
            'custom_streams': []
        }
        
        try:
            # Scan all XREFs for binary resources
            for xref in range(1, doc.xref_length()):
                try:
                    obj_str = doc.xref_object(xref)
                    
                    # ICC Color Profiles
                    if '/ICCBased' in obj_str or ('/ColorSpace' in obj_str and '/ICC' in obj_str):
                        try:
                            stream_length = len(doc.xref_stream(xref) or b'')
                            binary_resources['icc_profiles'].append({
                                'xref': xref,
                                'size': stream_length,
                                'size_human': _format_file_size(stream_length)
                            })
                        except Exception:
                            binary_resources['icc_profiles'].append({'xref': xref, 'size': 0})
                    
                    # Digital Signatures
                    if '/Sig' in obj_str or '/ByteRange' in obj_str:
                        binary_resources['digital_signatures'].append({
                            'xref': xref,
                            'type': 'Digital Signature'
                        })
                    
                    # Thumbnails
                    if '/Thumb' in obj_str:
                        try:
                            stream_length = len(doc.xref_stream(xref) or b'')
                            binary_resources['thumbnails'].append({
                                'xref': xref,
                                'size': stream_length,
                                'size_human': _format_file_size(stream_length)
                            })
                        except Exception:
                            binary_resources['thumbnails'].append({'xref': xref})
                    
                    # JavaScript
                    if '/JavaScript' in obj_str or '/JS' in obj_str:
                        try:
                            stream = doc.xref_stream(xref)
                            if stream:
                                js_preview = stream[:200].decode('utf-8', errors='replace')
                                binary_resources['javascript'].append({
                                    'xref': xref,
                                    'preview': js_preview[:100] + '...' if len(js_preview) > 100 else js_preview
                                })
                        except Exception:
                            binary_resources['javascript'].append({'xref': xref, 'preview': '(binary)'})
                    
                except Exception:
                    pass  # Skip problematic XREFs
            
            # Embedded Fonts (use PyMuPDF's font extraction)
            try:
                for page_num in range(min(len(doc), 5)):  # Sample first 5 pages
                    page = doc[page_num]
                    fonts = page.get_fonts(full=True)
                    for font in fonts:
                        if len(font) < 6:
                            continue  # Skip malformed font tuples
                        font_info = {
                            'xref': font[0],
                            'ext': font[1],  # File extension (ttf, cff, etc.)
                            'type': font[2],  # Font type (Type1, TrueType, etc.)
                            'name': font[3],  # Base font name
                            'internal_name': font[4],  # Internal reference name
                            'encoding': font[5],  # Encoding field
                            'embedded': 'yes' if font[0] > 0 else 'no'
                        }
                        # Avoid duplicates
                        if not any(f['xref'] == font[0] for f in binary_resources['embedded_fonts']):
                            binary_resources['embedded_fonts'].append(font_info)
            except Exception:
                pass
            
            # Embedded Images - scan ALL XREFs to find every image including unreferenced
            try:
                import base64
                for xref in range(1, doc.xref_length()):
                    try:
                        obj_str = doc.xref_object(xref)
                        # Check if this XREF is an image
                        if '/Subtype /Image' in obj_str or ('/Subtype' in obj_str and '/Image' in obj_str):
                            # Get image info from xref stream
                            try:
                                img = doc.extract_image(xref)
                                if img:
                                    # Convert image data to base64 for HTML embedding
                                    img_data = img.get('image', b'')
                                    img_ext = img.get('ext', 'png')
                                    img_b64 = base64.b64encode(img_data).decode('utf-8') if img_data else ''
                                    
                                    img_info = {
                                        'xref': xref,
                                        'width': img.get('width', 0),
                                        'height': img.get('height', 0),
                                        'colorspace': img.get('colorspace', 'Unknown'),
                                        'bpc': img.get('bpc', 0),
                                        'size': len(img_data),
                                        'size_human': _format_file_size(len(img_data)),
                                        'ext': img_ext,
                                        'data_b64': img_b64[:500000] if len(img_b64) > 500000 else img_b64  # Limit to ~375KB
                                    }
                                    # Avoid duplicates
                                    if not any(i['xref'] == xref for i in binary_resources['embedded_images']):
                                        binary_resources['embedded_images'].append(img_info)
                            except Exception:
                                # Image extraction failed, just record metadata
                                img_info = {
                                    'xref': xref,
                                    'width': 0,
                                    'height': 0,
                                    'colorspace': 'Unknown',
                                    'note': 'extraction failed'
                                }
                                if not any(i['xref'] == xref for i in binary_resources['embedded_images']):
                                    binary_resources['embedded_images'].append(img_info)
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Form Fields
            try:
                if doc.is_form_pdf:
                    for page in doc:
                        widgets = page.widgets() or []
                        for w in widgets:
                            field_info = {
                                'name': w.field_name,
                                'type': w.field_type_string,
                                'value': str(w.field_value)[:50] if w.field_value else ''
                            }
                            binary_resources['form_fields'].append(field_info)
            except Exception:
                pass
            
        except Exception as e:
            binary_resources['_error'] = str(e)
        
        result['binary_resources'] = binary_resources

        return result

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        if doc:
            doc.close()


def _parse_xmp_metadata(xmp_str: str) -> dict:
    """
    Parse XMP XML string to extract metadata properties.
    Returns dict with namespace-prefixed keys like 'dc:title', 'xmp:CreateDate'.
    """
    import re
    
    result = {}
    
    # Common XMP namespaces
    namespaces = {
        'dc': 'http://purl.org/dc/elements/1.1/',
        'xmp': 'http://ns.adobe.com/xap/1.0/',
        'xmpRights': 'http://ns.adobe.com/xap/1.0/rights/',
        'xmpMM': 'http://ns.adobe.com/xap/1.0/mm/',
        'pdf': 'http://ns.adobe.com/pdf/1.3/',
        'photoshop': 'http://ns.adobe.com/photoshop/1.0/',
    }
    
    # Extract simple properties: <prefix:Property>value</prefix:Property>
    for prefix in namespaces.keys():
        pattern = rf'<{prefix}:(\w+)[^>]*>([^<]+)</{prefix}:\1>'
        matches = re.findall(pattern, xmp_str, re.IGNORECASE)
        for prop_name, value in matches:
            key = f"{prefix}:{prop_name}"
            value = value.strip()
            if value:
                result[key] = value
    
    # Extract rdf:li list items (for multi-value fields like dc:creator)
    # Pattern: <prefix:Property>...<rdf:li>value</rdf:li>...</prefix:Property>
    for prefix in ['dc', 'xmp']:
        list_pattern = rf'<{prefix}:(\w+)[^>]*>.*?<rdf:Seq[^>]*>(.*?)</rdf:Seq>.*?</{prefix}:\1>'
        matches = re.findall(list_pattern, xmp_str, re.IGNORECASE | re.DOTALL)
        for prop_name, seq_content in matches:
            key = f"{prefix}:{prop_name}"
            items = re.findall(r'<rdf:li[^>]*>([^<]+)</rdf:li>', seq_content)
            if items:
                result[key] = items if len(items) > 1 else items[0]
    
    return result


def _identify_page_size(width: float, height: float) -> str:
    """Identify common page sizes from dimensions in points."""
    # Standard sizes (width x height in points, portrait orientation)
    sizes = {
        'Letter': (612, 792),
        'Legal': (612, 1008),
        'A4': (595, 842),
        'A3': (842, 1191),
        'A5': (420, 595),
        'Tabloid': (792, 1224),
    }
    
    # Check both orientations
    for name, (w, h) in sizes.items():
        if (abs(width - w) < 5 and abs(height - h) < 5) or \
           (abs(width - h) < 5 and abs(height - w) < 5):
            return name
    
    return "Custom"


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _parse_pdf_date(date_str: str) -> str:
    """Convert PDF date format (D:YYYYMMDDHHmmss+TZ) to human-readable format."""
    import re
    if not date_str or not date_str.startswith('D:'):
        return date_str
    
    try:
        # Parse: D:YYYYMMDDHHmmss+HH'mm' or D:YYYYMMDDHHmmss-HH'mm'
        match = re.match(r'D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})', date_str)
        if match:
            year, month, day, hour, minute, second = match.groups()
            from datetime import datetime
            dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
            return dt.strftime('%B %d, %Y at %I:%M:%S %p')
    except Exception:
        pass
    
    return date_str



def _has_signatures(doc) -> bool:
    """Check if document contains digital signatures."""
    try:
        # Check for signature form fields
        for i in range(len(doc)):
            page = doc[i]
            widgets = page.widgets()
            if widgets:
                for widget in widgets:
                    if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                        return True
    except Exception:
        pass
    return False


def generate_scrub_report(
    before: dict,
    after: dict,
    extracted_files: list,
    source_filename: str,
    data_dir_name: str,
    md5_checksum: str = None
) -> str:
    """
    Generate HTML scrub report comparing before/after metadata.
    
    Args:
        before: Output from extract_all_metadata before scrub
        after: Output from extract_all_metadata after scrub
        extracted_files: List of {'name': str, 'path': str, 'size': int}
        source_filename: Original PDF filename
        data_dir_name: Name of data subdirectory (relative path)
        md5_checksum: Optional MD5 checksum to include in report
    
    Returns:
        HTML string for the report
    """
    from datetime import datetime
    from html import escape as _html_escape
    from urllib.parse import quote as _url_quote

    def html_text(val) -> str:
        return _html_escape(str(val), quote=False)

    def html_attr(val) -> str:
        return _html_escape(str(val), quote=True)

    def relative_href(*parts) -> str:
        return "./" + "/".join(_url_quote(str(p), safe="._-") for p in parts)
    
    def format_value(val, field_name: str = None, data_dir: str = None, long_values: dict = None):
        """Format a value for HTML display."""
        if val is None or val == '':
            return '<em>(empty)</em>'
        if isinstance(val, list):
            return ' | '.join(html_text(v) for v in val)
        
        val_str = str(val)
        
        # Check if this is a long value that needs to be saved to file
        if long_values is not None and field_name and len(val_str) > 500:
            safe_name = field_name.replace(':', '_').replace('/', '_')
            filename = f"{safe_name}.txt"
            long_values[filename] = val_str
            size_kb = len(val_str.encode('utf-8')) / 1024
            href = relative_href(data_dir, filename)
            return f'<a href="{html_attr(href)}">{html_text(filename)}</a> ({size_kb:.1f} KB)'
        
        return html_text(val_str)
    
    def format_value_with_tooltip(val, field_name: str, data_dir: str = None, long_values: dict = None):
        """Format a value with human-readable tooltip for dates."""
        base = format_value(val, field_name, data_dir, long_values)
        
        # Add tooltip for PDF dates
        if val and isinstance(val, str) and val.startswith('D:'):
            human_date = _parse_pdf_date(val)
            if human_date != val:
                return f'<span title="{html_attr(human_date)}">{base}</span>'
        
        return base
    
    # Field descriptions for tooltips
    field_descriptions = {
        'title': 'Document title - often visible in browser tabs',
        'author': 'Person or organization who created the content',
        'subject': 'Topic or summary of the document',
        'keywords': 'Search keywords associated with the document',
        'creator': 'Software used to create the original document',
        'producer': 'Software used to convert/save as PDF',
        'creationDate': 'When the PDF was originally created (PDF date format: D:YYYYMMDDHHmmss+TZ)',
        'modDate': 'When the PDF was last modified (PDF date format: D:YYYYMMDDHHmmss+TZ)',
        'format': 'PDF version specification',
        'encryption': 'Encryption/security settings',
        'dc:title': 'XMP: Dublin Core title',
        'dc:creator': 'XMP: Dublin Core creator/author',
        'dc:description': 'XMP: Dublin Core description',
        'xmp:CreateDate': 'XMP: Date document was created (ISO 8601)',
        'xmp:ModifyDate': 'XMP: Date document was last modified (ISO 8601)',
        'xmp:CreatorTool': 'XMP: Software used to create the document',
        'pdf:Producer': 'XMP: PDF producer software',
        'xmpMM:DocumentID': 'XMP: Unique document identifier (UUID)',
        'xmpMM:InstanceID': 'XMP: Instance/version identifier',
    }
    
    def is_image(filename: str) -> bool:
        ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
        return ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'tif')
    
    # Track long values to save
    long_values = {}
    
    # Count changes
    doc_info_before = before.get('document_info', {})
    doc_info_after = after.get('document_info', {})
    xmp_before = before.get('xmp_metadata', {})
    xmp_after = after.get('xmp_metadata', {})
    
    fields_cleared = sum(1 for k in doc_info_before if doc_info_before.get(k) and not doc_info_after.get(k))
    xmp_cleared = sum(1 for k in xmp_before if xmp_before.get(k) and not xmp_after.get(k))
    
    # Get MD5 checksums from before/after data
    md5_before = before.get('md5', '')
    md5_after = after.get('md5', '')
    
    # Get filesystem metadata
    fs_before = before.get('filesystem_metadata', {})
    fs_after = after.get('filesystem_metadata', {})
    
    # Build HTML
    source_filename_html = html_text(source_filename)
    source_filename_attr = html_attr(source_filename)

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Scrub Report - {source_filename_html}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               margin: 20px; background: #f5f5f7; color: #1d1d1f; }}
        h1 {{ color: #1d1d1f; border-bottom: 1px solid #d2d2d7; padding-bottom: 10px; }}
        h2 {{ color: #424245; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: white; 
                 border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                 table-layout: fixed; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #e5e5e5; 
                  word-wrap: break-word; overflow-wrap: break-word; }}
        th {{ background: #f5f5f7; font-weight: 600; color: #424245; }}
        th:first-child {{ width: 20%; }}
        th:nth-child(2), th:nth-child(3) {{ width: 40%; }}
        tr:last-child td {{ border-bottom: none; }}
        img.preview {{ max-height: 60px; max-width: 100px; border-radius: 4px; }}
        .summary {{ background: white; padding: 20px; border-radius: 8px; 
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 20px 0; }}
        .summary ul {{ margin: 10px 0; padding-left: 20px; }}
        .cleared {{ color: #666; font-style: italic; }}
        .unchanged {{ color: #999; font-style: italic; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .meta {{ color: #666; font-size: 0.9em; }}
        code {{ background: #e5e5e5; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 0.9em; }}
        .field-name {{ cursor: help; border-bottom: 1px dotted #999; }}
        .field-name:hover {{ color: #0066cc; }}
        [title] {{ cursor: help; }}
        
        .no-preview {{ color: #999; font-style: italic; }}
    </style>
</head>
<body>
    <h1>Metadata Scrub Report</h1>
    <p class="meta"><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p class="meta"><strong>Source:</strong> {source_filename_html}</p>
    
    <div class="summary">
        <h2 style="margin-top: 0;">Summary</h2>
        <ul>
            <li>Document Info Fields Cleared: {fields_cleared}</li>
            <li>XMP Properties Removed: {xmp_cleared}</li>
            <li>Embedded Files Extracted: {len(extracted_files)}</li>
        </ul>
    </div>
'''
    
    # File Integrity (MD5) section
    if md5_before or md5_after:
        html += '''
    <h2>File Integrity</h2>
    <table>
        <tr><th>Property</th><th>Before</th><th>After</th></tr>
'''
        html += f'        <tr><td><span class="field-name" title="MD5 hash - 128-bit fingerprint for verifying file integrity">MD5 Checksum</span></td><td><code>{html_text(md5_before) if md5_before else "<em>(none)</em>"}</code></td><td><code>{html_text(md5_after) if md5_after else "<em>(none)</em>"}</code></td></tr>\n'
        # Show file size if available
        size_before = fs_before.get('file_size_human', '')
        size_after = fs_after.get('file_size_human', '')
        if size_before or size_after:
            html += f'        <tr><td><span class="field-name" title="File size on disk">File Size</span></td><td>{html_text(size_before) if size_before else "<em>(empty)</em>"}</td><td>{html_text(size_after) if size_after else "<em>(empty)</em>"}</td></tr>\n'
        html += '    </table>\n'
    
    # Filesystem Metadata section - ALL macOS Finder Get Info fields
    if fs_before or fs_after:
        html += '''
    <h2>Filesystem Metadata</h2>
    <p class="meta">macOS Finder Get Info fields</p>
    <table>
        <tr><th>Property</th><th>Before</th><th>After</th></tr>
'''
        # Define all macOS fields to show (even if empty)
        macos_fields = [
            ('kind', 'Kind', 'File type (e.g., PDF Document)'),
            ('where', 'Where', 'Parent directory path'),
            ('file_size_human', 'File Size', 'File size on disk'),
            ('created_human', 'Created', 'macOS file creation date'),
            ('modified_human', 'Modified', 'macOS file modification date'),
            ('accessed_human', 'Accessed', 'Last accessed date'),
            ('comment', 'Comments', 'Finder comment (Cmd+I)'),
            ('locked', 'Locked', 'File is locked (immutable)'),
            ('stationery_pad', 'Stationery Pad', 'Finder stationery pad setting'),
            ('permissions', 'Permissions', 'Read/Write permissions'),
            ('content_type', 'Content Type', 'Uniform Type Identifier (UTI)'),
            ('copyright', 'Copyright', 'Spotlight copyright metadata'),
            ('downloaded', 'Downloaded', 'Date file was downloaded'),
        ]
        
        for key, label, tooltip in macos_fields:
            val_before = fs_before.get(key, '')
            val_after = fs_after.get(key, '')
            # Format lists (like where_from)
            if isinstance(val_before, list):
                val_before = ', '.join(str(v) for v in val_before) if val_before else ''
            if isinstance(val_after, list):
                val_after = ', '.join(str(v) for v in val_after) if val_after else ''
            # Always show the row
            before_display = html_text(val_before) if val_before else '<em>(empty)</em>'
            after_display = html_text(val_after) if val_after else '<em>(empty)</em>'
            html += f'        <tr><td><span class="field-name" title="{html_attr(tooltip)}">{html_text(label)}</span></td><td>{before_display}</td><td>{after_display}</td></tr>\n'
        
        # Where From (special handling for download source URLs)
        where_from_before = fs_before.get('where_from', [])
        where_from_after = fs_after.get('where_from', [])
        if where_from_before or where_from_after:
            wf_before = html_text(', '.join(str(v) for v in where_from_before)) if where_from_before else '<em>(empty)</em>'
            wf_after = html_text(', '.join(str(v) for v in where_from_after)) if where_from_after else '<em>(empty)</em>'
            html += f'        <tr><td><span class="field-name" title="URL(s) where file was downloaded from">Where From</span></td><td>{wf_before}</td><td>{wf_after}</td></tr>\n'
        
        # Extended attributes - with binary value sanitization
        def sanitize_xattr_value(val):
            """Convert non-printable characters to readable hex representation"""
            if not val:
                return val
            result = []
            for c in str(val):
                if ord(c) < 32 or ord(c) > 126:
                    result.append(f'[0x{ord(c):02X}]')
                else:
                    result.append(c)
            return ''.join(result)
        
        def format_xattr_list(xattrs):
            """Format xattr list with sanitized values"""
            if not xattrs or not isinstance(xattrs, list):
                return '<em>(none)</em>'
            formatted = []
            for attr in xattrs:
                # attr might be "name: value" or just "name"
                if isinstance(attr, str):
                    formatted.append(sanitize_xattr_value(attr))
                else:
                    formatted.append(str(attr))
            return html_text(', '.join(formatted))
        
        xattrs_before = fs_before.get('extended_attrs', [])
        xattrs_after = fs_after.get('extended_attrs', [])
        xattr_before_str = format_xattr_list(xattrs_before)
        xattr_after_str = format_xattr_list(xattrs_after)
        
        # Check if macOS added system xattrs
        macos_added = []
        if isinstance(xattrs_after, list):
            for attr in xattrs_after:
                attr_name = attr.split(':')[0] if ':' in attr else attr
                if 'com.apple.provenance' in attr_name or 'com.apple.quarantine' in attr_name:
                    if not any(attr_name in str(a) for a in (xattrs_before or [])):
                        macos_added.append(attr_name)
        
        html += f'        <tr><td><span class="field-name" title="macOS extended attributes (xattr)">Extended Attributes</span></td><td>{xattr_before_str}</td><td>{xattr_after_str}</td></tr>\n'
        
        # Add note about macOS system xattrs if detected
        if macos_added:
            html += '    </table>\n'
            html += f'    <p class="meta"><strong>Note:</strong> macOS automatically added: {html_text(", ".join(macos_added))}. These are system security/provenance attributes, not user metadata.</p>\n'
        else:
            html += '    </table>\n'
    
    # Document Information table
    all_doc_keys = set(doc_info_before.keys()) | set(doc_info_after.keys())
    if all_doc_keys:
        html += '''
    <h2>Document Information</h2>
    <table>
        <tr><th>Field</th><th>Before</th><th>After</th></tr>
'''
        for key in sorted(all_doc_keys):
            field_desc = field_descriptions.get(key, f'PDF document info field: {key}')
            before_val_raw = doc_info_before.get(key)
            before_val = format_value_with_tooltip(before_val_raw, key, data_dir_name, long_values)
            after_val = doc_info_after.get(key)
            # Show 'unchanged' if both empty, 'cleared' only if before had value
            if after_val:
                after_display = format_value_with_tooltip(after_val, key)
            elif before_val_raw:
                after_display = '<span class="cleared">(cleared)</span>'
            else:
                after_display = '<span class="unchanged">(unchanged)</span>'
            html += f'        <tr><td><span class="field-name" title="{html_attr(field_desc)}">{html_text(key)}</span></td><td>{before_val}</td><td>{after_display}</td></tr>\n'
        html += '    </table>\n'
    
    # XMP Metadata table
    all_xmp_keys = set(xmp_before.keys()) | set(xmp_after.keys())
    # Filter out error keys
    all_xmp_keys = {k for k in all_xmp_keys if not k.startswith('_')}
    if all_xmp_keys:
        html += '''
    <h2>XMP Metadata</h2>
    <table>
        <tr><th>Property</th><th>Before</th><th>After</th></tr>
'''
        for key in sorted(all_xmp_keys):
            before_val_raw = xmp_before.get(key)
            before_val = format_value(before_val_raw, key, data_dir_name, long_values)
            after_val = xmp_after.get(key)
            # Show 'unchanged' if both empty, 'cleared' only if before had value
            if after_val:
                after_display = format_value(after_val)
            elif before_val_raw:
                after_display = '<span class="cleared">(cleared)</span>'
            else:
                after_display = '<span class="unchanged">(unchanged)</span>'
            html += f'        <tr><td>{html_text(key)}</td><td>{before_val}</td><td>{after_display}</td></tr>\n'
        html += '    </table>\n'
    
    # Embedded files table
    if extracted_files:
        html += '''
    <h2>Embedded Files</h2>
    <p>The following files were extracted before scrubbing:</p>
    <table>
        <tr><th>File</th><th>Size</th><th>Preview</th></tr>
'''
        for f in extracted_files:
            name = f.get('name', 'unknown')
            path = f.get('path', '')
            size = f.get('size', 0)
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            
            href = relative_href(data_dir_name, name)
            if is_image(name):
                preview = f'<img src="{html_attr(href)}" class="preview" alt="{html_attr(name)}"/>'
            else:
                preview = '—'
            
            html += f'        <tr><td><a href="{html_attr(href)}">{html_text(name)}</a></td><td>{html_text(size_str)}</td><td>{preview}</td></tr>\n'
        html += '    </table>\n'
    
    # Structure info - always show if we have any structure data
    struct_before = before.get('structure_info', {})
    if struct_before and 'page_count' in struct_before:
        html += '''
    <h2>Document Structure</h2>
    <table>
        <tr><th>Property</th><th>Value</th></tr>
'''
        # Always show page count
        html += f'        <tr><td>Page Count</td><td>{html_text(struct_before["page_count"])}</td></tr>\n'
        
        # Show page sizes if available
        page_sizes = struct_before.get('page_sizes', [])
        if page_sizes:
            sizes_str = ', '.join(str(s) for s in page_sizes[:3])
            if len(page_sizes) > 3:
                sizes_str += f' + {len(page_sizes) - 3} more'
            html += f'        <tr><td>Page Sizes</td><td>{html_text(sizes_str)}</td></tr>\n'
        
        # Show boolean properties with Yes/No
        bookmarks = struct_before.get('has_bookmarks', False)
        bookmark_count = struct_before.get('bookmark_count', 0)
        html += f'        <tr><td>Bookmarks</td><td>{"Yes (" + str(bookmark_count) + ")" if bookmarks else "No"}</td></tr>\n'
        
        html += f'        <tr><td>Form Fields</td><td>{"Yes" if struct_before.get("has_forms") else "No"}</td></tr>\n'
        html += f'        <tr><td>Digital Signatures</td><td>{"Yes" if struct_before.get("has_signatures") else "No"}</td></tr>\n'
        html += f'        <tr><td>Annotations</td><td>{"Yes" if struct_before.get("has_annotations") else "No"}</td></tr>\n'
        
        html += '    </table>\n'
    
    # Binary Resources section - ALL embedded binary content
    bin_before = before.get('binary_resources', {})
    bin_after = after.get('binary_resources', {})
    
    # Check if there's anything to show
    has_binary = any([
        bin_before.get('icc_profiles'),
        bin_before.get('digital_signatures'),
        bin_before.get('thumbnails'),
        bin_before.get('embedded_fonts'),
        bin_before.get('embedded_images'),
        bin_before.get('javascript'),
        bin_before.get('form_fields')
    ])
    
    if has_binary or bin_before:
        html += '''
    <h2>Binary Resources</h2>
    <p class="meta">Embedded binary content and resources</p>
'''
        # ICC Color Profiles
        icc = bin_before.get('icc_profiles', [])
        html += f'    <h3>ICC Color Profiles ({len(icc)})</h3>\n'
        if icc:
            html += '    <table>\n        <tr><th>XREF</th><th>Size</th></tr>\n'
            for profile in icc:
                size = profile.get('size_human', f"{profile.get('size', 0)} bytes")
                html += f'        <tr><td>#{html_text(profile.get("xref"))}</td><td>{html_text(size)}</td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
        
        # Digital Signatures
        sigs = bin_before.get('digital_signatures', [])
        html += f'    <h3>Digital Signatures ({len(sigs)})</h3>\n'
        if sigs:
            html += '    <table>\n        <tr><th>XREF</th><th>Type</th></tr>\n'
            for sig in sigs:
                html += f'        <tr><td>#{html_text(sig.get("xref"))}</td><td>{html_text(sig.get("type", "Unknown"))}</td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
        
        # Thumbnails
        thumbs = bin_before.get('thumbnails', [])
        html += f'    <h3>Thumbnails ({len(thumbs)})</h3>\n'
        if thumbs:
            html += '    <table>\n        <tr><th>XREF</th><th>Size</th></tr>\n'
            for t in thumbs:
                size = t.get('size_human', f"{t.get('size', 0)} bytes")
                html += f'        <tr><td>#{html_text(t.get("xref"))}</td><td>{html_text(size)}</td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
        
        # Embedded Fonts
        fonts = bin_before.get('embedded_fonts', [])
        html += f'    <h3>Embedded Fonts ({len(fonts)})</h3>\n'
        if fonts:
            html += '    <table>\n        <tr><th>Name</th><th>Type</th><th>Encoding</th><th>Embedded</th></tr>\n'
            for f in fonts:
                html += f'        <tr><td>{html_text(f.get("name", "Unknown"))}</td><td>{html_text(f.get("type", ""))}</td><td>{html_text(f.get("encoding", ""))}</td><td>{html_text(f.get("embedded", ""))}</td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
        
        # Embedded Images - clickable rows with popover
        images = bin_before.get('embedded_images', [])
        html += f'    <h3>Embedded Images ({len(images)})</h3>\n'
        if images:
            html += '    <table>\n        <tr><th>XREF</th><th>Dimensions</th><th>Size</th><th>Colorspace</th><th>Format</th></tr>\n'
            for img in images:
                dims = f'{img.get("width", 0)}x{img.get("height", 0)}'
                size = img.get('size_human', '')
                ext = img.get('ext', 'png')
                colorspace = img.get('colorspace', 'Unknown')
                
                note = img.get('note', '')
                fmt = ext.upper()
                if note:
                    fmt += f' ({note})'
                html += f'        <tr><td>#{html_text(img.get("xref"))}</td><td>{html_text(dims)}</td><td>{html_text(size)}</td><td>{html_text(colorspace)}</td><td>{html_text(fmt)}</td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
        
        # JavaScript
        js = bin_before.get('javascript', [])
        html += f'    <h3>JavaScript ({len(js)})</h3>\n'
        if js:
            html += '    <table>\n        <tr><th>XREF</th><th>Preview</th></tr>\n'
            for j in js:
                preview = html_text(j.get('preview', ''))
                html += f'        <tr><td>#{html_text(j.get("xref"))}</td><td><code>{preview}</code></td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
        
        # Form Fields
        forms = bin_before.get('form_fields', [])
        html += f'    <h3>Form Fields ({len(forms)})</h3>\n'
        if forms:
            html += '    <table>\n        <tr><th>Name</th><th>Type</th><th>Value</th></tr>\n'
            for f in forms:
                val = html_text(f.get('value', ''))
                html += f'        <tr><td>{html_text(f.get("name", ""))}</td><td>{html_text(f.get("type", ""))}</td><td>{val}</td></tr>\n'
            html += '    </table>\n'
        else:
            html += '    <p><em>(none)</em></p>\n'
    
    html += '''
</body>
</html>
'''
    
    return html, long_values


def scrub_all_metadata(input_path: str, output_path: str, data_dir: str = None) -> dict:
    """
    Remove all metadata from the PDF document and generate a comprehensive report.
    
    Args:
        input_path: Path to source PDF
        output_path: Path to save scrubbed PDF
        data_dir: Optional directory to save extracted attachments and long values
    
    Returns dict with:
        - success: bool
        - before: Full metadata before scrub
        - after: Full metadata after scrub
        - extracted_files: List of extracted files (if data_dir provided)
        - report_html: HTML report content
        - log: Debug log entries
    """
    debug_log = []
    debug_log.append("Starting metadata scrub")
    warnings = []

    extracted_files = []

    def _prepare_data_dir(path: str) -> str:
        abs_path = os.path.abspath(path)
        if os.path.lexists(abs_path) and os.path.islink(abs_path):
            raise ValueError(f"data_dir contains a symlink component: {path}")
        os.makedirs(abs_path, exist_ok=True)
        if os.path.islink(abs_path):
            raise ValueError(f"data_dir contains a symlink component: {path}")
        return os.path.realpath(abs_path)

    def _contained_path(base_real: str, name: str) -> str | None:
        candidate = os.path.join(base_real, name)
        candidate_real = os.path.realpath(candidate)
        try:
            if os.path.commonpath([base_real, candidate_real]) != base_real:
                return None
        except ValueError:
            return None
        return candidate_real
    
    try:
        # 1. Extract all metadata BEFORE scrubbing
        debug_log.append("Extracting metadata (before)...")
        before = extract_all_metadata(input_path)
        
        # 2. Extract embedded files if data_dir provided
        if data_dir:
            data_dir_real = _prepare_data_dir(data_dir)
            debug_log.append(f"Extracting embedded files to: {data_dir}")
            
            try:
                doc = fitz.open(input_path)
                try:
                    embfile_count = doc.embfile_count()

                    for i in range(embfile_count):
                        info = doc.embfile_info(i)
                        name = info.get('name', f'file_{i}')

                        # Sanitize filename
                        safe_name = "".join(c for c in name if c.isalnum() or c in '._-')
                        if not safe_name:
                            safe_name = f"file_{i}"

                        # Handle duplicates
                        base, ext = os.path.splitext(safe_name)
                        counter = 1
                        final_name = safe_name
                        while os.path.exists(os.path.join(data_dir, final_name)):
                            final_name = f"{base}_{counter}{ext}"
                            counter += 1

                        # Extract file content
                        file_data = doc.embfile_get(i)
                        file_path = _contained_path(data_dir_real, final_name)
                        if file_path is None:
                            debug_log.append(
                                f"  Skipped {final_name}: path escapes data_dir")
                            continue

                        with open(file_path, 'wb') as f:
                            f.write(file_data)

                        extracted_files.append({
                            'name': final_name,
                            'path': file_path,
                            'size': len(file_data)
                        })
                        debug_log.append(f"  Extracted: {final_name} ({len(file_data)} bytes)")
                finally:
                    doc.close()
            except Exception as e:
                debug_log.append(f"Embedded file extraction failed: {e}")
        
        # 3. Open document and clear metadata
        with fitz.open(input_path) as doc:
            old_metadata = doc.metadata
            debug_log.append(f"Original metadata keys: {list(old_metadata.keys())}")

            # Clear standard metadata
            doc.set_metadata({})
            debug_log.append("Standard metadata cleared")

            # Clear XMP by setting empty XML
            try:
                doc.set_xml_metadata("")
                debug_log.append("XMP metadata cleared")
            except Exception as _e:
                debug_log.append(f"XMP metadata clearing not available: {_e}")
                warnings.append(f"XMP metadata may not be fully cleared: {_e}")

            # Delete embedded files from scrubbed version
            try:
                while doc.embfile_count() > 0:
                    doc.embfile_del(0)
                debug_log.append("Embedded files removed from output")
            except Exception:
                pass

            # Remove annotations (reviewer names, comment text, timestamps).
            # Use the first_annot / returned-next pattern — delete_annot() returns the
            # next handle (or None) and invalidates the deleted wrapper, so iterating a
            # snapshot list would call delete_annot on stale wrappers.
            try:
                annot_count = 0
                for page in doc:
                    annot = page.first_annot
                    while annot:
                        annot = page.delete_annot(annot)
                        annot_count += 1
                debug_log.append(f"Removed {annot_count} annotation(s)")
            except Exception as e:
                debug_log.append(f"Annotation removal failed: {e}")
                warnings.append(f"Annotation removal failed: {e}")

            # Remove catalog-level keys that can carry identifying data.
            # /AcroForm   — form fields with author/app info
            # /OpenAction — launch/JS actions (author-fingerprintable)
            # /AA         — additional actions (page-open scripts etc.)
            # /PieceInfo  — app-private data (often author/app fingerprints)
            # /Outlines is the bookmark tree (functional navigation content) — not removed.
            # /StructTreeRoot contains accessibility structure (Alt text, ActualText) —
            #   not removed as content is more important than metadata risk.
            # /Names is handled separately below (targeted sub-key removal).
            # garbage=4 below will collect orphaned objects.
            try:
                catalog = doc.pdf_catalog()
                if catalog:
                    for key in ("AcroForm", "OpenAction", "AA", "PieceInfo"):
                        doc.xref_set_key(catalog, key, "null")
                    debug_log.append("Catalog privacy keys cleared (AcroForm, OpenAction, AA, PieceInfo)")

                    # Targeted /Names scrub: remove only /JavaScript and /EmbeddedFiles
                    # sub-trees; preserve /Dests (named destination anchors for TOC links).
                    try:
                        names_type, names_val = doc.xref_get_key(catalog, "Names")
                        if names_type == "xref":
                            names_xref = int(names_val.split()[0])
                            for sub_key in ("JavaScript", "EmbeddedFiles"):
                                doc.xref_set_key(names_xref, sub_key, "null")
                            debug_log.append("Names sub-keys cleared: JavaScript, EmbeddedFiles (Dests preserved)")
                        elif names_type == "dict" and names_val not in ("null", ""):
                            # Inline /Names — cannot selectively edit; nuke the whole tree as fallback
                            doc.xref_set_key(catalog, "Names", "null")
                            debug_log.append("Names dict removed (inline — Dests could not be preserved)")
                            warnings.append("Document named destinations removed (inline /Names dict cannot be selectively cleared)")
                        # else: /Names absent or already null, nothing to do
                    except Exception as e:
                        debug_log.append(f"Names JavaScript/EmbeddedFiles removal failed: {e}")
                        warnings.append(f"Could not clear /Names/JavaScript: {e}")
            except Exception as e:
                debug_log.append(f"Catalog key removal failed: {e}")
                warnings.append(f"Catalog privacy-key removal failed: {e}")

            # 4. Save with maximum cleaning
            debug_log.append("Saving with clean=True, garbage=4, deflate=True...")
            doc.save(output_path, garbage=4, clean=True, deflate=True)
        
        debug_log.append("Scrubbed document saved")
        
        # 5. Extract metadata AFTER scrubbing
        debug_log.append("Extracting metadata (after)...")
        after = extract_all_metadata(output_path)
        
        # 6. Generate HTML report
        source_filename = os.path.basename(input_path)
        data_dir_name = os.path.basename(data_dir) if data_dir else "scrub_data"
        
        report_html, long_values = generate_scrub_report(
            before, after, extracted_files, source_filename, data_dir_name
        )
        
        # Save long values to files
        if data_dir and long_values:
            data_dir_real = _prepare_data_dir(data_dir)
            for filename, content in long_values.items():
                filepath = _contained_path(data_dir_real, filename)
                if filepath is None:
                    debug_log.append(f"  Skipped long value: {filename} escapes data_dir")
                    continue
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                debug_log.append(f"  Saved long value: {filename}")
        
        return {
            'success': True,
            'before': before,
            'after': after,
            'extracted_files': extracted_files,
            'report_html': report_html,
            'log': debug_log,
            'warnings': warnings,
        }
        
    except Exception as e:
        import traceback
        debug_log.append(f"Metadata scrub failed: {e}")
        debug_log.append(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'log': debug_log,
            'warnings': warnings,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Batch Operations  (Week 7 Day 3)
# ──────────────────────────────────────────────────────────────────────────────

_MAX_BATCH_REPLACEMENTS = 500   # hard cap to prevent resource exhaustion
_MAX_REGEX_MATCHES_PER_PAGE = 1000
_MAX_REGEX_PATTERN_LEN = 500


@monitor_performance("batch_replace")
def batch_replace(input_path: str, output_path: str,
                  replacements: list,
                  progress_callback=None) -> dict:
    """
    Apply multiple text replacements to a PDF in a single pass.

    Each replacement is processed in order; the output of one becomes the
    input for the next so that edits accumulate correctly.

    Args:
        input_path:        Path to the source PDF.
        output_path:       Path where the final result is written.
        replacements:      list of dicts (max 500), each with:
                             "target_text":      str  (required)
                             "replacement_text": str  (required)
                             "page_number":      int  1-based (optional)
                             "manual_overrides": dict (optional)
        progress_callback: Optional callable(completed: int, total: int).

    Returns:
        dict with "success", "applied", "skipped", "results", "message".
    """
    import tempfile, shutil, os

    if not replacements:
        shutil.copy2(input_path, output_path)
        return {"success": True, "applied": 0, "skipped": 0, "results": [],
                "message": "No replacements specified"}

    if len(replacements) > _MAX_BATCH_REPLACEMENTS:
        return {"success": False, "applied": 0, "skipped": len(replacements),
                "results": [],
                "message": f"Too many replacements (max {_MAX_BATCH_REPLACEMENTS})"}

    total = len(replacements)
    results = []
    applied = 0
    skipped = 0
    current_src = input_path
    # Track only the *previous* temp file so it can be deleted as soon as we
    # advance current_src.  Avoids O(N × file_size) disk accumulation.
    previous_tmp: str | None = None

    try:
        for i, rep in enumerate(replacements):
            target = rep.get("target_text", "")
            replacement = rep.get("replacement_text", "")
            page_number = rep.get("page_number")
            overrides = rep.get("manual_overrides") or {}

            if not target:
                results.append({"index": i, "success": False, "message": "Empty target_text"})
                skipped += 1
                if progress_callback:
                    progress_callback(i + 1, total)
                continue

            if page_number:
                pages_to_try = [page_number]
            else:
                with fitz.open(current_src) as _doc:
                    pages_to_try = list(range(1, len(_doc) + 1))

            rep_result = {"index": i, "success": False, "message": "Not found on any page"}
            for pg in pages_to_try:
                _fd, tmp_out = tempfile.mkstemp(suffix=".pdf", prefix="marcedit_batch_")
                os.close(_fd)

                r = replace_text_in_pdf(
                    input_path=current_src,
                    output_path=tmp_out,
                    target_text=target,
                    replacement_text=replacement,
                    page_number=pg,
                    manual_overrides=overrides,
                )

                if r.get("success"):
                    # Delete the now-superseded intermediate temp file immediately
                    # to avoid O(N × file_size) disk accumulation.
                    if previous_tmp and previous_tmp != input_path:
                        try:
                            os.unlink(previous_tmp)
                        except OSError:
                            pass
                    previous_tmp = current_src if current_src != input_path else None
                    current_src = tmp_out
                    rep_result = {"index": i, "success": True, "page": pg,
                                  "message": r.get("message", "OK")}
                    applied += 1
                    break
                else:
                    # This tmp wasn't used — clean it up now.
                    try:
                        os.unlink(tmp_out)
                    except OSError:
                        pass

            if not rep_result["success"]:
                skipped += 1

            results.append(rep_result)

            if progress_callback:
                progress_callback(i + 1, total)

        shutil.copy2(current_src, output_path)

        return {
            "success": True,
            "applied": applied,
            "skipped": skipped,
            "results": results,
            "message": f"Batch complete: {applied}/{total} replacements applied",
        }

    except Exception as e:
        _log.error("batch_replace failed", error=str(e))
        return {
            "success": False,
            "applied": applied,
            "skipped": skipped,
            "results": results,
            "message": f"Batch failed: {e}",
        }
    finally:
        if previous_tmp and previous_tmp != input_path and previous_tmp != output_path:
            try:
                os.unlink(previous_tmp)
            except OSError:
                pass
        if current_src and current_src != input_path and current_src != output_path:
            try:
                os.unlink(current_src)
            except OSError:
                pass
        gc.collect()


@monitor_performance("regex_replace")
def regex_replace(input_path: str, output_path: str,
                  pattern: str, replacement: str,
                  flags: int = 0,
                  page_range: tuple = None,
                  progress_callback=None) -> dict:
    """
    Replace text matching a regex pattern throughout a PDF.

    The replacement string supports \\1, \\2 … back-references and the full
    re.sub() syntax.  Each match is replaced via the existing
    replace_text_in_pdf() logic so font matching and layout preservation are
    inherited for free.

    Args:
        input_path:        Path to the source PDF.
        output_path:       Path for the result.
        pattern:           Regex pattern string (max 500 chars, re module syntax).
        replacement:       Replacement string (supports back-references).
        flags:             re module flags (e.g. re.IGNORECASE).
                           re.UNICODE is always added automatically.
        page_range:        Optional (start, end) tuple of 1-based page numbers.
        progress_callback: Optional callable(page: int, total_pages: int).

    Returns:
        dict with "success", "replacements", "matches", "message".
    """
    import re, tempfile, shutil, os

    if len(pattern) > _MAX_REGEX_PATTERN_LEN:
        return {"success": False, "replacements": 0, "matches": [],
                "message": f"Regex pattern too long (max {_MAX_REGEX_PATTERN_LEN} chars)"}

    # Validate flags — only accept the well-known re module values.
    # Arbitrary integer flags could set internal bits (re.DEBUG, re.TEMPLATE, …)
    # with undefined behaviour, and passing 0x20000000-style values bypasses
    # Python's public API surface.
    # re.LOCALE is excluded: LOCALE|UNICODE raises ValueError (not re.error),
    # which would propagate uncaught since the except below only catches re.error.
    _ALLOWED_FLAGS = (re.IGNORECASE | re.MULTILINE | re.DOTALL |
                      re.VERBOSE | re.ASCII | re.UNICODE)
    if flags & ~_ALLOWED_FLAGS:
        return {"success": False, "replacements": 0, "matches": [],
                "message": f"Invalid regex flags: only re.IGNORECASE/MULTILINE/DOTALL/VERBOSE/ASCII/UNICODE are allowed"}

    try:
        regex = re.compile(pattern, flags | re.UNICODE)
    except re.error as e:
        return {"success": False, "replacements": 0, "matches": [],
                "message": f"Invalid regex: {e}"}

    matches_log = []
    total_replaced = 0
    current_src = input_path
    # Track only the *previous* temp file so it can be deleted as soon as we
    # advance current_src.  The old O(N) disk accumulation is gone.
    previous_tmp: str | None = None

    try:
        with fitz.open(input_path) as _doc:
            total_pages = len(_doc)

        if page_range:
            try:
                start_pg = max(1, int(page_range[0]))
                end_pg = min(total_pages, int(page_range[1]))
            except (TypeError, ValueError, IndexError) as _e:
                return {"success": False, "replacements": 0, "matches": [],
                        "message": f"Invalid page_range: {_e}"}
        else:
            start_pg, end_pg = 1, total_pages

        for pg in range(start_pg, end_pg + 1):
            if progress_callback:
                progress_callback(pg, total_pages)

            with fitz.open(current_src) as doc:
                page_text = doc[pg - 1].get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)

            page_matches = list(regex.finditer(page_text))
            if len(page_matches) > _MAX_REGEX_MATCHES_PER_PAGE:
                page_matches = page_matches[:_MAX_REGEX_MATCHES_PER_PAGE]
                _log.warning("regex_replace match limit hit",
                             page=pg, limit=_MAX_REGEX_MATCHES_PER_PAGE)

            try:
                reverse_order = any(
                    m.group(0) and m.group(0) in m.expand(replacement)
                    for m in page_matches
                )
            except re.error:
                reverse_order = False
            ordered_matches = reversed(page_matches) if reverse_order else page_matches
            replaced_before_by_text = {}

            for m in ordered_matches:
                old_text = m.group(0)
                try:
                    new_text = m.expand(replacement)
                except re.error:
                    # Invalid backreference in replacement — skip this match.
                    new_text = old_text
                if old_text == new_text:
                    continue

                try:
                    original_occurrence_index = len(list(re.finditer(re.escape(old_text), page_text[:m.start()])))
                    occurrence_index = original_occurrence_index
                    if not reverse_order:
                        occurrence_index = max(
                            0,
                            original_occurrence_index - replaced_before_by_text.get(old_text, 0),
                        )
                except re.error:
                    occurrence_index = None

                if occurrence_index is None:
                    _log.warning("regex_replace match limit hit",
                                 page=pg, target=old_text)

                _fd, tmp_out = tempfile.mkstemp(suffix=".pdf", prefix="marcedit_regex_")
                os.close(_fd)

                r = replace_text_in_pdf(
                    input_path=current_src,
                    output_path=tmp_out,
                    target_text=old_text,
                    replacement_text=new_text,
                    page_number=pg,
                    occurrence_index=occurrence_index,
                )

                if r.get("success"):
                    # Delete the now-superseded intermediate temp file immediately
                    # to avoid O(N × file_size) disk accumulation.
                    if previous_tmp and previous_tmp != input_path:
                        try:
                            os.unlink(previous_tmp)
                        except OSError:
                            pass
                    previous_tmp = current_src if current_src != input_path else None
                    current_src = tmp_out
                    matches_log.append((pg, old_text, new_text))
                    total_replaced += 1
                    if not reverse_order:
                        replaced_before_by_text[old_text] = (
                            replaced_before_by_text.get(old_text, 0) + 1
                        )
                else:
                    # This tmp wasn't used — clean it up now.
                    try:
                        os.unlink(tmp_out)
                    except OSError:
                        pass

        shutil.copy2(current_src, output_path)

        return {
            "success": True,
            "replacements": total_replaced,
            "matches": matches_log,
            "message": f"Regex replace complete: {total_replaced} replacements made",
        }

    except Exception as e:
        _log.error("regex_replace failed", error=str(e))
        return {
            "success": False,
            "replacements": total_replaced,
            "matches": matches_log,
            "message": f"Regex replace failed: {e}",
        }
    finally:
        # Clean up the last intermediate temp files if they weren't copied to output_path.
        if previous_tmp and previous_tmp != input_path and previous_tmp != output_path:
            try:
                os.unlink(previous_tmp)
            except OSError:
                pass
        if current_src and current_src != input_path and current_src != output_path:
            try:
                os.unlink(current_src)
            except OSError:
                pass
        gc.collect()


@monitor_performance("apply_template")
def apply_template(input_path: str, output_path: str,
                   placeholders: dict,
                   page_range: tuple = None,
                   delimiter_open: str = "{{",
                   delimiter_close: str = "}}") -> dict:
    """
    Replace template placeholders in a PDF with supplied values.

    Scans all pages (or the given page_range) for strings matching
    ``{{KEY}}`` and replaces them with the corresponding value from
    *placeholders*.  Keys are matched case-sensitively by default.

    Args:
        input_path:      Path to the source PDF.
        output_path:     Path for the result.
        placeholders:    dict mapping key → replacement value (str).
                         Keys must be printable ASCII without control characters.
        page_range:      Optional (start, end) 1-based inclusive page numbers.
        delimiter_open:  Opening delimiter (default "{{").
        delimiter_close: Closing delimiter (default "}}").

    Returns:
        dict with "success", "applied", "not_found", "results", "message".
    """
    import re, tempfile, shutil, os

    if not placeholders:
        shutil.copy2(input_path, output_path)
        return {"success": True, "applied": 0, "not_found": [], "results": [],
                "message": "No placeholders provided"}

    # Validate placeholder keys: must be non-empty printable strings without
    # control characters or path separators (security hardening).
    _bad_chars = set('\x00\n\r\t/\\')
    for key in placeholders:
        if not key or not isinstance(key, str):
            return {"success": False, "applied": 0,
                    "not_found": list(placeholders), "results": [],
                    "message": "Placeholder keys must be non-empty strings"}
        if any(c in _bad_chars for c in key) or not key.isprintable():
            return {"success": False, "applied": 0,
                    "not_found": list(placeholders), "results": [],
                    "message": f"Invalid characters in placeholder key: {key!r}"}

    escaped_open = re.escape(delimiter_open)
    escaped_close = re.escape(delimiter_close)
    keys_pattern = "|".join(re.escape(k) for k in placeholders)
    token_re = re.compile(f"{escaped_open}({keys_pattern}){escaped_close}")

    current_src = input_path
    tmp_files = []
    applied = 0
    results = []
    matched_keys = set()

    try:
        with fitz.open(input_path) as _doc:
            total_pages = len(_doc)

        if page_range:
            try:
                start_pg = max(1, int(page_range[0]))
                end_pg = min(total_pages, int(page_range[1]))
            except (TypeError, ValueError, IndexError) as _e:
                return {"success": False, "applied": 0,
                        "not_found": list(placeholders.keys()), "results": [],
                        "message": f"Invalid page_range: {_e}"}
        else:
            start_pg, end_pg = 1, total_pages

        for pg in range(start_pg, end_pg + 1):
            with fitz.open(current_src) as doc:
                page_text = doc[pg - 1].get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE)

            for m in token_re.finditer(page_text):
                key = m.group(1)
                token = m.group(0)
                value = str(placeholders[key])

                _fd, tmp_out = tempfile.mkstemp(suffix=".pdf", prefix="marcedit_tmpl_")
                os.close(_fd)
                tmp_files.append(tmp_out)

                r = replace_text_in_pdf(
                    input_path=current_src,
                    output_path=tmp_out,
                    target_text=token,
                    replacement_text=value,
                    page_number=pg,
                )

                if r.get("success"):
                    current_src = tmp_out
                    applied += 1
                    matched_keys.add(key)
                    results.append({"key": key, "value": value, "page": pg, "success": True})
                else:
                    results.append({"key": key, "value": value, "page": pg, "success": False,
                                    "message": r.get("message", "")})

        shutil.copy2(current_src, output_path)
        not_found = [k for k in placeholders if k not in matched_keys]

        return {
            "success": True,
            "applied": applied,
            "not_found": not_found,
            "results": results,
            "message": f"Template applied: {applied} substitutions, {len(not_found)} keys not found",
        }

    except Exception as e:
        _log.error("apply_template failed", error=str(e))
        return {
            "success": False,
            "applied": applied,
            "not_found": list(placeholders.keys()),
            "results": results,
            "message": f"Template failed: {e}",
        }
    finally:
        for f in tmp_files:
            try:
                if f != output_path and os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass
        gc.collect()
