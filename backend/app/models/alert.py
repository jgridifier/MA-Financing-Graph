"""Processing alerts for human-in-the-loop workflow."""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class AlertType(str, Enum):
    """Types of processing alerts requiring human review."""
    UNPARSED_MATERIAL_EXHIBIT = "UNPARSED_MATERIAL_EXHIBIT"
    FAILED_PRIVATE_TARGET_EXTRACTION = "FAILED_PRIVATE_TARGET_EXTRACTION"
    FAILED_SPONSOR_EXTRACTION = "FAILED_SPONSOR_EXTRACTION"
    LOW_CONFIDENCE_MATCH = "LOW_CONFIDENCE_MATCH"
    DEAL_MERGE_CANDIDATE = "DEAL_MERGE_CANDIDATE"
    UNRESOLVED_BANK = "UNRESOLVED_BANK"


class ProcessingAlert(Base):
    """
    Alert for human review when automated processing fails or has low confidence.

    Required for:
    - Material PDF exhibits that fail parsing (credit agreements, commitment letters)
    - Failed private target extraction from EX-2.1 preambles
    - Low confidence reconciliation matches
    """
    __tablename__ = "processing_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(SQLEnum(AlertType), nullable=False, index=True)

    # Source references
    filing_id = Column(Integer, ForeignKey("filings.id"))
    exhibit_id = Column(Integer, ForeignKey("exhibits.id"))
    deal_id = Column(Integer, ForeignKey("deals.id"))

    # Alert details
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # For UNPARSED_MATERIAL_EXHIBIT
    exhibit_link = Column(String(500))
    fields_needed = Column(JSONB)  # ["facility_type", "amount", "participants", "roles", "purpose"]

    # For FAILED_PRIVATE_TARGET_EXTRACTION
    preamble_hash = Column(String(64))
    preamble_preview = Column(Text)  # First N chars sanitized

    # Status
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolved_by = Column(String(100))
    resolution_notes = Column(Text)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_processing_alerts_unresolved", "alert_type", "is_resolved",
              postgresql_where=("is_resolved = false")),
    )
