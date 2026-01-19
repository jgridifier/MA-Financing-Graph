"""Deal API routes."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.base import get_db
from app.models.deal import Deal, DealState
from app.models.atomic_fact import AtomicFact, FactType
from app.models.financing import FinancingEvent
from app.schemas.deal import (
    DealResponse, DealSummary, DealSearchParams
)
from app.schemas.financing import FinancingEventResponse, AdvisorResponse

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=list[DealSummary])
def list_deals(
    query: Optional[str] = None,
    is_sponsor_backed: Optional[bool] = None,
    market_tag: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List deals with optional filtering.

    - **query**: Search in target/acquirer names
    - **is_sponsor_backed**: Filter by sponsor status
    - **market_tag**: Filter by market classification
    - **state**: Filter by deal state
    """
    q = db.query(Deal)

    if query:
        search_term = f"%{query.lower()}%"
        q = q.filter(
            or_(
                Deal.target_name_normalized.ilike(search_term),
                Deal.acquirer_name_normalized.ilike(search_term),
                Deal.target_name_display.ilike(search_term),
                Deal.acquirer_name_display.ilike(search_term),
            )
        )

    if is_sponsor_backed is not None:
        q = q.filter(Deal.is_sponsor_backed == is_sponsor_backed)

    if market_tag:
        q = q.filter(Deal.market_tag == market_tag)

    if state:
        q = q.filter(Deal.state == state)

    q = q.order_by(Deal.announcement_date.desc().nullslast())
    deals = q.offset(offset).limit(limit).all()

    return deals


@router.get("/{deal_id}", response_model=DealResponse)
def get_deal(deal_id: int, db: Session = Depends(get_db)):
    """Get deal by ID."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Add sponsor display name
    response = DealResponse.model_validate(deal)
    if deal.sponsor_name_raw:
        response.sponsor_name_display = deal.sponsor_name_raw

    return response


@router.get("/{deal_id}/financing", response_model=list[FinancingEventResponse])
def get_deal_financing(deal_id: int, db: Session = Depends(get_db)):
    """Get financing events for a deal."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    events = db.query(FinancingEvent).filter(
        FinancingEvent.deal_id == deal_id
    ).all()

    return events


@router.get("/{deal_id}/advisors", response_model=list[AdvisorResponse])
def get_deal_advisors(deal_id: int, db: Session = Depends(get_db)):
    """Get financial advisors for a deal."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Get advisor facts
    advisor_facts = db.query(AtomicFact).filter(
        AtomicFact.deal_id == deal_id,
        AtomicFact.fact_type == FactType.ADVISOR_MENTION,
    ).all()

    advisors = []
    for fact in advisor_facts:
        payload = fact.payload or {}
        advisors.append(AdvisorResponse(
            bank_name_raw=payload.get('bank_name_raw', ''),
            bank_name_normalized=payload.get('bank_name_normalized'),
            role=payload.get('role', 'unknown'),
            client_side=payload.get('client_side', 'unknown'),
            evidence_snippet=fact.evidence_snippet,
        ))

    return advisors


@router.get("/{deal_id}/facts")
def get_deal_facts(deal_id: int, db: Session = Depends(get_db)):
    """Get all atomic facts for a deal with evidence."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    facts = db.query(AtomicFact).filter(
        AtomicFact.deal_id == deal_id
    ).all()

    return [
        {
            "id": f.id,
            "fact_type": f.fact_type.value,
            "evidence_snippet": f.evidence_snippet,
            "source_section": f.source_section,
            "confidence": f.confidence,
            "payload": f.payload,
        }
        for f in facts
    ]


@router.get("/stats/summary")
def get_deal_stats(db: Session = Depends(get_db)):
    """Get summary statistics for deals."""
    total = db.query(Deal).count()
    by_state = {}
    for state in DealState:
        count = db.query(Deal).filter(Deal.state == state).count()
        by_state[state.value] = count

    sponsor_backed = db.query(Deal).filter(Deal.is_sponsor_backed == True).count()
    with_financing = db.query(Deal).join(FinancingEvent).distinct().count()

    return {
        "total_deals": total,
        "by_state": by_state,
        "sponsor_backed": sponsor_backed,
        "with_financing": with_financing,
    }
