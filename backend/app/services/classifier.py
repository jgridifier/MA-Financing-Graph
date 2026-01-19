"""
Classification Engine for deals and financing events.

Classifications:
- Sponsor vs Non-Sponsor (LevFin)
- HY vs IG
- Bond vs Loan
- TLB vs RCF
- Bridge-to-bond
"""
import re
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.deal import Deal
from app.models.financing import FinancingEvent


@dataclass
class Classification:
    """Classification result with confidence."""
    market_tag: str
    instrument_family: str
    instrument_type: str
    is_sponsor_backed: bool
    confidence: float
    signals: dict


class ClassificationEngine:
    """
    Classifies deals and financing events.

    Market Tags:
    - IG_Bond: Investment Grade bonds
    - HY_Bond: High Yield bonds
    - Term_Loan_B: Leveraged term loans
    - Term_Loan_A: Bank term loans
    - RCF: Revolving credit facility
    - Bridge: Bridge financing
    - Other_Loan: Other loan types
    """

    # IG indicators (investment grade)
    IG_INDICATORS = [
        r'\binvestment\s+grade\b',
        r'\bIG\b',
        r'\bBBB[\-\+]?\b',
        r'\bA[\-\+]?\b',
        r'\bAA[\-\+]?\b',
        r'\bAAA\b',
    ]

    # HY indicators (high yield / leveraged)
    HY_INDICATORS = [
        r'\bhigh\s+yield\b',
        r'\bHY\b',
        r'\bleveraged\b',
        r'\blevfin\b',
        r'\bBB[\-\+]?\b',
        r'\bB[\-\+]?\b',
        r'\bCCC[\-\+]?\b',
        r'\bjunk\b',
        r'\bsub[\-\s]?investment\s+grade\b',
    ]

    # Term Loan B indicators
    TLB_INDICATORS = [
        r'\bterm\s+loan\s+b\b',
        r'\bTLB\b',
        r'\bTL\s*B\b',
        r'\binstitutional\s+term\s+loan\b',
        r'\bterm\s+b\b',
    ]

    # Bridge indicators
    BRIDGE_INDICATORS = [
        r'\bbridge\b',
        r'\binterim\s+financing\b',
        r'\btemporary\s+financing\b',
    ]

    # RCF indicators
    RCF_INDICATORS = [
        r'\brevolving\b',
        r'\bRCF\b',
        r'\brevolver\b',
        r'\bABL\b',
        r'\basset[\-\s]based\s+(?:lending|loan)\b',
    ]

    def __init__(self, db: Session):
        self.db = db

    def classify_deal(self, deal: Deal) -> Classification:
        """
        Classify a deal based on available information.

        Sets deal.is_sponsor_backed and deal.market_tag.
        """
        signals = {}

        # Check sponsor status
        is_sponsor_backed = deal.is_sponsor_backed
        if is_sponsor_backed is None:
            # Infer from context
            if deal.sponsor_name_normalized:
                is_sponsor_backed = True
            else:
                # Check if any financing events suggest sponsor
                events = self.db.query(FinancingEvent).filter(
                    FinancingEvent.deal_id == deal.id
                ).all()

                for event in events:
                    if event.market_tag and 'HY' in event.market_tag:
                        signals['hy_financing'] = True
                    if event.instrument_type and 'term_loan_b' in event.instrument_type.lower():
                        signals['tlb_financing'] = True

                is_sponsor_backed = signals.get('tlb_financing', False)

        # Determine market tag based on financing
        market_tag = self._determine_market_tag(deal.id)

        # Update deal
        deal.is_sponsor_backed = is_sponsor_backed
        deal.market_tag = market_tag
        self.db.commit()

        return Classification(
            market_tag=market_tag or 'Unknown',
            instrument_family='mixed',
            instrument_type='mixed',
            is_sponsor_backed=is_sponsor_backed or False,
            confidence=0.8 if signals else 0.5,
            signals=signals,
        )

    def classify_financing_event(self, event: FinancingEvent) -> Classification:
        """
        Classify a financing event.

        Uses evidence text and instrument metadata.
        """
        signals = {}

        # Get evidence text
        evidence = ''
        if event.source_fact_ids:
            from app.models.atomic_fact import AtomicFact
            facts = self.db.query(AtomicFact).filter(
                AtomicFact.id.in_(event.source_fact_ids)
            ).all()
            evidence = ' '.join(f.evidence_snippet or '' for f in facts)

        evidence_lower = evidence.lower()

        # Check for IG vs HY
        is_ig = any(re.search(p, evidence_lower) for p in self.IG_INDICATORS)
        is_hy = any(re.search(p, evidence_lower) for p in self.HY_INDICATORS)

        if is_ig:
            signals['ig_indicator'] = True
        if is_hy:
            signals['hy_indicator'] = True

        # Check instrument type
        is_tlb = any(re.search(p, evidence_lower) for p in self.TLB_INDICATORS)
        is_bridge = any(re.search(p, evidence_lower) for p in self.BRIDGE_INDICATORS)
        is_rcf = any(re.search(p, evidence_lower) for p in self.RCF_INDICATORS)

        if is_tlb:
            signals['tlb_indicator'] = True
        if is_bridge:
            signals['bridge_indicator'] = True
        if is_rcf:
            signals['rcf_indicator'] = True

        # Determine classification
        instrument_family = event.instrument_family or 'unknown'
        instrument_type = event.instrument_type

        if is_bridge:
            market_tag = 'Bridge'
            instrument_type = 'bridge'
        elif is_tlb:
            market_tag = 'Term_Loan_B'
            instrument_type = 'term_loan_b'
            instrument_family = 'loan'
        elif is_rcf:
            market_tag = 'Other_Loan'
            instrument_type = 'rcf'
            instrument_family = 'loan'
        elif instrument_family == 'bond':
            if is_hy and not is_ig:
                market_tag = 'HY_Bond'
            elif is_ig:
                market_tag = 'IG_Bond'
            else:
                # Default to HY for sponsor-backed
                deal = self.db.query(Deal).filter(Deal.id == event.deal_id).first()
                if deal and deal.is_sponsor_backed:
                    market_tag = 'HY_Bond'
                else:
                    market_tag = 'IG_Bond'
        elif instrument_family == 'loan':
            if is_hy or is_tlb:
                market_tag = 'Term_Loan_B'
                instrument_type = 'term_loan_b'
            else:
                market_tag = 'Other_Loan'
        else:
            market_tag = 'Unknown'

        # Get sponsor status from deal
        deal = self.db.query(Deal).filter(Deal.id == event.deal_id).first()
        is_sponsor_backed = deal.is_sponsor_backed if deal else False

        # Update event
        event.market_tag = market_tag
        event.instrument_type = instrument_type
        event.instrument_family = instrument_family
        self.db.commit()

        return Classification(
            market_tag=market_tag,
            instrument_family=instrument_family,
            instrument_type=instrument_type or 'unknown',
            is_sponsor_backed=is_sponsor_backed or False,
            confidence=0.8 if signals else 0.5,
            signals=signals,
        )

    def _determine_market_tag(self, deal_id: int) -> Optional[str]:
        """Determine primary market tag for a deal from its financing events."""
        events = self.db.query(FinancingEvent).filter(
            FinancingEvent.deal_id == deal_id
        ).all()

        if not events:
            return None

        # Priority: Term_Loan_B > HY_Bond > Bridge > IG_Bond > Other
        tags = [e.market_tag for e in events if e.market_tag]

        if 'Term_Loan_B' in tags:
            return 'Term_Loan_B'
        if 'HY_Bond' in tags:
            return 'HY_Bond'
        if 'Bridge' in tags:
            return 'Bridge'
        if 'IG_Bond' in tags:
            return 'IG_Bond'
        if tags:
            return tags[0]

        return None

    def classify_all_deals(self) -> dict:
        """Classify all unclassified deals."""
        stats = {'deals_classified': 0}

        deals = self.db.query(Deal).filter(
            Deal.market_tag.is_(None)
        ).all()

        for deal in deals:
            self.classify_deal(deal)
            stats['deals_classified'] += 1

        return stats

    def classify_all_financing_events(self) -> dict:
        """Classify all unclassified financing events."""
        stats = {'events_classified': 0}

        events = self.db.query(FinancingEvent).filter(
            FinancingEvent.market_tag.is_(None)
        ).all()

        for event in events:
            self.classify_financing_event(event)
            stats['events_classified'] += 1

        return stats


def classify_deals(db: Session) -> dict:
    """Convenience function to classify all deals."""
    engine = ClassificationEngine(db)
    deal_stats = engine.classify_all_deals()
    event_stats = engine.classify_all_financing_events()

    return {
        'deals': deal_stats,
        'events': event_stats,
    }
