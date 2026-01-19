"""Financing Event models for debt instruments and syndicates."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class FinancingEvent(Base):
    """
    Represents a financing event (loan, bond, bridge) linked to a deal.

    Created by Reconciler after linking financing facts to deals.
    """
    __tablename__ = "financing_events"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False, index=True)

    # Instrument classification
    instrument_family = Column(String(50), nullable=False)  # bond, loan, bridge
    instrument_type = Column(String(50))  # term_loan_b, rcf, hy_bond, ig_bond
    market_tag = Column(String(50))  # HY_Bond, IG_Bond, Term_Loan_B, etc.

    # Amounts
    amount_usd = Column(Float)
    amount_raw = Column(String(100))
    currency = Column(String(10), default="USD")

    # Terms
    maturity_date = Column(DateTime)
    interest_rate = Column(String(100))
    spread_bps = Column(Integer)

    # Purpose
    purpose = Column(String(100))  # acquisition_financing, bridge_to_bond, refinancing

    # Reconciliation metadata
    reconciliation_confidence = Column(Float)
    reconciliation_explanation = Column(Text)

    # Evidence pointers
    source_exhibit_id = Column(Integer, ForeignKey("exhibits.id"))
    source_fact_ids = Column(JSONB)  # List of atomic fact IDs

    # Attribution
    estimated_fee_usd = Column(Float)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    deal = relationship("Deal", back_populates="financing_events")
    participants = relationship("FinancingParticipant", back_populates="financing_event", cascade="all, delete-orphan")
    source_exhibit = relationship("Exhibit")

    __table_args__ = (
        Index("ix_financing_events_deal_type", "deal_id", "instrument_family"),
    )


class FinancingParticipant(Base):
    """
    Represents a bank's role in a financing event.

    Examples: bookrunner, lead arranger, admin agent
    """
    __tablename__ = "financing_participants"

    id = Column(Integer, primary_key=True, index=True)
    financing_event_id = Column(Integer, ForeignKey("financing_events.id"), nullable=False)
    bank_id = Column(Integer, ForeignKey("banks.id"))

    # Bank identification
    bank_name_raw = Column(String(255), nullable=False)
    bank_name_normalized = Column(String(255))

    # Role
    role = Column(String(100), nullable=False)  # joint_bookrunner, lead_arranger, etc.
    role_normalized = Column(String(50))  # Canonical role for fee splits

    # Evidence
    evidence_snippet = Column(Text)
    evidence_source = Column(String(50))  # "table", "text", "manual"
    table_cell_coords = Column(JSONB)  # {row, col} if from table

    # Attribution
    role_weight = Column(Float)  # From config role_splits
    estimated_fee_usd = Column(Float)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    financing_event = relationship("FinancingEvent", back_populates="participants")
    bank = relationship("Bank")

    __table_args__ = (
        Index("ix_financing_participants_bank", "bank_id"),
        Index("ix_financing_participants_event_role", "financing_event_id", "role"),
    )
