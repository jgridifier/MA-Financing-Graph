#!/usr/bin/env python
"""
Script to ingest seed deals from test_set.md.

Loads deals from deliverables/seed_deals.json and ingests
filings for each CIK to populate the database with test data.
"""
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.base import SessionLocal
from app.workers.ingest import ingest_company_filings
from app.services.deal_clusterer import cluster_facts
from app.services.reconciler import reconcile_financing
from app.services.classifier import classify_deals
from app.services.attribution import calculate_fees
from app.services.bank_resolver import seed_banks


def load_seed_deals():
    """Load seed deals from JSON file."""
    seed_path = Path(__file__).parent.parent.parent / "deliverables" / "seed_deals.json"
    with open(seed_path) as f:
        data = json.load(f)
    return data.get('seed_deals', [])


def ingest_all_seed_deals():
    """Ingest all seed deals."""
    db = SessionLocal()

    try:
        # First seed banks
        print("Seeding bank data...")
        seed_banks(db)

        # Load seed deals
        seed_deals = load_seed_deals()
        print(f"Found {len(seed_deals)} seed deals")

        # Track CIKs we've already processed
        processed_ciks = set()

        for deal in seed_deals:
            print(f"\n{'='*60}")
            print(f"Processing: {deal['name']}")
            print(f"Test case: {deal.get('test_case', 'N/A')}")

            # Get CIKs to ingest
            target = deal.get('target', {})
            acquirer = deal.get('acquirer', {})

            ciks_to_process = []
            if target.get('cik') and target['cik'] not in processed_ciks:
                ciks_to_process.append(target['cik'])
            if acquirer.get('cik') and acquirer['cik'] not in processed_ciks:
                ciks_to_process.append(acquirer['cik'])

            form_types = deal.get('form_types', ['8-K', 'S-4', 'DEFM14A'])

            for cik in ciks_to_process:
                print(f"  Ingesting CIK: {cik}")
                try:
                    ingest_company_filings(
                        cik=cik,
                        form_types=form_types,
                    )
                    processed_ciks.add(cik)
                except Exception as e:
                    print(f"  Error ingesting {cik}: {e}")

        # Run pipeline
        print("\n" + "="*60)
        print("Running pipeline...")

        print("  Clustering facts...")
        cluster_stats = cluster_facts(db)
        print(f"    Created {cluster_stats.get('deals_created', 0)} deals")

        print("  Reconciling financing...")
        reconcile_stats = reconcile_financing(db)

        print("  Classifying deals...")
        classify_stats = classify_deals(db)

        print("  Calculating fees...")
        fee_stats = calculate_fees(db)

        print("\n" + "="*60)
        print("Ingestion complete!")
        print(f"  Total CIKs processed: {len(processed_ciks)}")

    except Exception as e:
        print(f"Error during ingestion: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    print("M&A Financing Graph - Seed Deal Ingestion")
    print("="*60)

    ingest_all_seed_deals()


if __name__ == "__main__":
    main()
