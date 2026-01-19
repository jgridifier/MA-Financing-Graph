"""
Bank Name Resolution Service.

Resolves bank names to canonical entities using:
1. Exact alias match
2. Fuzzy matching with configurable threshold
"""
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session
from rapidfuzz import fuzz, process

from app.models.bank import Bank, BankAlias
from app.services.attribution import get_attribution_config


@dataclass
class BankMatch:
    """Result of bank name resolution."""
    bank_id: int
    bank_name: str
    confidence: float
    match_type: str  # 'exact', 'alias', 'fuzzy'


class BankResolver:
    """
    Resolves raw bank names to canonical entities.

    Resolution order:
    1. Exact match on Bank.name
    2. Exact match on BankAlias.alias
    3. Fuzzy match if above threshold
    """

    def __init__(self, db: Session):
        self.db = db
        config = get_attribution_config()
        self.fuzzy_threshold = config.thresholds.get('fuzzy_bank_match_min', 92)
        self._cache: dict[str, Optional[BankMatch]] = {}

    def resolve(self, bank_name_raw: str) -> Optional[BankMatch]:
        """
        Resolve a raw bank name to a canonical entity.

        Args:
            bank_name_raw: Raw bank name from extraction

        Returns:
            BankMatch if found, None otherwise
        """
        if not bank_name_raw:
            return None

        # Normalize for comparison
        normalized = self._normalize(bank_name_raw)

        # Check cache
        if normalized in self._cache:
            return self._cache[normalized]

        # Try exact match on Bank.name
        bank = self.db.query(Bank).filter(
            Bank.name_normalized == normalized
        ).first()

        if bank:
            match = BankMatch(
                bank_id=bank.id,
                bank_name=bank.name,
                confidence=1.0,
                match_type='exact',
            )
            self._cache[normalized] = match
            return match

        # Try exact match on alias
        alias = self.db.query(BankAlias).filter(
            BankAlias.alias_normalized == normalized
        ).first()

        if alias:
            bank = self.db.query(Bank).filter(Bank.id == alias.bank_id).first()
            if bank:
                match = BankMatch(
                    bank_id=bank.id,
                    bank_name=bank.name,
                    confidence=0.95,
                    match_type='alias',
                )
                self._cache[normalized] = match
                return match

        # Try fuzzy match
        match = self._fuzzy_match(normalized)
        self._cache[normalized] = match
        return match

    def _normalize(self, name: str) -> str:
        """Normalize bank name for comparison."""
        name = name.lower().strip()
        # Remove common suffixes
        suffixes = [
            ', n.a.', ' n.a.', ', na', ' na',
            ', inc.', ' inc.', ', inc', ' inc',
            ', llc', ' llc', ', ltd', ' ltd',
            ' plc', ' ag', ' sa', ' nv', ' bv',
            ' securities', ' capital', ' bank',
            '& co.', '& co', ' & company',
        ]
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]

        # Collapse whitespace
        return ' '.join(name.split())

    def _fuzzy_match(self, normalized: str) -> Optional[BankMatch]:
        """Attempt fuzzy matching against all banks."""
        banks = self.db.query(Bank).all()
        if not banks:
            return None

        # Build choices from bank names and aliases
        choices = []
        choice_to_bank = {}

        for bank in banks:
            bank_normalized = bank.name_normalized or self._normalize(bank.name)
            choices.append(bank_normalized)
            choice_to_bank[bank_normalized] = bank

            # Add aliases
            for alias in bank.aliases:
                alias_normalized = alias.alias_normalized or self._normalize(alias.alias)
                choices.append(alias_normalized)
                choice_to_bank[alias_normalized] = bank

        # Find best match
        result = process.extractOne(
            normalized,
            choices,
            scorer=fuzz.ratio,
        )

        if result:
            match_text, score, _ = result
            if score >= self.fuzzy_threshold:
                bank = choice_to_bank[match_text]
                return BankMatch(
                    bank_id=bank.id,
                    bank_name=bank.name,
                    confidence=score / 100,
                    match_type='fuzzy',
                )

        return None

    def resolve_and_link(
        self,
        bank_name_raw: str,
        auto_create: bool = False
    ) -> tuple[Optional[int], str]:
        """
        Resolve bank name and optionally create new entry.

        Args:
            bank_name_raw: Raw bank name
            auto_create: If True, create new bank if not found

        Returns:
            Tuple of (bank_id or None, normalized_name)
        """
        normalized = self._normalize(bank_name_raw)
        match = self.resolve(bank_name_raw)

        if match:
            return (match.bank_id, match.bank_name)

        if auto_create:
            # Create new bank entry
            bank = Bank(
                name=bank_name_raw,
                name_normalized=normalized,
                display_name=bank_name_raw,
            )
            self.db.add(bank)
            self.db.flush()
            return (bank.id, bank.name)

        return (None, normalized)


def seed_banks(db: Session):
    """Seed database with common investment banks."""
    banks = [
        # Bulge bracket
        ('JPMorgan Chase & Co.', ['JPMorgan', 'J.P. Morgan', 'JP Morgan', 'JPMC', 'Chase'], True),
        ('Goldman Sachs', ['GS', 'Goldman'], True),
        ('Morgan Stanley', ['MS'], True),
        ('Bank of America', ['BofA', 'BAML', 'Bank of America Merrill Lynch', 'Merrill Lynch'], True),
        ('Citigroup', ['Citi', 'Citibank'], True),
        ('Barclays', ['BARC'], True),
        ('Deutsche Bank', ['DB'], True),
        ('UBS', ['UBS AG'], True),
        ('Credit Suisse', ['CS'], True),  # Now part of UBS

        # Large US banks
        ('Wells Fargo', ['WFC', 'Wells'], False),
        ('PNC Financial', ['PNC', 'PNC Bank'], False),
        ('U.S. Bank', ['USB', 'US Bank', 'US Bancorp'], False),
        ('Truist', ['Truist Financial', 'BB&T', 'SunTrust'], False),

        # International
        ('HSBC', ['HSBC Holdings'], False),
        ('BNP Paribas', ['BNP'], False),
        ('Societe Generale', ['SocGen'], False),
        ('RBC Capital Markets', ['RBC', 'Royal Bank of Canada'], False),
        ('TD Securities', ['TD', 'Toronto-Dominion'], False),
        ('Mizuho', ['Mizuho Financial', 'Mizuho Bank'], False),
        ('MUFG', ['Mitsubishi UFJ', 'Bank of Tokyo-Mitsubishi'], False),
        ('SMBC', ['Sumitomo Mitsui', 'SMBC Nikko'], False),

        # Boutiques
        ('Lazard', [], False),
        ('Evercore', [], False),
        ('Centerview Partners', ['Centerview'], False),
        ('Moelis & Company', ['Moelis'], False),
        ('PJT Partners', ['PJT'], False),
        ('Perella Weinberg', ['PWP'], False),
        ('Guggenheim Securities', ['Guggenheim Partners'], False),
        ('Jefferies', ['Jefferies Financial', 'Jefferies Group'], False),
        ('Piper Sandler', ['Piper Jaffray'], False),
        ('Raymond James', [], False),
    ]

    for name, aliases, is_bulge in banks:
        # Check if exists
        existing = db.query(Bank).filter(Bank.name == name).first()
        if existing:
            continue

        bank = Bank(
            name=name,
            name_normalized=name.lower().replace(',', '').replace('.', ''),
            display_name=name,
            is_bulge_bracket=is_bulge,
        )
        db.add(bank)
        db.flush()

        for alias in aliases:
            bank_alias = BankAlias(
                bank_id=bank.id,
                alias=alias,
                alias_normalized=alias.lower().replace(',', '').replace('.', ''),
            )
            db.add(bank_alias)

    db.commit()
