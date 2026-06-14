"""
searcher.py - robust PDF text search (Candidate C extraction).

One interface: find(page, target_text, ...) -> fitz.Rect | [fitz.Rect] | None.
Behind it sits a cascade of fallback strategies (exact, quads, block scan,
dict scan, bullet-strip, flexible-whitespace, multi-line). Lifted out of
core.replace_text_in_pdf so the cascade is the test surface - each strategy
is now exercisable against a hand-built page without driving a full edit.

The `diagnostic` argument is any object exposing .add_strategy(name, outcome);
core passes a SearchDiagnostic. Kept duck-typed so searcher need not import
core (which would be a circular import).
"""
import fitz

from .text_normalize import normalize_text_for_matching, normalize_special_chars


def find(page, target_text: str, return_all: bool = False, diagnostic=None):
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
