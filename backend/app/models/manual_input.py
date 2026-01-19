"""Manual input model for human-in-the-loop data entry."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class ManualInput(Base):
    """
    Stores manually entered data from human review.

    Manual inputs are treated as MANUAL facts and feed into:
    - Reconciler
    - Classifier
    - Attribution Engine

    All manual inputs have audit metadata.
    """
    __tablename__ = "manual_inputs"

    id = Column(Integer, primary_key=True, index=True)

    # Link to alert that triggered this input
    alert_id = Column(Integer, ForeignKey("processing_alerts.id"))

    # Target entity
    deal_id = Column(Integer, ForeignKey("deals.id"))
    financing_event_id = Column(Integer, ForeignKey("financing_events.id"))

    # Input data (flexible schema)
    input_type = Column(String(50), nullable=False)  # "financing", "participant", "target_name", etc.
    data = Column(JSONB, nullable=False)

    # Audit metadata (REQUIRED)
    entered_by = Column(String(100), nullable=False)
    entered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notes = Column(Text)

    # Verification
    verified = Column(DateTime)
    verified_by = Column(String(100))

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
