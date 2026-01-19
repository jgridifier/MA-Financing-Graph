"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-01-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    dealstate_enum = postgresql.ENUM(
        'CANDIDATE', 'OPEN', 'CLOSED', 'LOCKED', 'NEEDS_REVIEW',
        name='dealstate', create_type=False
    )
    facttype_enum = postgresql.ENUM(
        'PARTY_MENTION', 'PARTY_DEFINITION', 'SPONSOR_MENTION', 'DEAL_DATE',
        'FINANCING_MENTION', 'ADVISOR_MENTION', 'DEAL_VALUE', 'MANUAL',
        name='facttype', create_type=False
    )
    alerttype_enum = postgresql.ENUM(
        'UNPARSED_MATERIAL_EXHIBIT', 'FAILED_PRIVATE_TARGET_EXTRACTION',
        'FAILED_SPONSOR_EXTRACTION', 'LOW_CONFIDENCE_MATCH',
        'DEAL_MERGE_CANDIDATE', 'UNRESOLVED_BANK',
        name='alerttype', create_type=False
    )
    dealstate_enum.create(op.get_bind(), checkfirst=True)
    facttype_enum.create(op.get_bind(), checkfirst=True)
    alerttype_enum.create(op.get_bind(), checkfirst=True)

    # Filings table
    op.create_table(
        'filings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('accession_number', sa.String(25), nullable=False),
        sa.Column('cik', sa.String(10), nullable=False),
        sa.Column('form_type', sa.String(20), nullable=False),
        sa.Column('filing_date', sa.DateTime(), nullable=False),
        sa.Column('company_name', sa.String(255)),
        sa.Column('filing_url', sa.String(500)),
        sa.Column('index_url', sa.String(500)),
        sa.Column('processed', sa.Boolean(), default=False),
        sa.Column('processed_at', sa.DateTime()),
        sa.Column('raw_html', sa.Text()),
        sa.Column('visual_text', sa.Text()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_filings_accession_number', 'filings', ['accession_number'], unique=True)
    op.create_index('ix_filings_cik', 'filings', ['cik'])
    op.create_index('ix_filings_form_type', 'filings', ['form_type'])
    op.create_index('ix_filings_cik_form_type', 'filings', ['cik', 'form_type'])
    op.create_index('ix_filings_filing_date', 'filings', ['filing_date'])

    # Exhibits table
    op.create_table(
        'exhibits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filing_id', sa.Integer(), nullable=False),
        sa.Column('exhibit_type', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500)),
        sa.Column('filename', sa.String(255)),
        sa.Column('url', sa.String(500)),
        sa.Column('is_pdf', sa.Boolean(), default=False),
        sa.Column('is_material', sa.Boolean(), default=False),
        sa.Column('processed', sa.Boolean(), default=False),
        sa.Column('processed_at', sa.DateTime()),
        sa.Column('extraction_quality', sa.String(20)),
        sa.Column('raw_content', sa.Text()),
        sa.Column('visual_text', sa.Text()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['filing_id'], ['filings.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_exhibits_filing_exhibit_type', 'exhibits', ['filing_id', 'exhibit_type'])

    # Banks table
    op.create_table(
        'banks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('name_normalized', sa.String(255)),
        sa.Column('display_name', sa.String(255)),
        sa.Column('short_name', sa.String(100)),
        sa.Column('is_bulge_bracket', sa.Boolean(), default=False),
        sa.Column('is_regional', sa.Boolean(), default=False),
        sa.Column('primary_market', sa.String(50)),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_banks_name_normalized', 'banks', ['name_normalized'])

    # Bank aliases table
    op.create_table(
        'bank_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_id', sa.Integer(), nullable=False),
        sa.Column('alias', sa.String(255), nullable=False, unique=True),
        sa.Column('alias_normalized', sa.String(255)),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['bank_id'], ['banks.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bank_aliases_alias', 'bank_aliases', ['alias'])
    op.create_index('ix_bank_aliases_normalized', 'bank_aliases', ['alias_normalized'])

    # Deals table
    op.create_table(
        'deals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state', dealstate_enum, default='CANDIDATE', nullable=False),
        sa.Column('acquirer_cik', sa.String(10)),
        sa.Column('acquirer_name_raw', sa.String(500)),
        sa.Column('acquirer_name_display', sa.String(255)),
        sa.Column('acquirer_name_normalized', sa.String(255)),
        sa.Column('target_cik', sa.String(10)),
        sa.Column('target_name_raw', sa.String(500)),
        sa.Column('target_name_display', sa.String(255)),
        sa.Column('target_name_normalized', sa.String(255)),
        sa.Column('deal_key', sa.String(500), unique=True),
        sa.Column('announcement_date', sa.DateTime()),
        sa.Column('agreement_date', sa.DateTime()),
        sa.Column('expected_close_date', sa.DateTime()),
        sa.Column('actual_close_date', sa.DateTime()),
        sa.Column('deal_value_usd', sa.Float()),
        sa.Column('deal_value_evidence', sa.Text()),
        sa.Column('is_sponsor_backed', sa.Boolean()),
        sa.Column('sponsor_name_raw', sa.String(500)),
        sa.Column('sponsor_name_normalized', sa.String(255)),
        sa.Column('sponsor_confidence', sa.Float()),
        sa.Column('sponsor_evidence', postgresql.JSONB()),
        sa.Column('sponsor_entity_id', sa.Integer()),
        sa.Column('unresolved_sponsor_entity', sa.Boolean(), default=False),
        sa.Column('market_tag', sa.String(50)),
        sa.Column('is_cross_border', sa.Boolean(), default=False),
        sa.Column('advisory_fee_estimated', sa.Float()),
        sa.Column('underwriting_fee_estimated', sa.Float()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_deals_acquirer_cik', 'deals', ['acquirer_cik'])
    op.create_index('ix_deals_target_cik', 'deals', ['target_cik'])
    op.create_index('ix_deals_acquirer_target_cik', 'deals', ['acquirer_cik', 'target_cik'])
    op.create_index('ix_deals_acquirer_target_name', 'deals', ['acquirer_cik', 'target_name_normalized'])
    op.create_index('ix_deals_deal_key', 'deals', ['deal_key'], unique=True)
    op.create_index('ix_deals_state', 'deals', ['state'])
    op.create_index('ix_deals_sponsor_name_normalized', 'deals', ['sponsor_name_normalized'])

    # Atomic facts table
    op.create_table(
        'atomic_facts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fact_type', facttype_enum, nullable=False),
        sa.Column('filing_id', sa.Integer()),
        sa.Column('exhibit_id', sa.Integer()),
        sa.Column('deal_id', sa.Integer()),
        sa.Column('evidence_snippet', sa.Text(), nullable=False),
        sa.Column('evidence_start_offset', sa.Integer()),
        sa.Column('evidence_end_offset', sa.Integer()),
        sa.Column('source_section', sa.String(100)),
        sa.Column('extraction_method', sa.String(50)),
        sa.Column('extraction_pattern', sa.String(100)),
        sa.Column('confidence', sa.Float()),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['filing_id'], ['filings.id']),
        sa.ForeignKeyConstraint(['exhibit_id'], ['exhibits.id']),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_atomic_facts_fact_type', 'atomic_facts', ['fact_type'])
    op.create_index('ix_atomic_facts_deal_id', 'atomic_facts', ['deal_id'])
    op.create_index('ix_atomic_facts_deal_type', 'atomic_facts', ['deal_id', 'fact_type'])
    op.create_index('ix_atomic_facts_filing_type', 'atomic_facts', ['filing_id', 'fact_type'])

    # Financing events table
    op.create_table(
        'financing_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('deal_id', sa.Integer(), nullable=False),
        sa.Column('instrument_family', sa.String(50), nullable=False),
        sa.Column('instrument_type', sa.String(50)),
        sa.Column('market_tag', sa.String(50)),
        sa.Column('amount_usd', sa.Float()),
        sa.Column('amount_raw', sa.String(100)),
        sa.Column('currency', sa.String(10), default='USD'),
        sa.Column('maturity_date', sa.DateTime()),
        sa.Column('interest_rate', sa.String(100)),
        sa.Column('spread_bps', sa.Integer()),
        sa.Column('purpose', sa.String(100)),
        sa.Column('reconciliation_confidence', sa.Float()),
        sa.Column('reconciliation_explanation', sa.Text()),
        sa.Column('source_exhibit_id', sa.Integer()),
        sa.Column('source_fact_ids', postgresql.JSONB()),
        sa.Column('estimated_fee_usd', sa.Float()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id']),
        sa.ForeignKeyConstraint(['source_exhibit_id'], ['exhibits.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financing_events_deal_id', 'financing_events', ['deal_id'])
    op.create_index('ix_financing_events_deal_type', 'financing_events', ['deal_id', 'instrument_family'])

    # Financing participants table
    op.create_table(
        'financing_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('financing_event_id', sa.Integer(), nullable=False),
        sa.Column('bank_id', sa.Integer()),
        sa.Column('bank_name_raw', sa.String(255), nullable=False),
        sa.Column('bank_name_normalized', sa.String(255)),
        sa.Column('role', sa.String(100), nullable=False),
        sa.Column('role_normalized', sa.String(50)),
        sa.Column('evidence_snippet', sa.Text()),
        sa.Column('evidence_source', sa.String(50)),
        sa.Column('table_cell_coords', postgresql.JSONB()),
        sa.Column('role_weight', sa.Float()),
        sa.Column('estimated_fee_usd', sa.Float()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['financing_event_id'], ['financing_events.id']),
        sa.ForeignKeyConstraint(['bank_id'], ['banks.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_financing_participants_bank', 'financing_participants', ['bank_id'])
    op.create_index('ix_financing_participants_event_role', 'financing_participants', ['financing_event_id', 'role'])

    # Processing alerts table
    op.create_table(
        'processing_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_type', alerttype_enum, nullable=False),
        sa.Column('filing_id', sa.Integer()),
        sa.Column('exhibit_id', sa.Integer()),
        sa.Column('deal_id', sa.Integer()),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('exhibit_link', sa.String(500)),
        sa.Column('fields_needed', postgresql.JSONB()),
        sa.Column('preamble_hash', sa.String(64)),
        sa.Column('preamble_preview', sa.Text()),
        sa.Column('is_resolved', sa.Boolean(), default=False),
        sa.Column('resolved_at', sa.DateTime()),
        sa.Column('resolved_by', sa.String(100)),
        sa.Column('resolution_notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['filing_id'], ['filings.id']),
        sa.ForeignKeyConstraint(['exhibit_id'], ['exhibits.id']),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_processing_alerts_alert_type', 'processing_alerts', ['alert_type'])

    # Manual inputs table
    op.create_table(
        'manual_inputs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alert_id', sa.Integer()),
        sa.Column('deal_id', sa.Integer()),
        sa.Column('financing_event_id', sa.Integer()),
        sa.Column('input_type', sa.String(50), nullable=False),
        sa.Column('data', postgresql.JSONB(), nullable=False),
        sa.Column('entered_by', sa.String(100), nullable=False),
        sa.Column('entered_at', sa.DateTime(), nullable=False),
        sa.Column('notes', sa.Text()),
        sa.Column('verified', sa.DateTime()),
        sa.Column('verified_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['alert_id'], ['processing_alerts.id']),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id']),
        sa.ForeignKeyConstraint(['financing_event_id'], ['financing_events.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('manual_inputs')
    op.drop_table('processing_alerts')
    op.drop_table('financing_participants')
    op.drop_table('financing_events')
    op.drop_table('atomic_facts')
    op.drop_table('deals')
    op.drop_table('bank_aliases')
    op.drop_table('banks')
    op.drop_table('exhibits')
    op.drop_table('filings')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS alerttype')
    op.execute('DROP TYPE IF EXISTS facttype')
    op.execute('DROP TYPE IF EXISTS dealstate')
