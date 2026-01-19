"""Filing API routes."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.filing import Filing, Exhibit
from app.schemas.filing import (
    FilingResponse, FilingWithExhibits, IngestRequest
)

router = APIRouter(prefix="/filings", tags=["filings"])


@router.get("", response_model=list[FilingResponse])
def list_filings(
    cik: Optional[str] = None,
    form_type: Optional[str] = None,
    processed: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List filings with optional filtering.

    - **cik**: Filter by company CIK
    - **form_type**: Filter by form type (8-K, S-4, etc.)
    - **processed**: Filter by processing status
    """
    q = db.query(Filing)

    if cik:
        q = q.filter(Filing.cik == cik)
    if form_type:
        q = q.filter(Filing.form_type == form_type)
    if processed is not None:
        q = q.filter(Filing.processed == processed)

    q = q.order_by(Filing.filing_date.desc())
    filings = q.offset(offset).limit(limit).all()

    return filings


@router.get("/{filing_id}", response_model=FilingWithExhibits)
def get_filing(filing_id: int, db: Session = Depends(get_db)):
    """Get filing by ID with exhibits."""
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")

    return filing


@router.get("/{filing_id}/exhibits")
def get_filing_exhibits(filing_id: int, db: Session = Depends(get_db)):
    """Get exhibits for a filing."""
    filing = db.query(Filing).filter(Filing.id == filing_id).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")

    return filing.exhibits


@router.post("/ingest")
async def ingest_filings(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Ingest filings for a company.

    Triggers background job to:
    1. Fetch filing list from EDGAR
    2. Download and parse documents
    3. Extract atomic facts
    """
    from app.workers.ingest import ingest_company_filings

    # Queue background task
    background_tasks.add_task(
        ingest_company_filings,
        cik=request.cik,
        form_types=request.form_types,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    return {
        "status": "queued",
        "message": f"Ingestion started for CIK {request.cik}",
        "form_types": request.form_types,
    }


@router.get("/by-accession/{accession_number}", response_model=FilingResponse)
def get_filing_by_accession(
    accession_number: str,
    db: Session = Depends(get_db)
):
    """Get filing by accession number."""
    filing = db.query(Filing).filter(
        Filing.accession_number == accession_number
    ).first()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")

    return filing


@router.get("/stats/summary")
def get_filing_stats(db: Session = Depends(get_db)):
    """Get summary statistics for filings."""
    total = db.query(Filing).count()
    processed = db.query(Filing).filter(Filing.processed == True).count()
    by_form = {}

    for form_type in ['8-K', 'S-4', 'DEFM14A', '8-K/A']:
        count = db.query(Filing).filter(Filing.form_type == form_type).count()
        if count > 0:
            by_form[form_type] = count

    exhibits = db.query(Exhibit).count()
    material_exhibits = db.query(Exhibit).filter(Exhibit.is_material == True).count()

    return {
        "total_filings": total,
        "processed": processed,
        "unprocessed": total - processed,
        "by_form_type": by_form,
        "total_exhibits": exhibits,
        "material_exhibits": material_exhibits,
    }
