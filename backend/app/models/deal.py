"""Deal model with sponsor and private target support."""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class DealState(str, Enum):
    """Deal lifecycle states."""
    CANDIDATE = "CANDIDATE"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Deal(Base):
    """
    Represents an M&A deal.

    Key requirements:
    - Deal keys support private targets via target_name_normalized
    - Sponsor is stored separately from acquirer (not a signatory)
    - All assertions must have evidence backing
    """
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)

    # State management
    state = Column(SQLEnum(DealState), default=DealState.CANDIDATE, nullable=False)

    # Acquirer info
    acquirer_cik = Column(String(10), index=True)
    acquirer_name_raw = Column(String(500))
    acquirer_name_display = Column(String(255))
    acquirer_name_normalized = Column(String(255), index=True)

    # Target info - supports both CIK and private targets
    target_cik = Column(String(10), index=True)
    target_name_raw = Column(String(500))
    target_name_display = Column(String(255))
    target_name_normalized = Column(String(255), index=True)

    # Deal key for clustering (computed)
    deal_key = Column(String(500), unique=True, index=True)

    # Deal timeline
    announcement_date = Column(DateTime)
    agreement_date = Column(DateTime)
    expected_close_date = Column(DateTime)
    actual_close_date = Column(DateTime)

    # Deal value
    deal_value_usd = Column(Float)
    deal_value_evidence = Column(Text)

    # Sponsor info (CRITICAL: separate from acquirer)
    is_sponsor_backed = Column(Boolean)  # true/false/null (unknown)
    sponsor_name_raw = Column(String(500))
    sponsor_name_normalized = Column(String(255), index=True)
    sponsor_confidence = Column(Float)
    sponsor_evidence = Column(JSONB)  # {doc_id, snippet, pattern_matched}
    sponsor_entity_id = Column(Integer)  # FK to resolved entity if applicable
    unresolved_sponsor_entity = Column(Boolean, default=False)

    # Classification tags
    market_tag = Column(String(50))  # IG_Bond, HY_Bond, Term_Loan_B, etc.
    is_cross_border = Column(Boolean, default=False)

    # Attribution
    advisory_fee_estimated = Column(Float)
    underwriting_fee_estimated = Column(Float)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    atomic_facts = relationship("AtomicFact", back_populates="deal")
    financing_events = relationship("FinancingEvent", back_populates="deal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_deals_acquirer_target_cik", "acquirer_cik", "target_cik"),
        Index("ix_deals_acquirer_target_name", "acquirer_cik", "target_name_normalized"),
        Index("ix_deals_state", "state"),
    )

    def compute_deal_key(self) -> str:
        """
        Compute stable clustering key.

        Priority:
        1. (acquirer_cik, target_cik)
        2. (acquirer_cik, target_name_normalized)
        3. (acquirer_name_normalized, target_name_normalized) - flag NEEDS_REVIEW
        """
        if self.acquirer_cik and self.target_cik:
            return f"cik:{self.acquirer_cik}:cik:{self.target_cik}"
        elif self.acquirer_cik and self.target_name_normalized:
            return f"cik:{self.acquirer_cik}:name:{self.target_name_normalized}"
        elif self.acquirer_name_normalized and self.target_name_normalized:
            self.state = DealState.NEEDS_REVIEW
            return f"name:{self.acquirer_name_normalized}:name:{self.target_name_normalized}"
        return None
