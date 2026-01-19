"""
Unit tests for VisualTextExtractor.

Tests cover:
- Block-level boundary detection
- Smart quote normalization
- Table cell handling
- Whitespace normalization
"""
import pytest
from app.extraction.visual_text_extractor import (
    VisualTextExtractor,
    extract_visual_text,
    normalize_text,
    CHAR_REPLACEMENTS,
)


class TestSmartQuoteNormalization:
    """Tests for smart quote and dash normalization."""

    def test_smart_double_quotes(self):
        """Test smart double quote replacement."""
        text = '\u201cHello\u201d'
        result = normalize_text(text)
        assert result == '"Hello"'

    def test_smart_single_quotes(self):
        """Test smart single quote replacement."""
        text = "it\u2019s working"
        result = normalize_text(text)
        assert result == "it's working"

    def test_em_dash(self):
        """Test em dash replacement."""
        text = "word\u2014another"
        result = normalize_text(text)
        assert result == "word-another"

    def test_en_dash(self):
        """Test en dash replacement."""
        text = "2020\u20132024"
        result = normalize_text(text)
        assert result == "2020-2024"

    def test_non_breaking_space(self):
        """Test non-breaking space replacement."""
        text = "hello\xa0world"
        result = normalize_text(text)
        assert result == "hello world"


class TestWhitespaceNormalization:
    """Tests for whitespace handling."""

    def test_collapse_multiple_spaces(self):
        """Test multiple spaces collapse to single."""
        text = "hello    world"
        result = normalize_text(text)
        assert result == "hello world"

    def test_collapse_tabs(self):
        """Test tab normalization."""
        text = "hello\t\tworld"
        result = normalize_text(text)
        assert result == "hello world"

    def test_collapse_multiple_newlines(self):
        """Test multiple newlines collapse to double."""
        text = "para1\n\n\n\n\npara2"
        result = normalize_text(text)
        assert result == "para1\n\npara2"


class TestHTMLExtraction:
    """Tests for HTML text extraction."""

    def test_basic_paragraph(self):
        """Test basic paragraph extraction."""
        html = "<html><body><p>Hello World</p></body></html>"
        result = extract_visual_text(html)
        assert "Hello World" in result

    def test_strips_formatting_tags(self):
        """Test that formatting tags are stripped but text preserved."""
        html = "<p><b>Bold</b> and <i>italic</i> text</p>"
        result = extract_visual_text(html)
        assert "Bold" in result
        assert "italic" in result
        assert "<b>" not in result

    def test_div_boundaries(self):
        """Test div tags create boundaries."""
        html = "<div>First</div><div>Second</div>"
        result = extract_visual_text(html)
        # Should have paragraph break between divs
        assert "First" in result
        assert "Second" in result

    def test_table_cell_separation(self):
        """Test table cells are properly separated."""
        html = """
        <table>
            <tr>
                <td>Cell1</td>
                <td>Cell2</td>
            </tr>
        </table>
        """
        result = extract_visual_text(html)
        # Cells should not be fused
        assert "Cell1Cell2" not in result
        assert "Cell1" in result
        assert "Cell2" in result

    def test_br_tags(self):
        """Test br tags create line breaks."""
        html = "<p>Line1<br>Line2</p>"
        result = extract_visual_text(html)
        assert "Line1" in result
        assert "Line2" in result

    def test_skips_script_style(self):
        """Test script and style tags are skipped."""
        html = """
        <html>
        <head><style>.class { color: red; }</style></head>
        <body>
            <script>alert('test')</script>
            <p>Content</p>
        </body>
        </html>
        """
        result = extract_visual_text(html)
        assert "Content" in result
        assert "color" not in result
        assert "alert" not in result


class TestPreambleExtraction:
    """Tests for preamble-specific extraction."""

    def test_preamble_limit(self):
        """Test preamble respects character limit."""
        html = "<p>" + "A" * 10000 + "</p>"
        extractor = VisualTextExtractor(html)
        preamble = extractor.get_preamble(5000)
        assert len(preamble) <= 5000

    def test_preamble_contains_start(self):
        """Test preamble contains beginning of document."""
        html = """
        <p>AGREEMENT AND PLAN OF MERGER</p>
        <p>This Agreement is made by and among...</p>
        """ + "<p>Filler</p>" * 1000
        extractor = VisualTextExtractor(html)
        preamble = extractor.get_preamble(5000)
        assert "AGREEMENT AND PLAN OF MERGER" in preamble


class TestTableCellFusionPrevention:
    """Tests specifically for preventing PartyAPartyB fusion."""

    def test_adjacent_cells_separated(self):
        """Test adjacent cells without punctuation are separated."""
        html = """
        <table>
            <tr>
                <td>PartyA</td>
                <td>PartyB</td>
            </tr>
        </table>
        """
        result = extract_visual_text(html)
        assert "PartyAPartyB" not in result

    def test_cells_with_punctuation_preserved(self):
        """Test cells with punctuation are handled correctly."""
        html = """
        <table>
            <tr>
                <td>PartyA.</td>
                <td>PartyB</td>
            </tr>
        </table>
        """
        result = extract_visual_text(html)
        assert "PartyA." in result
        assert "PartyB" in result


class TestComplexEDGARHTML:
    """Tests with realistic EDGAR HTML patterns."""

    def test_nested_font_tags(self):
        """Test handling of nested font tags common in EDGAR."""
        html = """
        <div>
            <font style="font-family:Times New Roman">
                <font style="font-size:12pt">
                    <b>MERGER AGREEMENT</b>
                </font>
            </font>
        </div>
        """
        result = extract_visual_text(html)
        assert "MERGER AGREEMENT" in result
        assert "<font" not in result

    def test_span_styling(self):
        """Test span tags with styling are handled."""
        html = """
        <p>
            <span style="font-weight:bold">Agreement</span>
            <span style="text-decoration:underline">dated</span>
            January 1, 2024
        </p>
        """
        result = extract_visual_text(html)
        assert "Agreement" in result
        assert "dated" in result
        assert "January 1, 2024" in result
