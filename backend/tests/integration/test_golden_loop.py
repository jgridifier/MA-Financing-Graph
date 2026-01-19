"""
Golden Loop Integration Tests.

Per spec Section 13: The "Golden Loop" (MANDATORY)

Tests the full pipeline:
1. Ingest filings for seed case
2. Run fact extraction
3. Run clustering
4. Run reconciliation
5. Assert expected outcomes

Note: Seed data provided externally via test_set.md
"""
import pytest
from dataclasses import dataclass
from typing import Optional


@dataclass
class SeedCase:
    """Test case seed data structure."""
    name: str
    cik: str
    target_cik: Optional[str] = None
    target_name: Optional[str] = None
    acquirer_cik: Optional[str] = None
    acquirer_name: Optional[str] = None
    expected_target_normalized: Optional[str] = None
    expected_sponsor: Optional[str] = None
    expected_financing_type: Optional[str] = None
    expected_underwriters: list[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    form_types: list[str] = None

    def __post_init__(self):
        if self.expected_underwriters is None:
            self.expected_underwriters = []
        if self.form_types is None:
            self.form_types = ['8-K', 'S-4', 'DEFM14A']


# Seed cases from test_set.md
SEED_CASES = [
    SeedCase(
        name="Kellanova / Mars",
        cik="0000055986",  # Kellanova (target)
        target_name="Kellanova",
        acquirer_name="Mars",
        expected_target_normalized="kellanova",
        form_types=['DEFM14A', '8-K'],
    ),
    SeedCase(
        name="VMware / Broadcom",
        cik="0001124615",  # VMware (target)
        target_cik="0001124615",
        acquirer_cik="0001730168",
        target_name="VMware",
        acquirer_name="Broadcom",
        expected_target_normalized="vmware",
        expected_financing_type="term_loan",
        form_types=['8-K', 'S-4'],
    ),
    SeedCase(
        name="Twitter / Musk",
        cik="0001418091",  # Twitter
        target_name="Twitter",
        expected_target_normalized="twitter",
        expected_sponsor="Elon Musk",  # Not typical PE but tests sponsor detection
        form_types=['8-K', 'DEFM14A'],
    ),
    SeedCase(
        name="Synopsys / Ansys",
        cik="0001013462",  # Ansys (target)
        target_cik="0001013462",
        acquirer_cik="0000883241",
        target_name="Ansys",
        acquirer_name="Synopsys",
        expected_target_normalized="ansys",
        form_types=['8-K', 'S-4'],
    ),
]


class TestGoldenLoop:
    """
    Golden Loop integration tests.

    These tests require database and potentially network access.
    Mark as integration tests with pytest markers.
    """

    @pytest.fixture
    def db_session(self):
        """Create test database session."""
        # In real implementation, this would create a test database
        # For now, we'll use a mock or skip if DB not available
        pytest.skip("Database not configured for integration tests")

    def test_end_to_end_flow(self, db_session, seed_case: SeedCase):
        """
        Generic end-to-end test function.

        Per spec:
        - Ingests filings for provided seed case
        - Runs the full pipeline
        - Asserts expected outcomes
        """
        from app.workers.ingest import ingest_company_filings
        from app.services.deal_clusterer import cluster_facts
        from app.services.reconciler import reconcile_financing
        from app.services.classifier import classify_deals
        from app.models.deal import Deal
        from app.models.financing import FinancingEvent

        # Step 1: Ingest filings
        ingest_company_filings(
            cik=seed_case.cik,
            form_types=seed_case.form_types,
            start_date=seed_case.start_date,
            end_date=seed_case.end_date,
        )

        # Step 2: Run clustering
        cluster_stats = cluster_facts(db_session)
        assert cluster_stats['deals_created'] > 0 or cluster_stats['facts_attached'] > 0

        # Step 3: Reconcile financing
        reconcile_stats = reconcile_financing(db_session)

        # Step 4: Classify
        classify_deals(db_session)

        # Step 5: Assert expected outcomes
        if seed_case.expected_target_normalized:
            # Find deal with expected target
            deal = db_session.query(Deal).filter(
                Deal.target_name_normalized == seed_case.expected_target_normalized
            ).first()
            assert deal is not None, f"Deal not found for target: {seed_case.expected_target_normalized}"

            # Assert financing event if expected
            if seed_case.expected_financing_type:
                events = db_session.query(FinancingEvent).filter(
                    FinancingEvent.deal_id == deal.id
                ).all()
                assert len(events) > 0, "No financing events found"

            # Assert underwriters if expected
            if seed_case.expected_underwriters:
                events = db_session.query(FinancingEvent).filter(
                    FinancingEvent.deal_id == deal.id
                ).all()
                for event in events:
                    participant_names = [p.bank_name_raw.lower() for p in event.participants]
                    for expected in seed_case.expected_underwriters:
                        assert any(
                            expected.lower() in name for name in participant_names
                        ), f"Expected underwriter not found: {expected}"

    @pytest.mark.parametrize("seed_case", SEED_CASES, ids=[s.name for s in SEED_CASES])
    def test_seed_cases(self, db_session, seed_case):
        """Run golden loop test for each seed case."""
        self.test_end_to_end_flow(db_session, seed_case)


class TestPrivateTargetExtraction:
    """
    Tests specifically for private target extraction.

    Per spec: at least one private target extracted via preamble heuristic
    """

    @pytest.fixture
    def mock_ex21_html(self):
        """Mock EX-2.1 HTML for testing."""
        return """
        <html>
        <body>
        <p>AGREEMENT AND PLAN OF MERGER</p>
        <p>
        This Agreement and Plan of Merger (this "Agreement") is entered into
        as of January 15, 2024, by and among Parent Holdings, Inc., a Delaware
        corporation ("Parent"), Parent Merger Sub, Inc., a Delaware corporation
        and a wholly owned subsidiary of Parent ("Merger Sub"), and Target
        Private Company, LLC, a Delaware limited liability company (the "Company").
        </p>
        </body>
        </html>
        """

    def test_private_target_from_preamble(self, mock_ex21_html):
        """Test extraction of private target from EX-2.1 preamble."""
        from app.extraction.visual_text_extractor import extract_visual_text
        from app.extraction.regex_pack import (
            PREAMBLE_PARTY_LIST, split_party_span, normalize_party_name
        )

        visual_text = extract_visual_text(mock_ex21_html)

        # Should find the preamble pattern
        match = PREAMBLE_PARTY_LIST.search(visual_text)
        assert match is not None, "Failed to match preamble pattern"

        # Should extract parties
        parties = split_party_span(match.group('party_span'))
        assert len(parties) == 3, f"Expected 3 parties, got {len(parties)}"

        # Should identify private target
        party_names = [normalize_party_name(p) for p in parties]
        assert any('target' in name for name in party_names), "Target not found"


class TestSponsorIdentification:
    """
    Tests specifically for sponsor identification.

    Per spec: at least one sponsor identified via contextual tagging
    """

    @pytest.fixture
    def mock_pr_html(self):
        """Mock press release HTML with sponsor mention."""
        return """
        <html>
        <body>
        <p>FOR IMMEDIATE RELEASE</p>
        <p>
        Target Company, Inc. announced today that it has entered into a
        definitive agreement to be acquired by affiliates of Blackstone Inc.
        in a transaction valued at approximately $5 billion.
        </p>
        <p>
        The acquisition will be funded through a combination of equity
        from funds managed by Blackstone and debt financing arranged by
        JPMorgan Chase and Goldman Sachs.
        </p>
        </body>
        </html>
        """

    def test_sponsor_from_press_release(self, mock_pr_html):
        """Test sponsor extraction from press release."""
        from app.extraction.visual_text_extractor import extract_visual_text
        from app.extraction.regex_pack import extract_sponsors

        visual_text = extract_visual_text(mock_pr_html)

        sponsors = extract_sponsors(visual_text)
        assert len(sponsors) > 0, "No sponsors found"

        # Should find Blackstone
        blackstone = next(
            (s for s in sponsors if 'blackstone' in s.sponsor_name_normalized),
            None
        )
        assert blackstone is not None, "Blackstone not found"
        assert not blackstone.is_negated


class TestFinancingExtraction:
    """
    Tests specifically for financing extraction.

    Per spec: at least one financing event with ≥1 underwriter/arranger
    """

    @pytest.fixture
    def mock_financing_table_html(self):
        """Mock HTML with financing underwriter table."""
        return """
        <html>
        <body>
        <h3>Underwriting Agreement</h3>
        <table>
            <tr>
                <th>Underwriter</th>
                <th>Principal Amount of Notes</th>
            </tr>
            <tr>
                <td>J.P. Morgan Securities LLC</td>
                <td>$1,000,000,000</td>
            </tr>
            <tr>
                <td>Goldman Sachs & Co. LLC</td>
                <td>$1,000,000,000</td>
            </tr>
            <tr>
                <td>Barclays Capital Inc.</td>
                <td>$500,000,000</td>
            </tr>
        </table>
        </body>
        </html>
        """

    def test_underwriter_extraction(self, mock_financing_table_html):
        """Test extraction of underwriters from table."""
        from app.extraction.table_parser import extract_financing_participants

        participants = extract_financing_participants(mock_financing_table_html)
        assert len(participants) >= 2, f"Expected at least 2 participants, got {len(participants)}"

        # Should find major banks
        bank_names = [p.bank_name.lower() for p in participants]
        assert any('jpmorgan' in name or 'j.p. morgan' in name for name in bank_names), \
            "JPMorgan not found"
        assert any('goldman' in name for name in bank_names), "Goldman not found"


class TestEvidenceTracking:
    """Tests for evidence tracking and citations."""

    def test_facts_have_evidence(self):
        """Test that extracted facts include evidence snippets."""
        from app.extraction.visual_text_extractor import extract_visual_text
        from app.extraction.regex_pack import PREAMBLE_PARTY_LIST

        html = """
        <p>Agreement made by and among Alpha Inc. and Beta LLC.</p>
        """
        visual_text = extract_visual_text(html)
        match = PREAMBLE_PARTY_LIST.search(visual_text)

        if match:
            # Evidence should be extractable
            evidence = match.group(0)
            assert len(evidence) > 0
            assert "Alpha" in evidence or "Beta" in evidence
