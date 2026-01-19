"""
Atomic Fact models for evidence-backed extractions.

Key rule: Document processing emits Atomic Facts only.
It must NOT attempt to create Deals.
"""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class FactType(str, Enum):
    """Types of atomic facts that can be extracted."""
    PARTY_MENTION = "PARTY_MENTION"
    PARTY_DEFINITION = "PARTY_DEFINITION"
    SPONSOR_MENTION = "SPONSOR_MENTION"
    DEAL_DATE = "DEAL_DATE"
    FINANCING_MENTION = "FINANCING_MENTION"
    ADVISOR_MENTION = "ADVISOR_MENTION"
    DEAL_VALUE = "DEAL_VALUE"
    MANUAL = "MANUAL"


class AtomicFact(Base):
    """
    Base atomic fact with evidence.

    All facts must have evidence (citation/snippet/coordinates).
    deal_id is NULL until the Deal Clusterer assigns it.
    """
    __tablename__ = "atomic_facts"

    id = Column(Integer, primary_key=True, index=True)
    fact_type = Column(SQLEnum(FactType), nullable=False, index=True)

    # Source document
    filing_id = Column(Integer, ForeignKey("filings.id"))
    exhibit_id = Column(Integer, ForeignKey("exhibits.id"))

    # Deal linkage (NULL until clustered)
    deal_id = Column(Integer, ForeignKey("deals.id"), index=True)

    # Evidence (CRITICAL: required for all facts)
    evidence_snippet = Column(Text, nullable=False)
    evidence_start_offset = Column(Integer)
    evidence_end_offset = Column(Integer)
    source_section = Column(String(100))  # "preamble", "background_of_merger", etc.

    # Extraction metadata
    extraction_method = Column(String(50))  # "regex", "table", "manual"
    extraction_pattern = Column(String(100))  # Which pattern matched
    confidence = Column(Float)

    # Fact-specific payload (polymorphic data)
    payload = Column(JSONB, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    filing = relationship("Filing", back_populates="atomic_facts")
    exhibit = relationship("Exhibit", back_populates="atomic_facts")
    deal = relationship("Deal", back_populates="atomic_facts")

    __table_args__ = (
        Index("ix_atomic_facts_deal_type", "deal_id", "fact_type"),
        Index("ix_atomic_facts_filing_type", "filing_id", "fact_type"),
        Index("ix_atomic_facts_unclustered", "deal_id", "fact_type",
              postgresql_where=("deal_id IS NULL")),
    )


# Type-specific fact helper classes (for payload structure documentation)
class PartyDefinitionFact:
    """
    Payload structure for PARTY_DEFINITION facts.

    Extracted from EX-2.1 preambles and 8-K Item 1.01.
    """
    @staticmethod
    def create_payload(
        party_name_raw: str,
        party_name_normalized: str,
        party_name_display: str,
        role_label: str,  # Company, Parent, Merger Sub, Purchaser, Buyer
        cik: str = None,
    ) -> dict:
        return {
            "party_name_raw": party_name_raw,
            "party_name_normalized": party_name_normalized,
            "party_name_display": party_name_display,
            "role_label": role_label,
            "cik": cik,
        }


class SponsorMentionFact:
    """
    Payload structure for SPONSOR_MENTION facts.

    Extracted from Background of Merger, press releases, equity commitment letters.
    """
    @staticmethod
    def create_payload(
        sponsor_name_raw: str,
        sponsor_name_normalized: str,
        source_pattern: str,  # "seed_list", "affiliation_pattern"
        context_snippet: str,
        is_negated: bool = False,
    ) -> dict:
        return {
            "sponsor_name_raw": sponsor_name_raw,
            "sponsor_name_normalized": sponsor_name_normalized,
            "source_pattern": source_pattern,
            "context_snippet": context_snippet,
            "is_negated": is_negated,
        }


class DealDateFact:
    """Payload structure for DEAL_DATE facts."""
    @staticmethod
    def create_payload(
        date_type: str,  # "agreement_date", "announcement_date", "expected_close"
        date_value: str,  # ISO 8601 format
        date_raw: str,  # Original text
    ) -> dict:
        return {
            "date_type": date_type,
            "date_value": date_value,
            "date_raw": date_raw,
        }


class FinancingMentionFact:
    """
    Payload structure for FINANCING_MENTION facts.

    Extracted from credit agreements, commitment letters, underwriting agreements.
    """
    @staticmethod
    def create_payload(
        instrument_type: str,  # bond, term_loan, rcf, bridge
        instrument_subtype: str = None,  # TLB, TLA, etc.
        amount_usd: float = None,
        amount_raw: str = None,
        currency: str = "USD",
        participants: list = None,  # [{bank, role, evidence}]
        purpose: str = None,  # acquisition_financing, refinancing
        maturity: str = None,
        interest_rate: str = None,
    ) -> dict:
        return {
            "instrument_type": instrument_type,
            "instrument_subtype": instrument_subtype,
            "amount_usd": amount_usd,
            "amount_raw": amount_raw,
            "currency": currency,
            "participants": participants or [],
            "purpose": purpose,
            "maturity": maturity,
            "interest_rate": interest_rate,
        }


class AdvisorMentionFact:
    """
    Payload structure for ADVISOR_MENTION facts.

    Extracted from Background of Merger, fairness opinions, press releases.
    """
    @staticmethod
    def create_payload(
        bank_name_raw: str,
        bank_name_normalized: str,
        role: str,  # "lead_advisor", "co_advisor", "fairness_opinion"
        client_side: str,  # "target", "acquirer"
        bank_id: int = None,
    ) -> dict:
        return {
            "bank_name_raw": bank_name_raw,
            "bank_name_normalized": bank_name_normalized,
            "role": role,
            "client_side": client_side,
            "bank_id": bank_id,
        }
