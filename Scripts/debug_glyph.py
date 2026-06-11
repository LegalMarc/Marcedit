
import fitz

font_path = "/Applications/Microsoft Word.app/Contents/Resources/DFonts/Calibri.ttf"
try:
    font = fitz.Font(fontfile=font_path)
    char = 'M'
    gid = font.get_glyph_id(ord(char)) # verify this exists?
    # Actually checking docs... font.char_code_to_glyph(ord(char))?
    # Or just font.glyph_bbox?
    
    # Try typical method
    # font object has method to get glyph index?
    # Since v1.18.0: font.get_glyph_id(code) is available? No?
    # Let's try to find how to get gid.
    pass
except:
    pass

# Actually let's just dump what we can find
print(f"PyMuPDF Version: {fitz.version}")
doc = fitz.open()

# Load font
try:
    font = fitz.Font("helv")
    char = 'M'
    
    # Check if we can get bbox
    # There is font.char_bbox(char) ? No.
    # But there is font.buffer ...
    
    # We can create a temporary page, insert text, and measure it?
    page = doc.new_page()
    pos = fitz.Point(100, 100)
    # render text invisibly?
    # page.insert_text(pos, char, fontname="helv", fontsize=100)
    # Then get_text("rawdict") to find the bbox!
    
    # This is the most reliable way to get rendered glyph height!
    # Render at 100pt, measure height, divide by 100.
    
    page.insert_text(pos, char, font=font, fontsize=100)
    bad_rect = fitz.Rect(90, 90, 200, 200)
    raw = page.get_text("rawdict", clip=bad_rect)
    
    for span in raw["blocks"][0]["lines"][0]["spans"]:
        for c in span["chars"]:
            if c["c"] == char:
                bbox = fitz.Rect(c["bbox"])
                print(f"Rendered 'M' at 100pt: Height={bbox.height}, Width={bbox.width}")
                print(f"Normalized (1pt): Height={bbox.height/100}, Width={bbox.width/100}")

except Exception as e:
    print(f"Error: {e}")
