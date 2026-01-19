"""
Attribution Engine for fee estimation.

Uses JSON configuration for:
- Advisory fee bps by deal size
- Underwriting fee bps by market_tag
- Role splits for revenue allocation

Config is loaded at startup and fails fast if invalid.
"""
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.deal import Deal
from app.models.financing import FinancingEvent, FinancingParticipant


@dataclass
class AttributionConfig:
    """Parsed attribution configuration."""
    advisory_fee_bps: dict
    underwriting_fee_bps: dict
    role_splits: dict
    thresholds: dict


class AttributionConfigError(Exception):
    """Raised when attribution config is invalid or missing."""
    pass


def load_attribution_config() -> AttributionConfig:
    """
    Load and validate attribution configuration.

    Fails fast if config is missing or invalid.
    """
    settings = get_settings()
    config_path = Path(settings.ATTRIBUTION_CONFIG_PATH)

    # Try relative to backend directory
    if not config_path.is_absolute():
        backend_dir = Path(__file__).parent.parent.parent
        config_path = backend_dir / config_path

    if not config_path.exists():
        raise AttributionConfigError(
            f"Attribution config not found: {config_path}. "
            "This file is required for fee calculations."
        )

    try:
        with open(config_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise AttributionConfigError(f"Invalid JSON in attribution config: {e}")

    # Validate required fields
    required_fields = ['advisory_fee_bps', 'underwriting_fee_bps', 'role_splits', 'thresholds']
    for field in required_fields:
        if field not in data:
            raise AttributionConfigError(f"Missing required field in attribution config: {field}")

    return AttributionConfig(
        advisory_fee_bps=data['advisory_fee_bps'],
        underwriting_fee_bps=data['underwriting_fee_bps'],
        role_splits=data['role_splits'],
        thresholds=data['thresholds'],
    )


# Singleton config instance
_config: Optional[AttributionConfig] = None


def get_attribution_config() -> AttributionConfig:
    """Get cached attribution config."""
    global _config
    if _config is None:
        _config = load_attribution_config()
    return _config


class AttributionEngine:
    """
    Calculates estimated fees for advisory and underwriting.

    Fee calculation:
    1. Get base fee in bps from config based on market_tag
    2. Apply to deal value or financing amount
    3. Allocate to participants based on role_splits
    """

    def __init__(self, db: Session):
        self.db = db
        self.config = get_attribution_config()

    def calculate_deal_fees(self, deal: Deal) -> dict:
        """
        Calculate all fees for a deal.

        Returns:
            Dict with advisory and underwriting fee estimates
        """
        results = {
            'advisory_fee_usd': None,
            'underwriting_fee_usd': None,
            'participant_fees': [],
        }

        # Advisory fee (on deal value)
        if deal.deal_value_usd:
            advisory_bps = self._get_advisory_bps(deal.deal_value_usd)
            advisory_fee = deal.deal_value_usd * (advisory_bps / 10000)
            results['advisory_fee_usd'] = advisory_fee
            deal.advisory_fee_estimated = advisory_fee

        # Underwriting fees (on financing amounts)
        total_underwriting = 0
        events = self.db.query(FinancingEvent).filter(
            FinancingEvent.deal_id == deal.id
        ).all()

        for event in events:
            event_fee = self._calculate_event_fee(event)
            total_underwriting += event_fee

        results['underwriting_fee_usd'] = total_underwriting
        deal.underwriting_fee_estimated = total_underwriting

        self.db.commit()
        return results

    def calculate_event_fee(self, event: FinancingEvent) -> dict:
        """
        Calculate fees for a single financing event.

        Returns:
            Dict with event fee and participant allocations
        """
        event_fee = self._calculate_event_fee(event)

        # Allocate to participants
        participant_fees = self._allocate_to_participants(event, event_fee)

        return {
            'event_fee_usd': event_fee,
            'participant_fees': participant_fees,
        }

    def _get_advisory_bps(self, deal_value: float) -> float:
        """Get advisory fee bps based on deal size."""
        config = self.config.advisory_fee_bps

        if deal_value >= 5_000_000_000:  # $5B+
            return config.get('deal_size_over_5B', config['default'])
        elif deal_value >= 1_000_000_000:  # $1B+
            return config.get('deal_size_over_1B', config['default'])
        else:
            return config['default']

    def _get_underwriting_bps(self, market_tag: str) -> float:
        """Get underwriting fee bps based on market tag."""
        config = self.config.underwriting_fee_bps
        return config.get(market_tag, config.get('Unknown', 100))

    def _calculate_event_fee(self, event: FinancingEvent) -> float:
        """Calculate total fee for a financing event."""
        if not event.amount_usd:
            return 0

        market_tag = event.market_tag or 'Unknown'
        bps = self._get_underwriting_bps(market_tag)
        fee = event.amount_usd * (bps / 10000)

        event.estimated_fee_usd = fee
        return fee

    def _allocate_to_participants(
        self,
        event: FinancingEvent,
        total_fee: float
    ) -> list[dict]:
        """
        Allocate fees to participants based on role.

        Returns:
            List of {participant_id, bank_name, role, fee_usd}
        """
        if not total_fee or not event.participants:
            return []

        # Determine role splits based on instrument family
        instrument_family = event.instrument_family or 'loan'
        role_splits = self.config.role_splits.get(instrument_family, {})

        allocations = []
        total_weight = 0

        # First pass: assign weights
        for participant in event.participants:
            role_normalized = participant.role_normalized or 'other'
            weight = role_splits.get(role_normalized, role_splits.get('other', 0.1))
            participant.role_weight = weight
            total_weight += weight

        # Second pass: allocate fees
        for participant in event.participants:
            if total_weight > 0:
                fee_share = total_fee * (participant.role_weight / total_weight)
            else:
                fee_share = total_fee / len(event.participants)

            participant.estimated_fee_usd = fee_share

            allocations.append({
                'participant_id': participant.id,
                'bank_name': participant.bank_name_raw,
                'role': participant.role,
                'role_normalized': participant.role_normalized,
                'fee_usd': fee_share,
            })

        self.db.commit()
        return allocations

    def calculate_all_fees(self) -> dict:
        """Calculate fees for all deals."""
        stats = {
            'deals_processed': 0,
            'events_processed': 0,
            'total_advisory_fees': 0,
            'total_underwriting_fees': 0,
        }

        deals = self.db.query(Deal).all()

        for deal in deals:
            result = self.calculate_deal_fees(deal)
            stats['deals_processed'] += 1

            if result.get('advisory_fee_usd'):
                stats['total_advisory_fees'] += result['advisory_fee_usd']
            if result.get('underwriting_fee_usd'):
                stats['total_underwriting_fees'] += result['underwriting_fee_usd']

        return stats


def calculate_fees(db: Session) -> dict:
    """Convenience function to calculate all fees."""
    engine = AttributionEngine(db)
    return engine.calculate_all_fees()
