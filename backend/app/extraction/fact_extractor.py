"""
Atomic Fact Extraction Module.

Key rule: Document processing emits Atomic Facts only.
It must NOT attempt to create Deals.

This module implements:
- Party Identification (Section 2A of spec)
- Sponsor Entity Logic (Section 3A of spec)
- Date Extraction (Section 2B of spec)
"""
import hashlib
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.filing import Filing, Exhibit
from app.models.atomic_fact import (
    AtomicFact, FactType,
    PartyDefinitionFact, SponsorMentionFact, DealDateFact, AdvisorMentionFact,
    FinancingMentionFact,
)
from app.models.alert import ProcessingAlert, AlertType
from app.extraction.visual_text_extractor import extract_visual_text, get_preamble_text
from app.extraction.regex_pack import (
    PREAMBLE_PARTY_LIST, PREAMBLE_PARTIES_ALT, MERGER_AGREEMENT_HEADER,
    DEFINED_TERM_ROLE, extract_party_with_role, map_role_label,
    extract_sponsors, extract_agreement_date,
    normalize_party_name, display_party_name,
    ITEM_101_PATTERN, DEFINITIVE_AGREEMENT_PATTERN,
    split_party_span,
    # Financing patterns
    ITEM_801_PATTERN, PURCHASE_AGREEMENT_PATTERN,
    extract_debt_instruments, extract_underwriters,
)


@dataclass
class ExtractionResult:
    """Result from fact extraction."""
    facts: list[AtomicFact]
    alerts: list[ProcessingAlert]


class FactExtractor:
    """
    Extracts atomic facts from EDGAR documents.

    Supported document types:
    - EX-2.1: Merger Agreement (Party + Date extraction)
    - 8-K: Material events (Party + Date extraction)
    - EX-99.*: Press releases (Sponsor extraction)
    - EX-10.*: Commitment letters (Sponsor extraction)
    - S-4/DEFM14A: Proxy statements (Sponsor + Advisor extraction)
    """

    def __init__(self, db: Session):
        self.db = db

    def extract_from_filing(self, filing: Filing) -> ExtractionResult:
        """
        Extract atomic facts from a filing and its exhibits.

        Args:
            filing: Filing to process

        Returns:
            ExtractionResult with facts and alerts
        """
        facts = []
        alerts = []

        # Process main filing document
        if filing.form_type in ('8-K', '8-K/A'):
            result = self._extract_from_8k(filing)
            facts.extend(result.facts)
            alerts.extend(result.alerts)

        # Process exhibits
        for exhibit in filing.exhibits:
            result = self._extract_from_exhibit(exhibit)
            facts.extend(result.facts)
            alerts.extend(result.alerts)

        return ExtractionResult(facts=facts, alerts=alerts)

    def extract_from_exhibit(self, exhibit: Exhibit) -> ExtractionResult:
        """Extract atomic facts from a single exhibit."""
        return self._extract_from_exhibit(exhibit)

    def _extract_from_8k(self, filing: Filing) -> ExtractionResult:
        """
        Extract facts from 8-K filing.

        Handles:
        - Item 1.01 for merger announcements
        - Item 8.01 for debt issuances and other financing events
        """
        facts = []
        alerts = []

        if not filing.visual_text:
            if filing.raw_html:
                filing.visual_text = extract_visual_text(filing.raw_html)
            else:
                return ExtractionResult(facts=[], alerts=[])

        visual_text = filing.visual_text

        # Check for Item 1.01 (Entry into Material Definitive Agreement)
        if ITEM_101_PATTERN.search(visual_text):
            # Look for definitive agreement mention
            if DEFINITIVE_AGREEMENT_PATTERN.search(visual_text):
                # Extract parties from the announcement
                result = self._extract_parties_from_announcement(
                    visual_text, filing, None
                )
                facts.extend(result.facts)
                alerts.extend(result.alerts)

                # Extract agreement date
                date_result = extract_agreement_date(visual_text)
                if date_result:
                    raw_date, iso_date = date_result
                    fact = AtomicFact(
                        fact_type=FactType.DEAL_DATE,
                        filing_id=filing.id,
                        evidence_snippet=f"dated {raw_date}",
                        source_section="item_1.01",
                        extraction_method="regex",
                        confidence=0.9,
                        payload=DealDateFact.create_payload(
                            date_type="agreement_date",
                            date_value=iso_date,
                            date_raw=raw_date,
                        ),
                    )
                    facts.append(fact)

        # Check for Item 8.01 (Other Events - often debt issuances)
        if ITEM_801_PATTERN.search(visual_text):
            result = self._extract_financing_from_8k(filing, visual_text)
            facts.extend(result.facts)
            alerts.extend(result.alerts)

        # Also check for purchase/underwriting agreements anywhere in 8-K
        # (some filings don't use standard Item numbers)
        if PURCHASE_AGREEMENT_PATTERN.search(visual_text):
            result = self._extract_financing_from_8k(filing, visual_text)
            # Avoid duplicates if already extracted from Item 8.01
            existing_snippets = {f.evidence_snippet[:100] for f in facts}
            for fact in result.facts:
                if fact.evidence_snippet[:100] not in existing_snippets:
                    facts.append(fact)

        return ExtractionResult(facts=facts, alerts=alerts)

    def _extract_financing_from_8k(self, filing: Filing, visual_text: str) -> ExtractionResult:
        """
        Extract financing facts from 8-K (debt issuances, underwriting agreements).
        """
        facts = []
        alerts = []

        # Extract debt instruments (Senior Notes, bonds, credit facilities)
        debt_instruments = extract_debt_instruments(visual_text)
        for instrument in debt_instruments:
            # Build participants list from underwriters
            underwriters = extract_underwriters(visual_text)
            participants = [
                {
                    "bank": uw.name_raw,
                    "bank_normalized": uw.name_normalized,
                    "role": uw.role,
                    "evidence": uw.evidence_snippet[:200],
                }
                for uw in underwriters
            ]

            fact = AtomicFact(
                fact_type=FactType.FINANCING_MENTION,
                filing_id=filing.id,
                evidence_snippet=instrument.evidence_snippet,
                source_section="item_8.01",
                extraction_method="regex",
                extraction_pattern="DEBT_INSTRUMENT_PATTERN",
                confidence=instrument.confidence,
                payload=FinancingMentionFact.create_payload(
                    instrument_type=instrument.instrument_type,
                    instrument_subtype=instrument.instrument_raw,
                    amount_usd=instrument.amount_usd,
                    amount_raw=instrument.amount_raw,
                    currency="USD",
                    participants=participants,
                    maturity=instrument.maturity_year,
                    interest_rate=instrument.interest_rate,
                ),
            )
            facts.append(fact)

        # If no debt instruments found but we have underwriters, still record them
        if not debt_instruments:
            underwriters = extract_underwriters(visual_text)
            for uw in underwriters:
                fact = AtomicFact(
                    fact_type=FactType.ADVISOR_MENTION,
                    filing_id=filing.id,
                    evidence_snippet=uw.evidence_snippet,
                    source_section="item_8.01",
                    extraction_method="regex",
                    extraction_pattern="UNDERWRITER_PATTERN",
                    confidence=uw.confidence,
                    payload=AdvisorMentionFact.create_payload(
                        bank_name_raw=uw.name_raw,
                        bank_name_normalized=uw.name_normalized,
                        role=uw.role,
                        client_side="issuer",
                    ),
                )
                facts.append(fact)

        # Extract agreement date
        date_result = extract_agreement_date(visual_text)
        if date_result:
            raw_date, iso_date = date_result
            fact = AtomicFact(
                fact_type=FactType.DEAL_DATE,
                filing_id=filing.id,
                evidence_snippet=f"dated {raw_date}",
                source_section="item_8.01",
                extraction_method="regex",
                confidence=0.9,
                payload=DealDateFact.create_payload(
                    date_type="agreement_date",
                    date_value=iso_date,
                    date_raw=raw_date,
                ),
            )
            facts.append(fact)

        return ExtractionResult(facts=facts, alerts=alerts)

    def _extract_from_exhibit(self, exhibit: Exhibit) -> ExtractionResult:
        """Route exhibit to appropriate extractor based on type."""
        facts = []
        alerts = []

        exhibit_type = exhibit.exhibit_type.upper() if exhibit.exhibit_type else ''

        # EX-2.1: Merger Agreement
        if exhibit_type.startswith('EX-2'):
            result = self._extract_from_merger_agreement(exhibit)
            facts.extend(result.facts)
            alerts.extend(result.alerts)

        # EX-10.*: Could be commitment letters, credit agreements
        elif exhibit_type.startswith('EX-10'):
            result = self._extract_from_ex10(exhibit)
            facts.extend(result.facts)
            alerts.extend(result.alerts)

        # EX-99.*: Press releases
        elif exhibit_type.startswith('EX-99'):
            result = self._extract_from_press_release(exhibit)
            facts.extend(result.facts)
            alerts.extend(result.alerts)

        return ExtractionResult(facts=facts, alerts=alerts)

    def _extract_from_merger_agreement(self, exhibit: Exhibit) -> ExtractionResult:
        """
        Extract parties and dates from EX-2.1 Merger Agreement.

        This is the primary source for private target extraction.
        """
        facts = []
        alerts = []

        # Ensure visual text is available
        if not exhibit.visual_text:
            if exhibit.raw_content:
                exhibit.visual_text = extract_visual_text(exhibit.raw_content)
            else:
                return ExtractionResult(facts=[], alerts=[])

        preamble_text = exhibit.visual_text[:5000]  # First 5000 chars per spec

        # Step 1: Verify this is a merger agreement
        if not MERGER_AGREEMENT_HEADER.search(preamble_text):
            return ExtractionResult(facts=[], alerts=[])

        # Step 2: Extract party list from preamble
        party_match = PREAMBLE_PARTY_LIST.search(preamble_text)
        if not party_match:
            party_match = PREAMBLE_PARTIES_ALT.search(preamble_text)

        if party_match:
            party_span = party_match.group('party_span')
            parties = split_party_span(party_span)

            # Step 3: Extract defined term roles
            roles_found = extract_party_with_role(preamble_text)
            role_map = {normalize_party_name(p): (l, r) for p, l, r in roles_found}

            for i, party_raw in enumerate(parties):
                party_normalized = normalize_party_name(party_raw)
                party_display = display_party_name(party_raw)

                # Try to find role from defined terms
                role_info = role_map.get(party_normalized)
                if role_info:
                    role_label, canonical_role = role_info
                else:
                    # Heuristic: in 3-party list, last is often target ("Company")
                    if len(parties) == 3 and i == 2:
                        role_label = "Company"
                        canonical_role = "target"
                    elif len(parties) >= 2 and i == 0:
                        role_label = "Parent"
                        canonical_role = "acquirer"
                    else:
                        role_label = None
                        canonical_role = None

                confidence = 0.9 if role_info else 0.6

                fact = AtomicFact(
                    fact_type=FactType.PARTY_DEFINITION,
                    exhibit_id=exhibit.id,
                    filing_id=exhibit.filing_id,
                    evidence_snippet=party_span[:500],
                    evidence_start_offset=party_match.start(),
                    evidence_end_offset=party_match.end(),
                    source_section="preamble",
                    extraction_method="regex",
                    extraction_pattern="PREAMBLE_PARTY_LIST",
                    confidence=confidence,
                    payload=PartyDefinitionFact.create_payload(
                        party_name_raw=party_raw,
                        party_name_normalized=party_normalized,
                        party_name_display=party_display,
                        role_label=role_label or "Unknown",
                    ),
                )
                facts.append(fact)

        else:
            # Failed to extract parties - create alert
            alert = ProcessingAlert(
                alert_type=AlertType.FAILED_PRIVATE_TARGET_EXTRACTION,
                exhibit_id=exhibit.id,
                filing_id=exhibit.filing_id,
                title="Failed to extract parties from merger agreement preamble",
                description="Could not find 'by and among/between' pattern in preamble",
                preamble_hash=hashlib.sha256(preamble_text.encode()).hexdigest()[:64],
                preamble_preview=preamble_text[:500],
            )
            alerts.append(alert)

        # Step 4: Extract agreement date
        date_result = extract_agreement_date(preamble_text)
        if date_result:
            raw_date, iso_date = date_result
            fact = AtomicFact(
                fact_type=FactType.DEAL_DATE,
                exhibit_id=exhibit.id,
                filing_id=exhibit.filing_id,
                evidence_snippet=f"dated {raw_date}",
                source_section="preamble",
                extraction_method="regex",
                confidence=0.95,
                payload=DealDateFact.create_payload(
                    date_type="agreement_date",
                    date_value=iso_date,
                    date_raw=raw_date,
                ),
            )
            facts.append(fact)

        return ExtractionResult(facts=facts, alerts=alerts)

    def _extract_from_ex10(self, exhibit: Exhibit) -> ExtractionResult:
        """
        Extract from EX-10.* exhibits.

        Look for:
        - Equity commitment letters (sponsor evidence)
        - Credit agreements (financing facts)
        """
        facts = []
        alerts = []

        if not exhibit.visual_text:
            if exhibit.raw_content:
                exhibit.visual_text = extract_visual_text(exhibit.raw_content)
            else:
                return ExtractionResult(facts=[], alerts=[])

        text = exhibit.visual_text
        description = (exhibit.description or '').lower()

        # Check if this is a material financing document
        is_material = any(kw in description for kw in [
            'credit', 'commitment', 'bridge', 'loan', 'indenture', 'financing'
        ])

        if is_material:
            exhibit.is_material = True

        # Extract sponsor mentions from equity commitment letters
        if 'commitment' in description or 'equity' in description:
            sponsors = extract_sponsors(text)
            for sponsor in sponsors:
                if not sponsor.is_negated:
                    fact = AtomicFact(
                        fact_type=FactType.SPONSOR_MENTION,
                        exhibit_id=exhibit.id,
                        filing_id=exhibit.filing_id,
                        evidence_snippet=sponsor.context_snippet,
                        source_section="equity_commitment",
                        extraction_method="regex",
                        extraction_pattern=sponsor.source_pattern,
                        confidence=sponsor.confidence,
                        payload=SponsorMentionFact.create_payload(
                            sponsor_name_raw=sponsor.sponsor_name_raw,
                            sponsor_name_normalized=sponsor.sponsor_name_normalized,
                            source_pattern=sponsor.source_pattern,
                            context_snippet=sponsor.context_snippet,
                            is_negated=sponsor.is_negated,
                        ),
                    )
                    facts.append(fact)

        return ExtractionResult(facts=facts, alerts=alerts)

    def _extract_from_press_release(self, exhibit: Exhibit) -> ExtractionResult:
        """
        Extract from EX-99.* press releases.

        Look for:
        - Sponsor mentions
        - Advisor mentions
        - Deal value
        """
        facts = []
        alerts = []

        if not exhibit.visual_text:
            if exhibit.raw_content:
                exhibit.visual_text = extract_visual_text(exhibit.raw_content)
            else:
                return ExtractionResult(facts=[], alerts=[])

        text = exhibit.visual_text

        # Extract sponsor mentions
        sponsors = extract_sponsors(text)
        for sponsor in sponsors:
            if not sponsor.is_negated:
                fact = AtomicFact(
                    fact_type=FactType.SPONSOR_MENTION,
                    exhibit_id=exhibit.id,
                    filing_id=exhibit.filing_id,
                    evidence_snippet=sponsor.context_snippet,
                    source_section="press_release",
                    extraction_method="regex",
                    extraction_pattern=sponsor.source_pattern,
                    confidence=sponsor.confidence,
                    payload=SponsorMentionFact.create_payload(
                        sponsor_name_raw=sponsor.sponsor_name_raw,
                        sponsor_name_normalized=sponsor.sponsor_name_normalized,
                        source_pattern=sponsor.source_pattern,
                        context_snippet=sponsor.context_snippet,
                        is_negated=sponsor.is_negated,
                    ),
                )
                facts.append(fact)

        return ExtractionResult(facts=facts, alerts=alerts)

    def _extract_parties_from_announcement(
        self,
        text: str,
        filing: Filing,
        exhibit: Optional[Exhibit]
    ) -> ExtractionResult:
        """Extract party mentions from deal announcements."""
        facts = []
        alerts = []

        # Look for party list in announcement
        party_match = PREAMBLE_PARTY_LIST.search(text[:5000])
        if not party_match:
            party_match = PREAMBLE_PARTIES_ALT.search(text[:5000])

        if party_match:
            party_span = party_match.group('party_span')
            parties = split_party_span(party_span)

            for party_raw in parties:
                party_normalized = normalize_party_name(party_raw)
                party_display = display_party_name(party_raw)

                fact = AtomicFact(
                    fact_type=FactType.PARTY_MENTION,
                    filing_id=filing.id,
                    exhibit_id=exhibit.id if exhibit else None,
                    evidence_snippet=party_span[:500],
                    evidence_start_offset=party_match.start(),
                    evidence_end_offset=party_match.end(),
                    source_section="announcement",
                    extraction_method="regex",
                    extraction_pattern="PREAMBLE_PARTY_LIST",
                    confidence=0.7,
                    payload=PartyDefinitionFact.create_payload(
                        party_name_raw=party_raw,
                        party_name_normalized=party_normalized,
                        party_name_display=party_display,
                        role_label="Unknown",
                    ),
                )
                facts.append(fact)

        return ExtractionResult(facts=facts, alerts=alerts)


def extract_facts_from_filing(db: Session, filing: Filing) -> ExtractionResult:
    """Convenience function to extract facts from a filing."""
    extractor = FactExtractor(db)
    return extractor.extract_from_filing(filing)
