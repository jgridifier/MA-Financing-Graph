"""
Ingestion worker for SEC EDGAR filings.

Handles:
1. Fetching filing list from EDGAR
2. Downloading documents and exhibits
3. Parsing and extracting visual text
4. Running fact extraction
"""
import re
from typing import Optional
from datetime import datetime
from bs4 import BeautifulSoup

from app.db.base import SessionLocal
from app.models.filing import Filing, Exhibit
from app.services.edgar_client import get_edgar_client
from app.extraction.visual_text_extractor import extract_visual_text
from app.extraction.fact_extractor import extract_facts_from_filing


# Material exhibit patterns
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


def ingest_company_filings(
    cik: str,
    form_types: list[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Main ingestion function for a company's filings.

    Args:
        cik: Company CIK
        form_types: List of form types to ingest
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
    """
    db = SessionLocal()
    client = get_edgar_client()

    try:
        # Get filing list
        filings = client.search_filings(
            cik=cik,
            form_types=form_types,
            start_date=start_date,
            end_date=end_date,
        )

        print(f"Found {len(filings)} filings for CIK {cik}")

        for filing_data in filings:
            # Check if already ingested
            existing = db.query(Filing).filter(
                Filing.accession_number == filing_data['accession_number']
            ).first()

            if existing:
                print(f"Skipping existing filing: {filing_data['accession_number']}")
                continue

            # Create filing record
            filing = ingest_single_filing(db, client, filing_data)
            if filing:
                # Extract facts
                result = extract_facts_from_filing(db, filing)
                print(f"Extracted {len(result.facts)} facts, {len(result.alerts)} alerts")

                # Save facts
                for fact in result.facts:
                    db.add(fact)
                for alert in result.alerts:
                    db.add(alert)

                filing.processed = True
                filing.processed_at = datetime.utcnow()
                db.commit()

    except Exception as e:
        print(f"Error during ingestion: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def ingest_single_filing(db, client, filing_data: dict) -> Optional[Filing]:
    """
    Ingest a single filing with its exhibits.

    Returns:
        Filing object or None if failed
    """
    try:
        cik = filing_data['cik']
        accession = filing_data['accession_number']

        print(f"Ingesting: {accession} ({filing_data['form_type']})")

        # Create filing record
        filing = Filing(
            accession_number=accession,
            cik=cik,
            form_type=filing_data['form_type'],
            filing_date=datetime.fromisoformat(filing_data['filing_date']),
            company_name=filing_data.get('company_name'),
            filing_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{filing_data['primary_document']}",
        )

        # Fetch primary document
        try:
            primary_html = client.fetch_document(
                cik=cik,
                accession_number=accession,
                document_name=filing_data['primary_document'],
            )
            filing.raw_html = primary_html
            filing.visual_text = extract_visual_text(primary_html)
        except Exception as e:
            print(f"Failed to fetch primary document: {e}")

        db.add(filing)
        db.flush()

        # Fetch and parse index to get exhibits
        exhibits = fetch_exhibits(client, cik, accession)

        for exhibit_data in exhibits:
            exhibit = create_exhibit(db, client, filing, exhibit_data)
            if exhibit:
                filing.exhibits.append(exhibit)

        db.commit()
        return filing

    except Exception as e:
        print(f"Error ingesting filing: {e}")
        db.rollback()
        return None


def fetch_exhibits(client, cik: str, accession: str) -> list[dict]:
    """
    Parse filing index to extract exhibit information.

    Returns:
        List of exhibit metadata dicts
    """
    exhibits = []

    try:
        # Fetch index page
        index_url = f"/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40&search_text="
        acc_fmt = accession.replace('-', '')
        index_html = client.fetch(
            f"https://www.sec.gov/Archives/edgar/data/{cik.zfill(10)}/{acc_fmt}/{accession}-index.htm"
        )

        soup = BeautifulSoup(index_html, 'lxml')

        # Find document table
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Check if this is an exhibit row
                    seq = cells[0].get_text(strip=True) if len(cells) > 0 else ''
                    desc = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    doc_link = cells[2].find('a') if len(cells) > 2 else None

                    if doc_link and ('EX-' in desc.upper() or 'EXHIBIT' in desc.upper()):
                        filename = doc_link.get_text(strip=True)
                        href = doc_link.get('href', '')

                        # Determine exhibit type
                        exhibit_type = 'UNKNOWN'
                        ex_match = re.search(r'EX-(\d+\.?\d*)', desc.upper())
                        if ex_match:
                            exhibit_type = f"EX-{ex_match.group(1)}"

                        exhibits.append({
                            'exhibit_type': exhibit_type,
                            'description': desc,
                            'filename': filename,
                            'url': href if href.startswith('http') else f"https://www.sec.gov{href}",
                        })

    except Exception as e:
        print(f"Error fetching exhibits: {e}")

    return exhibits


def create_exhibit(db, client, filing: Filing, exhibit_data: dict) -> Optional[Exhibit]:
    """
    Create an exhibit record and fetch its content.

    Returns:
        Exhibit object or None
    """
    try:
        exhibit = Exhibit(
            filing_id=filing.id,
            exhibit_type=exhibit_data['exhibit_type'],
            description=exhibit_data.get('description'),
            filename=exhibit_data.get('filename'),
            url=exhibit_data.get('url'),
        )

        # Check if PDF
        filename = exhibit_data.get('filename', '').lower()
        exhibit.is_pdf = filename.endswith('.pdf')

        # Check if material exhibit
        desc_lower = exhibit_data.get('description', '').lower()
        exhibit.is_material = any(
            re.search(pattern, desc_lower)
            for pattern in MATERIAL_EXHIBIT_PATTERNS
        )

        # Fetch content for HTML exhibits
        if not exhibit.is_pdf and exhibit.url:
            try:
                content = client.fetch(exhibit.url)
                exhibit.raw_content = content
                exhibit.visual_text = extract_visual_text(content)
                exhibit.processed = True
                exhibit.extraction_quality = 'good'
            except Exception as e:
                print(f"Failed to fetch exhibit {exhibit.filename}: {e}")
                exhibit.extraction_quality = 'failed'

        return exhibit

    except Exception as e:
        print(f"Error creating exhibit: {e}")
        return None


def ingest_deal_from_cik(
    cik: str,
    include_related: bool = True,
):
    """
    Ingest all M&A related filings for a company.

    Includes: 8-K, S-4, DEFM14A, SC 14D9, SC TO-T
    """
    form_types = [
        '8-K', '8-K/A',
        'S-4', 'S-4/A',
        'DEFM14A', 'DEFA14A',
        'SC 14D9', 'SC 14D9/A',
        'SC TO-T', 'SC TO-T/A',
    ]

    ingest_company_filings(
        cik=cik,
        form_types=form_types,
    )
