import fitz

def _parse_font_name(font_name):
    """
    Parse font name into base family and weight/style.
    Returns: (base_family, is_bold, is_italic)
    """
    # Remove subset prefix (e.g., "AAAAAA+")
    if '+' in font_name:
        font_name = font_name.split('+')[-1]

    fn_lower = font_name.lower()

    # Detect weight/style
    is_bold = any(w in fn_lower for w in ['bold', '-bd', 'black', 'heavy', 'semibold', 'demibold'])
    is_italic = any(w in fn_lower for w in ['italic', 'oblique', '-it', 'ital'])

    # Extract base family by removing style suffixes
    base = fn_lower
    # Process longer suffixes first to avoid overlap issues (e.g., "BoldItalic" -> "Italic" -> "")
    # Use removesuffix to only remove from end
    suffixes = ['-bolditalic', ',bolditalic', '-bold', ',bold', '-italic', ',italic',
                '-oblique', '-regular', '-light', '-medium', '-semibold', '-black',
                '-heavy', '-bd', '-it', 'bolditalic', 'bold', 'italic']
    for suffix in suffixes:
        if base.lower().endswith(suffix.lower()):
            base = base[:-len(suffix)]
            break  # Only remove one suffix to avoid over-stripping

    # Handle comma-separated (e.g., "Arial,Bold")
    if ',' in base:
        base = base.split(',')[0]

    # Remove common suffixes (ArialMT -> Arial)
    for suffix in ['mt', 'ps', 'psmt']:
        if base.endswith(suffix):
            base = base[:-len(suffix)]

    return base.strip('-_ '), is_bold, is_italic

def harvest_glyphs(doc, required_chars, target_font_name, target_color=None, page_limit=10):
    """
    Search the document for instances of the required characters rendered with target_font_name.
    
    Args:
        doc: fitz.Document
        required_chars: set/list of chars
        target_font_name: str
        target_color: int (sRGB integer) or None. If set, filters by color.
        page_limit: int
    """
    glyph_map = {}
    missing = set(required_chars)

    # Parse target font for family and weight matching
    target_base, target_bold, target_italic = _parse_font_name(target_font_name)

    for pno in range(min(len(doc), page_limit)):
        if not missing: break

        page = doc[pno]
        # Use rawdict to get precise character bboxes
        blocks = page.get_text("rawdict").get("blocks", [])

        for b in blocks:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    # Parse source font
                    s_font = s.get('font', '')
                    if not s_font:
                        continue
                    src_base, src_bold, src_italic = _parse_font_name(s_font)

                    # BUG #50 FIX: Stricter font matching to avoid false matches
                    # Match criteria: family + weight + style must all match
                    if src_base != target_base:
                        continue

                    # Additional check: base family must be meaningful (not empty or too short)
                    # This prevents over-stripped font names from matching everything
                    if len(src_base) < 2 or len(target_base) < 2:
                        continue  # Skip fonts with invalid/too-short base names

                    if src_bold != target_bold:
                        continue
                    if src_italic != target_italic:
                        continue
                        
                    # Check Color Match (if requested)
                    if target_color is not None:
                        # s['color'] is typically an integer in sRGB format from PyMuPDF rawdict
                        # Note: This assumes sRGB color space. CMYK/Lab colors would need conversion.
                        s_color = s.get('color')
                        if s_color is None:
                            continue

                        # Validate that color is a valid integer (not None, not tuple)
                        if not isinstance(s_color, int) or not isinstance(target_color, int):
                            continue  # Skip if color format is unexpected

                        # Compare integers directly if exact match is needed?
                        # Or decompose to RGB.
                        if s_color != target_color:
                             # Allow small tolerance or simple exact match?
                             # In PDFs, black is 0. Blue is ~some large int.
                             # Decompose assuming sRGB (RGB888 format: 0xRRGGBB)
                             r1 = (s_color >> 16) & 0xFF
                             g1 = (s_color >> 8) & 0xFF
                             b1 = s_color & 0xFF

                             r2 = (target_color >> 16) & 0xFF
                             g2 = (target_color >> 8) & 0xFF
                             b2 = target_color & 0xFF

                             # Calculate Euclidean distance in RGB space
                             # This is more accurate than Manhattan distance
                             dist = ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)**0.5

                             # Use adaptive tolerance:
                             # - For black/dark colors: stricter (max 15)
                             # - For bright/colored text: more lenient (max 50)
                             # This handles anti-aliasing and slight color variations
                             if r1 < 50 and g1 < 50 and b1 < 50 and r2 < 50 and g2 < 50 and b2 < 50:
                                 # Both are dark - use strict tolerance
                                 max_dist = 20
                             else:
                                 # At least one is colored - be more lenient
                                 max_dist = 60

                             if dist > max_dist:
                                 continue
                        
                chars = s.get('chars', [])
                for i, char in enumerate(chars):
                    c = char.get('c', '')
                    if not c:
                        continue
                    if c in missing:
                        # Validate visual presence (Ink Check)
                        # Render a small thumbnail of the candidate char
                        # We use the bbox slightly padded to ensure we catch the ink
                        char_bbox = char.get('bbox')
                        if not char_bbox:
                            continue
                        check_rect = fitz.Rect(char_bbox)
                        if check_rect.is_empty or check_rect.width < 0.1 or check_rect.height < 0.1:
                            continue

                        # Check if it has ink AND correct color
                        # Assuming white background.
                        # We need to verify that the glyph:
                        # 1. Has visible ink (not completely white/transparent)
                        # 2. Matches the target color (if specified)
                        try:
                            pix = page.get_pixmap(clip=check_rect, matrix=fitz.Matrix(2, 2), alpha=False)

                            # Validate pixmap is not empty
                            if not pix or pix.width == 0 or pix.height == 0:
                                continue

                            has_ink = False
                            color_matches = True if target_color is None else False

                            samples = pix.samples
                            if samples:
                                # Scan pixels to validate both ink presence and color
                                for j in range(0, len(samples) - 2, 3): # RGB assumption; -2 prevents over-read
                                    r_pix = samples[j]
                                    g_pix = samples[j+1]
                                    b_pix = samples[j+2]
                                    lum = (r_pix + g_pix + b_pix) // 3

                                    # Check for ink (any non-white pixel)
                                    if lum < 240:
                                        has_ink = True

                                        # If target color is specified, validate pixel color
                                        if target_color is not None:
                                            # Extract target RGB
                                            r_target = (target_color >> 16) & 0xFF
                                            g_target = (target_color >> 8) & 0xFF
                                            b_target = target_color & 0xFF

                                            # Calculate color distance
                                            color_dist = ((r_pix - r_target)**2 + (g_pix - g_target)**2 + (b_pix - b_target)**2)**0.5

                                            # For dark/black targets, use strict tolerance
                                            # This prevents red glyphs from matching black targets
                                            if r_target < 50 and g_target < 50 and b_target < 50:
                                                # Strict tolerance for black - only allow near-black pixels
                                                if color_dist < 50:  # Allow some anti-aliasing
                                                    color_matches = True
                                                    break  # Found a valid pixel
                                            else:
                                                # More lenient for colored targets
                                                if color_dist < 80:
                                                    color_matches = True
                                                    break

                            if not has_ink:
                                # Skip invisible glyph
                                continue

                            if not color_matches:
                                # Skip glyph with wrong color
                                # This prevents red glyphs from being used when we want black
                                continue

                        except Exception:
                            # If pixmap fails, likely invalid rect. Skip.
                            continue

                        # Found a valid candidate!
                        # We capture detailed info.
                        
                        # Calculate advance width
                        # If not last char, diff with next char origin
                        advance = 0
                        if i < len(chars) - 1:
                            next_org = chars[i+1].get('origin')
                            curr_org = char.get('origin')
                            if next_org and curr_org and len(next_org) >= 1 and len(curr_org) >= 1:
                                advance = next_org[0] - curr_org[0]
                        else:
                            # Last char: bbox width + estimated side bearing
                            # BBox width is typically the "ink" bounds, not the full
                            # character cell. Add ~12% for typical side bearings.
                            # This prevents character overlap in synthesis.
                            bbox = char.get('bbox')
                            if not bbox:
                                continue
                            bbox_width = bbox[2] - bbox[0]
                            advance = bbox_width * 1.12  # 12% for side bearings

                        char_origin = char.get('origin')
                        if not char_origin:
                            continue  # Skip glyphs without origin data
                        char_bbox_final = char.get('bbox')
                        if not char_bbox_final:
                            continue
                        glyph_map[c] = {
                            'page': pno,
                            'bbox': fitz.Rect(char_bbox_final),
                            'origin': char_origin,
                            'font': s.get('font', ''),
                            'size': s.get('size', 12.0),
                            'color': s.get('color', 0),
                            'advance': advance
                        }
                        missing.discard(c)  # Use discard to avoid KeyError on duplicates
                        if not missing: break

                # Harvest space advance from this matching-font span if not yet measured.
                # Spaces have no ink, so they're excluded from the ink-check loop above.
                # Instead, find any space char in the span and measure origin-to-origin advance.
                if ' ' not in glyph_map:
                    for i, char in enumerate(chars):
                        if char.get('c') == ' ' and i < len(chars) - 1:
                            curr_org = char.get('origin')
                            next_org = chars[i + 1].get('origin')
                            if curr_org and next_org and len(curr_org) >= 1 and len(next_org) >= 1:
                                space_adv = next_org[0] - curr_org[0]
                                if space_adv > 0:
                                    # Scale-independent: store advance at the span's font size
                                    span_size = s.get('size', 12.0)
                                    glyph_map[' '] = {'advance': space_adv, 'size': span_size}
                                    break

                if not missing: break
            if not missing: break

    return glyph_map, missing
