import fitz
import os
from . import harvester
from . import synthesizer

def _get_line_structure(page, target_rect, debug_log=None):
    """
    Find the line containing the target_rect and split it into components.
    Uses 'rawdict' to handle character-level splitting for merged spans.

    Args:
        page: fitz.Page
        target_rect: fitz.Rect of the text being replaced
        debug_log: list for debug messages

    Returns:
        tuple: (
            line_rect: fitz.Rect (bounding box of entire line),
            prefix_spans: list of synthetic span dicts before target,
            target_spans: list of synthetic span dicts inside target,
            suffix_spans: list of synthetic span dicts after target
        )
    """
    # Input validation
    if page is None:
        if debug_log is not None:
            debug_log.append("[Reflow] ERROR: _get_line_structure called with None page")
        return None, [], [], []
    if target_rect is None or target_rect.is_empty:
        if debug_log is not None:
            debug_log.append("[Reflow] ERROR: _get_line_structure called with invalid rect")
        return None, [], [], []

    # Use rawdict to get character level data
    try:
        blocks = page.get_text("rawdict").get("blocks", [])
    except Exception as e:
        if debug_log is not None:
            debug_log.append(f"[Reflow] ERROR: Failed to get text from page: {e}")
        return None, [], [], []
    
    # Improved Strategy: Gather lines that fall within the target's vertical band
    # and are horizontally related to the selected text.
    #
    # This still handles cases where "Hello", "TARGET", "World" are separate
    # PDF text objects on one visual line, but it avoids pulling in distant
    # same-baseline content from another column or table cell.

    target_center_y = (target_rect.y0 + target_rect.y1) / 2
    target_height = target_rect.height

    candidate_lines = []

    horizontal_proximity = max(50.0, min(target_rect.width * 2.0, 150.0))

    for b in blocks:
        for l in b.get("lines", []):
            l_bbox = l.get("bbox")
            if not l_bbox:
                continue
            r = fitz.Rect(l_bbox)
            # Check if line center is roughly aligned with target center
            line_center_y = (r.y0 + r.y1) / 2

            # Adaptive tolerance calculation:
            # - For small fonts (< 8pt), use more lenient tolerance (60%)
            # - For normal fonts (8-14pt), use standard tolerance (40%)
            # - For large fonts (> 14pt), use stricter tolerance (25%)
            # We'll estimate font size from target height
            # Bbox height includes ascenders + descenders + leading, so it's ~20% larger than font size
            estimated_fontsize = target_height * 0.82  # Approximate correction for typical font metrics

            if estimated_fontsize < 8:
                tolerance_pct = 0.60
            elif estimated_fontsize < 14:
                tolerance_pct = 0.40
            else:
                tolerance_pct = 0.25

            # Also ensure at least some minimum absolute tolerance (2 points)
            min_tolerance = 2.0
            tolerance = max(target_height * tolerance_pct, min_tolerance)

            if abs(line_center_y - target_center_y) < tolerance:
                if r.x1 < target_rect.x0:
                    horizontal_gap = target_rect.x0 - r.x1
                elif r.x0 > target_rect.x1:
                    horizontal_gap = r.x0 - target_rect.x1
                else:
                    horizontal_gap = 0.0

                if horizontal_gap <= horizontal_proximity:
                    candidate_lines.append(l)
                    if debug_log is not None:
                        debug_log.append(
                            f"  Line candidate: center_y={line_center_y:.2f}, target={target_center_y:.2f}, "
                            f"diff={abs(line_center_y - target_center_y):.2f}, tol={tolerance:.2f}, "
                            f"h_gap={horizontal_gap:.1f}, h_tol={horizontal_proximity:.1f}"
                        )
                elif debug_log is not None:
                    debug_log.append(
                        f"  Line skipped (distant same-baseline content): center_y={line_center_y:.2f}, "
                        f"h_gap={horizontal_gap:.1f}pt > {horizontal_proximity:.1f}pt"
                    )
                
    if not candidate_lines or 'bbox' not in candidate_lines[0]:
        return None, [], [], []

    # Calculate union bounding box of the visual line
    line_rect = fitz.Rect(candidate_lines[0]['bbox'])
    for l in candidate_lines[1:]:
        line_rect |= fitz.Rect(l['bbox'])
        
    if debug_log is not None: debug_log.append(f"Reflow: Found {len(candidate_lines)} fragments for line. Combined Box: {line_rect}")

    prefix_chars = []
    target_chars = []
    suffix_chars = []
    
    t_x0 = target_rect.x0 - 1.0 # Tolerance
    t_x1 = target_rect.x1 + 1.0
    
    # Iterate ALL candidate lines
    for line in candidate_lines:
        for span in line.get("spans", []):
            # We need to preserve font info for reconstruction
            base_span_info = {
                'font': span['font'],
                'size': span['size'],
                'color': span['color'],
                'ascender': span.get('ascender', 0.8),
                'descender': span.get('descender', 0.2)
            }
            
            for char in span.get("chars", []):
                char_bbox = char.get("bbox")
                if not char_bbox:
                    continue
                c_bbox = fitz.Rect(char_bbox)
                c_mid_x = (c_bbox.x0 + c_bbox.x1) / 2
                
                # Create a mini-span equivalent for this char
                # Note: 'origin' for char is (origin.x, origin.y). 
                # rawdict char: {'c': 'H', 'bbox': ..., 'origin': ...}
                char_origin = char.get('origin')
                if not char_origin:
                    continue  # Skip chars without origin data
                char_obj = {
                    'text': char.get('c', ''),
                    'origin': char_origin,
                    'bbox': char_bbox,
                    **base_span_info
                }
                
                if c_mid_x < t_x0:
                    prefix_chars.append(char_obj)
                elif c_mid_x > t_x1:
                    suffix_chars.append(char_obj)
                else:
                    target_chars.append(char_obj)

    # Helper to merge adjacent chars back into spans if they share properties
    # This optimization reduces the number of draw calls, but drawing char-by-char is also fine regarding functionality.
    # For Reflow, checking distinct spans is easier if we group them.
    
    def _merge_chars_to_spans(char_list):
        if not char_list: return []
        merged = []
        current_span = None
        
        for ch in char_list:
            ch_origin = ch.get('origin', ())
            cs_origin = current_span.get('origin', ()) if current_span else ()
            if current_span and \
               ch['font'] == current_span['font'] and \
               ch['size'] == current_span['size'] and \
               ch['color'] == current_span['color'] and \
               len(ch_origin) >= 2 and len(cs_origin) >= 2 and \
               abs(ch_origin[1] - cs_origin[1]) < 0.1: # Same baseline
                
                # Check for adjacency? PyMuPDF inserts spaces as chars usually?
                # rawdict usually has spaces as characters with invisible bboxes or just space chars.
                # If they are adjacent in list, we append.
                current_span['text'] += ch['text']
                # Update bbox
                current_span['bbox'] = fitz.Rect(current_span['bbox']) | fitz.Rect(ch['bbox'])
            else:
                if current_span: merged.append(current_span)
                # Start new span
                current_span = ch.copy()
                current_span['bbox'] = fitz.Rect(ch['bbox']) # Ensure it's a Rect object
                
        if current_span: merged.append(current_span)
        return merged

    prefix = _merge_chars_to_spans(prefix_chars)
    target = _merge_chars_to_spans(target_chars)
    suffix = _merge_chars_to_spans(suffix_chars)
    
    if debug_log is not None:
        debug_log.append(f"  Prefix spans: {len(prefix)}")
        debug_log.append(f"  Target spans: {len(target)}")
        debug_log.append(f"  Suffix spans: {len(suffix)}")
        if suffix:
            first_s = suffix[0]
            debug_log.append(f"  First suffix length: {len(first_s.get('text', ''))} at {first_s.get('origin', '?')}")

    return line_rect, prefix, target, suffix


def _detect_alignment(page, target_rect, line_rect, debug_log=None):
    """
    Detect coarse horizontal alignment for isolated single-line replacement.

    This is intentionally conservative: it only returns center/right when the
    text is close to page-content alignment anchors. Otherwise left positioning
    preserves the historical behavior.
    """
    if debug_log is None:
        debug_log = []

    if page is None or target_rect is None:
        return "left"

    page_rect = page.rect
    page_width = page_rect.width
    content_left = page_width * 0.075
    content_right = page_width * 0.925
    content_width = content_right - content_left
    content_center = (content_left + content_right) / 2

    ref_rect = line_rect if line_rect else target_rect
    text_center = (ref_rect.x0 + ref_rect.x1) / 2
    text_left = ref_rect.x0
    text_right = ref_rect.x1

    center_tolerance = content_width * 0.05
    edge_tolerance = 20.0

    if abs(text_center - content_center) < center_tolerance and ref_rect.width < content_width * 0.9:
        debug_log.append(
            f"Alignment: CENTER (center dist: {abs(text_center - content_center):.1f}pt, "
            f"tol: {center_tolerance:.1f}pt)"
        )
        return "center"

    if abs(text_right - content_right) < edge_tolerance and abs(text_left - content_left) > edge_tolerance * 2:
        debug_log.append(
            f"Alignment: RIGHT (right dist: {abs(text_right - content_right):.1f}pt, "
            f"left dist: {abs(text_left - content_left):.1f}pt)"
        )
        return "right"

    debug_log.append("Alignment: LEFT (default)")
    return "left"


def reflow_line(page, target_rect, replacement_text, font_info, debug_log=None, font_buffer=None):
    """
    Redraw the line containing target_rect, inserting replacement_text and shifting suffix.
    Uses 'Visual Copy' (show_pdf_page) for Prefix and Suffix to preserve exact appearance.
    Uses 'Glyph Synthesis' (harvester+synthesizer) if font embedding fails for replacement text.
    font_buffer: optional bytes for synthesis font measurement
    """
    # Input validation
    if page is None:
        if debug_log is not None:
            debug_log.append("[Reflow] ERROR: reflow_line called with None page")
        return False, None
    if target_rect is None or target_rect.is_empty:
        if debug_log is not None:
            debug_log.append("[Reflow] ERROR: reflow_line called with invalid rect")
        return False, None
    if not replacement_text or not isinstance(replacement_text, str):
        if debug_log is not None:
            debug_log.append("[Reflow] ERROR: reflow_line called with invalid replacement_text")
        return False, None
    if not font_info or not isinstance(font_info, dict):
        if debug_log is not None:
            debug_log.append("[Reflow] ERROR: reflow_line called with invalid font_info")
        return False, None

    if debug_log is None: debug_log = []

    line_rect, prefix, target, suffix = _get_line_structure(page, target_rect, debug_log)
    
    if not line_rect:
        debug_log.append("Reflow: Could not identify matching line structure.")
        return False, None
        
    # AUTO-UPPERCASE CHECK
    # Check if target text was ALL CAPS (e.g. headers, fake small-caps).
    if target:
        full_target_text = "".join(t['text'] for t in target)
        # Verify length > 1 to avoid triggering on single initials or numbers
        if len(full_target_text) > 1 and full_target_text.isupper() and not replacement_text.isupper():
            debug_log.append(f"Reflow: Target length={len(full_target_text)} is ALL CAPS. Auto-converting replacement to UPPER.")
            replacement_text = replacement_text.upper()
    
    # 1. Calculate Old Width
    if target:
        # BUG #52 FIX: Use horizontal extent (not union rect) for accurate width
        # Union rect can include vertical gaps if spans aren't perfectly aligned
        # For width, we want leftmost x0 to rightmost x1
        t_bbox = target[0]['bbox'] if isinstance(target[0]['bbox'], fitz.Rect) else fitz.Rect(target[0]['bbox'])
        for s in target[1:]:
            s_rect = fitz.Rect(s['bbox']) if not isinstance(s['bbox'], fitz.Rect) else s['bbox']
            t_bbox.x0 = min(t_bbox.x0, s_rect.x0)
            t_bbox.x1 = max(t_bbox.x1, s_rect.x1)
            # Don't merge y-coordinates to avoid including vertical gaps
        old_width = t_bbox.width
        debug_log.append(f"Reflow: Calculated old_width from spans: {old_width:.2f}")
    else:
        old_width = target_rect.width
        debug_log.append(f"Reflow: Calculated old_width from rect: {old_width:.2f}")
    
    # 2. Calculate New Width
    fontname = font_info.get('fontname', 'helv')
    fontsize = font_info.get('fontsize', 11.0)

    # Compute clean font name once: strip PDF subset prefix (e.g. "AAAAAA+HelveticaNeue" -> "HelveticaNeue")
    # fitz.Font() and insert_text() cannot resolve subset-prefixed names and silently fail / fall back.
    clean_fontname = fontname.split('+', 1)[1] if '+' in fontname else fontname

    # Start with a conservative estimate
    est_new_width = len(replacement_text) * fontsize * 0.5

    try:
        if font_buffer:
            font = fitz.Font(fontbuffer=font_buffer)
        else:
            font = fitz.Font(clean_fontname)

        # Use text_length for accurate measurement
        est_new_width = font.text_length(replacement_text, fontsize=fontsize)

        # Apply kerning compensation
        # Some fonts have tight kerning that text_length doesn't fully account for
        # We add a small fudge factor for long strings with likely kerning pairs
        if len(replacement_text) > 5:
            # Common kerning pairs that might be tighter: AV, AY, AW, TA, WA, etc.
            # Add 1-2% for each 10 characters, capped at 3% max to avoid overestimation
            kerning_fudge = 1.0 + min((len(replacement_text) / 10.0) * 0.015, 0.03)
            est_new_width *= kerning_fudge

        debug_log.append(f"Reflow: Font text_length success: {est_new_width:.2f} using {clean_fontname}")
    except Exception as e:
        debug_log.append(f"Reflow: Font text_length failed ({e}), using fallback: {est_new_width:.2f}")
        # Improve fallback calculation based on character types
        # Wide characters (M, W, m, w) vs narrow (i, j, l, t, f)
        wide_chars = sum(1 for c in replacement_text if c in 'MWmwWM')
        narrow_chars = sum(1 for c in replacement_text if c in 'ijltfIJLT')
        avg_width_factor = 0.5 + (wide_chars - narrow_chars) * 0.1 / max(len(replacement_text), 1)
        est_new_width = len(replacement_text) * fontsize * avg_width_factor

    delta = est_new_width - old_width
    debug_log.append(f"Reflow: Old W: {old_width:.2f}, New W: {est_new_width:.2f}, Delta: {delta:.2f}")

    manual_alignment = font_info.get('justification') or font_info.get('alignment')
    if isinstance(manual_alignment, str) and manual_alignment.strip():
        alignment = manual_alignment.strip().lower()
        if alignment not in {"left", "center", "right"}:
            debug_log.append(f"Reflow: Unknown manual alignment '{manual_alignment}', defaulting to left")
            alignment = "left"
        else:
            debug_log.append(f"Reflow: Using manual alignment: {alignment.upper()}")
    else:
        alignment = _detect_alignment(page, target_rect, line_rect, debug_log)

    if alignment == "center":
        target_center_x = (target_rect.x0 + target_rect.x1) / 2
        insertion_x = target_center_x - (est_new_width / 2)
        debug_log.append(f"Reflow: CENTER positioning - center={target_center_x:.2f}, x={insertion_x:.2f}")
    elif alignment == "right":
        insertion_x = target_rect.x1 - est_new_width
        debug_log.append(f"Reflow: RIGHT positioning - right edge={target_rect.x1:.2f}, x={insertion_x:.2f}")
    else:
        insertion_x = target_rect.x0
        debug_log.append(f"Reflow: LEFT positioning - x={insertion_x:.2f}")

    suffix_shift_right = 0.0
    suffix_fontfile = font_info.get('fontfile')

    def can_reinsert_suffix_exactly():
        """Return false before redacting suffix text if its original font cannot be reinserted."""
        for sp in suffix:
            sp_text = sp.get('text', '')
            if not sp_text:
                continue
            sp_fontname = sp.get('font', fontname)
            clean_sp_font = sp_fontname.split('+', 1)[1] if '+' in sp_fontname else sp_fontname
            if clean_sp_font.startswith('R') and clean_sp_font[1:].isdigit():
                continue
            try:
                fitz.Font(clean_sp_font)
            except Exception as font_err:
                if suffix_fontfile and os.path.exists(suffix_fontfile):
                    try:
                        fitz.Font(fontfile=suffix_fontfile)
                        continue
                    except Exception as fontfile_err:
                        debug_log.append(
                            f"Reflow: Suffix fontfile '{suffix_fontfile}' cannot be loaded ({fontfile_err})"
                        )
                debug_log.append(
                    f"Reflow: Suffix shift skipped — cannot reinsert suffix font "
                    f"'{clean_sp_font}' exactly ({font_err})"
                )
                return False
        return True

    # BUG-3 FIX: Pre-check overflow before touching the document.
    # If the replacement is wider than the original AND there is suffix content on the
    # same line, shift the suffix right when there is room. If there is no room, block
    # before touching the document instead of falling back to a colliding legacy insert.
    if suffix and delta > fontsize * 0.5:
        suffix_bbox = suffix[0]['bbox']
        suffix_start_x = (suffix_bbox.x0 if isinstance(suffix_bbox, fitz.Rect) else fitz.Rect(suffix_bbox).x0)
        replacement_end_x = insertion_x + est_new_width
        if replacement_end_x > suffix_start_x:
            overflow_pt = replacement_end_x - suffix_start_x
            padding = max(1.0, fontsize * 0.15)
            required_shift = overflow_pt + padding
            suffix_end_x = max(
                (sp['bbox'] if isinstance(sp['bbox'], fitz.Rect) else fitz.Rect(sp['bbox'])).x1
                for sp in suffix
            )
            right_margin = min(page.rect.x1 - fontsize, line_rect.x1 + fontsize * 4)
            if suffix_end_x + required_shift > right_margin:
                debug_log.append(
                    f"Reflow: OVERFLOW BLOCKED — replacement ends at x={replacement_end_x:.1f}, "
                    f"suffix starts at x={suffix_start_x:.1f}, overflow={overflow_pt:.1f}pt, "
                    f"and shifting suffix to x={suffix_end_x + required_shift:.1f} would exceed "
                    f"right margin x={right_margin:.1f}. Returning failure to prevent collision."
                )
                return False, None
            suffix_shift_right = required_shift
            debug_log.append(
                f"Reflow: Suffix right-shift planned — replacement ends at x={replacement_end_x:.1f}, "
                f"suffix starts at x={suffix_start_x:.1f}, overflow={overflow_pt:.1f}pt, "
                f"shift={suffix_shift_right:.1f}pt."
            )
            if not can_reinsert_suffix_exactly():
                debug_log.append(
                    "Reflow: OVERFLOW BLOCKED — suffix requires shifting, but exact suffix "
                    "font reinsertion is unavailable. Returning failure before redacting suffix."
                )
                return False, None

    # SETUP SOURCE DOC for Visual Copy / Harvesting
    src_doc = None
    use_visual_copy = False

    try:
        if page.parent.name and os.path.exists(page.parent.name):
            src_doc = fitz.open(page.parent.name)
            use_visual_copy = True
            debug_log.append(f"Reflow: Opened source doc for visual copy: {page.parent.name}")
        else:
            debug_log.append("Reflow: No source file available, falling back to basic redraw.")
    except Exception as e:
        debug_log.append(f"Reflow: Failed to open source doc: {e}")

    # Ensure src_doc is closed even on exceptions
    try:
            # 3. Redact ONLY the target area (NOT the entire line!)
        # Previously we redacted line_rect which destroyed adjacent content.
        # Now we redact just the target + a small margin for anti-aliasing.
        #
        # NOTE: We use target_rect directly, not line_rect.
        # This preserves prefix and suffix content in their original positions.

        # Calculate precise redaction rect - just the target area
        if target:
            # Use the actual target spans' bounding box
            t_bbox = target[0]['bbox'] if isinstance(target[0]['bbox'], fitz.Rect) else fitz.Rect(target[0]['bbox'])
            for s in target[1:]:
                s_rect = s['bbox'] if isinstance(s['bbox'], fitz.Rect) else fitz.Rect(s['bbox'])
                t_bbox |= s_rect
            redact_rect = t_bbox
        else:
            redact_rect = target_rect

        # CRITICAL FIX: Use white overlay instead of redaction
        # PyMuPDF's redaction removes any text whose bbox intersects the redaction area,
        # even with minimal margins. When line spacing is tight, adjacent text gets destroyed.
        #
        # Alternative approach: Draw a white rectangle over the target text, then draw
        # replacement text on top. This preserves adjacent content that only slightly
        # overlaps with the target bounding box.
        #
        # Shrink the cover rect slightly to avoid covering adjacent content
        # Use 0pt margin - exact target bounds only
        cover_rect = redact_rect

        # TIGHT-LEADING FIX: Clip cover_rect against adjacent text lines.
        #
        # Problem: Many PDF generators (e.g. TCPDF) produce span bboxes that include
        # a full ascender+descender zone even when the font glyphs don't use that space.
        # This causes adjacent lines' bboxes to overlap by 1-2 pt. When we call
        # apply_redactions(), PyMuPDF removes any character whose bbox *intersects*
        # the redaction rect — so the 1-2 pt overlap destroys adjacent text.
        #
        # Fix: Before redacting, scan the page for text lines whose bbox extends INTO
        # cover_rect from above or below (i.e. they are a different line that bleeds
        # into our area). Clip cover_rect so it does not overlap those lines.
        # The clipped region is still removed from the content stream; the background
        # (already white/sampled) handles the visual gap.
        try:
            target_center_y_lc = (target_rect.y0 + target_rect.y1) / 2
            check_margin = 6.0  # search this many pts above/below cover_rect

            # --- Clip top: raise cover_rect.y0 if an adjacent line above bleeds in ---
            above_search = fitz.Rect(
                cover_rect.x0 - 2, cover_rect.y0 - check_margin,
                cover_rect.x1 + 2, cover_rect.y0 + 3.0
            ) & page.rect
            if not above_search.is_empty:
                above_blocks = page.get_text("rawdict", clip=above_search).get("blocks", [])
                max_above_y1 = cover_rect.y0
                for ab in above_blocks:
                    for al in ab.get("lines", []):
                        al_bbox = al.get("bbox")
                        if not al_bbox:
                            continue
                        al_center = (al_bbox[1] + al_bbox[3]) / 2
                        # Must be a different line (above ours) AND bleed into cover_rect
                        if (al_center < target_center_y_lc - 3.0
                                and al_bbox[3] > cover_rect.y0
                                and al_bbox[0] < cover_rect.x1
                                and al_bbox[2] > cover_rect.x0):
                            max_above_y1 = max(max_above_y1, al_bbox[3])
                if max_above_y1 > cover_rect.y0:
                    debug_log.append(
                        f"Reflow: Clipping cover_rect top {cover_rect.y0:.2f} → {max_above_y1:.2f} "
                        f"(adjacent line bleeds in from above)"
                    )
                    cover_rect = fitz.Rect(cover_rect.x0, max_above_y1, cover_rect.x1, cover_rect.y1)

            # --- Clip bottom: lower cover_rect.y1 if an adjacent line below bleeds in ---
            below_search = fitz.Rect(
                cover_rect.x0 - 2, cover_rect.y1 - 3.0,
                cover_rect.x1 + 2, cover_rect.y1 + check_margin
            ) & page.rect
            if not below_search.is_empty:
                below_blocks = page.get_text("rawdict", clip=below_search).get("blocks", [])
                min_below_y0 = cover_rect.y1
                for bb in below_blocks:
                    for bl in bb.get("lines", []):
                        bl_bbox = bl.get("bbox")
                        if not bl_bbox:
                            continue
                        bl_center = (bl_bbox[1] + bl_bbox[3]) / 2
                        # Must be a different line (below ours) AND bleed into cover_rect
                        if (bl_center > target_center_y_lc + 3.0
                                and bl_bbox[1] < cover_rect.y1
                                and bl_bbox[0] < cover_rect.x1
                                and bl_bbox[2] > cover_rect.x0):
                            min_below_y0 = min(min_below_y0, bl_bbox[1])
                if min_below_y0 < cover_rect.y1:
                    debug_log.append(
                        f"Reflow: Clipping cover_rect bottom {cover_rect.y1:.2f} → {min_below_y0:.2f} "
                        f"(adjacent line bleeds in from below)"
                    )
                    cover_rect = fitz.Rect(cover_rect.x0, cover_rect.y0, cover_rect.x1, min_below_y0)

            if cover_rect.is_empty or cover_rect.height < 1.0:
                debug_log.append("Reflow: cover_rect became too small after clipping; using original")
                cover_rect = redact_rect

        except Exception as _clip_err:
            debug_log.append(f"Reflow: adjacency clipping failed ({_clip_err}); using original cover_rect")
            cover_rect = redact_rect

        # GHOST TEXT FIX: Use redaction to remove both text layer AND visuals.
        # White-rect-only approach left the original text layer intact, causing
        # PDFKit to show hover highlights and clickable regions on "blank" areas.
        # Use tight redaction with sampled background fill to handle non-white backgrounds.

        # If the caller passed an explicit bg_fill (from the user's Fill Color picker),
        # use it directly without sampling.
        if font_info.get('bg_fill'):
            bg_fill = font_info['bg_fill']
            if debug_log is not None:
                debug_log.append(f"Reflow: Using caller-provided bg_fill: {bg_fill}")
        else:
            bg_fill = (1.0, 1.0, 1.0)  # Default: white
            try:
                # Sample background color. Strategy:
                #   1. Try a strip ABOVE the cover_rect (inter-line gap = pure background).
                #   2. If that strip is too thin (tight leading), fall back to a strip
                #      BELOW the cover_rect.
                #   3. Last resort: sample from the RIGHTMOST 20 pt of the cover_rect
                #      itself (likely background if text doesn't span the full width).
                # Use the BRIGHTEST pixel from each strip — background is always lighter
                # than text ink, so max-luminance avoids text-pixel contamination.
                page_rect = page.rect
                sample_h = 4.0  # pt strip height

                def _sample_brightest(rect):
                    """Return (r,g,b) of the brightest pixel in the rect, or None."""
                    r = rect & page_rect
                    if r.is_empty or r.height < 0.5 or r.width < 1:
                        return None
                    pix = page.get_pixmap(clip=r.irect, matrix=fitz.Matrix(2, 2), alpha=False)
                    s = pix.samples
                    if len(s) < 3:
                        return None
                    best_lum = -1
                    best_rgb = None
                    for i in range(0, len(s) - 2, 3):
                        lum = s[i] + s[i + 1] + s[i + 2]
                        if lum > best_lum:
                            best_lum = lum
                            best_rgb = (s[i] / 255.0, s[i + 1] / 255.0, s[i + 2] / 255.0)
                    return best_rgb

                sampled = None
                # Strip above cover_rect (most reliable — no text there)
                above = fitz.Rect(cover_rect.x0, cover_rect.y0 - sample_h, cover_rect.x1, cover_rect.y0)
                if above.height >= 0.5:
                    sampled = _sample_brightest(above)
                # If above was too thin or returned white (might be between-cell gap),
                # try below
                if sampled is None or (sampled[0] > 0.98 and sampled[1] > 0.98 and sampled[2] > 0.98):
                    below = fitz.Rect(cover_rect.x0, cover_rect.y1, cover_rect.x1, cover_rect.y1 + sample_h)
                    alt = _sample_brightest(below)
                    if alt and not (alt[0] > 0.98 and alt[1] > 0.98 and alt[2] > 0.98):
                        sampled = alt  # non-white found below
                # Last resort: right edge of cover_rect (20pt wide, full height)
                if sampled is None or (sampled[0] > 0.98 and sampled[1] > 0.98 and sampled[2] > 0.98):
                    right_strip = fitz.Rect(cover_rect.x1 - 20, cover_rect.y0, cover_rect.x1, cover_rect.y1)
                    alt = _sample_brightest(right_strip)
                    if alt and not (alt[0] > 0.98 and alt[1] > 0.98 and alt[2] > 0.98):
                        sampled = alt

                if sampled and not (sampled[0] > 0.97 and sampled[1] > 0.97 and sampled[2] > 0.97):
                    bg_fill = sampled
                    if debug_log is not None:
                        debug_log.append(f"Reflow: Sampled background color: ({bg_fill[0]:.2f}, {bg_fill[1]:.2f}, {bg_fill[2]:.2f})")
            except Exception as e:
                if debug_log is not None:
                    debug_log.append(f"Reflow: Background color sampling failed, using white: {e}")
        page.add_redact_annot(cover_rect, fill=bg_fill)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

        debug_log.append(f"Reflow: Redacted target area (removing text layer): {cover_rect}")
        debug_log.append(f"Reflow: Target-only redaction: {redact_rect} (NOT line_rect: {line_rect})")
    
        # 4. Prefix handling - NO LONGER NEEDED
        # Since we only redact the target area, prefix content is preserved automatically.
        # We don't need to redraw it.
        if prefix:
            debug_log.append(f"Reflow: Prefix preserved (not redacted): {len(prefix)} spans")

        # 5. Draw Replacement
        color = font_info.get('color', (0,0,0))
    
        # PHASE 1 FIX: Track synthesis mode for priority handling
        use_synthesis_mode = font_info.get('use_synthesis_mode', False)
        original_fontname = font_info.get('original_fontname', fontname)
        synthesis_attempted = False
        synthesis_success = False
    
        # Calculate baseline position
        # Prefer using the actual origin of the target spans if available.
        # This preserves baseline shifts for things like Superscripts/Subscripts.
        target_origin = target[0].get('origin') if target else None
        if target_origin and len(target_origin) >= 2:
            # Keep X aligned with target_rect to respect structure, but use valid Y baseline
            baseline_y = target_origin[1]

            # Validate the baseline is reasonable
            # It should be between the top and bottom of the target rect (with some tolerance)
            rect_top = target_rect.y0
            rect_bottom = target_rect.y1

            if rect_top - 5 <= baseline_y <= rect_bottom + 5:
                pos = (insertion_x, baseline_y)
                debug_log.append(f"Reflow: Using detected baseline from target span: {pos[1]:.2f}")
            else:
                # Baseline seems invalid, estimate it using font metrics if available
                rect_height = rect_bottom - rect_top
                # Try to get actual font metrics for better baseline calculation
                baseline_ratio = 0.85  # Default fallback
                try:
                    # Use clean_fontname so fitz.Font() can resolve the name
                    # (subset-prefixed names like "AAAAAA+HelveticaNeue" always fail)
                    font = fitz.Font(fontbuffer=font_buffer) if font_buffer else fitz.Font(clean_fontname)
                    # Use font ascender to calculate baseline position
                    # Ascender is typically 0.8-0.9 of total height
                    if hasattr(font, 'ascender') and font.ascender > 0:
                        total = font.ascender + (abs(font.descender) if hasattr(font, 'descender') else 0)
                        baseline_ratio = font.ascender / total if total > 0 else 0.85
                except Exception:
                    pass  # Fall back to default ratio
                est_baseline = rect_top + rect_height * baseline_ratio
                pos = (insertion_x, est_baseline)
                debug_log.append(f"Reflow: Baseline out of range, using font metric estimate (ratio={baseline_ratio:.2f}): {pos[1]:.2f}")
        else:
            # Fallback: Estimate baseline from rect geometry using font metrics
            rect_height = target_rect.y1 - target_rect.y0
            baseline_ratio = 0.85  # Default fallback
            try:
                font = fitz.Font(fontbuffer=font_buffer) if font_buffer else fitz.Font(clean_fontname)
                if hasattr(font, 'ascender') and font.ascender > 0:
                    total = font.ascender + (abs(font.descender) if hasattr(font, 'descender') else 0)
                    baseline_ratio = font.ascender / total if total > 0 else 0.85
            except Exception:
                pass
            est_baseline = target_rect.y0 + rect_height * baseline_ratio
            pos = (insertion_x, est_baseline)
            debug_log.append(f"Reflow: Using font metric baseline (ratio={baseline_ratio:.2f}): {pos[1]:.2f}")
    
        # PHASE 1 FIX: Attempt synthesis FIRST when synthesis mode is flagged
        if use_synthesis_mode and src_doc:
            debug_log.append(f"Reflow: Synthesis mode enabled - attempting glyph synthesis FIRST")
            synthesis_attempted = True
        
            try:
                needed_chars = set(replacement_text)
            
                # Convert target color (tuple 0..1) to int for harvester
                target_color_int = None
                if isinstance(color, (list, tuple)) and len(color) >= 3:
                    r = int(color[0] * 255)
                    g = int(color[1] * 255)
                    b = int(color[2] * 255)
                    target_color_int = (r << 16) | (g << 8) | b
                elif isinstance(color, int):
                    target_color_int = color
            
                # Use original font name for better glyph matching
                glyph_map, missing = harvester.harvest_glyphs(
                    src_doc, needed_chars, original_fontname, 
                    target_color=target_color_int, page_limit=50
                )
            
                # Filter space from missing (use discard to avoid KeyError)
                missing.discard(' ')

                if len(glyph_map) > 0 and not missing:
                    _, drawn_rects = synthesizer.draw_text_as_vectors(
                        page, pos, replacement_text, glyph_map, size=fontsize, doc=src_doc
                    )
                    debug_log.append(f"Reflow: Synthesis FIRST succeeded with {len(glyph_map)} glyphs")
                    synthesis_success = True
                else:
                    debug_log.append(f"Reflow: Synthesis FIRST failed - missing glyph count: {len(missing)}")
                
            except Exception as e:
                debug_log.append(f"Reflow: Synthesis FIRST exception: {e}")
    
        # Fall back to standard insertion if synthesis wasn't attempted or failed
        if not synthesis_success:
            standard_insertion_success = False
            try:
                # Try standard insertion with clean_fontname (subset prefix already stripped above)
                page.insert_text(pos, replacement_text, fontname=clean_fontname, fontsize=fontsize, color=color)
                debug_log.append(f"Reflow: Standard insertion succeeded with font: {clean_fontname} (original: {fontname})")
                standard_insertion_success = True
            except Exception as e:
                debug_log.append(f"Reflow: Standard insertion failed ({e}). Attempting Synthesis fallback.")
        
                # GLYPH SYNTHESIS FALLBACK (only when standard insertion FAILS)
                if src_doc:
                    # 1. Harvest Glyphs from Source Doc
                    # We need the characters present in replacement_text
                    needed_chars = set(replacement_text)
                    debug_log.append(f"Reflow: Needed glyph count: {len(needed_chars)}")
                
                    # Convert target color (tuple 0..1) to int for harvester
                    target_color_int = None
                    if isinstance(color, (list, tuple)) and len(color) >= 3:
                        r = int(color[0] * 255)
                        g = int(color[1] * 255)
                        b = int(color[2] * 255)
                        target_color_int = (r << 16) | (g << 8) | b
                    elif isinstance(color, int):
                        target_color_int = color

                    glyph_map, missing = harvester.harvest_glyphs(src_doc, needed_chars, original_fontname, target_color=target_color_int, page_limit=50)
                
                    # Debug harvested glyphs
                    debug_log.append(f"Reflow: Target Color: {color} (Int: {target_color_int})")
                    for glyph_index, v in enumerate(glyph_map.values(), start=1):
                        debug_log.append(f"  Glyph {glyph_index}: Page {v.get('page', '?')}, BBox {v.get('bbox', '?')}, Size {v.get('size', '?')}, Color {v.get('color', '?')}")
                    
                    debug_log.append(f"Reflow: Missing glyph count: {len(missing)}")
                
                    # Filter out space from missing — synthesized space is handled by logic, not glyphs
                    missing.discard(' ')
                
                    if len(glyph_map) > 0 and not missing:
                        # Perform Synthesis
                        _, drawn_rects = synthesizer.draw_text_as_vectors(page, pos, replacement_text, glyph_map, size=fontsize, doc=src_doc)
                        debug_log.append(f"Reflow: Synthesized text with {len(glyph_map)} glyphs.")
                    
                        # OUTPUT VERIFICATION
                        # Check if the synthesized chars actually rendered (have ink)
                        synthesis_failed = False
                        for char, rect in drawn_rects:
                            if char in ' .,': continue # Skip space/punctuation check
                        
                            try:
                                # Check output page for ink at this rect
                                check_rect = fitz.Rect(rect)
                                check_rect += (-1, -1, 1, 1) # Expand slightly
                            
                                pix = page.get_pixmap(clip=check_rect, matrix=fitz.Matrix(2,2), alpha=False)
                                has_ink = False
                                samples = pix.samples
                                if samples:
                                     # Stricter threshold: Text should be dark (lum < 180). 
                                     # 240 is too permissive for gray backgrounds.
                                     for j in range(0, len(samples) - 2, 3):
                                         lum = (samples[j] + samples[j+1] + samples[j+2]) // 3
                                         if lum < 180:
                                             has_ink = True
                                             break
                            
                                if not has_ink:
                                    debug_log.append("Reflow: Output verification failed for synthesized glyph (No dark ink)")
                                    synthesis_failed = True
                                    break
                            except Exception as e:
                                debug_log.append(f"Reflow: Output verification exception: {e}")
                    
                        if synthesis_failed:
                            # BUG-4 FIX: Don't silently use wrong-font fallback after synthesis
                            # verification fails. Return failure so the legacy path in core.py
                            # can handle the insertion explicitly with its own font-matching logic.
                            debug_log.append(
                                "Reflow: Synthesis verification failed — ink not detected for synthesized glyphs. "
                                "Returning failure to avoid silent wrong-font insertion."
                            )
                            return False, None

                    else:
                        msg = f"Reflow: Synthesis incomplete (missing {missing})." if missing else "Reflow: Synthesis failed/empty."
                        # BUG-4 FIX: Don't silently fall back to a generic font (helv/times)
                        # when synthesis is missing glyphs. A generic font can look completely
                        # wrong next to a custom condensed or display typeface. Return failure
                        # so the caller can report a meaningful error or try the legacy path.
                        debug_log.append(
                            f"{msg} Returning failure instead of silent generic-font insertion "
                            f"to prevent visually incorrect output."
                        )
                        return False, None

                else:
                    debug_log.append("Reflow: Cannot synthesize without source doc.")

        # 6. Suffix handling
        # Since we only redact the target area, suffix content is preserved automatically
        # when the replacement is close in width.
        # NOTE: Overflow-collision cases are already blocked earlier (BUG-3 pre-check).
        # If we reach here with delta > 0 and suffix, the overlap is within tolerance.
        #
        # BUG-2 FIX: When the replacement is significantly shorter, a visible gap is left
        # between the new text and the suffix. Erase the suffix from its old position and
        # reinsert it shifted left to close the gap.
        if suffix:
            debug_log.append(f"Reflow: Suffix found: {len(suffix)} spans")
            if delta > 5:
                debug_log.append(f"Reflow: NOTE - Replacement is {delta:.1f}pt wider; overlap within tolerance")

            # BUG-3: Move suffix right when replacement grows into it but there is room.
            gap_threshold = fontsize * 0.3  # 30% of char width is perceptibly large
            if suffix_shift_right > 0:
                shift = suffix_shift_right

                # Step 1: Redact all suffix spans from their current positions
                for sp in suffix:
                    sp_rect = sp['bbox'] if isinstance(sp['bbox'], fitz.Rect) else fitz.Rect(sp['bbox'])
                    sp_redact = fitz.Rect(sp_rect.x0 - 1, sp_rect.y0, sp_rect.x1 + 1, sp_rect.y1) & page.rect
                    if not sp_redact.is_empty:
                        page.add_redact_annot(sp_redact, fill=bg_fill)
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

                # Step 2: Reinsert each suffix span at its shifted position
                for sp in suffix:
                    sp_text = sp.get('text', '')
                    if not sp_text:
                        continue
                    sp_rect = sp['bbox'] if isinstance(sp['bbox'], fitz.Rect) else fitz.Rect(sp['bbox'])
                    sp_origin = sp.get('origin')
                    if sp_origin and len(sp_origin) >= 2:
                        new_pos = (sp_origin[0] + shift, sp_origin[1])
                    else:
                        rect_h = sp_rect.height
                        new_pos = (sp_rect.x0 + shift, sp_rect.y0 + rect_h * 0.85)

                    sp_fontname = sp.get('font', fontname)
                    sp_fontsize = sp.get('size', fontsize)
                    sp_color_raw = sp.get('color', color)
                    if isinstance(sp_color_raw, int):
                        sp_color = (
                            ((sp_color_raw >> 16) & 0xff) / 255.0,
                            ((sp_color_raw >> 8) & 0xff) / 255.0,
                            (sp_color_raw & 0xff) / 255.0,
                        )
                    else:
                        sp_color = sp_color_raw

                    clean_sp_font = sp_fontname.split('+', 1)[1] if '+' in sp_fontname else sp_fontname
                    inserted = False
                    try:
                        page.insert_text(new_pos, sp_text, fontname=clean_sp_font,
                                         fontfile=suffix_fontfile,
                                         fontsize=sp_fontsize, color=sp_color)
                        inserted = True
                    except Exception as _sp_err:
                        debug_log.append(f"Reflow: BUG-3 suffix reinsert failed for suffix length={len(sp_text)} ({clean_sp_font}): {_sp_err}")
                    if not inserted:
                        try:
                            fallback = "times" if ('times' in sp_fontname.lower() or 'serif' in sp_fontname.lower()) else "helv"
                            page.insert_text(new_pos, sp_text, fontname=fallback,
                                             fontsize=sp_fontsize, color=sp_color)
                            debug_log.append(f"Reflow: BUG-3 suffix reinsert used fallback font '{fallback}' for suffix length={len(sp_text)}")
                        except Exception as _sp_err2:
                            debug_log.append(f"Reflow: BUG-3 suffix reinsert fallback also failed for suffix length={len(sp_text)}: {_sp_err2}")

                debug_log.append(f"Reflow: BUG-3 fix complete — suffix shifted right by {shift:.1f}pt")

            # BUG-2: Close gap when replacement is shorter than original
            elif delta < -gap_threshold:
                suffix_bbox0 = suffix[0]['bbox'] if isinstance(suffix[0]['bbox'], fitz.Rect) else fitz.Rect(suffix[0]['bbox'])
                suffix_start_x = suffix_bbox0.x0
                replacement_end_x = insertion_x + est_new_width
                actual_gap = suffix_start_x - replacement_end_x

                if actual_gap > gap_threshold:
                    if not can_reinsert_suffix_exactly():
                        debug_log.append(
                            "Reflow: BUG-2 suffix gap left open — exact suffix font "
                            "reinsertion is unavailable, so suffix text was not redacted."
                        )
                        return True, line_rect

                    debug_log.append(
                        f"Reflow: BUG-2 fix — closing suffix gap of {actual_gap:.1f}pt "
                        f"(replacement_end_x={replacement_end_x:.1f}, suffix_start_x={suffix_start_x:.1f})"
                    )
                    shift = actual_gap  # points to move suffix leftward

                    # Step 1: Redact all suffix spans from their current positions
                    for sp in suffix:
                        sp_rect = sp['bbox'] if isinstance(sp['bbox'], fitz.Rect) else fitz.Rect(sp['bbox'])
                        # Expand by 1pt horizontally to ensure clean erasure of anti-aliasing
                        sp_redact = fitz.Rect(sp_rect.x0 - 1, sp_rect.y0, sp_rect.x1 + 1, sp_rect.y1) & page.rect
                        if not sp_redact.is_empty:
                            page.add_redact_annot(sp_redact, fill=bg_fill)
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

                    # Step 2: Reinsert each suffix span at its shifted position
                    for sp in suffix:
                        sp_text = sp.get('text', '')
                        if not sp_text:
                            continue
                        sp_rect = sp['bbox'] if isinstance(sp['bbox'], fitz.Rect) else fitz.Rect(sp['bbox'])
                        sp_origin = sp.get('origin')
                        if sp_origin and len(sp_origin) >= 2:
                            new_pos = (sp_origin[0] - shift, sp_origin[1])
                        else:
                            # Estimate baseline from bbox
                            rect_h = sp_rect.height
                            new_pos = (sp_rect.x0 - shift, sp_rect.y0 + rect_h * 0.85)

                        sp_fontname = sp.get('font', fontname)
                        sp_fontsize = sp.get('size', fontsize)
                        sp_color_raw = sp.get('color', color)
                        # Normalize color: rawdict may return int (packed RGB) or tuple
                        if isinstance(sp_color_raw, int):
                            sp_color = (
                                ((sp_color_raw >> 16) & 0xff) / 255.0,
                                ((sp_color_raw >> 8) & 0xff) / 255.0,
                                (sp_color_raw & 0xff) / 255.0,
                            )
                        else:
                            sp_color = sp_color_raw

                        clean_sp_font = sp_fontname.split('+', 1)[1] if '+' in sp_fontname else sp_fontname
                        inserted = False
                        try:
                            page.insert_text(new_pos, sp_text, fontname=clean_sp_font,
                                             fontfile=suffix_fontfile,
                                             fontsize=sp_fontsize, color=sp_color)
                            inserted = True
                        except Exception as _sp_err:
                            debug_log.append(f"Reflow: BUG-2 suffix reinsert failed for suffix length={len(sp_text)} ({clean_sp_font}): {_sp_err}")
                        if not inserted:
                            try:
                                fallback = "times" if ('times' in sp_fontname.lower() or 'serif' in sp_fontname.lower()) else "helv"
                                page.insert_text(new_pos, sp_text, fontname=fallback,
                                                 fontsize=sp_fontsize, color=sp_color)
                                debug_log.append(f"Reflow: BUG-2 suffix reinsert used fallback font '{fallback}' for suffix length={len(sp_text)}")
                            except Exception as _sp_err2:
                                debug_log.append(f"Reflow: BUG-2 suffix reinsert fallback also failed for suffix length={len(sp_text)}: {_sp_err2}")

                    debug_log.append(f"Reflow: BUG-2 fix complete — suffix shifted left by {shift:.1f}pt")
                else:
                    debug_log.append(f"Reflow: Suffix gap {actual_gap:.1f}pt below threshold ({gap_threshold:.1f}pt); suffix preserved in place")

        return True, line_rect

    finally:
        # Ensure document is always closed to prevent resource leaks
        if src_doc:
            src_doc.close()
