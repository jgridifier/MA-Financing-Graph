"""
Reconciliation Service for linking financing events to deals.

Responsibilities:
- Links financing facts to Deals using deal_id
- Uses target_name_normalized as strong signal
- Uses sponsor_name as weak-to-moderate supporting evidence
- Creates FinancingEvent records with confidence scores
"""
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session
from rapidfuzz import fuzz

from app.models.deal import Deal, DealState
from app.models.atomic_fact import AtomicFact, FactType
from app.models.financing import FinancingEvent, FinancingParticipant
from app.models.filing import Exhibit


@dataclass
class ReconciliationMatch:
    """Result of matching a financing fact to a deal."""
    deal_id: int
    confidence: float
    explanation: str
    match_signals: dict


class ReconciliationService:
    """
    Service for reconciling financing facts with deals.

    Join logic per spec:
    - target_name_normalized match: STRONG signal
    - sponsor_name match: WEAK-TO-MODERATE supporting evidence
    - acquisition_vehicle name match: MODERATE signal
    - acquirer_name match: MODERATE signal
    """

    def __init__(self, db: Session, min_confidence: float = 0.5):
        self.db = db
        self.min_confidence = min_confidence

    def reconcile_financing_facts(self) -> dict:
        """
        Main reconciliation entry point.

        Processes FINANCING_MENTION facts and creates FinancingEvent records.

        Returns:
            Statistics dict
        """
        stats = {
            'facts_processed': 0,
            'events_created': 0,
            'low_confidence_skipped': 0,
        }

        # Get financing facts that haven't been reconciled yet
        financing_facts = self.db.query(AtomicFact).filter(
            AtomicFact.fact_type == FactType.FINANCING_MENTION,
            AtomicFact.deal_id.isnot(None),  # Must be clustered first
        ).all()

        for fact in financing_facts:
            # Check if already reconciled
            existing = self._find_existing_event(fact)
            if existing:
                continue

            # Create financing event
            event = self._create_financing_event(fact)
            if event:
                self.db.add(event)
                stats['events_created'] += 1

            stats['facts_processed'] += 1

        self.db.commit()
        return stats

    def reconcile_unlinked_financing(self) -> dict:
        """
        Attempt to match unlinked financing facts to deals.

        For facts where deal_id is NULL, attempt to find matching deals.
        """
        stats = {
            'facts_processed': 0,
            'matches_found': 0,
            'low_confidence_skipped': 0,
        }

        # Get unlinked financing facts
        unlinked = self.db.query(AtomicFact).filter(
            AtomicFact.fact_type == FactType.FINANCING_MENTION,
            AtomicFact.deal_id.is_(None),
        ).all()

        for fact in unlinked:
            match = self._find_best_deal_match(fact)
            if match and match.confidence >= self.min_confidence:
                fact.deal_id = match.deal_id
                stats['matches_found'] += 1

                # Create financing event
                event = self._create_financing_event(fact, match)
                if event:
                    self.db.add(event)
            else:
                stats['low_confidence_skipped'] += 1

            stats['facts_processed'] += 1

        self.db.commit()
        return stats

    def _find_existing_event(self, fact: AtomicFact) -> Optional[FinancingEvent]:
        """Check if a financing event already exists for this fact."""
        if not fact.deal_id:
            return None

        # Check source_fact_ids
        events = self.db.query(FinancingEvent).filter(
            FinancingEvent.deal_id == fact.deal_id
        ).all()

        for event in events:
            if event.source_fact_ids and fact.id in event.source_fact_ids:
                return event

        return None

    def _find_best_deal_match(self, fact: AtomicFact) -> Optional[ReconciliationMatch]:
        """
        Find the best matching deal for a financing fact.

        Uses fuzzy matching on:
        - target_name_normalized (strong)
        - sponsor_name (weak)
        - acquirer_name (moderate)
        """
        payload = fact.payload or {}

        # Extract identifiers from financing fact
        # These might be in the evidence snippet or participants
        evidence = fact.evidence_snippet or ''
        evidence_lower = evidence.lower()

        # Get all candidate deals
        deals = self.db.query(Deal).filter(
            Deal.state.in_([DealState.CANDIDATE, DealState.OPEN])
        ).all()

        best_match = None
        best_score = 0

        for deal in deals:
            match = self._score_deal_match(deal, evidence_lower, payload)
            if match.confidence > best_score:
                best_score = match.confidence
                best_match = match

        return best_match if best_match and best_score >= self.min_confidence else None

    def _score_deal_match(
        self,
        deal: Deal,
        evidence_lower: str,
        payload: dict
    ) -> ReconciliationMatch:
        """Score how well a deal matches a financing fact."""
        signals = {}
        confidence = 0.0
        explanations = []

        # Target name match (STRONG signal)
        if deal.target_name_normalized:
            if deal.target_name_normalized in evidence_lower:
                signals['target_name_exact'] = True
                confidence += 0.5
                explanations.append(f"Target name '{deal.target_name_display}' found in evidence")
            else:
                # Fuzzy match
                score = fuzz.partial_ratio(deal.target_name_normalized, evidence_lower)
                if score > 85:
                    signals['target_name_fuzzy'] = score
                    confidence += 0.4 * (score / 100)
                    explanations.append(f"Target name fuzzy match: {score}%")

        # Sponsor name match (WEAK signal)
        if deal.sponsor_name_normalized:
            if deal.sponsor_name_normalized in evidence_lower:
                signals['sponsor_name_exact'] = True
                confidence += 0.2
                explanations.append(f"Sponsor '{deal.sponsor_name_normalized}' found")
            else:
                score = fuzz.partial_ratio(deal.sponsor_name_normalized, evidence_lower)
                if score > 80:
                    signals['sponsor_name_fuzzy'] = score
                    confidence += 0.1 * (score / 100)

        # Acquirer name match (MODERATE signal)
        if deal.acquirer_name_normalized:
            if deal.acquirer_name_normalized in evidence_lower:
                signals['acquirer_name_exact'] = True
                confidence += 0.3
                explanations.append(f"Acquirer '{deal.acquirer_name_display}' found")
            else:
                score = fuzz.partial_ratio(deal.acquirer_name_normalized, evidence_lower)
                if score > 85:
                    signals['acquirer_name_fuzzy'] = score
                    confidence += 0.2 * (score / 100)

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return ReconciliationMatch(
            deal_id=deal.id,
            confidence=confidence,
            explanation='; '.join(explanations) if explanations else 'No strong signals',
            match_signals=signals,
        )

    def _create_financing_event(
        self,
        fact: AtomicFact,
        match: Optional[ReconciliationMatch] = None
    ) -> Optional[FinancingEvent]:
        """Create a FinancingEvent from a financing fact."""
        if not fact.deal_id:
            return None

        payload = fact.payload or {}

        event = FinancingEvent(
            deal_id=fact.deal_id,
            instrument_family=payload.get('instrument_type', 'unknown'),
            instrument_type=payload.get('instrument_subtype'),
            amount_usd=payload.get('amount_usd'),
            amount_raw=payload.get('amount_raw'),
            currency=payload.get('currency', 'USD'),
            purpose=payload.get('purpose'),
            source_exhibit_id=fact.exhibit_id,
            source_fact_ids=[fact.id],
            reconciliation_confidence=match.confidence if match else 1.0,
            reconciliation_explanation=match.explanation if match else 'Direct link via clustering',
        )

        # Add participants if present
        participants = payload.get('participants', [])
        for p in participants:
            participant = FinancingParticipant(
                bank_name_raw=p.get('bank'),
                bank_name_normalized=self._normalize_bank_name(p.get('bank', '')),
                role=p.get('role', 'unknown'),
                role_normalized=self._normalize_role(p.get('role', '')),
                evidence_snippet=p.get('evidence'),
            )
            event.participants.append(participant)

        return event

    def _normalize_bank_name(self, name: str) -> str:
        """Normalize bank name for matching."""
        name = name.strip().lower()
        # Remove common suffixes
        for suffix in [', n.a.', ' n.a.', ', na', ', inc', ' inc', ' llc', ' ltd']:
            name = name.replace(suffix, '')
        return ' '.join(name.split())

    def _normalize_role(self, role: str) -> str:
        """Normalize role to canonical form."""
        role = role.strip().lower()

        # Bond roles
        if 'bookrunner' in role:
            if 'joint' in role:
                return 'joint_bookrunner'
            return 'bookrunner'
        if 'co-manager' in role or 'co manager' in role:
            return 'co_manager'
        if 'underwriter' in role:
            if 'lead' in role or 'senior' in role:
                return 'lead_underwriter'
            return 'underwriter'

        # Loan roles
        if 'arranger' in role:
            if 'joint' in role and 'lead' in role:
                return 'joint_lead_arranger'
            if 'lead' in role or 'mandated' in role:
                return 'lead_arranger'
            return 'arranger'
        if 'admin' in role and 'agent' in role:
            return 'admin_agent'
        if 'syndication' in role:
            return 'syndication_agent'
        if 'agent' in role:
            return 'agent'

        return role


def reconcile_financing(db: Session) -> dict:
    """Convenience function to run reconciliation."""
    service = ReconciliationService(db)
    stats = service.reconcile_financing_facts()
    unlinked_stats = service.reconcile_unlinked_financing()

    return {
        'linked': stats,
        'unlinked': unlinked_stats,
    }
