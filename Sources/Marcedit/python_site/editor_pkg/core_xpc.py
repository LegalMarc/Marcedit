"""
XPC-Compatible Wrappers for Marcedit Core Functions
Created: 2026-01-24 (Week 5 Day 1)
Purpose: Provide XPC-compatible function signatures for Swift XPC service

These functions wrap the existing core.py functions with XPC-compatible
signatures (0-based page indices, specific return formats).
"""

import fitz
from . import core
from .logging_utils import get_logger, health_check as _health_check, get_perf_stats

_log = get_logger("core_xpc")


def identify_font(document_path: str, page_index: int, target_text: str) -> dict:
    """
    Identify font used for specific text in PDF (XPC-compatible version).

    Args:
        document_path: Path to PDF file
        page_index: Zero-based page index (XPC uses 0-based)
        target_text: Text to locate and analyze

    Returns:
        dict with keys expected by XPC service:
        - family: str - Font family name
        - postscript_name: str | None - PostScript font name
        - weight: int - Font weight (400=normal, 700=bold)
        - width: str - Font width ("normal", "condensed", "expanded")
        - slant: str - Font slant ("normal", "italic", "oblique")
        - size: float - Font size in points
        - x_height: float | None - x-height metric
        - cap_height: float | None - cap-height metric
    """
    try:
        # Convert 0-based index to 1-based page number for core.identify_font
        page_number = page_index + 1

        # Call existing identify_font function
        result = core.identify_font(document_path, page_number, target_text)

        if not result.get('success'):
            # Return default values if identification failed
            return {
                'family': 'Helvetica',
                'postscript_name': None,
                'weight': 400,
                'width': 'normal',
                'slant': 'normal',
                'size': 12.0,
                'x_height': None,
                'cap_height': None
            }

        # Extract font information
        fontname = result.get('fontname', 'Helvetica')
        fontsize = result.get('fontsize', 12.0)

        # Parse font name to extract family and attributes
        family, postscript_name, weight, width, slant = _parse_font_name(fontname)

        # Extract metrics from PDF if possible
        x_height, cap_height = _extract_font_metrics(document_path, page_index, fontname)

        return {
            'family': family,
            'postscript_name': postscript_name,
            'weight': weight,
            'width': width,
            'slant': slant,
            'size': float(fontsize),
            'x_height': x_height,
            'cap_height': cap_height
        }

    except Exception as e:
        print(f"[XPC] identify_font error: {e}")
        import traceback
        traceback.print_exc()

        # Return safe defaults on error
        return {
            'family': 'Helvetica',
            'postscript_name': None,
            'weight': 400,
            'width': 'normal',
            'slant': 'normal',
            'size': 12.0,
            'x_height': None,
            'cap_height': None
        }


def replace_text(
    document_path: str,
    target_text: str,
    replacement_text: str,
    page_index: int,
    overrides: dict,
    detected_font: dict | None,
    target_rect: dict
) -> dict:
    """
    Replace text in PDF (XPC-compatible version).

    Args:
        document_path: Path to PDF file
        target_text: Text to find and replace
        replacement_text: New text content
        page_index: Zero-based page index
        overrides: Font/style overrides dict
        detected_font: Previously detected font info (can be None)
        target_rect: Bounding rectangle dict with keys: x, y, width, height

    Returns:
        dict with keys:
        - success: bool - Whether replacement succeeded
        - modified_path: str | None - Path to modified PDF
        - warnings: list[str] - List of warning messages
        - instances_replaced: int - Number of text instances replaced
        - font_used: str | None - Font name used for replacement
        - message: str | None - Additional info message
    """
    warnings = []

    try:
        # Validate inputs
        if not document_path or not isinstance(document_path, str):
            return {
                'success': False,
                'modified_path': None,
                'warnings': ['Invalid document path'],
                'instances_replaced': 0,
                'font_used': None,
                'message': 'Invalid document path provided'
            }

        if not target_text:
            return {
                'success': False,
                'modified_path': None,
                'warnings': ['Target text is empty'],
                'instances_replaced': 0,
                'font_used': None,
                'message': 'Target text cannot be empty'
            }

        # Check if document exists
        import os
        if not os.path.exists(document_path):
            return {
                'success': False,
                'modified_path': None,
                'warnings': [f'Document not found: {document_path}'],
                'instances_replaced': 0,
                'font_used': None,
                'message': f'Document does not exist: {document_path}'
            }

        # Convert 0-based index to 1-based page number
        page_number = page_index + 1

        # Validate page number
        try:
            with fitz.open(document_path) as doc:
                if page_number < 1 or page_number > len(doc):
                    return {
                        'success': False,
                        'modified_path': None,
                        'warnings': [f'Invalid page number {page_number} (document has {len(doc)} pages)'],
                        'instances_replaced': 0,
                        'font_used': None,
                        'message': f'Page {page_number} out of range'
                    }
        except Exception as e:
            return {
                'success': False,
                'modified_path': None,
                'warnings': [f'Cannot open document: {str(e)}'],
                'instances_replaced': 0,
                'font_used': None,
                'message': f'Failed to open PDF: {str(e)}'
            }

        # Prepare manual overrides in format expected by replace_text_in_pdf
        manual_overrides = _convert_overrides(overrides, detected_font)

        # Add info about overrides used
        if manual_overrides:
            override_keys = list(manual_overrides.keys())
            warnings.append(f"Using overrides: {', '.join(override_keys)}")

        # Generate output path
        import tempfile
        output_dir = os.path.dirname(document_path)
        base_name = os.path.basename(document_path)
        name, ext = os.path.splitext(base_name)
        output_path = os.path.join(output_dir, f"{name}_modified{ext}")

        # If that file exists, use temp file
        if os.path.exists(output_path):
            fd, output_path = tempfile.mkstemp(suffix='.pdf', prefix='marcedit_')
            os.close(fd)
            warnings.append(f"Output path already exists, using temp file: {os.path.basename(output_path)}")

        # Call existing replace_text_in_pdf function
        result = core.replace_text_in_pdf(
            input_path=document_path,
            output_path=output_path,
            target_text=target_text,
            replacement_text=replacement_text,
            page_number=page_number,
            manual_overrides=manual_overrides
        )

        success = result.get('success', False)
        core_warnings = result.get('warnings', [])

        # Combine warnings
        warnings.extend(core_warnings)

        # Extract additional info from result
        instances_replaced = 0
        font_used = None
        message = result.get('message', '')

        # Parse debug log for more details
        debug_log = result.get('debug_log', [])
        if debug_log:
            # Look for instance count
            for log_line in debug_log:
                if 'Found' in log_line and 'instances' in log_line:
                    try:
                        # Extract number from "Found N instances"
                        parts = log_line.split()
                        for i, part in enumerate(parts):
                            if part == 'Found' and i + 1 < len(parts):
                                instances_replaced = int(parts[i + 1])
                                break
                    except (ValueError, IndexError):
                        pass

                # Look for font info
                if 'Using font' in log_line or 'Font:' in log_line:
                    font_used = log_line.split(':')[-1].strip() if ':' in log_line else None

        # Add helpful messages
        if not success:
            if 'not found' in message.lower():
                warnings.append(f"Could not find target text length={len(target_text)} on page {page_number}")
            elif 'font' in message.lower():
                warnings.append(f"Font-related issue: {message}")
        else:
            if instances_replaced > 1:
                warnings.append(f"Replaced {instances_replaced} instances of target text length={len(target_text)}")

        return {
            'success': success,
            'modified_path': output_path if success else None,
            'warnings': warnings,
            'instances_replaced': instances_replaced,
            'font_used': font_used,
            'message': message if message else ('Replacement successful' if success else 'Replacement failed')
        }

    except Exception as e:
        print(f"[XPC] replace_text error: {e}")
        import traceback
        traceback.print_exc()

        return {
            'success': False,
            'modified_path': None,
            'warnings': [f"Unexpected error: {str(e)}"],
            'instances_replaced': 0,
            'font_used': None,
            'message': f"Exception occurred: {str(e)}"
        }


def create_memento(document_path: str, page_index: int, rect: dict, operation_type: str = "edit") -> dict:
    """
    Create memento for undo operation (XPC-compatible version).

    Enhanced version with:
    - Content stream compression
    - Metadata (timestamp, operation type, checksum)
    - Validation support
    - Size optimization

    Args:
        document_path: Path to PDF file
        page_index: Zero-based page index
        rect: Affected rectangle dict with keys: x, y, width, height
        operation_type: Type of operation (e.g., "edit", "replace", "delete")

    Returns:
        dict with keys:
        - page_index: int - Page index
        - content_stream: str - Base64-encoded, compressed content stream
        - rect: dict - Affected rectangle
        - timestamp: float - Creation timestamp
        - operation_type: str - Type of operation
        - checksum: str - SHA256 checksum for validation
        - original_size: int - Uncompressed size in bytes
        - compressed_size: int - Compressed size in bytes
        - version: int - Memento format version
    """
    try:
        import base64
        import zlib
        import hashlib
        import time

        with fitz.open(document_path) as doc:
            if page_index < 0 or page_index >= len(doc):
                raise ValueError(f"Invalid page index: {page_index}")

            page = doc[page_index]

            # Extract page content stream
            # Get the raw content stream - returns list of content stream xrefs
            content_streams = page.get_contents()

            # Convert to bytes - combine all content streams
            if isinstance(content_streams, list):
                # Multiple content streams - read and combine them
                content_data = b''
                for xref in content_streams:
                    stream = doc.xref_stream(xref)
                    if stream:
                        content_data += stream
            elif isinstance(content_streams, int):
                # Single content stream xref
                content_data = doc.xref_stream(content_streams) or b''
            else:
                content_data = b''

            # Calculate original size and checksum
            original_size = len(content_data)
            checksum = hashlib.sha256(content_data).hexdigest()

            # Compress content stream (typically 60-80% reduction)
            compressed_data = zlib.compress(content_data, level=6)
            compressed_size = len(compressed_data)

            # Encode as base64 for safe transport
            content_stream_b64 = base64.b64encode(compressed_data).decode('utf-8')

            return {
                'page_index': page_index,
                'content_stream': content_stream_b64,
                'rect': rect,
                'timestamp': time.time(),
                'operation_type': operation_type,
                'checksum': checksum,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'version': 2  # Memento format version
            }

    except Exception as e:
        print(f"[XPC] create_memento error: {e}")
        import traceback
        traceback.print_exc()

        # Return minimal memento on error
        import time
        return {
            'page_index': page_index,
            'content_stream': '',
            'rect': rect,
            'timestamp': time.time(),
            'operation_type': operation_type,
            'checksum': '',
            'original_size': 0,
            'compressed_size': 0,
            'version': 2
        }


def restore_from_memento(document_path: str, memento: dict, validate: bool = True) -> dict:
    """
    Restore PDF page from memento (XPC-compatible version).

    Enhanced version with:
    - Proper content stream restoration (not just copy)
    - Memento validation and checksum verification
    - Support for compressed mementos
    - Backward compatibility with v1 mementos

    Args:
        document_path: Path to PDF file
        memento: Memento dict with keys: page_index, content_stream, rect, ...
        validate: Whether to validate checksum before restoration

    Returns:
        dict with keys:
        - success: bool - Whether restoration succeeded
        - output_path: str - Path to restored PDF
        - validated: bool - Whether checksum was validated
        - message: str - Status message
    """
    try:
        import base64
        import zlib
        import hashlib
        import os
        import tempfile

        # Extract memento fields
        page_index = memento['page_index']
        content_stream_b64 = memento['content_stream']
        rect = memento.get('rect', {})
        version = memento.get('version', 1)  # Default to v1 for backward compat
        expected_checksum = memento.get('checksum', '')
        original_size = memento.get('original_size', 0)

        if not content_stream_b64:
            return {
                'success': False,
                'output_path': document_path,
                'validated': False,
                'message': 'Memento has empty content stream'
            }

        # Decode and decompress content stream
        compressed_data = base64.b64decode(content_stream_b64)

        # Check version and decompress if needed
        if version >= 2:
            # V2 mementos are compressed
            try:
                content_stream = zlib.decompress(compressed_data)
            except zlib.error as e:
                return {
                    'success': False,
                    'output_path': document_path,
                    'validated': False,
                    'message': f'Decompression failed: {e}'
                }
        else:
            # V1 mementos are not compressed
            content_stream = compressed_data

        # Validate checksum if requested
        validated = False
        if validate and expected_checksum:
            actual_checksum = hashlib.sha256(content_stream).hexdigest()
            if actual_checksum != expected_checksum:
                return {
                    'success': False,
                    'output_path': document_path,
                    'validated': False,
                    'message': f'Checksum mismatch: expected {expected_checksum[:8]}..., got {actual_checksum[:8]}...'
                }
            validated = True

        # Validate size if available
        if original_size > 0 and len(content_stream) != original_size:
            return {
                'success': False,
                'output_path': document_path,
                'validated': validated,
                'message': f'Size mismatch: expected {original_size} bytes, got {len(content_stream)} bytes'
            }

        # Generate output path
        output_dir = os.path.dirname(document_path)
        base_name = os.path.basename(document_path)
        name, ext = os.path.splitext(base_name)
        output_path = os.path.join(output_dir, f"{name}_restored{ext}")

        # If that file exists, use temp file
        if os.path.exists(output_path):
            fd, output_path = tempfile.mkstemp(suffix='.pdf', prefix='marcedit_restored_')
            os.close(fd)

        # Restore content stream using PyMuPDF's xref manipulation
        with fitz.open(document_path) as doc:
            if page_index < 0 or page_index >= len(doc):
                return {
                    'success': False,
                    'output_path': document_path,
                    'validated': validated,
                    'message': f'Invalid page index: {page_index}'
                }

            page = doc[page_index]

            # Get current content stream xrefs
            content_streams = page.get_contents()

            # Replace content stream(s)
            if isinstance(content_streams, list) and len(content_streams) > 0:
                # Multiple content streams - replace first one, delete others
                first_xref = content_streams[0]
                doc.update_stream(first_xref, content_stream)

                # Clean up additional content streams
                for xref in content_streams[1:]:
                    try:
                        doc.update_stream(xref, b'')  # Empty them out
                    except Exception:
                        pass  # Ignore errors on cleanup

            elif isinstance(content_streams, int):
                # Single content stream xref
                doc.update_stream(content_streams, content_stream)

            else:
                # No existing content streams - create new one
                # This is complex, so we'll use the clean_contents approach
                page.clean_contents()
                # Get the new content stream xref after cleaning
                new_contents = page.get_contents()
                if isinstance(new_contents, int):
                    doc.update_stream(new_contents, content_stream)
                elif isinstance(new_contents, list) and len(new_contents) > 0:
                    doc.update_stream(new_contents[0], content_stream)

            # Save restored PDF
            doc.save(output_path, garbage=4, clean=True, deflate=True)

        return {
            'success': True,
            'output_path': output_path,
            'validated': validated,
            'message': f'Restored page {page_index} from memento (validated: {validated})'
        }

    except Exception as e:
        print(f"[XPC] restore_from_memento error: {e}")
        import traceback
        traceback.print_exc()

        # Return error result
        return {
            'success': False,
            'output_path': document_path,
            'validated': False,
            'message': f'Restoration failed: {str(e)}'
        }


# Helper functions

def validate_memento(memento: dict) -> dict:
    """
    Validate a memento structure and integrity.

    Args:
        memento: Memento dict to validate

    Returns:
        dict with keys:
        - valid: bool - Whether memento is valid
        - errors: list[str] - List of validation errors
        - warnings: list[str] - List of warnings
        - info: dict - Additional info about the memento
    """
    errors = []
    warnings = []
    info = {}

    # Check required fields
    required_fields = ['page_index', 'content_stream']
    for field in required_fields:
        if field not in memento:
            errors.append(f"Missing required field: {field}")

    # Check field types
    if 'page_index' in memento:
        if not isinstance(memento['page_index'], int):
            errors.append(f"page_index must be int, got {type(memento['page_index'])}")
        elif memento['page_index'] < 0:
            errors.append(f"page_index must be non-negative, got {memento['page_index']}")

    if 'content_stream' in memento:
        if not isinstance(memento['content_stream'], str):
            errors.append(f"content_stream must be str, got {type(memento['content_stream'])}")
        elif not memento['content_stream']:
            warnings.append("content_stream is empty")

    # Check version
    version = memento.get('version', 1)
    info['version'] = version
    if version not in [1, 2]:
        warnings.append(f"Unknown memento version: {version}")

    # Check compression info for v2
    if version >= 2:
        if 'compressed_size' in memento and 'original_size' in memento:
            compressed = memento['compressed_size']
            original = memento['original_size']
            if compressed > 0 and original > 0:
                ratio = (1 - compressed / original) * 100
                info['compression_ratio'] = f"{ratio:.1f}%"

    # Check timestamp
    if 'timestamp' in memento:
        import time
        ts = memento['timestamp']
        age_seconds = time.time() - ts
        info['age_seconds'] = age_seconds
        if age_seconds < 0:
            errors.append("Memento timestamp is in the future")
        elif age_seconds > 86400 * 7:  # 7 days
            warnings.append(f"Memento is {age_seconds / 86400:.1f} days old")

    # Check checksum presence
    if 'checksum' in memento and memento['checksum']:
        info['has_checksum'] = True
    else:
        warnings.append("No checksum available for validation")
        info['has_checksum'] = False

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'info': info
    }


def _parse_font_name(fontname: str) -> tuple[str, str | None, int, str, str]:
    """
    Parse font name to extract family, postscript name, weight, width, slant.

    Returns:
        (family, postscript_name, weight, width, slant)
    """
    # Remove subset prefix like "ABCDEF+"
    clean_name = fontname.split('+')[-1] if '+' in fontname else fontname

    # Default values
    family = clean_name
    postscript_name = clean_name
    weight = 400  # normal
    width = "normal"
    slant = "normal"

    # Detect weight from name
    name_lower = clean_name.lower()
    if 'bold' in name_lower or '-bold' in name_lower:
        weight = 700
    elif 'light' in name_lower:
        weight = 300
    elif 'medium' in name_lower:
        weight = 500
    elif 'heavy' in name_lower or 'black' in name_lower:
        weight = 900

    # Detect slant from name
    if 'italic' in name_lower or '-it' in name_lower:
        slant = "italic"
    elif 'oblique' in name_lower:
        slant = "oblique"

    # Detect width from name
    if 'condensed' in name_lower or 'narrow' in name_lower:
        width = "condensed"
    elif 'expanded' in name_lower or 'wide' in name_lower:
        width = "expanded"

    # Extract base family name (remove style suffixes)
    family = clean_name
    for suffix in ['-Bold', '-Italic', '-BoldItalic', '-Regular', '-Light', '-Medium', '-Heavy', '-Black']:
        if family.endswith(suffix):
            family = family[:-len(suffix)]
            break

    return (family, postscript_name, weight, width, slant)


def _extract_font_metrics(document_path: str, page_index: int, fontname: str) -> tuple[float | None, float | None]:
    """
    Extract x-height and cap-height metrics from PDF font.

    Returns:
        (x_height, cap_height) or (None, None) if not available
    """
    try:
        with fitz.open(document_path) as doc:
            if page_index < 0 or page_index >= len(doc):
                return (None, None)

            page = doc[page_index]

            # Get font list
            font_list = page.get_fonts()

            for font_info in font_list:
                font_ref = font_info[0]
                font_name = font_info[3]

                # Match font name
                if font_name == fontname or font_name.split('+')[-1] == fontname.split('+')[-1]:
                    # Try to extract font object and get metrics
                    # PyMuPDF doesn't expose all metrics easily, so we'll estimate

                    # Typical ratios for common fonts:
                    # x-height ≈ 0.5 * font size
                    # cap-height ≈ 0.7 * font size

                    # For now, return None to indicate metrics not available
                    # This could be improved with fontTools if needed
                    return (None, None)

            return (None, None)

    except Exception as e:
        print(f"[XPC] _extract_font_metrics error: {e}")
        return (None, None)


def _convert_overrides(overrides: dict, detected_font: dict | None) -> dict:
    """
    Convert XPC overrides format to format expected by replace_text_in_pdf.

    Args:
        overrides: XPC overrides dict with keys:
            - font_family: str (optional) - Font family name
            - font_path: str (optional) - Path to font file or font name
            - font_size: float (optional) - Font size in points
            - size_delta: float (optional) - Size adjustment delta
            - x_offset: float (optional) - Horizontal offset adjustment
            - y_offset: float (optional) - Vertical offset adjustment
            - fill_color: str (optional) - Fill color (e.g., "black", "#000000")
            - is_bold: bool (optional) - Apply bold styling
            - is_italic: bool (optional) - Apply italic styling
            - underline: bool (optional) - Apply underline
            - strikethrough: bool (optional) - Apply strikethrough
            - justification: str (optional) - Text justification ("Left", "Center", "Right")
            - exhaustive_search: bool (optional) - Enable exhaustive font search
        detected_font: XPC detected font dict

    Returns:
        dict in format expected by replace_text_in_pdf with keys:
            - manual_font: str (optional)
            - manual_size_delta: float (optional)
            - manual_x_offset: float (optional)
            - manual_y_offset: float (optional)
            - fill_color: str (optional)
            - is_bold: bool (optional)
            - is_italic: bool (optional)
            - underline: bool (optional)
            - strikethrough: bool (optional)
            - justification: str (optional)
            - exhaustive_search: bool (optional)
    """
    manual_overrides = {}

    def first_present(*keys):
        for key in keys:
            if overrides.get(key) is not None:
                return overrides[key]
        return None

    # Font selection
    # Priority: font_path > font_family > detected_font
    font_path = first_present('font_path', 'fontPath', 'font_name', 'fontName')
    font_family = first_present('font_family', 'fontFamily')
    if font_path:
        # If font_path includes PostScript name (format: "path|PSName"), preserve it
        manual_overrides['manual_font'] = font_path
    elif font_family:
        # Use font family name (core.py will search for it)
        manual_overrides['manual_font'] = font_family
    elif detected_font and detected_font.get('postscript_name'):
        # Use detected PostScript name for precise matching
        ps_name = detected_font['postscript_name']
        manual_overrides['manual_font'] = f"internal|{ps_name}"

    # Size adjustments
    size_delta = first_present('size_delta', 'sizeDelta')
    if size_delta is not None:
        manual_overrides['manual_size_delta'] = float(size_delta)

    # Position adjustments
    x_offset = first_present('x_offset', 'xOffset')
    if x_offset is not None:
        manual_overrides['manual_x_offset'] = float(x_offset)

    y_offset = first_present('y_offset', 'yOffset')
    if y_offset is not None:
        manual_overrides['manual_y_offset'] = float(y_offset)

    # Color override
    fill_color = first_present('fill_color', 'fillColor')
    if fill_color:
        manual_overrides['fill_color'] = fill_color

    # Text styling
    is_bold = first_present('is_bold', 'isBold')
    if is_bold is not None:
        manual_overrides['is_bold'] = bool(is_bold)

    is_italic = first_present('is_italic', 'isItalic')
    if is_italic is not None:
        manual_overrides['is_italic'] = bool(is_italic)

    if overrides.get('underline') is not None:
        manual_overrides['underline'] = bool(overrides['underline'])

    if overrides.get('strikethrough') is not None:
        manual_overrides['strikethrough'] = bool(overrides['strikethrough'])

    # Text alignment
    justification = first_present('justification')
    if justification:
        # Validate justification value
        valid_justifications = ['Left', 'Center', 'Right']
        normalized_justification = str(justification).strip().capitalize()
        if normalized_justification in valid_justifications:
            manual_overrides['justification'] = normalized_justification
        else:
            # Default to Left if invalid
            manual_overrides['justification'] = 'Left'

    # Search options
    exhaustive_search = first_present('exhaustive_search', 'exhaustiveSearch')
    if exhaustive_search is not None:
        manual_overrides['exhaustive_search'] = bool(exhaustive_search)

    return manual_overrides


def get_block_spans(document_path: str, page_index: int, span_text: str) -> dict:
    """
    Extract styled spans from text block (XPC-compatible version).

    This function enables rich text editing by extracting all formatting
    information from a text block. Perfect for multi-font paragraphs where
    bold, italic, colors, and different fonts are used within the same block.

    Args:
        document_path: Path to PDF file
        page_index: Zero-based page index
        span_text: Any text within the target block

    Returns:
        dict with keys:
        - success: bool - Whether extraction succeeded
        - block_bbox: dict - Bounding box with keys: x, y, width, height
        - spans: list[dict] - Array of span objects with:
            - text: str - The text content
            - font_family: str - Font family name
            - font_postscript_name: str - PostScript font name
            - size: float - Font size in points
            - weight: int - Font weight (400=normal, 700=bold)
            - slant: str - Font slant ("normal", "italic", "oblique")
            - color: dict - RGB color with keys: r, g, b (0.0-1.0 range)
            - bbox: dict - Bounding box with keys: x, y, width, height
            - line_index: int - Line number within block
        - span_count: int - Total number of spans
        - message: str - Status message
    """
    try:
        # Convert 0-based index to 1-based page number
        page_number = page_index + 1

        # Guard: validate page index before passing to core
        try:
            with fitz.open(document_path) as _doc:
                if page_number < 1 or page_number > len(_doc):
                    return {
                        'success': False,
                        'block_bbox': {'x': 0, 'y': 0, 'width': 0, 'height': 0},
                        'spans': [],
                        'span_count': 0,
                        'message': f'Page {page_number} out of range',
                    }
        except Exception as _e:
            return {
                'success': False,
                'block_bbox': {'x': 0, 'y': 0, 'width': 0, 'height': 0},
                'spans': [],
                'span_count': 0,
                'message': f'Cannot open document: {_e}',
            }

        # Call existing get_block_spans function
        result = core.get_block_spans(document_path, page_number, span_text)

        if not result.get('success'):
            return {
                'success': False,
                'block_bbox': {'x': 0, 'y': 0, 'width': 0, 'height': 0},
                'spans': [],
                'span_count': 0,
                'message': result.get('message', 'Failed to extract spans')
            }

        # Convert block_bbox from list to dict
        block_bbox_list = result.get('block_bbox', [0, 0, 0, 0])
        block_bbox = {
            'x': float(block_bbox_list[0]),
            'y': float(block_bbox_list[1]),
            'width': float(block_bbox_list[2] - block_bbox_list[0]),
            'height': float(block_bbox_list[3] - block_bbox_list[1])
        }

        # Convert spans to XPC-compatible format
        spans_xpc = []
        for span in result.get('spans', []):
            # Parse font name to extract attributes
            font_name = span.get('font', '')
            family, postscript_name, weight, width, slant = _parse_font_name(font_name)

            # Convert bbox from list to dict
            bbox_list = span.get('bbox', [0, 0, 0, 0])
            bbox = {
                'x': float(bbox_list[0]),
                'y': float(bbox_list[1]),
                'width': float(bbox_list[2] - bbox_list[0]),
                'height': float(bbox_list[3] - bbox_list[1])
            }

            # Convert color from list to dict
            color_list = span.get('color', [0, 0, 0])
            color = {
                'r': float(color_list[0]) if len(color_list) > 0 else 0.0,
                'g': float(color_list[1]) if len(color_list) > 1 else 0.0,
                'b': float(color_list[2]) if len(color_list) > 2 else 0.0
            }

            # Override weight/slant from flags if more accurate
            if span.get('is_bold', False):
                weight = 700
            if span.get('is_italic', False):
                slant = "italic"

            spans_xpc.append({
                'text': span.get('text', ''),
                'font_family': family,
                'font_postscript_name': postscript_name or font_name,
                'size': float(span.get('size', 12.0)),
                'weight': weight,
                'slant': slant,
                'color': color,
                'bbox': bbox,
                'line_index': int(span.get('line_index', 0))
            })

        return {
            'success': True,
            'block_bbox': block_bbox,
            'spans': spans_xpc,
            'span_count': len(spans_xpc),
            'message': f'Extracted {len(spans_xpc)} spans from block'
        }

    except Exception as e:
        print(f"[XPC] get_block_spans error: {e}")
        import traceback
        traceback.print_exc()

        return {
            'success': False,
            'block_bbox': {'x': 0, 'y': 0, 'width': 0, 'height': 0},
            'spans': [],
            'span_count': 0,
            'message': f'Exception: {str(e)}'
        }


def replace_block_with_spans(
    document_path: str,
    page_index: int,
    block_bbox: dict,
    spans: list,
    overrides: dict = None
) -> dict:
    """
    Replace text block with styled spans (XPC-compatible version).

    This function enables rich text editing by allowing you to replace
    an entire text block with new content while preserving (or modifying)
    all formatting information like fonts, colors, bold/italic styles.

    Args:
        document_path: Path to PDF file
        page_index: Zero-based page index
        block_bbox: dict with keys: x, y, width, height
        spans: Array of span dicts (same format as get_block_spans output):
            - text: str
            - font_family: str (optional, can use font_postscript_name)
            - font_postscript_name: str (preferred for accuracy)
            - size: float
            - weight: int (400=normal, 700=bold)
            - slant: str ("normal", "italic", "oblique")
            - color: dict with keys: r, g, b
            - bbox: dict (optional, will be recalculated)
            - line_index: int
        overrides: Optional dict with:
            - size_delta: float - Add to all span sizes
            - x_offset: float - Horizontal offset
            - y_offset: float - Vertical offset
            - justification: str - "Left", "Center", "Right"

    Returns:
        dict with keys:
        - success: bool - Whether replacement succeeded
        - modified_path: str - Path to modified PDF
        - warnings: list[str] - List of warnings
        - spans_replaced: int - Number of spans inserted
        - message: str - Status message
    """
    warnings = []

    try:
        import os
        import tempfile

        # Validate inputs
        if not document_path or not os.path.exists(document_path):
            return {
                'success': False,
                'modified_path': None,
                'warnings': ['Document not found'],
                'spans_replaced': 0,
                'message': 'Document does not exist'
            }

        if not spans or len(spans) == 0:
            return {
                'success': False,
                'modified_path': None,
                'warnings': ['No spans provided'],
                'spans_replaced': 0,
                'message': 'Spans array is empty'
            }

        # Convert 0-based index to 1-based page number
        page_number = page_index + 1

        # Validate page number
        try:
            with fitz.open(document_path) as doc:
                if page_number < 1 or page_number > len(doc):
                    return {
                        'success': False,
                        'modified_path': None,
                        'warnings': [f'Invalid page number {page_number}'],
                        'spans_replaced': 0,
                        'message': f'Page {page_number} out of range'
                    }
        except Exception as e:
            return {
                'success': False,
                'modified_path': None,
                'warnings': [f'Cannot open document: {str(e)}'],
                'spans_replaced': 0,
                'message': f'Failed to open PDF: {str(e)}'
            }

        # Convert block_bbox from dict to list
        block_bbox_list = [
            block_bbox.get('x', 0),
            block_bbox.get('y', 0),
            block_bbox.get('x', 0) + block_bbox.get('width', 0),
            block_bbox.get('y', 0) + block_bbox.get('height', 0)
        ]

        # Convert spans from XPC format to core.py format
        spans_core = []
        for span in spans:
            # Convert color from dict to list
            color_dict = span.get('color', {})
            color_list = [
                color_dict.get('r', 0.0),
                color_dict.get('g', 0.0),
                color_dict.get('b', 0.0)
            ]

            # Convert bbox from dict to list (if present)
            bbox_dict = span.get('bbox', {})
            bbox_list = [
                bbox_dict.get('x', 0),
                bbox_dict.get('y', 0),
                bbox_dict.get('x', 0) + bbox_dict.get('width', 0),
                bbox_dict.get('y', 0) + bbox_dict.get('height', 0)
            ]

            # Determine font name (prefer PostScript name)
            font = span.get('font_postscript_name', '') or span.get('font_family', 'Helvetica')

            # Determine bold/italic from weight/slant
            is_bold = span.get('weight', 400) >= 700
            is_italic = span.get('slant', 'normal') in ['italic', 'oblique']

            # Build flags: 1=superscript, 2=italic, 4=serifed, 8=monospaced, 16=bold
            flags = 0
            if is_bold:
                flags |= 16
            if is_italic:
                flags |= 2

            spans_core.append({
                'text': span.get('text', ''),
                'font': font,
                'size': float(span.get('size', 12.0)),
                'flags': flags,
                'is_bold': is_bold,
                'is_italic': is_italic,
                'color': color_list,
                'bbox': bbox_list,
                'line_index': int(span.get('line_index', 0))
            })

        # Convert overrides to core.py format
        manual_overrides = {}
        if overrides:
            if overrides.get('size_delta') is not None:
                manual_overrides['manual_size_delta'] = float(overrides['size_delta'])
            if overrides.get('x_offset') is not None:
                manual_overrides['manual_x_offset'] = float(overrides['x_offset'])
            if overrides.get('y_offset') is not None:
                manual_overrides['manual_y_offset'] = float(overrides['y_offset'])
            if overrides.get('justification'):
                manual_overrides['justification'] = overrides['justification']

        # Generate output path
        output_dir = os.path.dirname(document_path)
        base_name = os.path.basename(document_path)
        name, ext = os.path.splitext(base_name)
        output_path = os.path.join(output_dir, f"{name}_modified{ext}")

        # If that file exists, use temp file
        if os.path.exists(output_path):
            fd, output_path = tempfile.mkstemp(suffix='.pdf', prefix='marcedit_')
            os.close(fd)
            warnings.append(f"Output path exists, using temp file: {os.path.basename(output_path)}")

        # Call existing replace_block_with_spans function
        result = core.replace_block_with_spans(
            input_path=document_path,
            output_path=output_path,
            page_number=page_number,
            block_bbox=block_bbox_list,
            spans=spans_core,
            manual_overrides=manual_overrides
        )

        success = result.get('success', False)
        core_warnings = result.get('debug_log', [])

        # Filter debug log for actual warnings
        for log in core_warnings:
            if 'error' in log.lower() or 'warning' in log.lower() or 'failed' in log.lower():
                warnings.append(log)

        # Count successful span insertions
        spans_replaced = 0
        for log in core_warnings:
            if 'Inserted' in log:
                spans_replaced += 1

        return {
            'success': success,
            'modified_path': output_path if success else None,
            'warnings': warnings,
            'spans_replaced': spans_replaced,
            'message': result.get('message', 'Replacement completed' if success else 'Replacement failed')
        }

    except Exception as e:
        print(f"[XPC] replace_block_with_spans error: {e}")
        import traceback
        traceback.print_exc()

        return {
            'success': False,
            'modified_path': None,
            'warnings': [f'Unexpected error: {str(e)}'],
            'spans_replaced': 0,
            'message': f'Exception: {str(e)}'
        }


# Convenience function for get_page_count (already works with 0-based in Python)
def get_page_count(document_path: str) -> int:
    """
    Get page count for PDF document.

    Args:
        document_path: Path to PDF file

    Returns:
        int: Number of pages
    """
    try:
        with fitz.open(document_path) as doc:
            return len(doc)
    except Exception as e:
        print(f"[XPC] get_page_count error: {e}")
        return 0


def batch_replace_text(document_path: str, output_path: str,
                       replacements: list) -> dict:
    """
    Apply multiple text replacements to a PDF (XPC-compatible).

    Args:
        document_path: Path to the source PDF.
        output_path:   Destination path.
        replacements:  list of dicts, each with:
                         "target_text":      str  (required)
                         "replacement_text": str  (required)
                         "page_index":       int  0-based (optional)
                         "manual_overrides": dict (optional)

    Returns:
        dict with "success", "applied", "skipped", "results", "message".
    """
    try:
        # Convert 0-based page_index → 1-based page_number for core
        core_reps = []
        for rep in replacements:
            r = dict(rep)
            if "page_index" in r:
                r["page_number"] = r.pop("page_index") + 1
            core_reps.append(r)

        return core.batch_replace(document_path, output_path, core_reps)

    except Exception as e:
        print(f"[XPC] batch_replace_text error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "applied": 0, "skipped": len(replacements),
                "results": [], "message": f"Exception: {e}"}


def regex_replace_text(document_path: str, output_path: str,
                       pattern: str, replacement: str,
                       ignore_case: bool = False,
                       page_range: list = None) -> dict:
    """
    Replace text matching a regex pattern in a PDF (XPC-compatible).

    Args:
        document_path: Path to the source PDF.
        output_path:   Destination path.
        pattern:       Regex pattern string.
        replacement:   Replacement string (supports back-references).
        ignore_case:   If True, matching is case-insensitive.
        page_range:    Optional [start_index, end_index] 0-based, inclusive.
                       Converted internally to 1-based page numbers.

    Returns:
        dict with "success", "replacements", "matches", "message".
    """
    import re
    try:
        flags = re.IGNORECASE if ignore_case else 0
        pg_range_1based = None
        if page_range:
            try:
                if len(page_range) < 2:
                    raise ValueError("page_range must have at least two elements")
                pg_range_1based = (int(page_range[0]) + 1, int(page_range[1]) + 1)
            except (TypeError, ValueError) as _e:
                return {"success": False, "replacements": 0, "matches": [],
                        "message": f"Invalid page_range: {_e}"}

        return core.regex_replace(document_path, output_path, pattern,
                                  replacement, flags, pg_range_1based)

    except Exception as e:
        print(f"[XPC] regex_replace_text error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "replacements": 0, "matches": [],
                "message": f"Exception: {e}"}


def apply_template_replacements(document_path: str, output_path: str,
                                placeholders: dict,
                                page_range: list = None,
                                delimiter_open: str = "{{",
                                delimiter_close: str = "}}") -> dict:
    """
    Fill template placeholders in a PDF (XPC-compatible).

    Args:
        document_path:   Path to the source PDF.
        output_path:     Destination path.
        placeholders:    dict mapping placeholder key → replacement value.
        page_range:      Optional [start_index, end_index] 0-based, inclusive.
        delimiter_open:  Opening delimiter (default "{{").
        delimiter_close: Closing delimiter (default "}}").

    Returns:
        dict with "success", "applied", "not_found", "results", "message".
    """
    try:
        pg_range_1based = None
        if page_range:
            try:
                if len(page_range) < 2:
                    raise ValueError("page_range must have at least two elements")
                pg_range_1based = (int(page_range[0]) + 1, int(page_range[1]) + 1)
            except (TypeError, ValueError) as _e:
                return {"success": False, "applied": 0,
                        "not_found": list(placeholders.keys()), "results": [],
                        "message": f"Invalid page_range: {_e}"}

        return core.apply_template(document_path, output_path, placeholders,
                                   pg_range_1based, delimiter_open, delimiter_close)

    except Exception as e:
        print(f"[XPC] apply_template_replacements error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "applied": 0,
                "not_found": list(placeholders.keys()),
                "results": [], "message": f"Exception: {e}"}


def analyze_layout(document_path: str, page_index: int,
                   rect: list = None) -> dict:
    """
    Analyse the layout context of a page (and optional focus rect).

    XPC-compatible: all fitz.Rect objects are serialised as
    [x0, y0, x1, y1] float lists.

    Args:
        document_path: Path to PDF file.
        page_index:    Zero-based page index.
        rect:          Optional [x0, y0, x1, y1] focus rect.

    Returns:
        dict with:
          - "layout_type":       str   – "single_column" | "multi_column" |
                                         "table" | "rotated" | "mixed"
          - "column_count":      int
          - "columns":           list of [x0, y0, x1, y1]
          - "has_tables":        bool
          - "tables":            list of table dicts, each with:
                                   "rect" [x0,y0,x1,y1], "rows" int,
                                   "cols" int, "cells" list of [x0,y0,x1,y1]
          - "dominant_rotation": int   – 0 | 90 | 180 | 270
          - "has_rotated_text":  bool
          - "column_index":      int | None
          - "rect_rotation":     int | None
          - "success":           bool
    """

    def rect_to_list(r):
        return [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]

    try:
        with fitz.open(document_path) as doc:
            # Guard: validate page index before indexing into the document
            if page_index < 0 or page_index >= len(doc):
                return {
                    "success": False,
                    "layout_type": "unknown",
                    "column_count": 0,
                    "columns": [],
                    "has_tables": False,
                    "tables": [],
                    "dominant_rotation": 0,
                    "has_rotated_text": False,
                    "column_index": None,
                    "rect_rotation": None,
                    "message": f"page_index {page_index} out of range (doc has {len(doc)} pages)",
                }
            page = doc[page_index]
            focus = fitz.Rect(rect) if rect else None
            ctx = core.detect_layout_context(page, focus)

        return {
            "success": True,
            "layout_type": ctx["layout_type"],
            "column_count": ctx["column_count"],
            "columns": [rect_to_list(c) for c in ctx["columns"]],
            "has_tables": ctx["has_tables"],
            "tables": [
                {
                    "rect": rect_to_list(t["rect"]),
                    "rows": t["rows"],
                    "cols": t["cols"],
                    "cells": [rect_to_list(c) for c in t["cells"]],
                }
                for t in ctx["tables"]
            ],
            "dominant_rotation": ctx["dominant_rotation"],
            "has_rotated_text": ctx["has_rotated_text"],
            "column_index": ctx["column_index"],
            "rect_rotation": ctx["rect_rotation"],
        }

    except Exception as e:
        print(f"[XPC] analyze_layout error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "layout_type": "single_column",
            "column_count": 1,
            "columns": [],
            "has_tables": False,
            "tables": [],
            "dominant_rotation": 0,
            "has_rotated_text": False,
            "column_index": None,
            "rect_rotation": None,
        }


def get_health_status() -> dict:
    """
    Return a health-check dict for XPC polling.

    Returns:
        dict with:
          "status":          "ok" | "degraded"
          "pymupdf_ok":      bool
          "pymupdf_version": str
          "error_rate":      float
          "total_calls":     int
          "total_errors":    int
          "perf_summary":    dict  – per-operation stats
          "log_level":       str
          "log_file":        str | None
    """
    try:
        return _health_check()
    except Exception as e:
        print(f"[XPC] get_health_status error: {e}")
        return {
            "status": "degraded",
            "pymupdf_ok": False,
            "pymupdf_version": "unknown",
            "error_rate": 1.0,
            "total_calls": 0,
            "total_errors": 0,
            "perf_summary": {},
            "log_level": "unknown",
            "log_file": None,
        }


def get_performance_stats() -> dict:
    """
    Return accumulated per-operation performance statistics.

    Returns:
        dict mapping operation_name → {"calls", "total_ms", "avg_ms", "errors"}
    """
    try:
        return get_perf_stats()
    except Exception as e:
        print(f"[XPC] get_performance_stats error: {e}")
        return {}
