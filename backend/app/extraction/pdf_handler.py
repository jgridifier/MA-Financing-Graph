"""
PDF Handler with human-in-the-loop support.

Per spec Section 7:
- Material PDF exhibits that fail parsing create ProcessingAlerts
- Users can manually input missing data
- Manual inputs feed into reconciler/classifier/attribution
"""
import re
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.filing import Exhibit
from app.models.alert import ProcessingAlert, AlertType


@dataclass
class PDFExtractionResult:
    """Result of PDF extraction attempt."""
    success: bool
    text: Optional[str] = None
    quality: str = 'unknown'  # good, poor, failed
    error: Optional[str] = None


# Material exhibit patterns (same as ingest.py)
MATERIAL_EXHIBIT_PATTERNS = [
    r'credit\s+agreement',
    r'commitment\s+letter',
    r'bridge',
    r'debt\s+financing',
    r'underwriting\s+agreement',
    r'indenture',
    r'loan\s+agreement',
    r'term\s+loan',
    r'revolving',
]


def extract_pdf_text(pdf_content: bytes) -> PDFExtractionResult:
    """
    Extract text from PDF using pdfplumber.

    Args:
        pdf_content: Raw PDF bytes

    Returns:
        PDFExtractionResult with extracted text or error
    """
    try:
        import pdfplumber
        from io import BytesIO

        with pdfplumber.open(BytesIO(pdf_content)) as pdf:
            text_parts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

            if not text_parts:
                return PDFExtractionResult(
                    success=False,
                    quality='failed',
                    error='No text extracted - may be scanned/image PDF',
                )

            full_text = '\n\n'.join(text_parts)

            # Quality check - look for readable content
            word_count = len(full_text.split())
            if word_count < 50:
                return PDFExtractionResult(
                    success=True,
                    text=full_text,
                    quality='poor',
                )

            return PDFExtractionResult(
                success=True,
                text=full_text,
                quality='good',
            )

    except Exception as e:
        return PDFExtractionResult(
            success=False,
            quality='failed',
            error=str(e),
        )


def is_material_exhibit(exhibit: Exhibit) -> bool:
    """Check if an exhibit is material (financing-related)."""
    desc_lower = (exhibit.description or '').lower()
    return any(
        re.search(pattern, desc_lower)
        for pattern in MATERIAL_EXHIBIT_PATTERNS
    )


def process_pdf_exhibit(
    db: Session,
    exhibit: Exhibit,
    pdf_content: bytes,
) -> tuple[Optional[str], Optional[ProcessingAlert]]:
    """
    Process a PDF exhibit.

    If material and extraction fails/poor, creates a ProcessingAlert.

    Args:
        db: Database session
        exhibit: Exhibit record
        pdf_content: Raw PDF bytes

    Returns:
        Tuple of (extracted_text, alert_if_any)
    """
    result = extract_pdf_text(pdf_content)

    if result.success and result.quality == 'good':
        exhibit.raw_content = result.text
        exhibit.extraction_quality = 'good'
        exhibit.processed = True
        return (result.text, None)

    # Extraction failed or poor quality
    exhibit.extraction_quality = result.quality

    # Check if material - if so, create alert
    if is_material_exhibit(exhibit):
        alert = ProcessingAlert(
            alert_type=AlertType.UNPARSED_MATERIAL_EXHIBIT,
            filing_id=exhibit.filing_id,
            exhibit_id=exhibit.id,
            title=f"Material PDF exhibit requires manual review: {exhibit.exhibit_type}",
            description=result.error or f"PDF extraction quality: {result.quality}",
            exhibit_link=exhibit.url,
            fields_needed=[
                "facility_type",
                "amount",
                "participants",
                "roles",
                "purpose",
            ],
        )
        db.add(alert)
        return (result.text, alert)

    # Non-material, just mark as processed
    exhibit.processed = True
    return (result.text, None)


def extract_tables_from_pdf(pdf_content: bytes) -> list[list[list[str]]]:
    """
    Extract tables from PDF using pdfplumber.

    Returns:
        List of tables, each table is list of rows, each row is list of cells
    """
    try:
        import pdfplumber
        from io import BytesIO

        tables = []
        with pdfplumber.open(BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)

        return tables

    except Exception as e:
        print(f"PDF table extraction error: {e}")
        return []


class PDFProcessor:
    """
    Handles PDF processing with fallback to human review.
    """

    def __init__(self, db: Session):
        self.db = db

    def process_exhibit(self, exhibit: Exhibit, content: bytes) -> bool:
        """
        Process a single PDF exhibit.

        Returns:
            True if successfully processed, False if needs manual review
        """
        if not exhibit.is_pdf:
            return True

        text, alert = process_pdf_exhibit(self.db, exhibit, content)

        if alert:
            self.db.commit()
            return False

        if text:
            from app.extraction.visual_text_extractor import normalize_text
            exhibit.visual_text = normalize_text(text)
            self.db.commit()
            return True

        return False

    def extract_financing_from_pdf(
        self,
        exhibit: Exhibit,
        content: bytes,
    ) -> dict:
        """
        Extract financing information from PDF.

        Returns dict with:
        - participants: list of {bank, role}
        - amount: extracted amount
        - facility_type: loan/bond/etc
        """
        from app.extraction.regex_pack import CURRENCY_AMOUNT, extract_currency_amounts

        result = {
            'participants': [],
            'amounts': [],
            'facility_type': None,
        }

        # Extract text
        extraction = extract_pdf_text(content)
        if not extraction.success or not extraction.text:
            return result

        text = extraction.text

        # Extract amounts
        amounts = extract_currency_amounts(text)
        result['amounts'] = [
            {'raw': a.raw_text, 'usd': a.value_usd}
            for a in amounts
        ]

        # Extract tables for participants
        tables = extract_tables_from_pdf(content)
        for table in tables:
            # Look for bank/role columns
            from app.extraction.table_parser import ROLE_KEYWORDS, BANK_PATTERNS
            bank_pattern = re.compile('|'.join(BANK_PATTERNS), re.IGNORECASE)

            for row in table:
                if not row:
                    continue

                # Look for bank name in row
                bank_name = None
                role = None
                for cell in row:
                    if not cell:
                        continue
                    cell_text = str(cell)
                    if bank_pattern.search(cell_text):
                        bank_name = cell_text.strip()
                    for keyword in ROLE_KEYWORDS:
                        if keyword in cell_text.lower():
                            role = cell_text.strip()
                            break

                if bank_name:
                    result['participants'].append({
                        'bank': bank_name,
                        'role': role or 'unknown',
                    })

        # Determine facility type from description/content
        text_lower = text.lower()
        if 'term loan' in text_lower:
            result['facility_type'] = 'term_loan'
        elif 'revolving' in text_lower:
            result['facility_type'] = 'rcf'
        elif 'bridge' in text_lower:
            result['facility_type'] = 'bridge'
        elif 'bond' in text_lower or 'note' in text_lower:
            result['facility_type'] = 'bond'
        elif 'credit' in text_lower:
            result['facility_type'] = 'loan'

        return result
