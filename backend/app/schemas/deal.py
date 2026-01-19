"""Pydantic schemas for Deal API."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class DealBase(BaseModel):
    """Base deal schema."""
    acquirer_name_display: Optional[str] = None
    target_name_display: Optional[str] = None
    announcement_date: Optional[datetime] = None
    deal_value_usd: Optional[float] = None
    is_sponsor_backed: Optional[bool] = None
    market_tag: Optional[str] = None


class DealCreate(DealBase):
    """Schema for creating a deal."""
    acquirer_cik: Optional[str] = None
    target_cik: Optional[str] = None
    acquirer_name_raw: Optional[str] = None
    target_name_raw: Optional[str] = None


class DealResponse(DealBase):
    """Schema for deal response."""
    id: int
    state: str
    acquirer_cik: Optional[str] = None
    target_cik: Optional[str] = None
    deal_key: Optional[str] = None
    agreement_date: Optional[datetime] = None
    sponsor_name_display: Optional[str] = None
    sponsor_confidence: Optional[float] = None
    advisory_fee_estimated: Optional[float] = None
    underwriting_fee_estimated: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DealSummary(BaseModel):
    """Summary schema for deal lists."""
    id: int
    acquirer_name_display: Optional[str] = None
    target_name_display: Optional[str] = None
    announcement_date: Optional[datetime] = None
    deal_value_usd: Optional[float] = None
    is_sponsor_backed: Optional[bool] = None
    market_tag: Optional[str] = None
    state: str

    class Config:
        from_attributes = True


class DealSearchParams(BaseModel):
    """Search parameters for deals."""
    query: Optional[str] = None
    is_sponsor_backed: Optional[bool] = None
    market_tag: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    state: Optional[str] = None
    limit: int = 50
    offset: int = 0
