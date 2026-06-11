import fitz

def draw_text_as_vectors(page, start_point, text, glyph_map, size, color=None, doc=None, space_width=None, tracking_delta=None):
    """
    Synthesize text by stamping harvested glyphs.

    Args:
        page: fitz.Page (target page)
        start_point: (x, y) tuple (baseline origin)
        text: str (text to write)
        glyph_map: dict from harvester
        size: float (target font size)
        color: tuple/int (ignored for stamping, as we copy source color)
        doc: fitz.Document (source document, usually same as page.parent)
        space_width: float or None (override space width for justified text)
        tracking_delta: float or None (additional spacing between characters)

    Returns:
        float: total width of drawn text
    """
    # Input validation
    if page is None:
        print("[Synthesizer] ERROR: draw_text_as_vectors called with None page")
        return (0.0, [])
    if not start_point or len(start_point) != 2:
        print("[Synthesizer] ERROR: draw_text_as_vectors called with invalid start_point")
        return (0.0, [])
    if not text or not isinstance(text, str):
        print("[Synthesizer] ERROR: draw_text_as_vectors called with invalid text")
        return (0.0, [])
    if not glyph_map or not isinstance(glyph_map, dict):
        print("[Synthesizer] ERROR: draw_text_as_vectors called with invalid glyph_map")
        return (0.0, [])
    if not size or size <= 0:
        print("[Synthesizer] ERROR: draw_text_as_vectors called with invalid size")
        return (0.0, [])

    if doc is None: doc = page.parent
    
    curr_x, curr_y = start_point
    total_width = 0
    drawn_rects = []
    
    for char in text:
        if char == ' ':
            if space_width is not None:
                # Explicit override (e.g., justified text)
                space_w = space_width
            elif ' ' in glyph_map and glyph_map[' '].get('size', 0) > 0:
                # Use harvested space advance, scaled to target size
                raw = glyph_map[' ']['advance']
                src_size = glyph_map[' ']['size']
                space_w = raw * (size / src_size)
            else:
                # Fallback: 30% of em (rough but acceptable)
                space_w = size * 0.30
            curr_x += space_w
            total_width += space_w
            continue
            
        g_info = glyph_map.get(char)
        if not g_info:
            # Fallback for missing char? 
            # Leave blank space or draw placeholder?
            # Phase 3 says "Synthesize". If missing, maybe draw a red box?
            # For now, skip.
            print("Synthesizer Warning: Missing glyph")
            continue
            
        # Source info — validate before use
        src_page_num = g_info.get('page')
        if src_page_num is None:
            print("Synthesizer Warning: Missing page for glyph")
            continue
        src_bbox = g_info.get('bbox')
        src_origin = g_info.get('origin')
        src_size = g_info.get('size', 0)
        if not src_bbox or not src_origin or not hasattr(src_bbox, 'x0') or len(src_origin) < 2:
            print("Synthesizer Warning: Invalid glyph data")
            continue
        
        # Calculate Scale
        # We want to scale based on Font Size ratio
        scale = size / src_size if src_size > 0 else 1.0
        scale = max(0.01, min(scale, 100.0))  # Clamp to sane range
        
        # Calculate Target Rect
        # We align by ORIGIN (Baseline)
        # src_bbox relative to src_origin needs to be mapped to target
        
        # Vector from origin to bbox top-left
        dx = (src_bbox.x0 - src_origin[0]) * scale
        dy = (src_bbox.y0 - src_origin[1]) * scale # y grows down
        
        target_x0 = curr_x + dx
        target_y0 = curr_y + dy
        
        target_w = src_bbox.width * scale
        target_h = src_bbox.height * scale
        
        target_rect = fitz.Rect(target_x0, target_y0, target_x0 + target_w, target_y0 + target_h)
        
        # STAMP IT
        # show_pdf_page places the WHOLE page clipped.
        # Format: page.show_pdf_page(rect, src_doc, pno, clip=src_bbox)
        # rect = target placement on 'page'
        # clip = source area on 'src_doc[pno]'
        
        page.show_pdf_page(target_rect, doc, src_page_num, clip=src_bbox)
        drawn_rects.append((char, target_rect))
        
        # Advance Cursor
        # We need the "advance width" of the character.
        # BBox width is NOT the advance width (e.g. 'i' vs 'w').
        # BBox is tight and doesn't include side bearings.
        # We can approximate advance width by bbox.width + small tracking?
        # Or better: if we have the span info, can we calculate advance?
        # PyMuPDF rawdict doesn't give advance width directly.
        # But we can assume bbox.width + buffer?

        if 'advance' in g_info and g_info['advance'] > 0:
             # Use the measured advance from the harvester (most accurate)
             advance = g_info['advance'] * scale
        else:
             # Fallback: Use bbox width + side bearing estimate
             # Side bearings as percentage of bbox are larger for narrow glyphs
             # but we also enforce a minimum advance based on font size to prevent
             # narrow chars (i, l, t) from collapsing together
             if char in 'ijltfIJLTF':
                 side_bearing_pct = 0.25
                 min_advance = size * 0.28  # narrow chars need minimum spacing
             elif char in 'mwMW':
                 side_bearing_pct = 0.08
                 min_advance = 0
             elif char in '.,:;!?':
                 side_bearing_pct = 0.20
                 min_advance = size * 0.20
             else:
                 side_bearing_pct = 0.15
                 min_advance = 0

             advance = max(target_w * (1.0 + side_bearing_pct), min_advance)

        if tracking_delta:
            advance += tracking_delta
        curr_x += advance
        total_width += advance
        
    return total_width, drawn_rects
