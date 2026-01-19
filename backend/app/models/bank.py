"""Bank entity with alias resolution."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Index, ForeignKey
from sqlalchemy.orm import relationship

from app.db.base import Base


class Bank(Base):
    """
    Canonical bank entity for normalization and attribution.

    Banks are resolved via exact match, alias lookup, or fuzzy matching.
    """
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, index=True)

    # Canonical name
    name = Column(String(255), unique=True, nullable=False)
    name_normalized = Column(String(255), index=True)

    # Display name
    display_name = Column(String(255))
    short_name = Column(String(100))

    # Classification
    is_bulge_bracket = Column(Boolean, default=False)
    is_regional = Column(Boolean, default=False)
    primary_market = Column(String(50))  # US, EU, APAC

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    aliases = relationship("BankAlias", back_populates="bank", cascade="all, delete-orphan")


class BankAlias(Base):
    """
    Alias mapping for bank name resolution.

    Examples:
    - "JPMorgan" -> "JPMorgan Chase & Co."
    - "J.P. Morgan" -> "JPMorgan Chase & Co."
    - "JPMC" -> "JPMorgan Chase & Co."
    """
    __tablename__ = "bank_aliases"

    id = Column(Integer, primary_key=True, index=True)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)

    alias = Column(String(255), unique=True, nullable=False, index=True)
    alias_normalized = Column(String(255), index=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    bank = relationship("Bank", back_populates="aliases")

    __table_args__ = (
        Index("ix_bank_aliases_normalized", "alias_normalized"),
    )
