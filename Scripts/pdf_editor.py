import re
import pikepdf
from pikepdf import Operator, Name

def load_pdf(path: str) -> pikepdf.Pdf:
    """Load a PDF file from the given path."""
    return pikepdf.open(path)

def save_pdf(pdf: pikepdf.Pdf, out_path: str) -> None:
    """Save the edited PDF to the output path."""
    pdf.save(out_path)

def replace_text(pdf: pikepdf.Pdf, page_idx: int, pattern: str, repl: str) -> int:
    """
    Replace all occurrences matching *pattern* on *page_idx* while keeping the original font.
    Returns the number of replacements made.
    """
    if page_idx >= len(pdf.pages):
        return 0
        
    page = pdf.pages[page_idx]
    
    # Parse the content stream into a list of (operands, operator)
    try:
        ops = list(pikepdf.parse_content_stream(page))
    except Exception as e:
        print(f"Error parsing page {page_idx}: {e}")
        return 0

    new_ops = []
    replacement_count = 0
    regex = re.compile(pattern)

    for operands, operator in ops:
        if operator == Operator("Tj"):
            # operands[0] is the text string or bytes
            text_obj = operands[0]
            
            # Convert to string for regex matching
            # pikepdf handles encoding, so str(text_obj) generally works for simple cases
            # For complex encodings, we might need more care, but this is a starting point
            try:
                txt = str(text_obj)
            except Exception:
                # If decoding fails, skip
                new_ops.append((operands, operator))
                continue
                
            if regex.search(txt):
                new_txt = regex.sub(repl, txt)
                # Ensure we wrap it back in the same type if possible or just string
                new_ops.append(([new_txt], Operator("Tj")))
                print(f"DEBUG: Replaced Tj '{txt}' -> '{new_txt}'")
                replacement_count += 1
                continue
                
        elif operator == Operator("TJ"):
            # operands[0] is an array of strings (text) and numbers (kerning adjustments)
            array_obj = operands[0]
            new_array = []
            changed_in_tj = False
            
            for item in array_obj:
                if isinstance(item, (str, pikepdf.String)):
                    try:
                        s = str(item)
                    except Exception:
                        new_array.append(item)
                        continue
                        
                    if regex.search(s):
                        s_new = regex.sub(repl, s)
                        new_array.append(s_new)
                        changed_in_tj = True
                        print(f"DEBUG: Replaced TJ item '{s}' -> '{s_new}'")
                        replacement_count += 1
                    else:
                        new_array.append(item)
                else:
                    # Numbers (spacing)
                    new_array.append(item)
            
            if changed_in_tj:
                new_ops.append(([new_array], Operator("TJ")))
                continue

        # Keep other operators unchanged
        new_ops.append((operands, operator))

    if replacement_count > 0:
        new_stream_data = pikepdf.unparse_content_stream(new_ops)
        # Create a new stream object attached to the PDF
        new_stream = pdf.make_stream(new_stream_data)
        # Assign to the page's /Contents key directly
        page.Contents = new_stream
        print(f"DEBUG: Updated page {page_idx} content stream (size: {len(new_stream_data)})")


    return replacement_count
