"""Pydantic schemas for Filing API."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class FilingBase(BaseModel):
    """Base filing schema."""
    accession_number: str
    cik: str
    form_type: str
    filing_date: datetime
    company_name: Optional[str] = None


class FilingCreate(FilingBase):
    """Schema for creating a filing."""
    filing_url: Optional[str] = None
    index_url: Optional[str] = None


class FilingResponse(FilingBase):
    """Schema for filing response."""
    id: int
    filing_url: Optional[str] = None
    processed: bool
    processed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExhibitResponse(BaseModel):
    """Schema for exhibit response."""
    id: int
    exhibit_type: str
    description: Optional[str] = None
    filename: Optional[str] = None
    url: Optional[str] = None
    is_pdf: bool
    is_material: bool
    processed: bool
    extraction_quality: Optional[str] = None

    class Config:
        from_attributes = True


class FilingWithExhibits(FilingResponse):
    """Filing with its exhibits."""
    exhibits: list[ExhibitResponse] = []


class IngestRequest(BaseModel):
    """Request to ingest filings for a company."""
    cik: str
    form_types: list[str] = ["8-K", "S-4", "DEFM14A"]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
