
import fitz
import os
import random
import sys
from pathlib import Path

# Add python_site to path (assuming this script is in tests/)
sys.path.insert(0, str(Path(__file__).parent.parent / "Sources/Marcedit/python_site"))
from editor_pkg import core

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PDF = os.path.join(PROJECT_ROOT, "ignored-resources", "bulk_visual_test_report.pdf")
SAMPLE_DIR = os.path.join(PROJECT_ROOT, "ignored-resources", "sample-files-marcedit")

def generate_report():
    print(f"Scanning for PDFs in {SAMPLE_DIR}...")
    
    if not os.path.exists(SAMPLE_DIR):
        print(f"Error: Directory not found: {SAMPLE_DIR}")
        return

    pdf_files = [f for f in os.listdir(SAMPLE_DIR) if f.lower().endswith(".pdf")]
    print(f"Found {len(pdf_files)} PDF files.")

    final_candidates = []
    
    for pdf_name in pdf_files:
        pdf_path = os.path.join(SAMPLE_DIR, pdf_name)
        print(f"Processing {pdf_name}...")
        
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"  Example failed to open: {e}")
            continue

        file_candidates = []
        for page_num, page in enumerate(doc):
            # Extract words
            words = page.get_text("words")
            # Filter words: length > 3, alpha only
            valid_words = [w for w in words if len(w[4]) > 3 and w[4].isalpha()]
            
            for w in valid_words:
                 file_candidates.append({
                    "src_pdf": pdf_path, # Absolute path
                    "short_name": pdf_name,
                    "page": page_num + 1,
                    "target": w[4],
                    "rect": fitz.Rect(w[0], w[1], w[2], w[3]),
                    "type": "word"
                })
        doc.close()
        
        if not file_candidates:
            print(f"  No valid text found in {pdf_name}")
            continue
            
        # Pick 10 random per file
        sample_size = min(len(file_candidates), 10)
        selected = random.sample(file_candidates, sample_size)
        final_candidates.extend(selected)
        print(f"  Selected {len(selected)} candidates.")

    if not final_candidates:
        print("No candidates found in any files!")
        return

    print(f"Total candidates for testing: {len(final_candidates)}")
    
    # Create Report PDF
    report_doc = fitz.open()

    short_replacements = ["Edit", "Test", "Fix", "Data", "New", "Code", "Safe", "User", "Date", "Log"]
    medium_replacements = ["Redacted", "Confirmed", "Approved", "Updated", "Verified", "Standard", "Replacement"]
    long_replacements = ["CONFIDENTIAL DATA REDACTED", "Privileged and Confidential Material", "See Attached Addendum for Details"]
    
    # Process each candidate
    for i, cand in enumerate(final_candidates):
        src_path = cand['src_pdf']
        target_len = len(cand['target'])
        
        # Decide Test Type
        is_stress_test = (i % 5 == 0) # 20% are stress tests (intentional overflow)
        
        if is_stress_test:
            new_text = random.choice(long_replacements)
            test_type = "SAFETY CHECK (Expected Collision)"
        else:
            # Smart pick to ensure fit
            # If target is short, pick short. 
            if target_len < 5:
                new_text = random.choice(short_replacements)
            elif target_len < 12:
                new_text = random.choice(medium_replacements)
            else:
                new_text = random.choice(medium_replacements + long_replacements)
                
            # Randomly inject NBCP case
            if i % 10 == 3:
                new_text = "$1, 000"
                test_type = "NBCP TOKEN CHECK"
            else:
                test_type = "VISUAL FIT CHECK"
        
        print(f"[{i+1}/100] {test_type}: '{cand['target']}' -> '{new_text}' in {cand['src_pdf']}...")

        # 1. Capture Original State (Image)
        try:
            doc_src = fitz.open(src_path)
            page_src = doc_src[cand['page']-1]
            
            # Zoom in on the target rect
            target_rect = cand['rect']
            clip_rect = fitz.Rect(target_rect)
            clip_rect.x0 -= 50
            clip_rect.y0 -= 30
            clip_rect.x1 += 50
            clip_rect.y1 += 30
            clip_rect &= page_src.rect # Intersect with page
            
            pix_orig = page_src.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip_rect)
            doc_src.close()
        except:
            print(f"  Skipping image capture for {src_path}")
            continue
        
        # 2. Perform Replacement
        temp_out = f"temp_rep_{i}.pdf"
        
        try:
            res = core.replace_text_in_pdf(
                input_path=src_path,
                output_path=temp_out,
                page_number=cand['page'],
                target_text=cand['target'],
                replacement_text=new_text
            )
            
            success = res['success']
            msg = res.get('message', '')
            
            # 3. Capture Result State (Image)
            pix_res = None
            if success:
                doc_res = fitz.open(temp_out)
                page_res = doc_res[cand['page']-1]
                pix_res = page_res.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip_rect)
                doc_res.close()
            else:
                print(f"  Result: {msg}")
                
        except Exception as e:
            print(f"  Exception: {e}")
            success = False
            msg = str(e)
            pix_res = None
        
        # 4. Add to Report
        rep_page = report_doc.new_page(width=600, height=400)
        
        # Draw Title
        title_col = (0, 0, 0)
        status_text = "SUCCESS"
        status_col = (0, 0.6, 0)
        
        if not success:
            if "Collision" in msg and is_stress_test:
                status_text = "SAFETY BLOCKED (Correct)"
                status_col = (0, 0, 1) # Blue for expected safety
            else:
                status_text = "FAILED"
                status_col = (1, 0, 0)
        
        rep_page.insert_text((20, 30), f"Case #{i+1}: {test_type}", fontsize=12, fontname="helv")
        rep_page.insert_text((20, 45), f"'{cand['target']}' -> '{new_text}'", fontsize=11, fontname="helv")
        if 'short_name' in cand:
            src_label = cand['short_name']
        else:
            src_label = os.path.basename(cand['src_pdf'])
            
        rep_page.insert_text((20, 60), f"Source: {src_label} p{cand['page']} - Result: ", fontsize=10, fontname="helv")
        rep_page.insert_text((250, 60), status_text, fontsize=10, fontname="helv", color=status_col)
        
        # Insert Images
        y_img = 80
        img_h = 200
        
        # Original
        if pix_orig:
            try:
                rep_page.insert_image(fitz.Rect(20, y_img, 280, y_img+img_h), stream=pix_orig.tobytes())
                rep_page.insert_text((20, y_img-5), "Original", fontsize=10)
            except: pass
            
        # Result
        if success and pix_res:
            try:
                rep_page.insert_image(fitz.Rect(300, y_img, 560, y_img+img_h), stream=pix_res.tobytes())
                rep_page.insert_text((300, y_img-5), "Result", fontsize=10)
            except: pass
        else:
            # Show error message nicely
            textbox = fitz.Rect(300, y_img + 50, 580, y_img + 180)
            rep_page.insert_textbox(textbox, f"Action Blocked:\n{msg}", fontsize=10, color=(0.5, 0, 0))
            
        # Clean up temp file
        if os.path.exists(temp_out):
            try: os.remove(temp_out)
            except: pass
            
    # Save Report
    report_doc.save(OUTPUT_PDF)
    print(f"\nReport saved to: {os.path.abspath(OUTPUT_PDF)}")

if __name__ == "__main__":
    generate_report()
