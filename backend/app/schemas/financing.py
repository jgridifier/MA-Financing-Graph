"""Pydantic schemas for Financing API."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class FinancingParticipantResponse(BaseModel):
    """Schema for financing participant response."""
    id: int
    bank_name_raw: str
    bank_name_normalized: Optional[str] = None
    role: str
    role_normalized: Optional[str] = None
    evidence_snippet: Optional[str] = None
    estimated_fee_usd: Optional[float] = None

    class Config:
        from_attributes = True


class FinancingEventBase(BaseModel):
    """Base financing event schema."""
    instrument_family: str
    instrument_type: Optional[str] = None
    market_tag: Optional[str] = None
    amount_usd: Optional[float] = None
    amount_raw: Optional[str] = None
    purpose: Optional[str] = None


class FinancingEventResponse(FinancingEventBase):
    """Schema for financing event response."""
    id: int
    deal_id: int
    currency: str = "USD"
    reconciliation_confidence: Optional[float] = None
    reconciliation_explanation: Optional[str] = None
    estimated_fee_usd: Optional[float] = None
    participants: list[FinancingParticipantResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class AdvisorResponse(BaseModel):
    """Schema for advisor response."""
    bank_name_raw: str
    bank_name_normalized: Optional[str] = None
    role: str
    client_side: str
    evidence_snippet: Optional[str] = None

    class Config:
        from_attributes = True
