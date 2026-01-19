"""
Unit tests for regex_pack.py.

Tests cover:
- Preamble party list extraction (A1)
- Defined term role extraction (A2)
- Sponsor affiliation patterns (A3)
- Currency amount parsing (A4)
- Date extraction
- Party name normalization
"""
import pytest
from app.extraction.regex_pack import (
    PREAMBLE_PARTY_LIST,
    PREAMBLE_PARTIES_ALT,
    DEFINED_TERM_ROLE,
    SPONSOR_AFFILIATION,
    SPONSOR_NEGATIVE_PHRASES,
    CURRENCY_AMOUNT,
    split_party_span,
    map_role_label,
    extract_party_with_role,
    extract_sponsors,
    extract_currency_amounts,
    parse_currency_amount,
    extract_agreement_date,
    normalize_party_name,
    display_party_name,
    SPONSOR_SEED_LIST,
)


class TestPreamblePartyList:
    """Tests for A1: PREAMBLE_PARTY_LIST pattern."""

    def test_basic_by_and_among(self):
        """Test basic 'by and among' pattern."""
        text = """
        This Agreement and Plan of Merger is entered into by and among
        Alpha Corp., a Delaware corporation, Beta Inc., a Nevada corporation,
        and Gamma LLC, a Delaware limited liability company.
        """
        match = PREAMBLE_PARTY_LIST.search(text)
        assert match is not None
        assert "Alpha Corp" in match.group('party_span')

    def test_by_and_between(self):
        """Test 'by and between' pattern."""
        text = """
        AGREEMENT AND PLAN OF MERGER by and between Parent Holdings Inc.
        and Target Company Inc.
        """
        match = PREAMBLE_PARTY_LIST.search(text)
        assert match is not None
        party_span = match.group('party_span')
        assert "Parent Holdings" in party_span
        assert "Target Company" in party_span

    def test_with_newlines(self):
        """Test pattern handles newlines in party span."""
        text = """
        This Agreement is entered into by and among
        First Party, Inc.,
        Second Party, LLC,
        and Third Party Corp.
        """
        match = PREAMBLE_PARTY_LIST.search(text)
        assert match is not None

    def test_split_party_span_basic(self):
        """Test party span splitting."""
        span = "Alpha Inc., Beta Corp., and Gamma LLC"
        parties = split_party_span(span)
        assert len(parties) == 3
        assert "Alpha Inc" in parties[0]
        assert "Beta Corp" in parties[1]
        assert "Gamma LLC" in parties[2]

    def test_split_party_span_with_parentheses(self):
        """Test party span splitting preserves parenthetical content."""
        span = 'Alpha Inc. (a Delaware corporation), Beta Corp. (the "Company"), and Gamma LLC'
        parties = split_party_span(span)
        assert len(parties) == 3
        assert "(a Delaware corporation)" in parties[0]


class TestDefinedTermRole:
    """Tests for A2: DEFINED_TERM_ROLE pattern."""

    def test_the_company(self):
        """Test '(the "Company")' pattern."""
        text = 'Target Corp. (the "Company")'
        match = DEFINED_TERM_ROLE.search(text)
        assert match is not None
        assert match.group('label') == 'Company'

    def test_purchaser(self):
        """Test '("Purchaser")' pattern."""
        text = 'Buyer Holdings ("Purchaser")'
        match = DEFINED_TERM_ROLE.search(text)
        assert match is not None
        assert match.group('label') == 'Purchaser'

    def test_hereinafter(self):
        """Test 'hereinafter "Parent"' pattern."""
        text = 'Acquirer Inc. (hereinafter "Parent")'
        match = DEFINED_TERM_ROLE.search(text)
        assert match is not None
        assert match.group('label') == 'Parent'

    def test_hereinafter_referred_to_as(self):
        """Test full 'hereinafter referred to as' pattern."""
        text = 'Target LLC (hereinafter referred to as the "Company")'
        match = DEFINED_TERM_ROLE.search(text)
        assert match is not None
        assert match.group('label') == 'Company'

    def test_map_role_label(self):
        """Test role label mapping."""
        assert map_role_label('Company') == 'target'
        assert map_role_label('company') == 'target'
        assert map_role_label('Parent') == 'acquirer'
        assert map_role_label('Buyer') == 'acquirer'
        assert map_role_label('Purchaser') == 'acquirer'
        assert map_role_label('Merger Sub') == 'merger_sub'
        assert map_role_label('Unknown') is None


class TestSponsorAffiliation:
    """Tests for A3: SPONSOR_AFFILIATION pattern."""

    def test_affiliates_of(self):
        """Test 'affiliates of' pattern."""
        text = "Parent is controlled by affiliates of Blackstone Inc."
        match = SPONSOR_AFFILIATION.search(text)
        assert match is not None
        assert "Blackstone" in match.group('sponsor')

    def test_funds_managed_by(self):
        """Test 'funds managed by' pattern."""
        text = "The acquisition is being made by funds managed by KKR & Co."
        match = SPONSOR_AFFILIATION.search(text)
        assert match is not None
        assert "KKR" in match.group('sponsor')

    def test_portfolio_company_of(self):
        """Test 'portfolio company of' pattern."""
        text = "The Company is a portfolio company of Apollo Global Management."
        match = SPONSOR_AFFILIATION.search(text)
        assert match is not None
        assert "Apollo" in match.group('sponsor')

    def test_extract_sponsors_seed_list(self):
        """Test sponsor extraction from seed list."""
        text = "Blackstone and its affiliates will provide equity financing."
        sponsors = extract_sponsors(text)
        assert len(sponsors) >= 1
        blackstone_sponsor = next((s for s in sponsors if 'blackstone' in s.sponsor_name_normalized), None)
        assert blackstone_sponsor is not None
        assert blackstone_sponsor.source_pattern == 'seed_list'
        assert blackstone_sponsor.confidence >= 0.9

    def test_extract_sponsors_negative_phrase(self):
        """Test negative phrase exclusion."""
        text = "The Company is not a financial sponsor. It operates independently."
        sponsors = extract_sponsors(text)
        # Should not find sponsors or should be marked as negated
        non_negated = [s for s in sponsors if not s.is_negated]
        assert len(non_negated) == 0


class TestCurrencyAmount:
    """Tests for A4: CURRENCY_AMOUNT pattern."""

    def test_plain_number(self):
        """Test plain dollar amount."""
        text = "$500,000,000"
        match = CURRENCY_AMOUNT.search(text)
        assert match is not None
        result = parse_currency_amount(match)
        assert result.value_usd == 500_000_000

    def test_billion(self):
        """Test billion scale word."""
        text = "$1.5 billion"
        match = CURRENCY_AMOUNT.search(text)
        assert match is not None
        result = parse_currency_amount(match)
        assert result.value_usd == 1_500_000_000

    def test_million(self):
        """Test million scale word."""
        text = "$750 million"
        match = CURRENCY_AMOUNT.search(text)
        assert match is not None
        result = parse_currency_amount(match)
        assert result.value_usd == 750_000_000

    def test_abbreviation_b(self):
        """Test B abbreviation."""
        text = "$2.5B"
        match = CURRENCY_AMOUNT.search(text)
        assert match is not None
        result = parse_currency_amount(match)
        assert result.value_usd == 2_500_000_000

    def test_abbreviation_m(self):
        """Test M abbreviation."""
        text = "$500M"
        match = CURRENCY_AMOUNT.search(text)
        assert match is not None
        result = parse_currency_amount(match)
        assert result.value_usd == 500_000_000

    def test_extract_multiple_amounts(self):
        """Test extracting multiple amounts."""
        text = "The deal was valued at $1.5 billion with a $500 million term loan."
        amounts = extract_currency_amounts(text)
        assert len(amounts) == 2
        values = [a.value_usd for a in amounts]
        assert 1_500_000_000 in values
        assert 500_000_000 in values


class TestDateExtraction:
    """Tests for date extraction."""

    def test_dated_as_of(self):
        """Test 'dated as of' pattern."""
        text = "This Agreement is dated as of January 15, 2024."
        result = extract_agreement_date(text)
        assert result is not None
        raw, iso = result
        assert iso == "2024-01-15"

    def test_entered_into_on(self):
        """Test 'entered into on' pattern."""
        text = "This Agreement is entered into on February 28, 2024."
        result = extract_agreement_date(text)
        assert result is not None
        raw, iso = result
        assert iso == "2024-02-28"

    def test_ordinal_day(self):
        """Test ordinal day format."""
        text = "This Agreement is dated as of the 15th day of March, 2024."
        result = extract_agreement_date(text)
        assert result is not None
        raw, iso = result
        assert iso == "2024-03-15"


class TestPartyNameNormalization:
    """Tests for party name normalization."""

    def test_strip_inc(self):
        """Test stripping Inc suffix."""
        assert normalize_party_name("Alpha Corp., Inc.") == "alpha corp"

    def test_strip_llc(self):
        """Test stripping LLC suffix."""
        assert normalize_party_name("Beta Holdings LLC") == "beta holdings"

    def test_strip_jurisdiction(self):
        """Test stripping jurisdictional descriptor."""
        name = "Gamma Corp., a Delaware corporation"
        normalized = normalize_party_name(name)
        assert "delaware" not in normalized
        assert "gamma corp" in normalized

    def test_strip_parenthetical(self):
        """Test stripping parenthetical content."""
        name = 'Target Inc. (the "Company")'
        normalized = normalize_party_name(name)
        assert "company" not in normalized
        assert "target" in normalized

    def test_display_name_preserves_case(self):
        """Test display name preserves capitalization."""
        name = "Alpha Corp., a Delaware corporation"
        display = display_party_name(name)
        assert display.startswith("Alpha")


class TestSponsorSeedList:
    """Tests for sponsor seed list coverage."""

    def test_major_sponsors_in_list(self):
        """Test that major PE sponsors are in seed list."""
        major_sponsors = [
            'blackstone', 'kkr', 'apollo', 'carlyle', 'thoma bravo',
            'tpg', 'bain capital', 'warburg pincus', 'silver lake'
        ]
        for sponsor in major_sponsors:
            assert sponsor in SPONSOR_SEED_LIST, f"{sponsor} not in seed list"

    def test_seed_list_aliases(self):
        """Test that common aliases are included."""
        assert 'cd&r' in SPONSOR_SEED_LIST
        assert '3g capital' in SPONSOR_SEED_LIST
        assert 'sycamore' in SPONSOR_SEED_LIST


# Golden snippet fixtures for regression testing
GOLDEN_PREAMBLE_SNIPPETS = [
    # Standard 3-party merger agreement
    (
        """
        AGREEMENT AND PLAN OF MERGER by and among Alpha Holdings, Inc.,
        a Delaware corporation ("Parent"), Alpha Merger Sub, Inc., a Delaware
        corporation and wholly owned subsidiary of Parent ("Merger Sub"), and
        Target Company, Inc., a Delaware corporation (the "Company").
        """,
        {
            'parent': 'Alpha Holdings',
            'merger_sub': 'Alpha Merger Sub',
            'target': 'Target Company',
        }
    ),
    # 2-party with "by and between"
    (
        """
        MERGER AGREEMENT entered into by and between
        Acquirer Corp., a Nevada corporation (the "Buyer"),
        and Target LLC, a Delaware limited liability company (the "Company").
        """,
        {
            'buyer': 'Acquirer Corp',
            'target': 'Target LLC',
        }
    ),
]


class TestGoldenSnippets:
    """Regression tests using golden snippets."""

    @pytest.mark.parametrize("snippet,expected", GOLDEN_PREAMBLE_SNIPPETS)
    def test_preamble_extraction(self, snippet, expected):
        """Test preamble extraction against golden snippets."""
        match = PREAMBLE_PARTY_LIST.search(snippet)
        if not match:
            match = PREAMBLE_PARTIES_ALT.search(snippet)
        assert match is not None, "Failed to match preamble pattern"

        party_span = match.group('party_span')
        for role, name_fragment in expected.items():
            assert name_fragment in party_span, f"Expected {name_fragment} in party span"
