"""
Centralized Regex Pattern Pack for EDGAR Document Extraction.

All patterns assume PRIOR NORMALIZATION of smart quotes/dashes to ASCII
via VisualTextExtractor.

Appendix A Mandatory Patterns:
- A1: PREAMBLE_PARTY_LIST - Party list in merger agreement preambles
- A2: DEFINED_TERM_ROLE - Defined term role labels (Company, Parent, etc.)
- A3: SPONSOR_AFFILIATION - Sponsor linkage phrases
- A4: CURRENCY_AMOUNT - Money amounts with scale words

Each pattern is documented with:
- Target: What the pattern matches
- Spec: Technical requirements
- Usage: How to use the pattern and post-processing requirements
"""
import re
from typing import Optional, NamedTuple
from dataclasses import dataclass


# =============================================================================
# A1: PREAMBLE_PARTY_LIST
# =============================================================================
# Target: Matches party list in preamble: "by and among [Party A], [Party B], and [Party C]..."
# Spec: Case-insensitive; tolerates arbitrary whitespace/newlines; stops at first sentence terminator

# Primary pattern: matches party lists with "by and among/between"
# Uses greedy matching to capture entire party list until final period
PREAMBLE_PARTY_LIST = re.compile(
    r'\bby\s+and\s+(?:among|between)\b\s+(?P<party_span>.+)\.\s*$',
    re.IGNORECASE | re.DOTALL | re.MULTILINE
)

# Non-greedy version for texts with content after the party list
PREAMBLE_PARTY_LIST_LAZY = re.compile(
    r'\bby\s+and\s+(?:among|between)\b\s+(?P<party_span>.+?["\')]\s*)\.',
    re.IGNORECASE | re.DOTALL
)

# Alternative pattern: for "entered into" / "made" structures
PREAMBLE_PARTIES_ALT = re.compile(
    r'(?:entered\s+into|made)\s+(?:by\s+and\s+)?(?:among|between)\s+(?P<party_span>.+)\.\s*$',
    re.IGNORECASE | re.DOTALL | re.MULTILINE
)

# Pattern to identify merger agreement headers
MERGER_AGREEMENT_HEADER = re.compile(
    r'(?:AGREEMENT\s+AND\s+PLAN\s+OF\s+MERGER|PLAN\s+OF\s+MERGER|MERGER\s+AGREEMENT)',
    re.IGNORECASE
)


@dataclass
class PartySpan:
    """Parsed party from preamble."""
    name_raw: str
    name_normalized: str
    role_label: Optional[str] = None
    confidence: float = 1.0


def split_party_span(party_span: str) -> list[str]:
    """
    Split party span into individual parties using parentheses-aware splitting.

    Post-processing requirement from spec:
    - party_span must be split into parties using a parentheses-aware splitter
    - Do not split inside parentheses
    - Do not split on commas that introduce jurisdictional descriptors
    - Prefer splitting on ", and" / "and" near end for last party

    Examples:
        "Alpha Inc., Beta Corp., and Gamma LLC" -> ["Alpha Inc.", "Beta Corp.", "Gamma LLC"]
        "Alpha Inc. (a Delaware corporation), and Beta Corp." -> ["Alpha Inc. (a Delaware corporation)", "Beta Corp."]
    """
    # Normalize whitespace first
    party_span = ' '.join(party_span.split())

    # Jurisdictional descriptor pattern - don't split before these
    jurisdictional_pattern = re.compile(
        r'^,?\s*a\s+(?:Delaware|Nevada|California|New York|Texas|Florida|Maryland|[A-Z][a-z]+)\s+',
        re.IGNORECASE
    )

    # Track parenthesis depth to avoid splitting inside parens
    parties = []
    current = []
    paren_depth = 0

    i = 0
    while i < len(party_span):
        char = party_span[i]

        if char == '(':
            paren_depth += 1
            current.append(char)
        elif char == ')':
            paren_depth = max(0, paren_depth - 1)
            current.append(char)
        elif char == ',' and paren_depth == 0:
            rest = party_span[i:]
            rest_lower = rest.lower()

            # Check if this comma introduces a jurisdictional descriptor - if so, don't split
            if jurisdictional_pattern.match(rest):
                current.append(char)
            # Check for ", and" pattern - this IS a party separator
            elif rest_lower.startswith(', and ') or rest_lower.startswith(', and\n'):
                party_text = ''.join(current).strip()
                if party_text:
                    parties.append(party_text)
                current = []
                i += 5  # Skip ", and"
            # Check if comma is followed by a new party (capital letter after space)
            # but not if it's "Inc." or "LLC" etc. followed by jurisdictional info
            elif re.match(r',\s+[A-Z][a-z]+\s+(?:Inc|Corp|LLC|Ltd|Co|LP|Holdings|Group|Merger)', rest):
                party_text = ''.join(current).strip()
                if party_text:
                    parties.append(party_text)
                current = []
                i += 1  # Skip the comma
                # Skip any following whitespace
                while i < len(party_span) and party_span[i] in ' \t\n':
                    i += 1
                continue
            else:
                current.append(char)
        elif party_span[i:i+5].lower() == ' and ' and paren_depth == 0:
            # Check if this is a standalone "and" separator after a closing paren or quote
            before = ''.join(current).strip()
            if before and (before.endswith(')') or before.endswith('"') or before.endswith("'")):
                parties.append(before)
                current = []
                i += 5  # Skip " and "
                continue
            else:
                current.append(char)
        else:
            current.append(char)
        i += 1

    # Add final party
    final = ''.join(current).strip()
    if final:
        parties.append(final)

    return parties


# =============================================================================
# A2: DEFINED_TERM_ROLE
# =============================================================================
# Target: Captures defined-term role labels such as (the "Company"), ("Purchaser"), etc.
# Spec: Matches parentheses wrappers with optional lead-in words; relies on smart quote normalization

DEFINED_TERM_ROLE = re.compile(
    r'\(\s*(?:the\s+|hereinafter\s+(?:the\s+)?|hereinafter\s+referred\s+to\s+as\s+(?:the\s+)?|referred\s+to\s+as\s+(?:the\s+)?)?["\'](?P<label>[A-Za-z0-9][A-Za-z0-9\s\-]{0,40}?)["\']\s*\)',
    re.IGNORECASE
)

# Role label to canonical role mapping
ROLE_LABEL_MAPPING = {
    # Target-side roles
    'company': 'target',
    'target': 'target',
    'seller': 'target',

    # Acquirer-side roles
    'parent': 'acquirer',
    'buyer': 'acquirer',
    'purchaser': 'acquirer',
    'acquirer': 'acquirer',
    'acquiror': 'acquirer',

    # Acquisition vehicle
    'merger sub': 'merger_sub',
    'merger subsidiary': 'merger_sub',
    'acquisition sub': 'merger_sub',
    'acquisition subsidiary': 'merger_sub',
    'newco': 'merger_sub',
    'holdco': 'acquirer',
    'holdings': 'acquirer',
}


def map_role_label(label: str) -> Optional[str]:
    """
    Map a defined term label to canonical role.

    Returns:
        'target', 'acquirer', 'merger_sub', or None if unknown
    """
    normalized = label.lower().strip()
    return ROLE_LABEL_MAPPING.get(normalized)


def extract_party_with_role(text: str) -> list[tuple[str, str, str]]:
    """
    Extract parties with their defined roles from text.

    Returns:
        List of (party_text_before_paren, role_label, canonical_role)
    """
    results = []

    for match in DEFINED_TERM_ROLE.finditer(text):
        label = match.group('label')
        canonical = map_role_label(label)

        # Get text before the parenthetical (the party name)
        start = match.start()
        # Look backwards to find start of party name
        text_before = text[:start].strip()
        # Take last "sentence" or comma-separated segment
        segments = re.split(r'[,;]', text_before)
        party_name = segments[-1].strip() if segments else ''

        if party_name and canonical:
            results.append((party_name, label, canonical))

    return results


# =============================================================================
# A3: SPONSOR_AFFILIATION
# =============================================================================
# Target: Sponsor linkage phrases like "affiliates of [PE Firm]", "funds managed by [PE Firm]"
# Spec: Capture sponsor firm name; stop at punctuation or conjunction

SPONSOR_AFFILIATION = re.compile(
    r'(?:affiliates?\s+of|funds?\s+managed\s+by|portfolio\s+compan(?:y|ies)\s+of|controlled\s+by)\s+(?P<sponsor>[A-Z][A-Za-z0-9\s,&.\'-]{2,80}?)(?:\.|,|;|\s+and\b|\s+\)|$)',
    re.IGNORECASE
)

# Financial sponsor keyword detection
SPONSOR_KEYWORDS = re.compile(
    r'\b(?:financial\s+sponsor|private\s+equity|PE\s+firm|buyout\s+(?:firm|fund)|sponsor(?:ed)?(?:\s+transaction)?)\b',
    re.IGNORECASE
)

# Equity commitment letter indicators
EQUITY_COMMITMENT = re.compile(
    r'\b(?:equity\s+commitment\s+letter|equity\s+financing|sponsor\s+equity)\b',
    re.IGNORECASE
)

# PE Sponsor seed list (Tier 1 - exact match)
SPONSOR_SEED_LIST = {
    # Normalized name -> Display name
    'blackstone': 'Blackstone',
    'kkr': 'KKR',
    'kohlberg kravis roberts': 'KKR',
    'apollo': 'Apollo Global Management',
    'apollo global': 'Apollo Global Management',
    'carlyle': 'The Carlyle Group',
    'the carlyle group': 'The Carlyle Group',
    'thoma bravo': 'Thoma Bravo',
    'tpg': 'TPG',
    'tpg capital': 'TPG',
    'texas pacific group': 'TPG',
    'advent': 'Advent International',
    'advent international': 'Advent International',
    'bain capital': 'Bain Capital',
    'warburg pincus': 'Warburg Pincus',
    'silver lake': 'Silver Lake',
    'vista equity': 'Vista Equity Partners',
    'vista equity partners': 'Vista Equity Partners',
    'clayton dubilier': 'Clayton, Dubilier & Rice',
    'clayton, dubilier & rice': 'Clayton, Dubilier & Rice',
    'cd&r': 'Clayton, Dubilier & Rice',
    'cvc': 'CVC Capital Partners',
    'cvc capital': 'CVC Capital Partners',
    'eqt': 'EQT',
    'eqt partners': 'EQT',
    'brookfield': 'Brookfield Asset Management',
    'brookfield asset management': 'Brookfield Asset Management',
    'permira': 'Permira',
    'hellman & friedman': 'Hellman & Friedman',
    'h&f': 'Hellman & Friedman',
    'general atlantic': 'General Atlantic',
    'insight partners': 'Insight Partners',
    'providence equity': 'Providence Equity Partners',
    'ares': 'Ares Management',
    'ares management': 'Ares Management',
    'apax': 'Apax Partners',
    'apax partners': 'Apax Partners',
    'cinven': 'Cinven',
    'pai partners': 'PAI Partners',
    '3g capital': '3G Capital',
    'sycamore partners': 'Sycamore Partners',
    'sycamore': 'Sycamore Partners',
}

# Negative phrases that indicate NOT a sponsor
SPONSOR_NEGATIVE_PHRASES = re.compile(
    r'\b(?:not\s+a\s+(?:financial\s+)?sponsor|independent\s+of\s+(?:any\s+)?sponsor|no\s+sponsor|without\s+(?:any\s+)?sponsor|non-sponsored)\b',
    re.IGNORECASE
)


@dataclass
class SponsorMatch:
    """Sponsor extraction result."""
    sponsor_name_raw: str
    sponsor_name_normalized: str
    sponsor_name_display: str
    source_pattern: str  # 'seed_list', 'affiliation_pattern', 'keyword'
    context_snippet: str
    confidence: float
    is_negated: bool = False


def extract_sponsors(text: str, context_window: int = 150) -> list[SponsorMatch]:
    """
    Extract sponsor mentions from text.

    Uses two-tier approach:
    1. Seed list exact/alias match
    2. Pattern-based extraction

    Args:
        text: Visual text buffer
        context_window: Characters before/after match for context

    Returns:
        List of SponsorMatch objects
    """
    results = []
    text_lower = text.lower()

    # Tier 1: Seed list matching
    for seed_key, display_name in SPONSOR_SEED_LIST.items():
        if seed_key in text_lower:
            # Find the match position
            pos = text_lower.find(seed_key)
            if pos >= 0:
                # Get context window
                start = max(0, pos - context_window)
                end = min(len(text), pos + len(seed_key) + context_window)
                context = text[start:end]

                # Check for negation
                is_negated = bool(SPONSOR_NEGATIVE_PHRASES.search(context))

                if not is_negated:
                    results.append(SponsorMatch(
                        sponsor_name_raw=text[pos:pos + len(seed_key)],
                        sponsor_name_normalized=seed_key,
                        sponsor_name_display=display_name,
                        source_pattern='seed_list',
                        context_snippet=context,
                        confidence=0.95,
                        is_negated=is_negated,
                    ))

    # Tier 2: Pattern-based extraction
    for match in SPONSOR_AFFILIATION.finditer(text):
        sponsor_raw = match.group('sponsor').strip()

        # Get context window
        start = max(0, match.start() - context_window)
        end = min(len(text), match.end() + context_window)
        context = text[start:end]

        # Check for negation
        is_negated = bool(SPONSOR_NEGATIVE_PHRASES.search(context))

        # Normalize sponsor name
        sponsor_normalized = sponsor_raw.lower().strip()
        sponsor_normalized = re.sub(r'[,.\-\']', '', sponsor_normalized)
        sponsor_normalized = ' '.join(sponsor_normalized.split())

        # Check if it matches seed list
        display_name = SPONSOR_SEED_LIST.get(sponsor_normalized, sponsor_raw)
        source = 'seed_list' if sponsor_normalized in SPONSOR_SEED_LIST else 'affiliation_pattern'

        if not is_negated and sponsor_raw:
            results.append(SponsorMatch(
                sponsor_name_raw=sponsor_raw,
                sponsor_name_normalized=sponsor_normalized,
                sponsor_name_display=display_name,
                source_pattern=source,
                context_snippet=context,
                confidence=0.85 if source == 'affiliation_pattern' else 0.95,
                is_negated=is_negated,
            ))

    return results


# =============================================================================
# A4: CURRENCY_AMOUNT
# =============================================================================
# Target: Money amounts like "$500,000,000", "$1.5 billion", "$750 million"
# Spec: Capture numeric and optional scale word/abbrev

CURRENCY_AMOUNT = re.compile(
    r'\$\s?(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<scale>billion|million|b|m|bn|mm|mil)?',
    re.IGNORECASE
)

# Scale multipliers
SCALE_MULTIPLIERS = {
    'million': 1_000_000,
    'mil': 1_000_000,
    'm': 1_000_000,
    'mm': 1_000_000,
    'billion': 1_000_000_000,
    'b': 1_000_000_000,
    'bn': 1_000_000_000,
}


@dataclass
class CurrencyAmount:
    """Parsed currency amount."""
    raw_text: str
    numeric_value: float
    scale_word: Optional[str]
    value_usd: float


def parse_currency_amount(match: re.Match) -> CurrencyAmount:
    """
    Parse a currency regex match into structured amount.

    Post-processing requirement:
    - Convert to numeric value when scale present
    - million/m -> *1e6
    - billion/b -> *1e9
    """
    raw = match.group(0)
    num_str = match.group('num').replace(',', '')
    scale = match.group('scale')

    numeric_value = float(num_str)
    scale_lower = scale.lower() if scale else None
    multiplier = SCALE_MULTIPLIERS.get(scale_lower, 1)
    value_usd = numeric_value * multiplier

    return CurrencyAmount(
        raw_text=raw,
        numeric_value=numeric_value,
        scale_word=scale,
        value_usd=value_usd,
    )


def extract_currency_amounts(text: str) -> list[CurrencyAmount]:
    """Extract all currency amounts from text."""
    return [parse_currency_amount(m) for m in CURRENCY_AMOUNT.finditer(text)]


# =============================================================================
# DATE EXTRACTION
# =============================================================================
# For agreement date extraction from preambles

DATE_PATTERNS = [
    # "dated as of January 15, 2024"
    re.compile(
        r'dated\s+(?:as\s+of\s+)?(?P<date>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
        re.IGNORECASE
    ),
    # "entered into on January 15, 2024"
    re.compile(
        r'entered\s+into\s+(?:on\s+)?(?P<date>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
        re.IGNORECASE
    ),
    # "dated as of the 15th day of January, 2024"
    re.compile(
        r'dated\s+(?:as\s+of\s+)?the\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December),?\s+(?P<year>\d{4})',
        re.IGNORECASE
    ),
    # ISO format: 2024-01-15
    re.compile(r'dated\s+(?:as\s+of\s+)?(?P<date>\d{4}-\d{2}-\d{2})'),
]

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def parse_date_to_iso(date_str: str) -> Optional[str]:
    """Convert extracted date string to ISO 8601 format."""
    from datetime import datetime

    date_str = date_str.strip()

    # Try ISO format first
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return date_str

    # Try "Month DD, YYYY"
    match = re.match(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
        date_str, re.IGNORECASE
    )
    if match:
        month = MONTH_MAP[match.group(1).lower()]
        day = int(match.group(2))
        year = int(match.group(3))
        try:
            dt = datetime(year, month, day)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            return None

    return None


def extract_agreement_date(text: str, max_chars: int = 1000) -> Optional[tuple[str, str]]:
    """
    Extract agreement date from preamble text.

    Args:
        text: Visual text (first portion of document)
        max_chars: Search within first N characters

    Returns:
        Tuple of (raw_date, iso_date) or None
    """
    search_text = text[:max_chars]

    for pattern in DATE_PATTERNS:
        match = pattern.search(search_text)
        if match:
            if 'date' in match.groupdict():
                raw_date = match.group('date')
                iso_date = parse_date_to_iso(raw_date)
                if iso_date:
                    return (raw_date, iso_date)
            elif all(k in match.groupdict() for k in ['day', 'month', 'year']):
                day = match.group('day')
                month = match.group('month')
                year = match.group('year')
                raw_date = f"{month} {day}, {year}"
                iso_date = parse_date_to_iso(raw_date)
                if iso_date:
                    return (raw_date, iso_date)

    return None


# =============================================================================
# PARTY NAME NORMALIZATION
# =============================================================================

# Common suffixes to strip
# Note: We strip full words like "Inc", "LLC", "Corporation" etc. but preserve "Corp."
# when it appears to be part of the company name (e.g., "Gamma Corp.")
COMPANY_SUFFIXES = re.compile(
    r',?\s*(?:Inc\.?|Incorporated|Corporation|LLC|L\.?L\.?C\.?|Ltd\.?|Limited|Company|LP|L\.?P\.?|LLP|PLC|N\.?A\.?|S\.?A\.?|AG|GmbH|BV|NV)\.?$',
    re.IGNORECASE
)

# Secondary pattern for "Corp." and "Co." - only strip when preceded by comma
COMPANY_SUFFIXES_SECONDARY = re.compile(
    r',\s*(?:Corp\.?|Co\.?)$',
    re.IGNORECASE
)

# Jurisdictional descriptors to strip
JURISDICTIONAL_DESCRIPTOR = re.compile(
    r',?\s*a\s+(?:Delaware|Nevada|California|New York|Texas|Florida|Maryland|[A-Z][a-z]+)\s+(?:corporation|limited\s+liability\s+company|limited\s+partnership|company)$',
    re.IGNORECASE
)


def normalize_party_name(name: str) -> str:
    """
    Normalize party name for clustering/reconciliation.

    Normalization rules:
    1. Strip common suffixes (Inc, LLC, etc.)
    2. Remove jurisdictional descriptors
    3. Collapse whitespace
    4. Trim punctuation
    5. Lowercase for comparison

    Note: "Corp." and "Co." are only stripped when preceded by comma,
    to preserve company names like "Gamma Corp."
    """
    # Remove parenthetical content (defined terms)
    name = re.sub(r'\([^)]*\)', '', name)

    # Strip jurisdictional descriptors
    name = JURISDICTIONAL_DESCRIPTOR.sub('', name)

    # Strip company suffixes (primary patterns like Inc, LLC, etc.)
    name = COMPANY_SUFFIXES.sub('', name)

    # Strip secondary suffixes (Corp., Co.) only when preceded by comma
    name = COMPANY_SUFFIXES_SECONDARY.sub('', name)

    # Collapse whitespace and trim
    name = ' '.join(name.split())
    name = name.strip(' ,.-')

    # Lowercase for comparison
    return name.lower()


def display_party_name(name: str) -> str:
    """
    Clean party name for display (keep capitalization, remove noise).
    """
    # Remove parenthetical defined terms
    name = re.sub(r'\s*\([^)]*\)\s*', ' ', name)

    # Remove jurisdictional descriptors
    name = JURISDICTIONAL_DESCRIPTOR.sub('', name)

    # Clean whitespace
    name = ' '.join(name.split())
    name = name.strip(' ,.-')

    return name


# =============================================================================
# ITEM 1.01 DETECTION
# =============================================================================

ITEM_101_PATTERN = re.compile(
    r'Item\s+1\.01[.\s]+Entry\s+into\s+a\s+Material\s+Definitive\s+Agreement',
    re.IGNORECASE
)

DEFINITIVE_AGREEMENT_PATTERN = re.compile(
    r'entered\s+into\s+(?:a|an)\s+(?:Agreement\s+and\s+Plan\s+of\s+Merger|Merger\s+Agreement|definitive\s+agreement)',
    re.IGNORECASE
)


def find_item_101_section(text: str) -> Optional[tuple[int, int]]:
    """Find Item 1.01 section boundaries in 8-K."""
    match = ITEM_101_PATTERN.search(text)
    if match:
        start = match.start()
        # Look for next Item or end of document
        next_item = re.search(r'Item\s+\d+\.\d+', text[match.end():])
        if next_item:
            end = match.end() + next_item.start()
        else:
            end = len(text)
        return (start, end)
    return None


# =============================================================================
# FINANCING / CAPITAL MARKETS PATTERNS
# =============================================================================

# Item 8.01 detection (Other Events - often used for debt issuances)
ITEM_801_PATTERN = re.compile(
    r'Item\s+8\.01[.\s]+Other\s+Events',
    re.IGNORECASE
)

# Purchase Agreement (underwriting for debt/equity)
PURCHASE_AGREEMENT_PATTERN = re.compile(
    r'entered\s+into\s+(?:a\s+)?(?P<agreement_type>purchase\s+agreement|underwriting\s+agreement)',
    re.IGNORECASE
)

# Debt instrument patterns - Senior Notes, bonds, etc.
DEBT_INSTRUMENT_PATTERN = re.compile(
    r'(?P<amount>\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|b|m|bn|mm))?)\s+'
    r'(?:aggregate\s+)?(?:principal\s+)?(?:amount\s+)?(?:of\s+)?(?:its\s+)?'
    r'(?P<rate>[\d.]+%\s+)?'
    r'(?P<instrument>Senior\s+Notes?|Senior\s+Secured\s+Notes?|'
    r'Subordinated\s+Notes?|Convertible\s+Notes?|Notes?|Bonds?|Debentures?)'
    r'(?:\s+due\s+(?P<maturity>\d{4}))?',
    re.IGNORECASE
)

# Credit facility patterns
CREDIT_FACILITY_PATTERN = re.compile(
    r'(?P<amount>\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|b|m|bn|mm))?)\s+'
    r'(?:aggregate\s+)?(?:principal\s+)?(?:amount\s+)?'
    r'(?P<instrument>(?:senior\s+)?(?:secured\s+)?(?:unsecured\s+)?'
    r'(?:revolving\s+)?(?:credit\s+)?(?:facility|term\s+loan|bridge\s+loan|rcf|revolver))',
    re.IGNORECASE
)

# Underwriter/representative extraction
UNDERWRITER_PATTERN = re.compile(
    r'(?:with|among)\s+(?P<underwriters>[\w\s,&.]+?(?:LLC|Inc\.?|L\.?P\.?|Securities|Capital|Bank)?'
    r'(?:\s+and\s+[\w\s,&.]+?(?:LLC|Inc\.?|L\.?P\.?|Securities|Capital|Bank))?)'
    r'(?:,?\s+as\s+(?:representatives?\s+of\s+(?:the\s+)?(?:several\s+)?underwriters?|'
    r'underwriters?|lead\s+(?:book-?running\s+)?managers?|joint\s+(?:book-?running\s+)?managers?))',
    re.IGNORECASE
)

# Alternative underwriter pattern for simpler mentions
UNDERWRITER_SIMPLE_PATTERN = re.compile(
    r'(?:underwriters?\s+(?:named|identified|listed)\s+(?:in|on)\s+|'
    r'(?:the\s+)?underwriters?\s+(?:are|include|were)\s+)'
    r'(?P<underwriters>[A-Z][\w\s,&.]+?)(?:\.|,\s+(?:relating|whereby|pursuant))',
    re.IGNORECASE
)

# Instrument type classification
INSTRUMENT_TYPE_MAP = {
    'senior notes': 'bond',
    'senior secured notes': 'bond',
    'subordinated notes': 'bond',
    'convertible notes': 'convertible_bond',
    'notes': 'bond',
    'bonds': 'bond',
    'debentures': 'bond',
    'term loan': 'term_loan',
    'bridge loan': 'bridge_loan',
    'revolving credit facility': 'rcf',
    'revolving facility': 'rcf',
    'credit facility': 'credit_facility',
    'revolver': 'rcf',
    'rcf': 'rcf',
}


@dataclass
class DebtInstrumentMatch:
    """Parsed debt instrument from text."""
    instrument_type: str  # bond, term_loan, rcf, etc.
    instrument_raw: str
    amount_usd: Optional[float]
    amount_raw: str
    interest_rate: Optional[str]
    maturity_year: Optional[str]
    evidence_snippet: str
    confidence: float


def extract_debt_instruments(text: str, context_window: int = 200) -> list[DebtInstrumentMatch]:
    """
    Extract debt instrument mentions from text.

    Handles Senior Notes, bonds, credit facilities, term loans, etc.
    """
    results = []

    # Try debt instrument pattern (notes, bonds)
    for match in DEBT_INSTRUMENT_PATTERN.finditer(text):
        amount_raw = match.group('amount')
        instrument_raw = match.group('instrument')
        rate = match.group('rate')
        maturity = match.group('maturity')

        # Parse amount
        amount_match = CURRENCY_AMOUNT.search(amount_raw)
        amount_usd = None
        if amount_match:
            parsed = parse_currency_amount(amount_match)
            amount_usd = parsed.value_usd

        # Map instrument type
        instrument_lower = instrument_raw.lower().strip()
        instrument_type = 'bond'  # default for notes
        for key, val in INSTRUMENT_TYPE_MAP.items():
            if key in instrument_lower:
                instrument_type = val
                break

        # Get context
        start = max(0, match.start() - context_window)
        end = min(len(text), match.end() + context_window)
        context = text[start:end]

        results.append(DebtInstrumentMatch(
            instrument_type=instrument_type,
            instrument_raw=instrument_raw,
            amount_usd=amount_usd,
            amount_raw=amount_raw,
            interest_rate=rate.strip() if rate else None,
            maturity_year=maturity,
            evidence_snippet=context,
            confidence=0.9,
        ))

    # Try credit facility pattern
    for match in CREDIT_FACILITY_PATTERN.finditer(text):
        amount_raw = match.group('amount')
        instrument_raw = match.group('instrument')

        # Parse amount
        amount_match = CURRENCY_AMOUNT.search(amount_raw)
        amount_usd = None
        if amount_match:
            parsed = parse_currency_amount(amount_match)
            amount_usd = parsed.value_usd

        # Map instrument type
        instrument_lower = instrument_raw.lower().strip()
        instrument_type = 'credit_facility'
        for key, val in INSTRUMENT_TYPE_MAP.items():
            if key in instrument_lower:
                instrument_type = val
                break

        # Get context
        start = max(0, match.start() - context_window)
        end = min(len(text), match.end() + context_window)
        context = text[start:end]

        results.append(DebtInstrumentMatch(
            instrument_type=instrument_type,
            instrument_raw=instrument_raw,
            amount_usd=amount_usd,
            amount_raw=amount_raw,
            interest_rate=None,
            maturity_year=None,
            evidence_snippet=context,
            confidence=0.85,
        ))

    return results


@dataclass
class UnderwriterMatch:
    """Parsed underwriter from text."""
    name_raw: str
    name_normalized: str
    role: str  # underwriter, lead_manager, book_runner
    evidence_snippet: str
    confidence: float


def extract_underwriters(text: str, context_window: int = 150) -> list[UnderwriterMatch]:
    """
    Extract underwriter mentions from purchase/underwriting agreements.
    """
    results = []

    for pattern in [UNDERWRITER_PATTERN, UNDERWRITER_SIMPLE_PATTERN]:
        for match in pattern.finditer(text):
            underwriters_raw = match.group('underwriters')

            # Get context
            start = max(0, match.start() - context_window)
            end = min(len(text), match.end() + context_window)
            context = text[start:end]

            # Split multiple underwriters
            # Handle "X and Y" or "X, Y and Z" patterns
            underwriter_list = re.split(r'\s+and\s+|,\s*', underwriters_raw)

            for uw in underwriter_list:
                uw = uw.strip()
                if not uw or len(uw) < 3:
                    continue

                # Skip common non-underwriter phrases
                if uw.lower() in ('the', 'as', 'of', 'several', 'representatives'):
                    continue

                # Determine role from context
                role = 'underwriter'
                if 'lead' in context.lower() or 'book-running' in context.lower():
                    role = 'lead_manager'
                elif 'representative' in context.lower():
                    role = 'representative'

                results.append(UnderwriterMatch(
                    name_raw=uw,
                    name_normalized=uw.lower().strip(),
                    role=role,
                    evidence_snippet=context,
                    confidence=0.85,
                ))

    return results
