# M&A Financing Graph

SEC EDGAR M&A Deal and Debt Financing Analysis Application

## Overview

This application ingests SEC EDGAR filings and extracts:
- M&A deal parties and timeline
- Financial advisor banks and roles
- Debt financing events (loans/bonds/bridge) and underwriting syndicates
- Specialized classification (sponsor vs non-sponsor LevFin; HY vs IG)
- Modeled advisory vs underwriting revenue attribution by bank

All outputs are evidence-backed with citations and snippets from source documents.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- Node.js 20+ (for frontend development)

### Running with Docker Compose

```bash
# Clone the repository
git clone <repository-url>
cd MA-Financing-Graph

# Create environment file
cp backend/.env.example backend/.env
# Edit .env with your email for SEC compliance

# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec backend alembic upgrade head

# Seed initial bank data
docker-compose exec backend python -c "from app.db.base import SessionLocal; from app.services.bank_resolver import seed_banks; db = SessionLocal(); seed_banks(db)"
```

The application will be available at:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Local Development

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Copy and edit environment
cp .env.example .env
# Edit .env with your email

# Start Postgres and Redis (using Docker)
docker compose up -d db redis

# Run migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload

# Frontend setup (in another terminal)
cd frontend
npm install
npm run dev
```

## Architecture

### Pipeline Stages

1. **Ingestion** → Raw filings/docs/exhibits from SEC EDGAR
2. **Document Processor** → Parse HTML/text/PDF + extract tables
3. **Atomic Fact Extraction** → Emit facts with evidence (no deal_id yet)
4. **Deal Clusterer** → Creates/updates Deals by clustering facts
5. **Reconciler** → Links financing events to Deals
6. **Classifier** → Tags sponsor/LevFin and product taxonomy
7. **Attribution Engine** → Modeled fees using JSON config

### Key Components

- **VisualTextExtractor**: Handles EDGAR HTML normalization including smart quote/dash replacement
- **regex_pack.py**: Centralized patterns for preamble, sponsor, and amount extraction
- **Table Parser**: Extracts bank roles from underwriting/syndicate tables
- **Deal Clusterer**: Groups facts into deals using (acquirer_cik, target_cik) or name-based keys

## API Endpoints

### Deals
- `GET /api/deals` - List deals with filtering
- `GET /api/deals/{id}` - Get deal details
- `GET /api/deals/{id}/financing` - Get financing events
- `GET /api/deals/{id}/advisors` - Get financial advisors

### Filings
- `GET /api/filings` - List filings
- `POST /api/filings/ingest` - Trigger filing ingestion for a CIK

### Alerts
- `GET /api/alerts` - List processing alerts
- `GET /api/alerts/unresolved` - Get unresolved alerts
- `POST /api/alerts/{id}/resolve` - Mark alert as resolved

### Pipeline
- `POST /api/pipeline/run` - Run full processing pipeline

## Configuration

### SEC User-Agent Compliance

The application requires valid `APP_NAME` and `ADMIN_EMAIL` environment variables for SEC EDGAR API compliance. The app will fail to start if these are not configured.

Format: `{APP_NAME} {ADMIN_EMAIL}` (e.g., `MAFinancingApp user@example.com`)

### Attribution Config

Fee calculations use `config/attribution_config.json`:

```json
{
  "advisory_fee_bps": {
    "default": 100,
    "deal_size_over_1B": 85,
    "deal_size_over_5B": 70
  },
  "underwriting_fee_bps": {
    "IG_Bond": 45,
    "HY_Bond": 125,
    "Term_Loan_B": 200
  }
}
```

## Testing

```bash
cd backend

# Unit tests
pytest tests/unit -v

# Integration tests (requires database)
pytest tests/integration -v

# All tests with coverage
pytest --cov=app tests/
```

## Seed Deals

The `deliverables/seed_deals.json` file contains test cases covering:
- Private target extraction
- Sponsor identification
- Bond underwriter table extraction
- Loan arranger extraction
- Cross-border deals
- Bridge-to-bond transitions

## Human-in-the-Loop

Material PDF exhibits that fail parsing create `ProcessingAlert` records. The UI allows users to:
1. View unresolved alerts
2. Access the original exhibit
3. Manually input missing data
4. Mark alerts as resolved

Manual inputs feed into the reconciler, classifier, and attribution engine.

## Success Criteria

Per the specification, implementation is successful when:

1. ✅ Ingest real EDGAR filings for at least 20 real M&A deals
2. ✅ Extract ≥1 financial advisor with citation for 10+ deals
3. ✅ Identify ≥1 financing event with underwriter/arranger for 10+ deals
4. ✅ Reconciliation produces matched financing with confidence
5. ✅ UI supports search, deal pages, advisors/underwriters, EDGAR links
6. ✅ No synthetic data; everything grounded with traceable evidence
7. ✅ Backend includes caching/rate limiting for SEC compliance
8. ✅ Reproducible dev setup with Docker Compose

## License

MIT
