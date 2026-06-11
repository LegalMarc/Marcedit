#!/usr/bin/env python3
"""
Visual Stress Test Generator

Generates a PDF with 200 permutations of text blocks to visually verify:
- Justification (Left/Center/Right)
- Auto-flow wrapping
- Font styling (Bold/Italic)
- Color batching
- Mixed spans
"""

import sys
import os
import random
from pathlib import Path
import fitz

# Setup paths
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
PYTHON_SITE = PROJECT_ROOT / "Sources" / "Marcedit" / "python_site"

sys.path.insert(0, str(PYTHON_SITE))

from editor_pkg import core

def generate_scenarios(count=200):
    scenarios = []
    
    alignments = ['Left', 'Center', 'Right']
    fonts = ['Helvetica', 'Times-Roman', 'Courier']
    sizes = [8, 10, 12, 14]
    colors = [
        [0,0,0], # Black
        [1,0,0], # Red
        [0,0,1], # Blue
        [0,0.5,0] # Green
    ]
    
    texts = [
        "Short label",
        "A longer sentence.",
        "Line 1\nLine 2\nLine 3",
        "Mixed styles",
        "123.45"
    ]
    
    for i in range(count):
        # Random mix
        align = random.choice(alignments)
        font = random.choice(fonts)
        size = random.choice(sizes)
        color = random.choice(colors)
        text_template = random.choice(texts)
        
        # Construct spans based on template
        spans = []
        
        if "Mixed styles" in text_template:
            # Manually construct mixed span (same line)
            spans = [
                {'text': "Mixed ", 'font': font, 'size': size, 'color': color, 'line_index': 0},
                {'text': "Bold ", 'font': font, 'size': size, 'is_bold': True, 'color': [1,0,0], 'line_index': 0},
                {'text': "Italic", 'font': font, 'size': size, 'is_italic': True, 'color': [0,0,1], 'line_index': 0},
            ]
        elif "\n" in text_template:
            # Multi-line: split into separate spans with different line_index
            lines = text_template.split("\n")
            for idx, line_text in enumerate(lines):
                spans.append({
                    'text': line_text, 
                    'font': font, 
                    'size': size, 
                    'color': color,
                    'line_index': idx
                })
        else:
             spans = [
                 {'text': text_template, 'font': font, 'size': size, 'color': color, 'line_index': 0}
             ]
             
        scenarios.append({
            'label': f"#{i+1} {align} {font[:4]} {size}",
            'overrides': {
                'justification': align,
                'manual_size_delta': 0.0
            },
            'spans': spans
        })
        
    return scenarios

def main():
    print("Generating visual stress test...")
    
    # OUTPUT PATH
    output_filename = "visual_stress_test.pdf"
    final_output = SCRIPT_DIR / output_filename
    
    # 1. Create Base PDF
    doc = fitz.open()
    
    # Grid Config
    COLS = 3
    ROWS = 8
    BLOCKS_PER_PAGE = COLS * ROWS
    
    PAGE_WIDTH = 612 # Letter
    PAGE_HEIGHT = 792
    
    MARGIN_X = 50
    MARGIN_Y = 50
    GAP_X = 20
    GAP_Y = 20
    
    BLOCK_W = (PAGE_WIDTH - (2 * MARGIN_X) - ((COLS - 1) * GAP_X)) / COLS
    BLOCK_H = (PAGE_HEIGHT - (2 * MARGIN_Y) - ((ROWS - 1) * GAP_Y)) / ROWS
    
    scenarios = generate_scenarios(200)
    
    # Pre-render pages with placeholder rectangles
    total_pages = (len(scenarios) + BLOCKS_PER_PAGE - 1) // BLOCKS_PER_PAGE
    
    block_map = [] # List of (page_idx, rect, scenario)
    
    print(f"Layout: {total_pages} pages, {COLS}x{ROWS} grid.")
    
    for p_idx in range(total_pages):
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        
        # Draw grid
        shape = page.new_shape()
        
        for r in range(ROWS):
            for c in range(COLS):
                idx = (p_idx * BLOCKS_PER_PAGE) + (r * COLS) + c
                if idx >= len(scenarios): break
                
                x = MARGIN_X + (c * (BLOCK_W + GAP_X))
                y = MARGIN_Y + (r * (BLOCK_H + GAP_Y))
                rect = fitz.Rect(x, y, x + BLOCK_W, y + BLOCK_H)
                
                # Draw border
                shape.draw_rect(rect)
                shape.finish(color=(0.8, 0.8, 0.8)) # Gray Stroke
                
                # Add label
                label = scenarios[idx]['label']
                page.insert_text((x, y - 5), label, fontsize=6, color=(0.5, 0.5, 0.5))
                
                block_map.append({
                    'page': p_idx + 1,
                    'bbox': [rect.x0, rect.y0, rect.x1, rect.y1],
                    'scenario': scenarios[idx]
                })
        
        shape.commit()

    # Save initial base
    doc.save(final_output)
    doc.close()
    
    print(f"Base PDF created at {final_output}. Applies edits...")
    
    # 2. Iterate and Apply Edits
    # We chain edits to avoid re-opening too much, but replace_block_with_spans saves every time.
    # To optimize, we could modify core logic, but let's just stick to the API for correctness.
    
    current_pdf = str(final_output)
    temp_pdf = str(SCRIPT_DIR / "temp_work.pdf")
    
    total = len(block_map)
    for i, item in enumerate(block_map):
        if i % 10 == 0:
            print(f"Processing {i}/{total}...")
            
        scenario = item['scenario']
        spans = scenario['spans']
        
        # Add bbox to spans (all zero to force flow) - preserve existing line_index
        for s in spans:
            s['bbox'] = [0,0,0,0]
            if 'line_index' not in s:
                s['line_index'] = 0
            
        overrides = scenario['overrides']
        
        result = core.replace_block_with_spans(
            input_path=current_pdf,
            output_path=temp_pdf,
            page_number=item['page'],
            block_bbox=item['bbox'],
            spans=spans,
            manual_overrides=overrides
        )
        
        if not result['success']:
            print(f"FAILED at #{i}: {result['message']}")
        else:
            # Swap paths
            os.replace(temp_pdf, current_pdf)
            
    print(f"Done! Saved to {final_output}")

if __name__ == "__main__":
    main()
