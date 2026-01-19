"""
Table Parser for EDGAR HTML Tables.

Strategy (per spec Section 5):
1. Try pandas.read_html(..., flavor="bs4") first
2. Fallback to custom extraction
3. Build canonical Table IR expanding rowspan/colspan
4. Header heuristics for column identification
5. Role-column detection for bank/role mapping
"""
import re
from typing import Optional
from dataclasses import dataclass, field
from io import StringIO

import pandas as pd
from bs4 import BeautifulSoup, Tag


# Role keywords for column detection
ROLE_KEYWORDS = {
    # Bond underwriting roles
    'bookrunner', 'joint bookrunner', 'active bookrunner', 'passive bookrunner',
    'co-manager', 'co manager', 'lead manager', 'manager',
    'underwriter', 'senior underwriter', 'lead underwriter',
    # Loan arranging roles
    'arranger', 'lead arranger', 'joint lead arranger', 'mandated lead arranger',
    'administrative agent', 'admin agent', 'syndication agent', 'documentation agent',
    'collateral agent', 'paying agent',
    # Advisory roles
    'financial advisor', 'financial adviser', 'advisor', 'adviser',
    'fairness opinion',
}

# Bank name patterns to identify bank columns
BANK_PATTERNS = [
    r'\b(?:J\.?P\.?\s*Morgan|JPMorgan)\b',
    r'\b(?:Goldman\s*Sachs|GS)\b',
    r'\b(?:Morgan\s*Stanley)\b',
    r'\b(?:Bank\s*of\s*America|BofA|BAML)\b',
    r'\b(?:Citi(?:group|bank)?)\b',
    r'\b(?:Wells\s*Fargo)\b',
    r'\b(?:Barclays)\b',
    r'\b(?:Deutsche\s*Bank)\b',
    r'\b(?:Credit\s*Suisse)\b',
    r'\b(?:UBS)\b',
    r'\b(?:HSBC)\b',
    r'\b(?:BNP\s*Paribas)\b',
    r'\b(?:Societe\s*Generale)\b',
    r'\b(?:RBC|Royal\s*Bank\s*of\s*Canada)\b',
    r'\b(?:TD\s*Securities)\b',
    r'\b(?:Mizuho)\b',
    r'\b(?:MUFG|Mitsubishi\s*UFJ)\b',
    r'\b(?:SMBC|Sumitomo\s*Mitsui)\b',
]


@dataclass
class TableCell:
    """Represents a cell in the table IR."""
    text: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False


@dataclass
class TableIR:
    """
    Intermediate Representation for a parsed table.

    Features:
    - Expanded rowspan/colspan
    - Header row detection
    - Role column identification
    """
    cells: list[list[TableCell]]
    header_rows: int = 0
    role_column: Optional[int] = None
    bank_columns: list[int] = field(default_factory=list)
    num_rows: int = 0
    num_cols: int = 0


@dataclass
class BankRoleExtraction:
    """Extracted bank-role pair from a table."""
    bank_name: str
    role: str
    row: int
    col: int
    evidence_text: str


class TableParser:
    """
    Parses EDGAR HTML tables into structured Table IR.

    Implements:
    - pandas.read_html with bs4 flavor
    - Custom fallback extraction
    - Rowspan/colspan expansion
    - Header heuristics
    - Role column detection
    """

    def __init__(self, html: str):
        """
        Initialize parser with HTML content.

        Args:
            html: HTML content containing tables
        """
        self.soup = BeautifulSoup(html, 'lxml')
        self.tables: list[TableIR] = []

    def parse_all_tables(self) -> list[TableIR]:
        """Parse all tables in the HTML document."""
        table_elements = self.soup.find_all('table')

        for table_el in table_elements:
            table_ir = self._parse_table_element(table_el)
            if table_ir and table_ir.num_rows > 0:
                self._detect_headers(table_ir)
                self._detect_role_column(table_ir)
                self._detect_bank_columns(table_ir)
                self.tables.append(table_ir)

        return self.tables

    def parse_with_pandas(self) -> list[pd.DataFrame]:
        """
        Try parsing with pandas.read_html (bs4 flavor).

        Returns:
            List of DataFrames, one per table
        """
        try:
            dfs = pd.read_html(StringIO(str(self.soup)), flavor='bs4')
            return dfs
        except Exception:
            return []

    def _parse_table_element(self, table: Tag) -> Optional[TableIR]:
        """Parse a single table element into TableIR."""
        rows = table.find_all('tr')
        if not rows:
            return None

        # First pass: collect all cells with their spans
        raw_cells: list[list[tuple[str, int, int]]] = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = []
            for cell in cells:
                text = self._get_cell_text(cell)
                rowspan = int(cell.get('rowspan', 1))
                colspan = int(cell.get('colspan', 1))
                is_header = cell.name == 'th'
                row_data.append((text, rowspan, colspan, is_header))
            raw_cells.append(row_data)

        # Second pass: expand spans into grid
        if not raw_cells:
            return None

        # Calculate grid dimensions
        max_cols = max(
            sum(c[2] for c in row) for row in raw_cells
        ) if raw_cells else 0

        # Initialize grid
        num_rows = len(raw_cells)
        grid: list[list[Optional[TableCell]]] = [
            [None for _ in range(max_cols)] for _ in range(num_rows)
        ]

        # Fill grid expanding spans
        for row_idx, row in enumerate(raw_cells):
            col_idx = 0
            for text, rowspan, colspan, is_header in row:
                # Find next empty column
                while col_idx < max_cols and grid[row_idx][col_idx] is not None:
                    col_idx += 1

                if col_idx >= max_cols:
                    break

                # Create cell and fill span
                cell = TableCell(
                    text=text,
                    row=row_idx,
                    col=col_idx,
                    rowspan=rowspan,
                    colspan=colspan,
                    is_header=is_header,
                )

                for r in range(row_idx, min(row_idx + rowspan, num_rows)):
                    for c in range(col_idx, min(col_idx + colspan, max_cols)):
                        grid[r][c] = cell

                col_idx += colspan

        # Convert to TableIR (replace None with empty cells)
        cells = []
        for row_idx, row in enumerate(grid):
            row_cells = []
            for col_idx, cell in enumerate(row):
                if cell is None:
                    cell = TableCell(text="", row=row_idx, col=col_idx)
                row_cells.append(cell)
            cells.append(row_cells)

        return TableIR(
            cells=cells,
            num_rows=num_rows,
            num_cols=max_cols,
        )

    def _get_cell_text(self, cell: Tag) -> str:
        """Extract clean text from a table cell."""
        # Get text content
        text = cell.get_text(separator=' ', strip=True)
        # Normalize whitespace
        text = ' '.join(text.split())
        return text

    def _detect_headers(self, table: TableIR):
        """
        Detect header rows using heuristics.

        Heuristics:
        - Rows with all <th> tags
        - First row if it contains header-like keywords (short, descriptive text)
        - Rows with bold/different styling (limited in text extraction)
        """
        header_count = 0

        for row_idx, row in enumerate(table.cells):
            if row_idx > 2:  # Headers usually in first 3 rows
                break

            # Check if all cells in row were originally headers (<th> tags)
            all_headers = all(cell.is_header for cell in row if cell.text.strip())

            if all_headers:
                header_count = row_idx + 1
                continue

            # Only check for header keywords in the first row, and only if cells are short
            # (header cells are typically short labels, not long entity names)
            if row_idx == 0:
                row_cells = [cell.text.strip() for cell in row if cell.text.strip()]
                # Headers are typically short (< 30 chars) and contain keywords
                all_short = all(len(cell) < 30 for cell in row_cells)
                if all_short:
                    row_text = ' '.join(cell.lower() for cell in row_cells)
                    has_header_keywords = any(
                        kw in row_text for kw in ['name', 'lender', 'underwriter', 'role', 'institution', 'amount', 'commitment']
                    )
                    if has_header_keywords:
                        header_count = row_idx + 1

        table.header_rows = header_count

    def _detect_role_column(self, table: TableIR):
        """
        Detect column with high density of role keywords.

        Per spec: If one column has high density of role keywords,
        treat as role_column and map adjacent bank names to that role.
        """
        if table.num_cols == 0 or table.num_rows <= table.header_rows:
            return

        role_counts = [0] * table.num_cols

        for row in table.cells[table.header_rows:]:
            for col_idx, cell in enumerate(row):
                text_lower = cell.text.lower()
                for keyword in ROLE_KEYWORDS:
                    if keyword in text_lower:
                        role_counts[col_idx] += 1
                        break

        # Find column with highest role keyword density
        data_rows = table.num_rows - table.header_rows
        if data_rows > 0:
            for col_idx, count in enumerate(role_counts):
                density = count / data_rows
                if density > 0.3:  # 30% threshold
                    table.role_column = col_idx
                    break

    def _detect_bank_columns(self, table: TableIR):
        """Detect columns that contain bank names."""
        if table.num_cols == 0 or table.num_rows <= table.header_rows:
            return

        bank_regex = re.compile('|'.join(BANK_PATTERNS), re.IGNORECASE)

        bank_counts = [0] * table.num_cols

        for row in table.cells[table.header_rows:]:
            for col_idx, cell in enumerate(row):
                if bank_regex.search(cell.text):
                    bank_counts[col_idx] += 1

        # Mark columns with bank mentions
        data_rows = table.num_rows - table.header_rows
        if data_rows > 0:
            for col_idx, count in enumerate(bank_counts):
                density = count / data_rows
                if density > 0.2:  # 20% threshold
                    table.bank_columns.append(col_idx)

    def extract_bank_roles(self, table: TableIR) -> list[BankRoleExtraction]:
        """
        Extract bank-role pairs from a table.

        Uses role column detection to map banks to roles.
        Also infers role from column headers if not found in data rows.
        """
        extractions = []

        bank_regex = re.compile('|'.join(BANK_PATTERNS), re.IGNORECASE)

        # Check if header contains role information
        header_role = None
        if table.header_rows > 0:
            for row_idx in range(table.header_rows):
                for cell in table.cells[row_idx]:
                    text_lower = cell.text.lower()
                    if 'underwriter' in text_lower:
                        header_role = 'underwriter'
                        break
                    elif 'lender' in text_lower:
                        header_role = 'lender'
                        break
                    elif 'arranger' in text_lower:
                        header_role = 'arranger'
                        break
                    elif 'bank' in text_lower or 'institution' in text_lower:
                        header_role = 'participant'
                        break
                if header_role:
                    break

        for row_idx in range(table.header_rows, table.num_rows):
            row = table.cells[row_idx]

            # Find bank in this row - try regex first, then look for LLC/Inc patterns
            bank_name = None
            bank_col = None
            for col_idx, cell in enumerate(row):
                cell_text = cell.text.strip()
                if not cell_text:
                    continue
                # Try bank regex patterns
                if bank_regex.search(cell_text):
                    bank_name = cell_text
                    bank_col = col_idx
                    break
                # Also check for common bank suffixes (LLC, Inc., N.A., etc.)
                if re.search(r'\b(?:LLC|Inc\.?|N\.?A\.?|Bank|Securities|Capital)\s*$', cell_text, re.IGNORECASE):
                    # Verify it's not just a dollar amount or number
                    if not re.match(r'^[\$\d,.\s]+$', cell_text):
                        bank_name = cell_text
                        bank_col = col_idx
                        break

            if not bank_name:
                continue

            # Find role in this row
            role = None
            if table.role_column is not None:
                role_cell = row[table.role_column]
                role = role_cell.text.strip()
            else:
                # Look for role keywords in other cells
                for col_idx, cell in enumerate(row):
                    if col_idx == bank_col:
                        continue
                    text_lower = cell.text.lower()
                    for keyword in ROLE_KEYWORDS:
                        if keyword in text_lower:
                            role = cell.text.strip()
                            break
                    if role:
                        break

            # Use header-inferred role if no explicit role found
            if not role and header_role:
                role = header_role

            if bank_name and role:
                evidence = ' | '.join(c.text for c in row if c.text.strip())
                extractions.append(BankRoleExtraction(
                    bank_name=bank_name,
                    role=role,
                    row=row_idx,
                    col=bank_col or 0,
                    evidence_text=evidence,
                ))

        return extractions


def parse_tables(html: str) -> list[TableIR]:
    """Convenience function to parse all tables from HTML."""
    parser = TableParser(html)
    return parser.parse_all_tables()


def extract_financing_participants(html: str) -> list[BankRoleExtraction]:
    """Extract bank-role pairs from all tables in HTML."""
    parser = TableParser(html)
    tables = parser.parse_all_tables()

    all_extractions = []
    for table in tables:
        extractions = parser.extract_bank_roles(table)
        all_extractions.extend(extractions)

    return all_extractions
