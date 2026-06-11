import fitz
import sys

def _estimate_background_lum(samples, w, h, n):
    """
    Estimate the background luminance by sampling the outer border of a pixmap.
    The capture region extends past the text (10pt buffer), so border pixels
    are likely background rather than ink.
    Returns: float luminance in range [0, 255].
    """
    if w < 4 or h < 4 or len(samples) < n:
        return 255.0
    lum_sum = 0.0
    count = 0
    # Sample first two rows (above-text buffer) and last two rows (below-text buffer)
    sample_x_step = max(1, w // 8)
    for row in [0, 1, h - 2, h - 1]:
        if row < 0 or row >= h:
            continue
        for x in range(0, w, sample_x_step):
            off = (row * w + x) * n
            if off + 2 < len(samples):
                lum_sum += (samples[off] + samples[off + 1] + samples[off + 2]) / 3.0
                count += 1
    # Also sample first and last columns
    for col in [0, 1, w - 2, w - 1]:
        if col < 0 or col >= w:
            continue
        for y in range(0, h, max(1, h // 8)):
            off = (y * w + col) * n
            if off + 2 < len(samples):
                lum_sum += (samples[off] + samples[off + 1] + samples[off + 2]) / 3.0
                count += 1
    return (lum_sum / count) if count > 0 else 255.0


def capture_region(page, rect, zoom=2.0):
    """
    Capture a high-res bitmap of a specific rectangular region on the page.
    Args:
        page: fitz.Page object
        rect: fitz.Rect of the region to capture
        zoom: Scale factor (2.0 = 144 DPI, good for collision detection)
    Returns:
        fitz.Pixmap
    """
    mat = fitz.Matrix(zoom, zoom)
    # Clip to rect to avoid rendering whole page
    pix = page.get_pixmap(matrix=mat, clip=rect)
    return pix

def detect_visual_collision(before_pix, after_pix, sensitivity=10, exclusion_rect=None, allow_warning=False):
    """
    Compare before/after snapshots to detect if new text touches old text.

    Args:
        before_pix: Pixmap of region BEFORE edit
        after_pix: Pixmap of region AFTER edit
        sensitivity: Threshold for pixel difference (0-255) to count as change.
        exclusion_rect: fitz.Rect (relative to pixmap) where static content is allowed (original text area).
        allow_warning: If True, return warning instead of error for minor collisions

    Returns:
        tuple: (has_collision: bool, details: str)
    """
    if before_pix.w != after_pix.w or before_pix.h != after_pix.h:
        return True, "Dimension mismatch between snapshots"

    if before_pix.n != after_pix.n:
        return True, "Pixel component count mismatch between snapshots"

    w, h = before_pix.w, before_pix.h
    n = before_pix.n # components per pixel (e.g. 3 for RGB, 4 for RGBA)

    # Guard: pixel access below assumes at least 3 components (RGB)
    if n < 3:
        return True, f"Unsupported pixel format (n={n}, expected >= 3)"

    # Access raw samples
    samples_before = before_pix.samples
    samples_after = after_pix.samples

    # Estimate background luminance from border pixels (buffers above/below/beside text).
    # This allows correct classification on tinted, gray, or colored-background pages.
    # On a plain white page, bg_lum ≈ 255 → ink_threshold ≈ 225 (stricter than old 240).
    # On a cream page (bg_lum ≈ 245), ink_threshold ≈ 215 → avoids classifying paper as ink.
    # On a dark background (bg_lum ≈ 60), ink_threshold ≈ 30 → only classifies very dark ink.
    bg_lum = _estimate_background_lum(samples_before, w, h, n)
    ink_threshold = max(bg_lum - 30.0, 10.0)

    # We map pixels to a 2D grid:
    # 0 = Background (at or near page background color)
    # 1 = Static Content (dark ink that didn't change between snapshots)
    # 2 = New Content (pixels that changed, becoming darker)
    
    grid = [0] * (w * h)
    
    # Pass 1: Classify pixels
    
    changes_detected = False
    
    try:
        for y in range(h):
            for x in range(w):
                offset = (y * w + x) * n
                
                # Get luminance/darkness
                # Simple average of RGB
                r_b, g_b, b_b = samples_before[offset], samples_before[offset+1], samples_before[offset+2]
                r_a, g_a, b_a = samples_after[offset], samples_after[offset+1], samples_after[offset+2]
                
                lum_before = (r_b + g_b + b_b) / 3
                lum_after = (r_a + g_a + b_a) / 3

                is_dark_before = lum_before < ink_threshold  # Ink, not background
                is_dark_after = lum_after < ink_threshold    # Ink, not background
                
                diff = abs(lum_after - lum_before)
                is_changed = diff > sensitivity
                
                idx = y * w + x
                
                if is_changed and is_dark_after:
                    # New ink added here
                    grid[idx] = 2    # NEW CONTENT
                    changes_detected = True
                elif is_dark_before and is_dark_after and not is_changed:
                    # Ink was here, and stayed here
                    # CHECK EXCLUSION: If this static content is inside the original text box, ignore it.
                    # It's likely just the new text overlapping the old text exactly.
                    is_excluded = False
                    if exclusion_rect:
                        # exclusion_rect is rect relative to pixmap (0,0 is top-left of pixmap)
                        # Pixel x,y corresponds to x,y in pixmap
                        if exclusion_rect.contains(fitz.Point(x, y)):
                            is_excluded = True
                    
                    if not is_excluded:
                        grid[idx] = 1    # STATIC CONTENT (Neighbor)
                    else:
                        grid[idx] = 0    # Treated as safe background/overlap
                else:
                    grid[idx] = 0    # BACKGROUND or erased content
                    
    except IndexError:
        return True, "Pixel access error"

    if not changes_detected:
        return True, "No visual change detected (Ghost Edit)"
        
    # Pass 2: Check for collisions (Adjacency)
    # Check if any '2' pixel is adjacent to a '1' pixel
    
    # 8-neighbor checks are best
    neighbors = [
        (-1, -1), (0, -1), (1, -1),
        (-1,  0),          (1,  0),
        (-1,  1), (0,  1), (1,  1)
    ]
    
    collision_points = []

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if grid[idx] == 2: # If this is new content
                # Look around for static content (1), with bounds checking
                for dy, dx in neighbors:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        n_idx = ny * w + nx
                        if grid[n_idx] == 1:
                            collision_points.append((x, y))
                            break  # Break inner loop to avoid counting same pixel multiple times

    # Phase 2: Smart ratio-based detection (Week 6 Day 4)
    if len(collision_points) > 0:
        # Calculate collision ratio (percentage of new pixels touching old content)
        total_new_pixels = sum(1 for p in grid if p == 2)

        if total_new_pixels > 0:
            collision_ratio = len(collision_points) / total_new_pixels

            # Determine severity based on ratio
            if collision_ratio < 0.05:  # <5% of new pixels touching
                # Minor collision - likely anti-aliasing or minimal overlap
                if allow_warning:
                    return False, f"Minor overlap: {len(collision_points)} pixels ({collision_ratio*100:.1f}% of new content) - acceptable"
                else:
                    # Even in strict mode, <5% is very minor
                    return False, f"Clean edit (minor anti-aliasing: {len(collision_points)} pixels, {collision_ratio*100:.1f}%)"

            elif collision_ratio < 0.20:  # 5-20% touching
                # Moderate collision - noticeable but might be acceptable
                if allow_warning:
                    return False, f"Moderate overlap: {len(collision_points)} pixels ({collision_ratio*100:.1f}% of new content) - review recommended"
                else:
                    return True, f"Moderate collision: {len(collision_points)} pixels ({collision_ratio*100:.1f}% of new content). Suggestion: Check spacing or reduce font size."

            else:  # >20% touching
                # Major collision - significant overlap
                return True, f"Major collision: {len(collision_points)} pixels ({collision_ratio*100:.1f}% of new content). Suggestion: Text overlaps existing content significantly - choose different location or reduce text size."
        else:
            # Shouldn't happen (changes_detected would be False), but handle it
            return True, f"Visual collision detected ({len(collision_points)} pixels touching)"

    return False, "Clean edit"
