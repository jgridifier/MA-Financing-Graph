"""
Visual Text Extractor for EDGAR HTML documents.

EDGAR HTML is often non-semantic, using <div>, <font>, <br><br>, etc.
This module implements proper text extraction that:
- Handles block-level boundaries correctly
- Normalizes smart quotes and dashes to ASCII
- Prevents "PartyAPartyB" fusion in tables
- Strips formatting tags while preserving text

Per instructions: Do NOT rely on <p> tags.
"""
import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag


# Block-level elements that create visual breaks
BLOCK_ELEMENTS = {
    'div', 'p', 'br', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'table', 'thead', 'tbody', 'tfoot', 'section', 'article', 'header',
    'footer', 'aside', 'nav', 'blockquote', 'pre', 'hr', 'address',
    'figcaption', 'figure', 'main', 'dd', 'dt', 'dl',
}

# Formatting tags to strip (preserve inner text)
FORMATTING_TAGS = {
    'b', 'strong', 'i', 'em', 'font', 'span', 'u', 'sup', 'sub',
    'small', 'big', 'a', 'abbr', 'acronym', 'cite', 'code', 'dfn',
    'kbd', 'samp', 'var', 'mark', 's', 'strike', 'del', 'ins', 'q',
}

# Smart quote and dash replacements
CHAR_REPLACEMENTS = {
    # Smart double quotes
    '\u201c': '"',  # Left double quotation mark
    '\u201d': '"',  # Right double quotation mark
    '\u201e': '"',  # Double low-9 quotation mark
    '\u201f': '"',  # Double high-reversed-9 quotation mark
    # Smart single quotes/apostrophes
    '\u2018': "'",  # Left single quotation mark
    '\u2019': "'",  # Right single quotation mark
    '\u201a': "'",  # Single low-9 quotation mark
    '\u201b': "'",  # Single high-reversed-9 quotation mark
    # Dashes
    '\u2013': '-',  # En dash
    '\u2014': '-',  # Em dash
    '\u2015': '-',  # Horizontal bar
    '\u2012': '-',  # Figure dash
    # Non-breaking space
    '\xa0': ' ',
    # Other whitespace
    '\u00a0': ' ',  # No-break space
    '\u2002': ' ',  # En space
    '\u2003': ' ',  # Em space
    '\u2009': ' ',  # Thin space
    '\u200a': ' ',  # Hair space
    '\u200b': '',   # Zero-width space
    '\ufeff': '',   # BOM
}


class VisualTextExtractor:
    """
    Extracts normalized visual text from EDGAR HTML documents.

    Key features:
    - Block-level boundary detection for proper paragraph breaks
    - Smart quote/dash normalization for regex compatibility
    - Table cell separation to prevent word fusion
    - Whitespace normalization
    """

    def __init__(self, html: str):
        """
        Initialize extractor with HTML content.

        Args:
            html: Raw HTML content from EDGAR
        """
        self.soup = BeautifulSoup(html, 'lxml')
        self._buffer: list[str] = []
        self._last_was_block = False

    def extract(self) -> str:
        """
        Extract and normalize visual text from HTML.

        Returns:
            Normalized text buffer suitable for regex extraction
        """
        self._buffer = []
        self._last_was_block = False
        self._process_element(self.soup)
        text = ''.join(self._buffer)
        return self._normalize_text(text)

    def _process_element(self, element):
        """Recursively process an HTML element."""
        if isinstance(element, NavigableString):
            text = str(element)
            if text.strip():
                self._buffer.append(text)
                self._last_was_block = False
            return

        if not isinstance(element, Tag):
            return

        tag_name = element.name.lower() if element.name else ''

        # Skip script, style, and hidden elements
        if tag_name in ('script', 'style', 'noscript', 'head', 'meta', 'link'):
            return

        # Handle block-level elements - add paragraph break before
        is_block = tag_name in BLOCK_ELEMENTS
        if is_block and not self._last_was_block:
            self._buffer.append('\n\n')
            self._last_was_block = True

        # Handle table cells - add separator
        if tag_name in ('td', 'th'):
            # Process children
            for child in element.children:
                self._process_element(child)
            # Add cell separator unless already ends with punctuation/newline
            if self._buffer:
                last = self._buffer[-1].rstrip()
                if last and last[-1] not in '.!?;:\n|':
                    self._buffer.append(' | ')
            return

        # Handle <br> tags
        if tag_name == 'br':
            self._buffer.append('\n')
            self._last_was_block = False
            return

        # Handle table row end
        if tag_name == 'tr':
            for child in element.children:
                self._process_element(child)
            self._buffer.append('\n')
            self._last_was_block = True
            return

        # Process children for all other elements
        for child in element.children:
            self._process_element(child)

        # Add paragraph break after block elements
        if is_block and not self._last_was_block:
            self._buffer.append('\n\n')
            self._last_was_block = True

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text with character replacements and whitespace handling.

        Normalization rules:
        1. Replace smart quotes with ASCII equivalents
        2. Replace en/em dashes with ASCII hyphen
        3. Replace non-breaking spaces with regular spaces
        4. Collapse multiple spaces to single space
        5. Collapse more than 2 newlines to double newline
        """
        # Character replacements
        for old, new in CHAR_REPLACEMENTS.items():
            text = text.replace(old, new)

        # Collapse multiple spaces/tabs to single space (preserve newlines)
        text = re.sub(r'[ \t]+', ' ', text)

        # Collapse more than 2 newlines to double newline
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Clean up space around newlines
        text = re.sub(r' *\n *', '\n', text)

        # Trim leading/trailing whitespace
        text = text.strip()

        return text

    def get_preamble(self, max_chars: int = 5000) -> str:
        """
        Get the first N characters of visual text for preamble extraction.

        Args:
            max_chars: Maximum characters to return (default 5000)

        Returns:
            First portion of normalized visual text
        """
        full_text = self.extract()
        return full_text[:max_chars]


def extract_visual_text(html: str) -> str:
    """
    Convenience function to extract visual text from HTML.

    Args:
        html: Raw HTML content

    Returns:
        Normalized visual text
    """
    extractor = VisualTextExtractor(html)
    return extractor.extract()


def get_preamble_text(html: str, max_chars: int = 5000) -> str:
    """
    Convenience function to get preamble text for extraction.

    Args:
        html: Raw HTML content
        max_chars: Maximum characters for preamble

    Returns:
        First portion of normalized visual text
    """
    extractor = VisualTextExtractor(html)
    return extractor.get_preamble(max_chars)


def normalize_text(text: str) -> str:
    """
    Normalize text without HTML parsing.

    Useful for normalizing text that's already been extracted.
    """
    # Character replacements
    for old, new in CHAR_REPLACEMENTS.items():
        text = text.replace(old, new)

    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' *\n *', '\n', text)

    return text.strip()
