"""
Visual Font Matcher - Pixel-based font matching for PDF text replacement.

This module provides visual matching to find the best system font when an
embedded PDF font cannot be reused. It works by:
1. Extracting individual character bitmaps from the PDF
2. Rendering the same characters with candidate fonts
3. Scoring similarity using Intersection over Union (IoU)
4. Returning the best matching font
"""

import os
import fitz  # PyMuPDF


class VisualFontMatcher:
    """
    Matches PDF text appearance to system fonts using pixel comparison.
    """
    
    # Default path to curated font list
    # Path relative to python_site/editor_pkg -> python_site -> Marcedit -> Sources -> Marcedit -> assets
    # OR in app bundle: Marcedit_Marcedit.bundle/python_site/editor_pkg -> bundle/assets
    # We'll try multiple possible locations
    DEFAULT_FONT_LIST = None  # Will be resolved dynamically
    
    # Characters to use for matching (chosen for their distinctive shapes)
    # - Uppercase for consistency
    # - Mix of round, straight, and diagonal shapes
    MATCH_CHARS = ['C', 'M', 'A', 'E', 'R', 'O', 'I', 'N', 'S', 'T']
    
    def __init__(self, font_list_path: str = None, exhaustive: bool = False):
        """
        Initialize the matcher.
        
        Args:
            font_list_path: Path to text file with font names (one per line).
                           Defaults to assets/searched-fonts.txt.
            exhaustive: If True, searches ALL system fonts instead of the curated list.
        """
        self.exhaustive = exhaustive
        self.font_list_path = font_list_path or self.DEFAULT_FONT_LIST
        self.font_names = []
        self.font_paths = {}  # name -> path mapping
        
        if not self.exhaustive:
            self._load_font_list()
            
        self._resolve_font_paths()
    
    def _load_font_list(self):
        """Load the curated list of font names to search."""
        # If a path was provided, use it
        if self.font_list_path and os.path.exists(self.font_list_path):
            with open(self.font_list_path, 'r') as f:
                self.font_names = [line.strip() for line in f if line.strip()]
            return
        
        # Try multiple possible locations
        pkg_dir = os.path.dirname(__file__)  # python_site/editor_pkg
        possible_paths = [
            # Dev environment: project_root/assets/
            os.path.join(pkg_dir, "..", "..", "..", "..", "assets", "searched-fonts.txt"),
            # App bundle: bundle/assets/
            os.path.join(pkg_dir, "..", "assets", "searched-fonts.txt"),
            # Fallback: next to python_site
            os.path.join(pkg_dir, "..", "..", "assets", "searched-fonts.txt"),
        ]
        
        for path in possible_paths:
            normalized = os.path.normpath(path)
            if os.path.exists(normalized):
                with open(normalized, 'r') as f:
                    self.font_names = [line.strip() for line in f if line.strip()]
                self.font_list_path = normalized
                return
    
    def _resolve_font_paths(self):
        """
        Map font names to system font paths.
        Uses CoreText on macOS if available, otherwise scans standard directories.
        """
        # Try CoreText first (macOS, App Store safe)
        try:
            self._resolve_via_coretext()
            return
        except ImportError:
            pass
        
        # Fallback: scan standard font directories
        self._resolve_via_directory_scan()
    
    def _resolve_via_coretext(self):
        """Use CoreText to find font paths (macOS only)."""
        from CoreText import (
            CTFontCollectionCreateFromAvailableFonts,
            CTFontCollectionCreateMatchingFontDescriptors,
            CTFontDescriptorCopyAttribute,
            kCTFontDisplayNameAttribute,
            kCTFontFamilyNameAttribute,
            kCTFontURLAttribute,
        )
        
        collection = CTFontCollectionCreateFromAvailableFonts(None)
        descriptors = CTFontCollectionCreateMatchingFontDescriptors(collection)
        
        if not descriptors:
            return
        
        # Build a lookup of display/family names to paths
        name_to_path = {}
        for descriptor in descriptors:
            display_name = CTFontDescriptorCopyAttribute(descriptor, kCTFontDisplayNameAttribute)
            family_name = CTFontDescriptorCopyAttribute(descriptor, kCTFontFamilyNameAttribute)
            font_url = CTFontDescriptorCopyAttribute(descriptor, kCTFontURLAttribute)
            
            if font_url:
                path = font_url.path() if hasattr(font_url, 'path') else str(font_url)
                if display_name:
                    name_to_path[str(display_name).lower()] = path
                if family_name:
                    name_to_path[str(family_name).lower()] = path
        
        if self.exhaustive:
            # Load ALL available system fonts
            for name, path in name_to_path.items():
                self.font_paths[name] = path
            return

        # Map our font list to paths
        for name in self.font_names:
            key = name.lower()
            if key in name_to_path:
                self.font_paths[name] = name_to_path[key]
            else:
                # Try partial match
                for k, v in name_to_path.items():
                    if key in k or k in key:
                        self.font_paths[name] = v
                        break
    
    def _resolve_via_directory_scan(self):
        """Fallback: scan standard font directories."""
        font_dirs = [
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.expanduser("~/Library/Fonts"),
        ]
        
        # Build index of available fonts
        available = {}
        for font_dir in font_dirs:
            if not os.path.isdir(font_dir):
                continue
            for root, dirs, files in os.walk(font_dir):
                for f in files:
                    if f.endswith(('.ttf', '.ttc', '.otf', '.dfont')):
                        name_key = os.path.splitext(f)[0].lower()
                        available[name_key] = os.path.join(root, f)
        
        if self.exhaustive:
             self.font_paths.update(available)
             return

        # Map our font list to paths
        for name in self.font_names:
            key = name.lower().replace(' ', '')
            for avail_key, path in available.items():
                if key in avail_key or avail_key in key:
                    self.font_paths[name] = path
                    break
    
    def _is_font_serif_by_name(self, font_name: str) -> bool | None:
        """
        Determine if a font is serif based on its name.
        Returns True for serif, False for sans-serif, None if unknown.
        """
        fn_lower = font_name.lower()
        
        # Known serif fonts
        serif_fonts = ['times', 'georgia', 'garamond', 'palatino', 'cambria', 
                       'baskerville', 'book', 'charter', 'century', 
                       'bodoni', 'didot', 'caslon', 'minion', 'cochin', 'hoefler',
                       'rockwell', 'clarendon', 'new york', 'courier', 'slab']
        
        # Known sans-serif fonts
        sans_fonts = ['arial', 'helvetica', 'verdana', 'tahoma', 'calibri', 
                      'segoe', 'gothic', 'sans', 'gill', 'futura', 'avenir',
                      'roboto', 'lato', 'montserrat', 'nunito',
                      'ubuntu', 'trebuchet', 'franklin', 'myriad', 'optima']
        
        for font in serif_fonts:
            if font in fn_lower:
                return True
        
        for font in sans_fonts:
            if font in fn_lower:
                return False
        
        return None  # Unknown
    
    def detect_serif_visually(self, page, text: str, font_name: str) -> bool | None:
        """
        Analyze character bitmaps to detect if the text is serif or sans-serif.
        
        This is useful when PDF metadata is unreliable (e.g., obfuscated fonts).
        
        Detection method:
        1. Extract bitmap for letters like 'I', 'T', or 'M' (clear serif indicators)
        2. Analyze horizontal pixels at top and bottom rows
        3. Serif fonts have horizontal extensions (feet) at letter extremities
        4. Sans-serif fonts have more uniform vertical strokes
        
        Returns:
            True if serif detected, False if sans-serif, None if unable to determine
        """
        # Try to extract character bitmaps
        raw = page.get_text('rawdict')
        
        # Characters that clearly show serifs - 'T', 'M', 'H' are most reliable. {'I', 'L'} removed as they can be misleading.
        serif_test_chars = ['T', 'M', 'H', 'E']
        
        for block in raw.get('blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    chars = span.get('chars', [])
                    # Reconstruct text from chars (span.text is often empty in obfuscated PDFs)
                    span_text = ''.join([c.get('c', '') for c in chars]) if chars else span.get('text', '')
                    if text not in span_text:
                        continue
                    for char_info in chars:
                        c = char_info.get('c', '')
                        if c not in serif_test_chars:
                            continue

                        # Get bitmap of this character
                        char_bbox = char_info.get('bbox')
                        if not char_bbox:
                            continue
                        bbox = fitz.Rect(char_bbox)
                        if bbox.width < 5 or bbox.height < 5:
                            continue
                        
                        pix = page.get_pixmap(clip=bbox, colorspace=fitz.csGRAY)
                        
                        if pix.width < 5 or pix.height < 5:
                            continue
                        
                        # Analyze top and bottom rows for horizontal "feet" (serifs)
                        # Serif fonts have wider ink coverage at top/bottom
                        # Sans fonts have uniform vertical strokes
                        
                        samples = pix.samples
                        w, h = pix.width, pix.height
                        threshold = 180  # Pixel values below this are "ink"
                        
                        # Count ink pixels in top 20% vs middle 20%
                        top_rows = max(1, h // 5)
                        mid_start = h // 3
                        mid_end = 2 * h // 3
                        
                        top_ink = 0
                        mid_ink = 0
                        
                        # Top section
                        for y in range(top_rows):
                            for x in range(w):
                                idx = y * w + x
                                if idx < len(samples) and samples[idx] < threshold:
                                    top_ink += 1
                        
                        # Middle section
                        for y in range(mid_start, mid_end):
                            for x in range(w):
                                idx = y * w + x
                                if idx < len(samples) and samples[idx] < threshold:
                                    mid_ink += 1
                        
                        # Normalize by area
                        top_area = top_rows * w
                        mid_area = (mid_end - mid_start) * w
                        
                        if top_area == 0 or mid_area == 0:
                            continue
                        
                        top_density = top_ink / top_area
                        mid_density = mid_ink / mid_area
                        
                        # For 'I' character:
                        # - Serif: top is WIDER than middle (has horizontal feet)
                        # - Sans: top is SIMILAR or narrower than middle
                        if c == 'I':
                            # Serif 'I' has top density >= middle (wide serifs)
                            # Sans 'I' has top density < middle (thin vertical stroke)
                            ratio = top_density / mid_density if mid_density > 0 else 0
                            if ratio > 0.8:
                                return True  # Serif (top spread wider)
                            elif ratio < 0.5:
                                return False  # Sans (top much narrower than middle)
                        
                        # For 'T', 'M', 'H' - different analysis needed
                        # Just check if top has serif-like features (more ink spread)
                        if c in ['T', 'M', 'H', 'E', 'L']:
                            # Less reliable but still useful
                            if top_density > 0.5:  # Lots of ink at top = serif likely (increased from 0.4)
                                return True
                            elif top_density < 0.15 and mid_density > 0.2:
                                return False  # Very thin top, thick middle = sans
                        
        return None  # Unable to determine
    
    def extract_char_bitmaps(self, page, text: str, font_name: str) -> dict:
        """
        Extract individual character bitmaps from a PDF page.
        
        Args:
            page: fitz.Page object
            text: The text string to find
            font_name: Font name to match (may have subset prefix like AAAAAA+)
            
        Returns:
            Dictionary of {char: (bitmap_bytes, width, height)}
        """
        raw = page.get_text('rawdict')
        char_bitmaps = {}
        
        # Strip subset prefix (e.g., "AAAAAA+Calibri" -> "Calibri")
        base_font_name = font_name.split('+')[-1].lower() if '+' in font_name else font_name.lower()
        
        for block in raw.get('blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    # Also strip prefix from span's font name for comparison
                    span_font = span.get('font', '')
                    span_font_base = span_font.split('+')[-1].lower() if '+' in span_font else span_font.lower()
                    
                    if base_font_name not in span_font_base:
                        continue
                    
                    chars = span.get('chars', [])
                    span_text = ''.join([c.get('c', '') for c in chars])

                    if text not in span_text:
                        continue

                    # Extract bitmaps for matching characters
                    for char_info in chars:
                        c = char_info.get('c', '')
                        if c in self.MATCH_CHARS and c not in char_bitmaps:
                            ci_bbox = char_info.get('bbox')
                            if not ci_bbox:
                                continue
                            bbox = fitz.Rect(ci_bbox)
                            # Add small padding
                            bbox = bbox + (-1, -1, 1, 1)
                            pix = page.get_pixmap(clip=bbox, colorspace=fitz.csGRAY)
                            char_bitmaps[c] = (pix.samples, pix.width, pix.height)
                            
                            if len(char_bitmaps) >= 5:
                                return char_bitmaps
        
        return char_bitmaps
    
    def render_char_bitmap(self, doc, font_path: str, char: str, target_height: int) -> tuple:
        """
        Render a character using a candidate font at the target height.
        
        Args:
            doc: Reusable scratch fitz.Document
            font_path: Path to font file
            char: Character to render
            target_height: Target height in pixels (for scaling)
            
        Returns:
            Tuple of (bitmap_bytes, width, height) or None if failed
        """
        try:
            page = doc.new_page(width=100, height=100)
            
            # Scale font size to match target height
            # Approximate: font size ~= height * 0.8
            fontsize = target_height * 0.85
            
            # Insert text
            font = fitz.Font(fontfile=font_path)
            writer = fitz.TextWriter(page.rect)
            writer.append((10, 50), char, font=font, fontsize=fontsize)
            writer.write_text(page)
            
            # Find the text bbox
            rects = page.search_for(char)
            if not rects:
                doc.delete_page(page.number)
                return None
            
            bbox = rects[0] + (-1, -1, 1, 1)
            pix = page.get_pixmap(clip=bbox, colorspace=fitz.csGRAY)
            result = (pix.samples, pix.width, pix.height)
            
            doc.delete_page(page.number)
            return result
            
        except Exception:
            try:
                # Cleanup if failed — delete last page (page var may be undefined)
                if len(doc) > 0:
                    doc.delete_page(-1)
            except Exception:
                pass
            return None
    
    def calculate_iou(self, bitmap1: tuple, bitmap2: tuple) -> float:
        """
        Calculate Intersection over Union for two bitmaps.
        
        Args:
            bitmap1: (samples, width, height)
            bitmap2: (samples, width, height)
            
        Returns:
            IoU score between 0.0 and 1.0
        """
        samples1, w1, h1 = bitmap1
        samples2, w2, h2 = bitmap2
        
        # Resize to common dimensions (use smaller)
        target_w = min(w1, w2)
        target_h = min(h1, h2)
        
        if target_w == 0 or target_h == 0:
            return 0.0
        
        # Simple pixel comparison (threshold at 200 for "ink")
        threshold = 200
        
        intersection = 0
        union = 0
        
        for y in range(target_h):
            for x in range(target_w):
                # Map coordinates with clamping to prevent out-of-bounds from rounding
                my1 = min(int(y * h1 / target_h), h1 - 1)
                mx1 = min(int(x * w1 / target_w), w1 - 1)
                my2 = min(int(y * h2 / target_h), h2 - 1)
                mx2 = min(int(x * w2 / target_w), w2 - 1)
                idx1 = my1 * w1 + mx1
                idx2 = my2 * w2 + mx2

                if idx1 >= len(samples1) or idx2 >= len(samples2):
                    continue
                
                p1_ink = samples1[idx1] < threshold
                p2_ink = samples2[idx2] < threshold
                
                if p1_ink and p2_ink:
                    intersection += 1
                if p1_ink or p2_ink:
                    union += 1
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def find_best_match_gen(self, page, text: str, font_name: str, src_is_serif: bool = None):
        """
        Generator that yields progress events while searching for fonts.
        Yields dicts with 'type': 'progress' | 'complete'.

        Args:
            src_is_serif: If provided, applies penalty for serif/sans mismatch.
                         True = source is serif, False = source is sans-serif.
        """
        # Extract character bitmaps from PDF
        pdf_chars = self.extract_char_bitmaps(page, text, font_name)

        if not pdf_chars:
            yield {
                'type': 'complete',
                'best_match': None,
                'candidates': []
            }
            return

        # Get target height from first character
        first_char_data = list(pdf_chars.values())[0]
        target_height = first_char_data[2]

        best_match = (None, None, 0.0)
        candidates = []

        # Helper scratch document for rendering candidates
        scratch_doc = fitz.open()

        # Early exit threshold - if we find a match with score >= 0.85, stop searching
        # This dramatically speeds up the search for common fonts
        EARLY_EXIT_THRESHOLD = 0.85

        try:
            total_fonts = len(self.font_paths)

            # Score each candidate font
            for i, (name, path) in enumerate(self.font_paths.items()):
                yield {
                    'type': 'progress',
                    'message': name,
                    'progress': float(i + 1) / total_fonts
                }

                if not os.path.exists(path):
                    continue

                total_score = 0.0
                matched_chars = 0

                for char, pdf_bitmap in pdf_chars.items():
                    candidate_bitmap = self.render_char_bitmap(scratch_doc, path, char, target_height)
                    if candidate_bitmap:
                        score = self.calculate_iou(pdf_bitmap, candidate_bitmap)
                        total_score += score
                        matched_chars += 1

                if matched_chars > 0:
                    avg_score = total_score / matched_chars

                    # Apply serif/sans-serif penalty if src_is_serif is known
                    if src_is_serif is not None:
                        cand_is_serif = self._is_font_serif_by_name(name)
                        if cand_is_serif is not None and cand_is_serif != src_is_serif:
                            # Major penalty for serif/sans mismatch (0.4 = 60% reduction)
                            avg_score *= 0.4

                    # Store candidate
                    candidates.append({
                        'name': name,
                        'path': path,
                        'score': avg_score
                    })

                    if avg_score > best_match[2]:
                        best_match = (path, name, avg_score)

                    # EARLY EXIT: If we found an excellent match, stop searching
                    # This prevents hanging on exhaustive searches of hundreds of fonts
                    if avg_score >= EARLY_EXIT_THRESHOLD:
                        # Add a small buffer of fonts to ensure we have the best match
                        # Check up to 10 more fonts or 5% more, whichever is smaller
                        remaining_check = min(10, int(total_fonts * 0.05))
                        if i >= remaining_check:
                            # We've checked enough fonts after finding the excellent match
                            break

        finally:
            scratch_doc.close()

        # Sort candidates by score descending
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # Convert best match tuple to dict for transport
        best_match_dict = None
        if best_match[0]:
            best_match_dict = {
                'path': best_match[0],
                'name': best_match[1],
                'score': best_match[2]
            }
        
        # If no candidates found, yield error instead of empty complete
        if not candidates:
            yield {
                'type': 'error',
                'message': 'No matching fonts found. Try enabling Exhaustive Font Search in Preferences.'
            }
            return
            
        yield {
            'type': 'complete',
            'best_match': best_match_dict,
            'candidates': candidates
        }

    def find_best_match(self, page, text: str, font_name: str, callback=None, src_is_serif: bool = None) -> tuple:
        """
        Wrapper around generator for backward compatibility.
        Note: callback parameter is deprecated and ignored.
        
        Args:
            src_is_serif: If provided, apply penalty for serif/sans mismatch.
        """
        for event in self.find_best_match_gen(page, text, font_name, src_is_serif=src_is_serif):
            if event['type'] == 'complete':
                b = event['best_match']
                best = (b['path'], b['name'], b['score']) if b else (None, None, 0)
                return (best, event['candidates'])
        
        # Fallback if generator doesn't yield complete
        return ((None, None, 0), [])


def find_matching_font(page, text: str, font_name: str, font_list_path: str = None, exhaustive: bool = False, src_is_serif: bool = None) -> tuple:
    """
    Convenience function to find the best matching font.
    Preserves original return signature for backward compatibility.
    
    Args:
        src_is_serif: If provided, apply penalty for serif/sans mismatch.
    """
    matcher = VisualFontMatcher(font_list_path, exhaustive=exhaustive)
    best_match, _ = matcher.find_best_match(page, text, font_name, src_is_serif=src_is_serif)
    return best_match
