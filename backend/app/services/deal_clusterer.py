"""
Deal Clustering Service.

Responsibilities (per spec Section 4):
- Creates/updates Deals by clustering atomic facts
- Uses stable deal keys for clustering
- Supports merging CandidateDeals
- Manages deal lifecycle states

Mental model: "I group facts into deals and assign deal_id."
"""
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models.deal import Deal, DealState
from app.models.atomic_fact import AtomicFact, FactType
from app.models.alert import ProcessingAlert, AlertType


class DealClusteringService:
    """
    Stateful service for clustering atomic facts into deals.

    Deal Key Construction Rules:
    1. Preferred: (acquirer_cik, target_cik)
    2. If target_cik missing: (acquirer_cik, target_name_normalized)
    3. If acquirer_cik missing: (acquirer_name_normalized, target_name_normalized) + NEEDS_REVIEW

    Lifecycle:
    - CANDIDATE: New deal from clustering
    - OPEN: Confirmed deal in progress
    - CLOSED: Deal completed
    - LOCKED: Archived deal (no more updates)
    - NEEDS_REVIEW: Requires manual review
    """

    def __init__(self, db: Session):
        self.db = db

    def cluster_unclustered_facts(self) -> dict:
        """
        Main clustering entry point.

        Scans atomic_fact where deal_id IS NULL and:
        - Attaches to existing deals by key matching
        - Creates CandidateDeals when no match exists
        - Flags manual review when match exists but deal is locked

        Returns:
            Statistics dict with counts
        """
        stats = {
            'facts_processed': 0,
            'facts_attached': 0,
            'deals_created': 0,
            'alerts_created': 0,
        }

        # Get unclustered party definition facts (most important for deal creation)
        unclustered = self.db.query(AtomicFact).filter(
            AtomicFact.deal_id.is_(None),
            AtomicFact.fact_type.in_([
                FactType.PARTY_DEFINITION,
                FactType.PARTY_MENTION,
            ])
        ).all()

        for fact in unclustered:
            result = self._cluster_fact(fact)
            stats['facts_processed'] += 1
            if result.get('attached'):
                stats['facts_attached'] += 1
            if result.get('deal_created'):
                stats['deals_created'] += 1
            if result.get('alert_created'):
                stats['alerts_created'] += 1

        self.db.commit()

        # Now attach other fact types (sponsor, date, etc.) to their filing's deals
        self._attach_secondary_facts()

        return stats

    def _cluster_fact(self, fact: AtomicFact) -> dict:
        """
        Cluster a single fact into a deal.

        Returns:
            Dict with processing result
        """
        result = {
            'attached': False,
            'deal_created': False,
            'alert_created': False,
        }

        payload = fact.payload or {}
        role_label = payload.get('role_label', '').lower()
        party_normalized = payload.get('party_name_normalized', '')

        if not party_normalized:
            return result

        # Determine if this is target or acquirer
        if role_label in ('company', 'target', 'seller'):
            return self._handle_target_fact(fact, payload)
        elif role_label in ('parent', 'buyer', 'purchaser', 'acquirer', 'acquiror'):
            return self._handle_acquirer_fact(fact, payload)
        else:
            # Unknown role - can't cluster without more context
            return result

    def _handle_target_fact(self, fact: AtomicFact, payload: dict) -> dict:
        """Handle a target party fact."""
        result = {'attached': False, 'deal_created': False, 'alert_created': False}

        target_normalized = payload.get('party_name_normalized', '')
        target_cik = payload.get('cik')

        # Find associated acquirer facts from same filing/exhibit
        acquirer_facts = self._find_related_party_facts(
            fact, ['parent', 'buyer', 'purchaser', 'acquirer', 'acquiror']
        )

        if not acquirer_facts:
            # No acquirer found yet - can't create deal
            return result

        # Use first acquirer fact
        acquirer_payload = acquirer_facts[0].payload or {}
        acquirer_normalized = acquirer_payload.get('party_name_normalized', '')
        acquirer_cik = acquirer_payload.get('cik')

        # Build deal key
        deal_key = self._build_deal_key(
            acquirer_cik=acquirer_cik,
            acquirer_name=acquirer_normalized,
            target_cik=target_cik,
            target_name=target_normalized,
        )

        if not deal_key:
            return result

        # Try to find existing deal
        existing = self.db.query(Deal).filter(Deal.deal_key == deal_key).first()

        if existing:
            if existing.state == DealState.LOCKED:
                # Create alert for review
                alert = ProcessingAlert(
                    alert_type=AlertType.LOW_CONFIDENCE_MATCH,
                    deal_id=existing.id,
                    filing_id=fact.filing_id,
                    title=f"New fact for locked deal: {target_normalized}",
                    description="Deal is locked but new facts were found",
                )
                self.db.add(alert)
                result['alert_created'] = True
            else:
                # Attach fact to existing deal
                fact.deal_id = existing.id
                result['attached'] = True

                # Also attach the acquirer fact
                for af in acquirer_facts:
                    if af.deal_id is None:
                        af.deal_id = existing.id
        else:
            # Create new candidate deal
            deal = Deal(
                state=DealState.CANDIDATE,
                acquirer_cik=acquirer_cik,
                acquirer_name_normalized=acquirer_normalized,
                acquirer_name_raw=acquirer_payload.get('party_name_raw'),
                acquirer_name_display=acquirer_payload.get('party_name_display'),
                target_cik=target_cik,
                target_name_normalized=target_normalized,
                target_name_raw=payload.get('party_name_raw'),
                target_name_display=payload.get('party_name_display'),
                deal_key=deal_key,
            )

            # Set NEEDS_REVIEW if using name-only key
            if not acquirer_cik:
                deal.state = DealState.NEEDS_REVIEW

            self.db.add(deal)
            self.db.flush()  # Get deal ID

            # Attach facts
            fact.deal_id = deal.id
            for af in acquirer_facts:
                if af.deal_id is None:
                    af.deal_id = deal.id

            result['deal_created'] = True
            result['attached'] = True

        return result

    def _handle_acquirer_fact(self, fact: AtomicFact, payload: dict) -> dict:
        """Handle an acquirer party fact."""
        result = {'attached': False, 'deal_created': False, 'alert_created': False}

        acquirer_normalized = payload.get('party_name_normalized', '')
        acquirer_cik = payload.get('cik')

        # Find associated target facts
        target_facts = self._find_related_party_facts(
            fact, ['company', 'target', 'seller']
        )

        if not target_facts:
            return result

        # Use first target fact
        target_payload = target_facts[0].payload or {}
        target_normalized = target_payload.get('party_name_normalized', '')
        target_cik = target_payload.get('cik')

        # Build deal key
        deal_key = self._build_deal_key(
            acquirer_cik=acquirer_cik,
            acquirer_name=acquirer_normalized,
            target_cik=target_cik,
            target_name=target_normalized,
        )

        if not deal_key:
            return result

        # Try to find existing deal
        existing = self.db.query(Deal).filter(Deal.deal_key == deal_key).first()

        if existing:
            if existing.state != DealState.LOCKED:
                fact.deal_id = existing.id
                result['attached'] = True

                for tf in target_facts:
                    if tf.deal_id is None:
                        tf.deal_id = existing.id
        # Don't create deals from acquirer facts alone - wait for target

        return result

    def _find_related_party_facts(
        self,
        fact: AtomicFact,
        role_labels: list[str]
    ) -> list[AtomicFact]:
        """Find related party facts from same filing/exhibit."""
        query = self.db.query(AtomicFact).filter(
            AtomicFact.fact_type.in_([FactType.PARTY_DEFINITION, FactType.PARTY_MENTION]),
            AtomicFact.id != fact.id,
        )

        # Same exhibit or same filing
        if fact.exhibit_id:
            query = query.filter(AtomicFact.exhibit_id == fact.exhibit_id)
        elif fact.filing_id:
            query = query.filter(AtomicFact.filing_id == fact.filing_id)
        else:
            return []

        facts = query.all()

        # Filter by role label
        matching = []
        for f in facts:
            payload = f.payload or {}
            role = payload.get('role_label', '').lower()
            if role in role_labels:
                matching.append(f)

        return matching

    def _build_deal_key(
        self,
        acquirer_cik: Optional[str],
        acquirer_name: Optional[str],
        target_cik: Optional[str],
        target_name: Optional[str],
    ) -> Optional[str]:
        """
        Build stable deal clustering key.

        Priority:
        1. (acquirer_cik, target_cik)
        2. (acquirer_cik, target_name_normalized)
        3. (acquirer_name_normalized, target_name_normalized)
        """
        if acquirer_cik and target_cik:
            return f"cik:{acquirer_cik}:cik:{target_cik}"
        elif acquirer_cik and target_name:
            return f"cik:{acquirer_cik}:name:{target_name}"
        elif acquirer_name and target_name:
            return f"name:{acquirer_name}:name:{target_name}"
        return None

    def _attach_secondary_facts(self):
        """
        Attach non-party facts (sponsor, date, etc.) to deals.

        These facts are attached based on their filing/exhibit relationship
        to already-clustered party facts.
        """
        # Get unclustered non-party facts
        unclustered = self.db.query(AtomicFact).filter(
            AtomicFact.deal_id.is_(None),
            AtomicFact.fact_type.in_([
                FactType.SPONSOR_MENTION,
                FactType.DEAL_DATE,
                FactType.ADVISOR_MENTION,
                FactType.FINANCING_MENTION,
            ])
        ).all()

        for fact in unclustered:
            deal_id = self._find_deal_for_fact(fact)
            if deal_id:
                fact.deal_id = deal_id

                # Update deal with sponsor info if sponsor fact
                if fact.fact_type == FactType.SPONSOR_MENTION:
                    self._update_deal_sponsor(deal_id, fact)

                # Update deal with date if date fact
                if fact.fact_type == FactType.DEAL_DATE:
                    self._update_deal_date(deal_id, fact)

        self.db.commit()

    def _find_deal_for_fact(self, fact: AtomicFact) -> Optional[int]:
        """Find deal ID for a fact based on filing/exhibit relationship."""
        # Look for party facts in same exhibit/filing that have deal_id
        query = self.db.query(AtomicFact.deal_id).filter(
            AtomicFact.deal_id.isnot(None),
            AtomicFact.fact_type.in_([FactType.PARTY_DEFINITION, FactType.PARTY_MENTION]),
        )

        if fact.exhibit_id:
            query = query.filter(AtomicFact.exhibit_id == fact.exhibit_id)
        elif fact.filing_id:
            query = query.filter(AtomicFact.filing_id == fact.filing_id)
        else:
            return None

        result = query.first()
        return result[0] if result else None

    def _update_deal_sponsor(self, deal_id: int, fact: AtomicFact):
        """Update deal with sponsor information from fact."""
        deal = self.db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            return

        payload = fact.payload or {}
        sponsor_raw = payload.get('sponsor_name_raw')
        sponsor_normalized = payload.get('sponsor_name_normalized')
        confidence = fact.confidence or 0.5

        # Only update if we have higher confidence or no existing sponsor
        if not deal.sponsor_name_normalized or (deal.sponsor_confidence or 0) < confidence:
            deal.sponsor_name_raw = sponsor_raw
            deal.sponsor_name_normalized = sponsor_normalized
            deal.sponsor_confidence = confidence
            deal.is_sponsor_backed = True
            deal.sponsor_evidence = {
                'fact_id': fact.id,
                'snippet': fact.evidence_snippet[:500] if fact.evidence_snippet else None,
                'pattern': payload.get('source_pattern'),
            }

            # Check if unresolved
            from app.extraction.regex_pack import SPONSOR_SEED_LIST
            if sponsor_normalized and sponsor_normalized.lower() not in SPONSOR_SEED_LIST:
                deal.unresolved_sponsor_entity = True

    def _update_deal_date(self, deal_id: int, fact: AtomicFact):
        """Update deal with date information from fact."""
        deal = self.db.query(Deal).filter(Deal.id == deal_id).first()
        if not deal:
            return

        payload = fact.payload or {}
        date_type = payload.get('date_type')
        date_value = payload.get('date_value')

        if not date_value:
            return

        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_value)

            if date_type == 'agreement_date' and not deal.agreement_date:
                deal.agreement_date = dt
            elif date_type == 'announcement_date' and not deal.announcement_date:
                deal.announcement_date = dt
            elif date_type == 'expected_close' and not deal.expected_close_date:
                deal.expected_close_date = dt
        except ValueError:
            pass

    def merge_deals(self, source_deal_id: int, target_deal_id: int, reason: str) -> bool:
        """
        Merge two deals when later filings show they're the same deal.

        Moves all facts from source to target and marks source as merged.
        """
        source = self.db.query(Deal).filter(Deal.id == source_deal_id).first()
        target = self.db.query(Deal).filter(Deal.id == target_deal_id).first()

        if not source or not target:
            return False

        # Move facts
        self.db.query(AtomicFact).filter(
            AtomicFact.deal_id == source_deal_id
        ).update({'deal_id': target_deal_id})

        # Move financing events
        from app.models.financing import FinancingEvent
        self.db.query(FinancingEvent).filter(
            FinancingEvent.deal_id == source_deal_id
        ).update({'deal_id': target_deal_id})

        # Create audit trail alert
        alert = ProcessingAlert(
            alert_type=AlertType.DEAL_MERGE_CANDIDATE,
            deal_id=target_deal_id,
            title=f"Deal merged: {source.target_name_display or source_deal_id}",
            description=f"Merged with deal {target.target_name_display or target_deal_id}. Reason: {reason}",
            is_resolved=True,
            resolved_at=datetime.utcnow(),
            resolution_notes=f"Auto-merged. Source deal key: {source.deal_key}",
        )
        self.db.add(alert)

        # Delete source deal
        self.db.delete(source)
        self.db.commit()

        return True

    def find_merge_candidates(self) -> list[tuple[Deal, Deal, float]]:
        """
        Find pairs of deals that might be duplicates.

        Returns:
            List of (deal1, deal2, similarity_score) tuples
        """
        from rapidfuzz import fuzz

        candidates = []
        deals = self.db.query(Deal).filter(
            Deal.state.in_([DealState.CANDIDATE, DealState.OPEN])
        ).all()

        for i, d1 in enumerate(deals):
            for d2 in deals[i + 1:]:
                # Skip if same deal key
                if d1.deal_key == d2.deal_key:
                    continue

                # Compare target names
                if d1.target_name_normalized and d2.target_name_normalized:
                    similarity = fuzz.ratio(
                        d1.target_name_normalized,
                        d2.target_name_normalized
                    )
                    if similarity > 85:
                        candidates.append((d1, d2, similarity / 100))

        return candidates


def cluster_facts(db: Session) -> dict:
    """Convenience function to run clustering."""
    service = DealClusteringService(db)
    return service.cluster_unclustered_facts()
