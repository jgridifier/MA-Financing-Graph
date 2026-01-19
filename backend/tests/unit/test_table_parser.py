"""
Unit tests for Table Parser.

Tests cover:
- Basic table parsing
- Rowspan/colspan expansion
- Header detection
- Role column detection
- Bank extraction
"""
import pytest
from app.extraction.table_parser import (
    TableParser,
    TableIR,
    parse_tables,
    extract_financing_participants,
)


class TestBasicTableParsing:
    """Tests for basic table parsing functionality."""

    def test_simple_table(self):
        """Test parsing a simple table."""
        html = """
        <table>
            <tr><td>A</td><td>B</td></tr>
            <tr><td>1</td><td>2</td></tr>
        </table>
        """
        tables = parse_tables(html)
        assert len(tables) == 1
        table = tables[0]
        assert table.num_rows == 2
        assert table.num_cols == 2
        assert table.cells[0][0].text == 'A'
        assert table.cells[1][1].text == '2'

    def test_empty_table(self):
        """Test empty table handling."""
        html = "<table></table>"
        tables = parse_tables(html)
        assert len(tables) == 0

    def test_multiple_tables(self):
        """Test parsing multiple tables."""
        html = """
        <table><tr><td>Table1</td></tr></table>
        <table><tr><td>Table2</td></tr></table>
        """
        tables = parse_tables(html)
        assert len(tables) == 2


class TestRowspanColspan:
    """Tests for rowspan/colspan expansion."""

    def test_colspan(self):
        """Test colspan expansion."""
        html = """
        <table>
            <tr><td colspan="2">Header</td></tr>
            <tr><td>A</td><td>B</td></tr>
        </table>
        """
        tables = parse_tables(html)
        assert len(tables) == 1
        table = tables[0]
        assert table.num_cols == 2
        # Header cell should span both columns
        assert table.cells[0][0].text == 'Header'
        assert table.cells[0][1].text == 'Header'

    def test_rowspan(self):
        """Test rowspan expansion."""
        html = """
        <table>
            <tr><td rowspan="2">Span</td><td>A</td></tr>
            <tr><td>B</td></tr>
        </table>
        """
        tables = parse_tables(html)
        assert len(tables) == 1
        table = tables[0]
        assert table.num_rows == 2
        # First cell should span both rows
        assert table.cells[0][0].text == 'Span'
        assert table.cells[1][0].text == 'Span'


class TestHeaderDetection:
    """Tests for header row detection."""

    def test_th_tags(self):
        """Test header detection from th tags."""
        html = """
        <table>
            <tr><th>Name</th><th>Role</th></tr>
            <tr><td>Bank A</td><td>Bookrunner</td></tr>
        </table>
        """
        tables = parse_tables(html)
        assert len(tables) == 1
        table = tables[0]
        assert table.header_rows >= 1
        assert table.cells[0][0].is_header

    def test_header_keywords(self):
        """Test header detection from keywords."""
        html = """
        <table>
            <tr><td>Bank Name</td><td>Role</td><td>Amount</td></tr>
            <tr><td>JPMorgan</td><td>Lead</td><td>$100M</td></tr>
        </table>
        """
        tables = parse_tables(html)
        assert len(tables) == 1
        table = tables[0]
        assert table.header_rows >= 1


class TestRoleColumnDetection:
    """Tests for role column detection."""

    def test_role_column_detection(self):
        """Test detection of column with high role keyword density."""
        html = """
        <table>
            <tr><td>Bank</td><td>Role</td></tr>
            <tr><td>JPMorgan</td><td>Bookrunner</td></tr>
            <tr><td>Goldman</td><td>Co-Manager</td></tr>
            <tr><td>Morgan Stanley</td><td>Underwriter</td></tr>
        </table>
        """
        tables = parse_tables(html)
        assert len(tables) == 1
        table = tables[0]
        assert table.role_column is not None
        assert table.role_column == 1  # Second column


class TestBankExtraction:
    """Tests for bank name extraction from tables."""

    def test_extract_banks_with_roles(self):
        """Test extracting bank-role pairs."""
        html = """
        <table>
            <tr><th>Institution</th><th>Role</th></tr>
            <tr><td>JPMorgan Chase & Co.</td><td>Joint Bookrunner</td></tr>
            <tr><td>Goldman Sachs</td><td>Bookrunner</td></tr>
            <tr><td>Bank of America</td><td>Co-Manager</td></tr>
        </table>
        """
        extractions = extract_financing_participants(html)
        assert len(extractions) >= 2

        banks = [e.bank_name for e in extractions]
        assert any('JPMorgan' in b for b in banks)
        assert any('Goldman' in b for b in banks)

    def test_extract_roles(self):
        """Test that roles are correctly extracted."""
        html = """
        <table>
            <tr><td>JPMorgan</td><td>Lead Arranger</td></tr>
            <tr><td>Citi</td><td>Administrative Agent</td></tr>
        </table>
        """
        extractions = extract_financing_participants(html)

        roles = [e.role.lower() for e in extractions]
        assert any('arranger' in r for r in roles) or any('agent' in r for r in roles)


class TestRealWorldEDGARTables:
    """Tests with realistic EDGAR table patterns."""

    def test_underwriter_table(self):
        """Test typical underwriter table from prospectus."""
        html = """
        <table>
            <tr>
                <th>Underwriters</th>
                <th>Principal Amount</th>
            </tr>
            <tr>
                <td>J.P. Morgan Securities LLC</td>
                <td>$500,000,000</td>
            </tr>
            <tr>
                <td>Goldman Sachs & Co. LLC</td>
                <td>$500,000,000</td>
            </tr>
            <tr>
                <td>Barclays Capital Inc.</td>
                <td>$250,000,000</td>
            </tr>
        </table>
        """
        extractions = extract_financing_participants(html)
        assert len(extractions) >= 2

    def test_syndicate_table(self):
        """Test loan syndicate table."""
        html = """
        <table>
            <tr>
                <th>Lender</th>
                <th>Commitment</th>
                <th>Role</th>
            </tr>
            <tr>
                <td>JPMorgan Chase Bank, N.A.</td>
                <td>$1,000,000,000</td>
                <td>Administrative Agent and Joint Lead Arranger</td>
            </tr>
            <tr>
                <td>Bank of America, N.A.</td>
                <td>$750,000,000</td>
                <td>Syndication Agent and Joint Lead Arranger</td>
            </tr>
        </table>
        """
        extractions = extract_financing_participants(html)
        assert len(extractions) >= 2

        jpmorgan = next((e for e in extractions if 'JPMorgan' in e.bank_name), None)
        assert jpmorgan is not None
        assert 'arranger' in jpmorgan.role.lower() or 'agent' in jpmorgan.role.lower()


class TestTableIRStructure:
    """Tests for TableIR data structure."""

    def test_cell_coordinates(self):
        """Test that cells have correct row/col coordinates."""
        html = """
        <table>
            <tr><td>0,0</td><td>0,1</td></tr>
            <tr><td>1,0</td><td>1,1</td></tr>
        </table>
        """
        tables = parse_tables(html)
        table = tables[0]

        assert table.cells[0][0].row == 0
        assert table.cells[0][0].col == 0
        assert table.cells[1][1].row == 1
        assert table.cells[1][1].col == 1

    def test_bank_columns_detection(self):
        """Test bank column detection."""
        html = """
        <table>
            <tr><td>Role</td><td>Bank</td></tr>
            <tr><td>Lead</td><td>JPMorgan</td></tr>
            <tr><td>Agent</td><td>Goldman Sachs</td></tr>
            <tr><td>Manager</td><td>Morgan Stanley</td></tr>
        </table>
        """
        tables = parse_tables(html)
        table = tables[0]

        assert len(table.bank_columns) >= 1
        assert 1 in table.bank_columns  # Second column has banks
