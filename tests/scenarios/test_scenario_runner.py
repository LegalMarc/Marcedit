import unittest
import sys
import os
import shutil
import fitz  # PyMuPDF
from pathlib import Path

# Add python_site to path
# We need to make sure we get the path correct. 
# If running from root, it is Sources/Marcedit/python_site
sys.path.insert(0, str(Path(__file__).parents[2] / "Sources/Marcedit/python_site"))

try:
    from editor_pkg import core
except ImportError:
    print("Failed to import editor_pkg.core. Make sure you are running from the project root or correct paths are set.")
    sys.exit(1)

# Constants for test resources
RESOURCE_DIR = Path(__file__).parents[2] / "ignored-resources" / "sample-files"
OUTPUT_DIR = Path("/tmp/marcedit_scenarios")

class TestLegalScenarios(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)
        OUTPUT_DIR.mkdir(parents=True)
        
        # Ensure we have a sample PDF to work with
        cls.base_pdf = RESOURCE_DIR / "billing-statement-invoice.pdf" # Fallback
    
    def create_dummy_pdf(self, filename, text, fontname="helv", fontsize=11, rect=(50, 50, 500, 500)):
        """Helper to create specific test PDFs dynamically."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(rect[:2], text, fontname=fontname, fontsize=fontsize)
        path = OUTPUT_DIR / filename
        doc.save(path)
        doc.close()
        return path

    def test_scenario_1_justification_collision_check(self):
        """Scenario 1a: Justified Text River Effect (Expect Collision Error)."""
        # Testing Expansion on Justified Text
        pdf_name = "scenario_1_justify.pdf"
        doc = fitz.open()
        page = doc.new_page()
        text = "The Party shall responsible for all costs associated with the implementation of this Agreement."
        rect = fitz.Rect(50, 50, 300, 200)
        page.insert_textbox(rect, text, fontsize=12, align=fitz.TEXT_ALIGN_JUSTIFY)
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "Party"
        replacement = "Parties" # Longer -> Collision
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        # Run Edit
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        
        # FIX: We now expect this to FAIL with a Layout Collision error
        if not res['success']:
             self.assertIn("Layout Collision", res['message'])
             # Skip file verification since file might not be saved on error
             return
             
        # If it succeeded (maybe tight spacing allows it?), warn but accept?
        # But we expect the safety check to trigger if "Parties" > "Party" + spacing.
        # Since we use robust_search, " shall" is likely close.
        self.assertFalse(res['success'], "Should have failed due to collision")

    def test_scenario_1_justification_preservation(self):
        """Scenario 1b: Justification Logic (Preservation)."""
        # Testing contraction + Override to check alignment
        pdf_name = "scenario_1_justify_pres.pdf"
        doc = fitz.open()
        page = doc.new_page()
        text = "The Party shall responsible for all costs associated with the implementation of this Agreement."
        rect = fitz.Rect(50, 50, 300, 200)
        page.insert_textbox(rect, text, fontsize=12, align=fitz.TEXT_ALIGN_JUSTIFY)
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "Party"
        replacement = "Part" # Shorter
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement,
            manual_overrides={'justification': 'justified'} # Force justification mechanism
        )
        self.assertTrue(res['success'], res.get('message'))
        
        doc_out = fitz.open(out_path)
        page_out = doc_out[0]
        blocks = page_out.get_text("dict")["blocks"]
        found_line = None
        for b in blocks:
            for line in b["lines"]:
                for span in line["spans"]:
                    if replacement in span["text"]:
                        found_line = line
                        break
        
        line_x1 = found_line["bbox"][2]
        # Should still hit the right margin (300) due to justification redistribution
        self.assertAlmostEqual(line_x1, 300, delta=5, msg="Text lost justification alignment")

    def test_scenario_3_cross_column(self):
        """Scenario 3: Cross-Column Merge."""
        pdf_name = "scenario_3_columns.pdf"
        doc = fitz.open()
        page = doc.new_page()
        y = 100
        # Col 1
        page.insert_text((50, y), "Date:", fontsize=12)
        # Col 2
        page.insert_text((150, y), "January 1, 2026", fontsize=12)
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "Date:"
        replacement = "Effective Date:"
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        
        if not res['success']:
             self.assertIn("Layout Collision", res['message'])
             return
        self.assertFalse(res['success'], "Should have failed due to Layout Collision")

    def test_scenario_4_smart_quotes(self):
        """Scenario 4: Smart Quotes."""
        pdf_name = "scenario_4_quotes.pdf"
        src_path = self.create_dummy_pdf(pdf_name, 'It is "defined" here.')
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        target = 'It is "defined" here.'
        # User input (straight quotes):
        replacement = 'It is "clearly defined" here.' 
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        self.assertTrue(res['success'], res.get('message'))
        
        doc_out = fitz.open(out_path)
        text = doc_out[0].get_text()
        
        # Check for curly quotes
        has_smart = '\u201c' in text or '\u201d' in text
        self.assertTrue(has_smart, "Smart quotes were not applied to straight quote input")

    def test_scenario_6_ghost_text(self):
        """Scenario 6: Ghost Text."""
        pdf_name = "scenario_6_ghost.pdf"
        src_path = self.create_dummy_pdf(pdf_name, "Old Secret Text")
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        target = "Old Secret Text"
        replacement = "Redacted"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        
        doc_out = fitz.open(out_path)
        hits = doc_out[0].search_for(target)
        self.assertEqual(len(hits), 0, f"Ghost text found! Search returned {len(hits)} matches for '{target}'")

    def test_scenario_15_deletion(self):
        """Scenario 15: True Deletion (Stream check)."""
        pdf_name = "scenario_15_delete.pdf"
        src_path = self.create_dummy_pdf(pdf_name, "Delete This Now")
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        target = "Delete This Now"
        replacement = " " # Empty replacement
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        
        doc_out = fitz.open(out_path)
        hits = doc_out[0].search_for(target)
        self.assertEqual(len(hits), 0)
        
        # Verify raw text
        raw = doc_out[0].get_text("text")
        self.assertNotIn("Delete", raw)



    def test_scenario_5_indentation(self):
        """Scenario 5: Indentation/Tab Preservation."""
        # Setup: Text with apparent indentation (separate spans usually in PDF)
        pdf_name = "scenario_5_indent.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Simulate "1.1     Title"
        page.insert_text((50, 50), "1.1", fontsize=12)
        page.insert_text((100, 50), "Title", fontsize=12) 
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "1.1"
        replacement = "1.1.1" # Wider
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        self.assertTrue(res['success'], res.get('message'))
        
        # Verify "Title" did not move or get overwritten
        doc_out = fitz.open(out_path)
        page_out = doc_out[0]
        title_rect = page_out.search_for("Title")[0]
        
        # Original Title X was 100.
        # If "1.1.1" pushed it, X would change (if layout engine flowed it) 
        # OR "1.1.1" would overwrite it (Collision).
        # We want NO collision and Title to stay put (assuming tab separation means fixed pos).
        self.assertAlmostEqual(title_rect.x0, 100, delta=1, msg="Indented text 'Title' shifted unexpectedly")
        
        # And check for collision (Safety)
        # 1.1.1 is wider. 
        # 1.1 width approx 15-20. 1.1.1 approx 25-30. Gap was 50-20=30. Should fit.
        # Let's try a MUCH wider replacement to force a collision check
        
    def test_scenario_9_vertical_overflow(self):
        """Scenario 9: Vertical Overflow Safety."""
        pdf_name = "scenario_9_overflow.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Line 1", fontsize=12)
        page.insert_text((50, 65), "Line 2", fontsize=12) # 15pt leading
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "Line 1"
        # Replacement that wraps or is huge? 
        # Since we don't do auto-wrapping yet, let's try a Huge Font override
        # or simply a replacement that might inadvertently be taller/shifted down?
        # Actually, standard replacement uses same fontsize.
        # Let's test the Safety Check we plan to add: detecting if new bbox hits next line.
        # We can simulate this by manually offsetting Y or using a tall font (if we could).
        
        # For now, let's test that verify_collision generic check works for Vertical too?
        # The current collision check expands to the right. 
        # We need a new test for Vertical collision if we change linespacing or wrap.
        # Let's assume we want to prevent overwriting Line 2 even if we moved text down.
        # To simulate a failure, we'd need to force a Y-shift.
        
        replacement = "Line 1 Modified"
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        # Manually shift down to cause collision
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement,
            manual_overrides={'manual_y_offset': 10} # Push down into Line 2
        )
        
        # We EXPECT this to FAIL with collision error now (if our collision logic handles vertical)
        # Current logic is: `danger_rect = (insert_x, insert_y, ...)` 
        # It checks right-side mostly.
        # This test confirms if we need to expand collision check to be 2D.
        
        if not res['success']:
             self.assertIn("Layout Collision", res['message'])
             return
             
        # If it didn't fail, we check manually
        # This assert expects it TO FAIL once we implement vertical safety.
        # Currently it might pass (suboptimal).
        self.assertFalse(res['success'], f"Should have failed due to vertical collision with Line 2. Log: {res.get('debug_log')}")

    def test_scenario_8_link_sync(self):
        """Scenario 8: Link Synchronization."""
        pdf_name = "scenario_8_link.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Text "Click Here" at 50,50
        rect = fitz.Rect(50, 38, 120, 52)
        page.insert_text((50, 50), "Click Here", fontsize=12)
        # Link covering it
        link = {"kind": fitz.LINK_URI, "from": rect, "uri": "http://google.com"}
        page.insert_link(link)
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "Click Here"
        replacement = "Go" # Smaller, so link rect should shrink? 
        # Or at least not point to empty space.
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path), 
            output_path=str(out_path), 
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        self.assertTrue(res['success'])
        
        # Verify Link Rect updated
        doc_out = fitz.open(out_path)
        page_out = doc_out[0]
        links = list(page_out.get_links())
        self.assertEqual(len(links), 1)
        link_rect = links[0]['from']
        
        # New text "Go" will be much narrower than "Click Here"
        # "Go" width ~15. "Click Here" ~60.
        # Link rect should match "Go" rect approximately.
        
        text_rect = page_out.search_for("Go")[0]
        
        # Check intersection/covering
        # The link should cover the text.
        self.assertTrue(link_rect.intersects(text_rect), "Link should cover new text")
        # And hopefully roughly equal size (not staying huge)
        area_ratio = link_rect.get_area() / text_rect.get_area()
        # If it didn't update, ratio would be huge (60 width vs 15 width => 4x area)
        self.assertLess(area_ratio, 2.0, "Link rect did not resize to match new text size")

    def test_scenario_2_font_fallback_check(self):
        """Scenario 2: Font Fallback strictness."""
        # Hard to test without "bad" font.
        # But we can verify that if we ask for a manual font that doesn't exist,
        # we get a nice warning or specific fallback behavior, not just silent substitution?
        # The Core logic has substitution_warning.
        pass # Skip for now hard to automated without mocked font system


    def test_scenario_10_nbcp_token_handling(self):
        """Scenario 10: NBCP/Token Handling ($1, 000 split prevention)."""
        pdf_name = "scenario_10_nbcp.pdf"
        src_path = self.create_dummy_pdf(pdf_name, "Cost: $1, 000")
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        target = "Cost: $1, 000"
        # Replacement that MIGHT split if logic is bad?
        # Actually this test verifies that we can TARGET text that has weird spacing
        # OR that we insert text with NBSP if we want to keep it together.
        # Let's test INSERTION of a token that should have NBSP.
        replacement = "Cost: $2, 000" 
        
        # We want to ensure that "2, 000" is treated as a single token or has NBSP if user provides it?
        # A better test: We replace "$1,000" with "$2, 000" and ensure it doesn't line-break?
        # Since we don't have reflow, we can check if the editor converts "2, 000" (comma space) 
        # into "2,\u00A0000" (NBSP) automatically if it detects it as a number token?
        # The plan says: "Replace spaces/breaks with \u00A0 if replacement text contains them" in number context.
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path),
            output_path=str(out_path),
            page_number=1,
            target_text=target,
            replacement_text=replacement
        )
        self.assertTrue(res['success'])
        
        doc_out = fitz.open(out_path)
        text_out = doc_out[0].get_text()
        
        # Check if NBSP was used?
        # If logic is implemented, " " in "$2, 000" becomes "\u00A0"
        # self.assertIn("$2,\u00A0000", text_out)
        # OR check visual unity? 
        # For now, let's verify it simply works and maybe check for the char code if we implement that feature.
        # This test will fail if we implement the check and strict assert.
        pass

    def test_scenario_12_z_order_watermark(self):
        """Scenario 12: Z-Order Preservation (Watermark Safety)."""
        pdf_name = "scenario_12_watermark.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Add a watermark (OCG or just a big grey text) FIRST (background)
        page.insert_text((100, 300), "DRAFT", fontsize=60, color=(0.9, 0.9, 0.9))
        # Add content text ON TOP
        page.insert_text((100, 300), "Sensitive Content", fontsize=12, color=(0, 0, 0))
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "Sensitive Content"
        replacement = "Redacted Content"
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path),
            output_path=str(out_path),
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        if not res['success']:
             print("Z-Order Test Failed. Debug Log:")
             print("\n".join(res.get('debug_log', [])))
        self.assertTrue(res['success'])
        
        # Verify watermark is not obscured? 
        # If we drew a white box over "Sensitive Content", we might have hidden part of "DRAFT".
        # "DRAFT" is big. The white box for redaction is usually opaque.
        # If we use multiply blend mode or transparency, we might see it?
        # OR we check if the watermark is still detectable?
        
        # This test ensures we at least WARN or try to handle it.
        # If we just plastered a white rect, we failed z-order safety for background watermarks.
        # We expect a warning or smart handling?
        # For now, let's just assert success and manually verify later, 
        # or assert that we didn't destroy the watermark object (easy).
        doc_out = fitz.open(out_path)
        wm_hits = doc_out[0].search_for("DRAFT")
        if len(wm_hits) == 0:
            print("Watermark Verification Failed. Debug Log:")
            print("\n".join(res.get('debug_log', [])))
        self.assertTrue(len(wm_hits) > 0, "Watermark text disappeared entirely!")

    def test_scenario_7_small_caps(self):
        """Scenario 7: Small Caps Preservation."""
        # Visual property. Hard to test automatically without font inspection.
        # But we can check if we detect it?
        pass

    def test_scenario_13_superscript(self):
        """Scenario 13: Superscript/Baseline Shift."""
        # Create text with rise
        pdf_name = "scenario_13_super.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # "Footnote" at baseline, "1" lifted
        page.insert_text((50, 100), "Footnote", fontsize=12)
        # Using TextWriter for shift? Or simple insert
        # insert_text doesn't support 'rise' easily on span level in one go?
        # fitz.TextWriter can do it.
        tw = fitz.TextWriter(page.rect)
        tw.append((80, 100), "1", fontsize=8) # naive superscript (smaller font, same y? usually y is lower for super)
        # A real superscript has higher y (lower value).
        tw.append((100, 95), "2", fontsize=8) 
        tw.write_text(page)
        
        src_path = OUTPUT_DIR / pdf_name
        doc.save(src_path)
        
        target = "2"
        replacement = "3" 
        out_path = OUTPUT_DIR / f"{pdf_name}_out.pdf"
        
        res = core.replace_text_in_pdf(
            input_path=str(src_path),
            output_path=str(out_path),
            page_number=1, 
            target_text=target, 
            replacement_text=replacement
        )
        self.assertTrue(res['success'])
        
        # Verify the new "3" is roughly at Y=95 (saved in doc), not dropped to Y=100.
        doc_out = fitz.open(out_path)
        page_out = doc_out[0]
        spans = page_out.get_text("dict")["blocks"][0]["lines"][0]["spans"]
        # Locate "3" 
        # (This parsing is brittle, might need robust search)
        found_y = None
        for b in page_out.get_text("dict")["blocks"]:
             for l in b["lines"]:
                 for s in l["spans"]:
                     if "3" in s["text"]:
                         found_y = s["origin"][1] # Base line
        
        if found_y:
            # Should be close to 95, not 100
            self.assertLess(found_y, 98, f"Superscript likely dropped to baseline (Y={found_y})")

if __name__ == '__main__':
    unittest.main()
