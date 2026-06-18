"""
text_normalize.py - Unicode/text normalization (Candidate E extraction).

Pure functions lifted out of core.py. No PyMuPDF and no core dependency -
only the standard library. The interface is the test surface: every
function here is exercisable without constructing a PDF.
"""
from functools import lru_cache


@lru_cache(maxsize=4000)
def normalize_unicode(text: str, form: str = 'NFC') -> str:
    """
    Normalize Unicode text using specified normalization form.

    Args:
        text: Text to normalize
        form: Normalization form - 'NFC', 'NFD', 'NFKC', or 'NFKD'
            - NFC: Canonical Composition (default, preserves ligatures)
            - NFD: Canonical Decomposition (separates combining marks)
            - NFKC: Compatibility Composition (decomposes ligatures)
            - NFKD: Compatibility Decomposition (maximum decomposition)

    Returns:
        Normalized text

    Examples:
        >>> normalize_unicode("café", "NFC")   # é as single codepoint
        'café'
        >>> normalize_unicode("café", "NFD")   # e + combining accent
        'café'
        >>> normalize_unicode("ﬁnd", "NFKC")  # ligature → fi
        'find'
    """
    import unicodedata

    if not text:
        return text

    valid_forms = ['NFC', 'NFD', 'NFKC', 'NFKD']
    if form not in valid_forms:
        raise ValueError(f"Invalid normalization form '{form}'. Must be one of {valid_forms}")

    return unicodedata.normalize(form, text)


def strip_invisible_chars(text: str, strip_zwsp: bool = True, strip_control: bool = True) -> str:
    """
    Remove invisible and zero-width characters from text.

    Args:
        text: Text to process
        strip_zwsp: Strip zero-width spaces and joiners (default True)
        strip_control: Strip control characters (default True)

    Returns:
        Text with invisible characters removed

    Removes:
        - Zero-width space (U+200B)
        - Zero-width non-joiner (U+200C)
        - Zero-width joiner (U+200D)
        - Zero-width no-break space / BOM (U+FEFF)
        - Word joiner (U+2060)
        - Control characters (U+0000-U+001F, U+007F-U+009F) if strip_control=True
    """
    if not text:
        return text

    result = text

    # Strip zero-width characters
    if strip_zwsp:
        zero_width_chars = [
            '\u200B',  # Zero-width space
            '\u200C',  # Zero-width non-joiner
            '\u200D',  # Zero-width joiner
            '\uFEFF',  # Zero-width no-break space (BOM)
            '\u2060',  # Word joiner
        ]
        for char in zero_width_chars:
            result = result.replace(char, '')

    # Strip control characters (but preserve \n, \r, \t)
    if strip_control:
        import unicodedata
        result = ''.join(
            char for char in result
            if unicodedata.category(char) != 'Cc' or char in '\n\r\t'
        )

    return result


# Common ligatures mapping (ligature → decomposed form)
LIGATURE_MAP = {
    # Latin ligatures
    'ﬁ': 'fi',
    'ﬂ': 'fl',
    'ﬀ': 'ff',
    'ﬃ': 'ffi',
    'ﬄ': 'ffl',
    'ﬅ': 'ft',  # Long s + t
    'ﬆ': 'st',
    # IJ ligatures
    'Ĳ': 'IJ',
    'ĳ': 'ij',
    # Æ/Œ ligatures
    'Æ': 'AE',
    'æ': 'ae',
    'Œ': 'OE',
    'œ': 'oe',
    # Armenian ligatures
    'ﬓ': 'մն',
    'ﬔ': 'մե',
    'ﬕ': 'մի',
    'ﬖ': 'վն',
    'ﬗ': 'մխ',
}

# Reverse mapping for restoration
LIGATURE_REVERSE_MAP = {v: k for k, v in LIGATURE_MAP.items()}


def detect_ligatures(text: str) -> dict:
    """
    Detect ligatures in text and return mapping.

    Args:
        text: Text to analyze

    Returns:
        dict with keys:
        - positions: list of (start, end, ligature, decomposed)
        - has_ligatures: bool
        - count: int

    Example:
        >>> detect_ligatures("ﬁnd the ﬁle")
        {
            'positions': [(0, 1, 'ﬁ', 'fi'), (9, 10, 'ﬁ', 'fi')],
            'has_ligatures': True,
            'count': 2
        }
    """
    if not text:
        return {'positions': [], 'has_ligatures': False, 'count': 0}

    positions = []

    for i, char in enumerate(text):
        if char in LIGATURE_MAP:
            decomposed = LIGATURE_MAP[char]
            positions.append((i, i + 1, char, decomposed))

    return {
        'positions': positions,
        'has_ligatures': len(positions) > 0,
        'count': len(positions)
    }


def decompose_ligatures(text: str) -> tuple[str, dict]:
    """
    Decompose ligatures and return both decomposed text and ligature map.

    Args:
        text: Text with potential ligatures

    Returns:
        (decomposed_text, ligature_info)

    Example:
        >>> decompose_ligatures("ﬁnd")
        ('find', {'positions': [(0, 1, 'ﬁ', 'fi')], ...})
    """
    if not text:
        return text, {'positions': [], 'has_ligatures': False, 'count': 0}

    # Detect ligatures first
    ligature_info = detect_ligatures(text)

    # Decompose
    result = text
    for ligature, decomposed in LIGATURE_MAP.items():
        result = result.replace(ligature, decomposed)

    return result, ligature_info


def restore_ligatures(text: str, ligature_info: dict) -> str:
    """
    Restore ligatures in text based on ligature map from original.

    This attempts to restore ligatures in replacement text if the original
    text had ligatures in similar positions.

    Args:
        text: Replacement text (decomposed)
        ligature_info: Ligature info from detect_ligatures() on original

    Returns:
        Text with ligatures restored where possible

    Example:
        >>> original_info = detect_ligatures("ﬁnd")
        >>> restore_ligatures("finding", original_info)
        'ﬁnding'  # Ligature restored at start
    """
    if not text or not ligature_info.get('has_ligatures'):
        return text

    result = text

    # Restore ligatures only at the exact recorded positions.
    #
    # ligature_info['positions'] contains (pos, end, ligature, decomposed)
    # tuples where pos/end are character offsets in the *original* ligatured
    # text.  When the original is decomposed, each ligature (1 char) expands
    # to its multi-char form, so every subsequent position in the decomposed
    # text is shifted forward by (len(decomposed) - 1) for each prior
    # ligature.  We call this the "expansion shift".
    #
    # As we restore ligatures left-to-right in `result` the string shrinks,
    # so we subtract (len(decomposed) - 1) for each successful restoration.
    # The two effects cancel: expansion_shift grows +1 per prior original
    # ligature, and shrinkage grows -1 per restored ligature.  We combine
    # them into a single running `offset_delta`:
    #   • +=(len(decomposed) - 1) for each original ligature before this pos
    #     (expansion from decomposing the original), then
    #   • -=(len(decomposed) - 1) for each ligature we have already restored
    #     into result (shrinkage).
    #
    # For a 1-to-1 restore path (same text, same positions) those cancel to
    # zero net shift after each step.  For replacement text that matches only
    # some positions, the expansion shift accounts for unrestored gaps.
    #
    # If the decomposed form is NOT present at the computed position we skip
    # it — the replacement text simply does not have a matching span there,
    # and we must not corrupt other words that happen to contain the same
    # character sequence elsewhere.
    expansion_shift = 0   # chars added by expanding prior original ligatures
    restore_shrink = 0    # chars removed by restoring ligatures into result
    for pos, _end, ligature, decomposed in sorted(
        ligature_info['positions'], key=lambda x: x[0]
    ):
        decomposed_len = len(decomposed)
        # Position of this span in the decomposed text (before any restoration)
        decomposed_pos = pos + expansion_shift
        # Adjust for chars already removed by previous restorations
        result_pos = decomposed_pos - restore_shrink
        if result[result_pos:result_pos + decomposed_len] == decomposed:
            result = result[:result_pos] + ligature + result[result_pos + decomposed_len:]
            restore_shrink += decomposed_len - 1
        # Account for this original ligature expanding the decomposed text
        # regardless of whether we restored it in result.
        expansion_shift += decomposed_len - 1

    return result


@lru_cache(maxsize=2000)
def normalize_text_for_matching(text: str, preserve_case: bool = False) -> str:
    """
    Normalize text for matching (aggressive normalization).

    Used when searching for text to find. More aggressive than replacement.

    Args:
        text: Text to normalize
        preserve_case: Keep original case (default False = lowercase)

    Returns:
        Normalized text suitable for matching

    Applies:
        - NFKC normalization (decomposes ligatures, converts compatibility chars)
        - Strips zero-width characters
        - Normalizes whitespace
        - Optionally lowercases
    """
    if not text:
        return text

    # Apply NFKC (compatibility composition)
    # This converts ligatures: "ﬁ" → "fi"
    result = normalize_unicode(text, form='NFKC')

    # Strip invisible characters
    result = strip_invisible_chars(result)

    # BUG #49 FIX: Preserve whitespace patterns while normalizing
    # Instead of aggressively collapsing all whitespace to single spaces,
    # preserve intentional spacing (double/triple spaces for formatting)
    # Only normalize truly excessive runs (4+ consecutive spaces)
    import re
    # Replace 4+ spaces with 2 spaces (preserve some spacing intent)
    # This handles tables, indentation, justified text, etc.
    result = re.sub(r' {4,}', '  ', result)
    # Normalize line endings to single newline
    result = re.sub(r'\n+', '\n', result)
    # Trim leading/trailing whitespace per line (not entire string)
    result = '\n'.join(line.rstrip() for line in result.split('\n'))

    # Lowercase for case-insensitive matching
    if not preserve_case:
        result = result.lower()

    return result


def normalize_text_for_replacement(text: str, preserve_ligatures: bool = True) -> str:
    """
    Normalize text for replacement (conservative normalization).

    Used when inserting replacement text. More conservative than matching.

    Args:
        text: Replacement text
        preserve_ligatures: Try to preserve ligatures (default True)

    Returns:
        Normalized text suitable for PDF insertion

    Applies:
        - NFC normalization (composes combining characters, preserves ligatures)
        - Does NOT strip zero-width chars (may be intentional)
        - Does NOT normalize whitespace (preserve user formatting)
    """
    if not text:
        return text

    # Apply NFC (canonical composition)
    # This preserves ligatures like "ﬁ" but composes "e + ́" → "é"
    result = normalize_unicode(text, form='NFC' if preserve_ligatures else 'NFKC')

    return result


@lru_cache(maxsize=2000)
def normalize_special_chars(text: str) -> str:
    """
    Normalize special characters for robust text matching.

    Converts various Unicode characters to their ASCII equivalents for comparison.
    This handles:
    - Smart quotes → straight quotes
    - Various dashes → hyphen-minus
    - Ligatures → component letters
    - Special whitespace → regular space
    - Currency symbols → abbreviated names

    Args:
        text: Text to normalize

    Returns:
        Text with special characters normalized to ASCII equivalents
    """
    if not text:
        return text

    # Comprehensive character normalization map
    replacements = {
        # Whitespace
        '\u00a0': ' ',    # Non-breaking space -> regular space
        '\u2003': ' ',    # Em space
        '\u2002': ' ',    # En space
        '\u2009': ' ',    # Thin space
        '\u200a': ' ',    # Hair space
        '\u200b': '',     # Zero-width space (remove)
        '\ufeff': '',     # BOM / zero-width no-break space (remove)

        # Quotes - smart quotes to straight
        '\u2018': "'",    # Left single quote
        '\u2019': "'",    # Right single quote / apostrophe
        '\u201a': "'",    # Single low-9 quote
        '\u201b': "'",    # Single high-reversed-9 quote
        '\u2032': "'",    # Prime
        '\u2035': "'",    # Reversed prime
        '\u2033': '"',    # Double prime
        '\u2036': '"',    # Reversed double prime
        '\u201c': '"',    # Left double quote
        '\u201d': '"',    # Right double quote
        '\u201e': '"',    # Double low-9 quote
        '\u201f': '"',    # Double high-reversed-9 quote
        '\u00ab': '"',    # Left guillemet
        '\u00bb': '"',    # Right guillemet
        '\u2039': "'",    # Single left guillemet
        '\u203a': "'",    # Single right guillemet

        # Dashes and hyphens
        '\u2212': '-',    # Minus sign -> hyphen
        '\u2013': '-',    # En-dash -> hyphen
        '\u2014': '-',    # Em-dash -> hyphen
        '\u2015': '-',    # Horizontal bar
        '\u2010': '-',    # Hyphen
        '\u2011': '-',    # Non-breaking hyphen
        '\u2012': '-',    # Figure dash
        '\u00ad': '',     # Soft hyphen (remove)

        # Ligatures (common ones that NFKC might miss)
        '\ufb00': 'ff',   # ff ligature
        '\ufb01': 'fi',   # fi ligature
        '\ufb02': 'fl',   # fl ligature
        '\ufb03': 'ffi',  # ffi ligature
        '\ufb04': 'ffl',  # ffl ligature
        '\ufb05': 'st',   # st ligature (long s + t)
        '\ufb06': 'st',   # st ligature

        # Currency and symbols
        '\uff04': '$',    # Fullwidth dollar
        '\u20ac': 'EUR',  # Euro symbol
        '\u00a3': 'GBP',  # Pound symbol
        '\u00a5': 'JPY',  # Yen symbol

        # Ellipsis and dots
        '\u2026': '...',  # Horizontal ellipsis
        '\u22ef': '...',  # Midline horizontal ellipsis

        # Other common substitutions
        '\u00b7': '.',    # Middle dot
        '\u2022': '*',    # Bullet
        '\u2219': '*',    # Bullet operator
        '\u00d7': 'x',    # Multiplication sign
        '\u00f7': '/',    # Division sign
    }

    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result
