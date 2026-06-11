# Collision Detection Analysis and Improvements

**Date:** 2026-01-24
**Issue:** Visual collision detection too strict, blocking valid edits
**Location:** `Sources/Marcedit/python_site/editor_pkg/optical.py:19-134`

---

## 🐛 Current Problem

**User Report:** "Edit failed: Visual Collision: Visual collision detected at 43,57"

**Root Cause:** The collision detection algorithm in `detect_visual_collision()` is too aggressive:
- Triggers on ANY adjacent pixels (>5 touching pixels)
- No tolerance for anti-aliasing
- No configuration options
- No override capability

---

## 🔍 Current Algorithm Analysis

### Algorithm Overview

**Location:** `optical.py:detect_visual_collision()`

**2-Pass Process:**
1. **Pass 1** (lines 57-100): Classify each pixel as:
   - `0` = Background (white)
   - `1` = Static content (existing text)
   - `2` = New content (changed pixels)

2. **Pass 2** (lines 105-134): Check adjacency
   - For each new content pixel (`2`)
   - Check 8 neighbors for static content (`1`)
   - If >5 touching pixels found → ERROR

### Problem Areas

**Issue 1: Too Strict Threshold (lines 126-129)**
```python
if len(collision_points) > 5:
    return True, f"Visual collision detected at {x},{y}"
```
- Threshold of 5 pixels is very low
- Anti-aliasing can easily cause 5+ pixel overlap
- No configuration option

**Issue 2: Binary Decision (lines 131-132)**
```python
if len(collision_points) > 0:
    return True, f"Visual collision detected ({len(collision_points)} pixels touching)"
```
- Even 1 pixel touching → error
- No "warning" mode
- No override option

**Issue 3: Sensitivity Hardcoded (line 27)**
```python
def detect_visual_collision(before_pix, after_pix, sensitivity=10, exclusion_rect=None):
```
- `sensitivity=10` works for most cases
- But some PDFs have gradients, shadows, anti-aliasing
- Needs per-PDF tuning

---

## ✅ Proposed Solutions

### Solution 1: Configurable Thresholds

**Add parameters:**
```python
def detect_visual_collision(
    before_pix, after_pix,
    sensitivity=10,
    exclusion_rect=None,
    collision_threshold=20,  # NEW: Min pixels to consider collision
    allow_warning=False       # NEW: Return warning instead of error
):
```

**Benefits:**
- User can tune sensitivity per PDF
- Warning mode for review
- Backward compatible (defaults unchanged)

### Solution 2: Smart Tolerance

**Implement intelligent thresholds based on content:**
```python
# Calculate collision severity
total_new_pixels = sum(1 for p in grid if p == 2)
collision_ratio = len(collision_points) / total_new_pixels

if collision_ratio < 0.05:  # <5% of new pixels touching
    return False, "Minor anti-aliasing overlap (acceptable)"
elif collision_ratio < 0.15:  # 5-15% touching
    if allow_warning:
        return False, f"Warning: {len(collision_points)} pixels near existing text"
    else:
        return True, f"Moderate collision: {len(collision_points)} pixels"
else:  # >15% touching
    return True, f"Major collision: {len(collision_points)} pixels ({collision_ratio*100:.1f}%)"
```

**Benefits:**
- Context-aware (small overlap vs large overlap)
- Percentage-based (scales with text size)
- Three severity levels

### Solution 3: Exclusion Zone Expansion

**Current:** Exclusion rect only covers exact replaced text
**Problem:** Doesn't account for anti-aliasing bleeding

**Fix:**
```python
# Expand exclusion zone by 2-3 pixels for anti-aliasing
if exclusion_rect:
    expanded_rect = exclusion_rect + (-3, -3, 3, 3)  # Add 3px margin
    if expanded_rect.contains(fitz.Point(x, y)):
        is_excluded = True
```

**Benefits:**
- Accounts for font rendering differences
- Still catches real collisions
- Simple to implement

---

## 🎯 Recommended Implementation

### Phase 1: Quick Fix (Today - Week 6 Day 1)

**Change line 126 threshold:**
```python
# BEFORE:
if len(collision_points) > 5:

# AFTER:
if len(collision_points) > 20:  # More tolerant threshold
```

**Add collision_threshold parameter:**
```python
def detect_visual_collision(before_pix, after_pix, sensitivity=10, exclusion_rect=None, collision_threshold=20):
    # ... existing code ...
    if len(collision_points) > collision_threshold:
        return True, f"Visual collision detected at {x},{y}"
```

**Update core.py to pass threshold:**
```python
has_collision, msg = optical.detect_visual_collision(
    before_pix, after_pix,
    exclusion_rect=excl_rect,
    collision_threshold=20  # NEW parameter
)
```

### Phase 2: Smart Detection (Week 6 Day 4)

**Implement ratio-based detection:**
- Calculate collision_ratio
- Three severity levels
- Warning mode option
- Better error messages with suggestions

### Phase 3: User Controls (Week 6 Day 4)

**Add UI controls** (if accessible):
- Collision sensitivity slider
- "Force override" checkbox
- Visual preview of collision zones

---

## 📊 Expected Impact

### Current Behavior
- 5+ pixels touching → ERROR
- Blocks many valid edits
- User frustrated
- No override option

### After Phase 1 (Quick Fix)
- 20+ pixels touching → ERROR
- Most valid edits work
- Still catches real collisions
- Configurable threshold

### After Phase 2 (Smart Detection)
- Ratio-based (<5% OK, 5-15% warning, >15% error)
- Context-aware decisions
- Better error messages
- Warning mode available

### After Phase 3 (User Controls)
- User has full control
- Can override when needed
- Visual feedback
- Production-ready

---

## 🔧 Implementation Plan

**Today (Week 6 Day 1):**
- [x] Analyze collision detection
- [ ] Implement Phase 1 (quick fix)
- [ ] Test with user's PDF
- [ ] Verify existing tests still pass

**Week 6 Day 4:**
- [ ] Implement Phase 2 (smart detection)
- [ ] Implement Phase 3 (user controls)
- [ ] Comprehensive testing
- [ ] Documentation

---

## 📝 Code Changes Required

### File 1: `optical.py`

**Function signature change (line 19):**
```python
def detect_visual_collision(before_pix, after_pix, sensitivity=10, exclusion_rect=None, collision_threshold=20, allow_warning=False):
```

**Threshold check change (line 126):**
```python
if len(collision_points) > collision_threshold:
    return True, f"Visual collision detected at {x},{y}"
```

**Final check change (lines 131-132):**
```python
if len(collision_points) > 0:
    if allow_warning:
        return False, f"Warning: {len(collision_points)} pixels near existing text"
    else:
        return True, f"Visual collision detected ({len(collision_points)} pixels touching)"
```

### File 2: `core.py`

**Function call change (line 2692):**
```python
has_collision, msg = optical.detect_visual_collision(
    before_pix, after_pix,
    exclusion_rect=excl_rect,
    collision_threshold=20,  # NEW
    allow_warning=False      # NEW (could be True for lenient mode)
)
```

---

## ✅ Testing Strategy

### Test 1: User's PDF
- Use the PDF from screenshot
- Try the edit that failed
- Should now succeed

### Test 2: Real Collision
- Create PDF with overlapping text
- Verify collision still detected
- Threshold should catch it

### Test 3: Anti-Aliasing
- Create PDF with anti-aliased fonts
- Small overlap should be OK
- Large overlap should fail

### Test 4: Existing Tests
- Run all 21 Week 5 tests
- Should all still pass
- No regressions

---

**Status:** Analysis complete, ready to implement Phase 1
**Next:** Implement quick fix and test with user's PDF
