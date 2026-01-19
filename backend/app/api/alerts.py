"""Alert API routes for human-in-the-loop workflow."""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.alert import ProcessingAlert, AlertType
from app.models.manual_input import ManualInput

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertResponse(BaseModel):
    """Schema for alert response."""
    id: int
    alert_type: str
    title: str
    description: Optional[str] = None
    filing_id: Optional[int] = None
    exhibit_id: Optional[int] = None
    deal_id: Optional[int] = None
    exhibit_link: Optional[str] = None
    fields_needed: Optional[list] = None
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ResolveAlertRequest(BaseModel):
    """Request to resolve an alert."""
    resolved_by: str
    resolution_notes: Optional[str] = None


class ManualInputRequest(BaseModel):
    """Request to submit manual input for an alert."""
    input_type: str
    data: dict
    entered_by: str
    notes: Optional[str] = None


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    alert_type: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List processing alerts.

    - **alert_type**: Filter by alert type
    - **is_resolved**: Filter by resolution status
    """
    q = db.query(ProcessingAlert)

    if alert_type:
        try:
            at = AlertType(alert_type)
            q = q.filter(ProcessingAlert.alert_type == at)
        except ValueError:
            pass

    if is_resolved is not None:
        q = q.filter(ProcessingAlert.is_resolved == is_resolved)

    q = q.order_by(ProcessingAlert.created_at.desc())
    alerts = q.offset(offset).limit(limit).all()

    return alerts


@router.get("/unresolved", response_model=list[AlertResponse])
def list_unresolved_alerts(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List unresolved alerts requiring human review."""
    alerts = db.query(ProcessingAlert).filter(
        ProcessingAlert.is_resolved == False
    ).order_by(ProcessingAlert.created_at.desc()).limit(limit).all()

    return alerts


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """Get alert by ID."""
    alert = db.query(ProcessingAlert).filter(
        ProcessingAlert.id == alert_id
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return alert


@router.post("/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    request: ResolveAlertRequest,
    db: Session = Depends(get_db),
):
    """Mark an alert as resolved."""
    alert = db.query(ProcessingAlert).filter(
        ProcessingAlert.id == alert_id
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = request.resolved_by
    alert.resolution_notes = request.resolution_notes
    db.commit()

    return {"status": "resolved", "alert_id": alert_id}


@router.post("/{alert_id}/manual-input")
def submit_manual_input(
    alert_id: int,
    request: ManualInputRequest,
    db: Session = Depends(get_db),
):
    """
    Submit manual input for an alert.

    Creates a MANUAL fact and links it to the alert's deal/financing event.
    """
    alert = db.query(ProcessingAlert).filter(
        ProcessingAlert.id == alert_id
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Create manual input record
    manual_input = ManualInput(
        alert_id=alert_id,
        deal_id=alert.deal_id,
        input_type=request.input_type,
        data=request.data,
        entered_by=request.entered_by,
        notes=request.notes,
        entered_at=datetime.utcnow(),
    )
    db.add(manual_input)

    # Mark alert as resolved
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = request.entered_by

    db.commit()

    return {
        "status": "submitted",
        "manual_input_id": manual_input.id,
        "alert_id": alert_id,
    }


@router.get("/stats/summary")
def get_alert_stats(db: Session = Depends(get_db)):
    """Get summary statistics for alerts."""
    total = db.query(ProcessingAlert).count()
    unresolved = db.query(ProcessingAlert).filter(
        ProcessingAlert.is_resolved == False
    ).count()

    by_type = {}
    for alert_type in AlertType:
        count = db.query(ProcessingAlert).filter(
            ProcessingAlert.alert_type == alert_type,
            ProcessingAlert.is_resolved == False,
        ).count()
        if count > 0:
            by_type[alert_type.value] = count

    return {
        "total_alerts": total,
        "unresolved": unresolved,
        "resolved": total - unresolved,
        "unresolved_by_type": by_type,
    }
