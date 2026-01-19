"""Filing and Exhibit models for SEC EDGAR documents."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship

from app.db.base import Base


class Filing(Base):
    """Represents an SEC EDGAR filing."""
    __tablename__ = "filings"

    id = Column(Integer, primary_key=True, index=True)
    accession_number = Column(String(25), unique=True, nullable=False, index=True)
    cik = Column(String(10), nullable=False, index=True)
    form_type = Column(String(20), nullable=False, index=True)
    filing_date = Column(DateTime, nullable=False)

    # Company info from EDGAR
    company_name = Column(String(255))

    # URLs
    filing_url = Column(String(500))
    index_url = Column(String(500))

    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)

    # Raw content cache
    raw_html = Column(Text)
    visual_text = Column(Text)  # Normalized visual text buffer

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    exhibits = relationship("Exhibit", back_populates="filing", cascade="all, delete-orphan")
    atomic_facts = relationship("AtomicFact", back_populates="filing", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_filings_cik_form_type", "cik", "form_type"),
        Index("ix_filings_filing_date", "filing_date"),
    )


class Exhibit(Base):
    """Represents an exhibit attached to a filing."""
    __tablename__ = "exhibits"

    id = Column(Integer, primary_key=True, index=True)
    filing_id = Column(Integer, ForeignKey("filings.id"), nullable=False)

    exhibit_type = Column(String(50), nullable=False)  # EX-2.1, EX-10.1, etc.
    description = Column(String(500))
    filename = Column(String(255))
    url = Column(String(500))

    # Content type
    is_pdf = Column(Boolean, default=False)
    is_material = Column(Boolean, default=False)  # Credit Agreement, Commitment Letter, etc.

    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    extraction_quality = Column(String(20))  # good, poor, failed

    # Cached content
    raw_content = Column(Text)
    visual_text = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    filing = relationship("Filing", back_populates="exhibits")
    atomic_facts = relationship("AtomicFact", back_populates="exhibit", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_exhibits_filing_exhibit_type", "filing_id", "exhibit_type"),
    )
