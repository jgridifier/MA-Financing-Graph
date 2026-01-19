"""
M&A Financing Graph API

FastAPI application for SEC EDGAR M&A deal and financing analysis.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.services.attribution import get_attribution_config
from app.api import deals, filings, alerts


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Validates configuration on startup (fail-fast).
    """
    # Validate settings
    settings = get_settings()
    print(f"Starting {settings.APP_NAME}")
    print(f"SEC User-Agent: {settings.sec_user_agent}")

    # Validate attribution config
    try:
        config = get_attribution_config()
        print("Attribution config loaded successfully")
    except Exception as e:
        print(f"FATAL: Attribution config error: {e}")
        raise

    yield

    # Cleanup
    print("Shutting down")


app = FastAPI(
    title="M&A Financing Graph API",
    description="API for analyzing SEC EDGAR M&A deals and debt financing",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(deals.router, prefix="/api")
app.include_router(filings.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": "M&A Financing Graph API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/search")
def search(q: str, limit: int = 20):
    """
    Global search across deals, companies, and banks.

    Returns combined results from multiple entities.
    """
    from app.db.base import SessionLocal
    from app.models.deal import Deal
    from sqlalchemy import or_

    db = SessionLocal()
    try:
        search_term = f"%{q.lower()}%"

        # Search deals
        deal_results = db.query(Deal).filter(
            or_(
                Deal.target_name_display.ilike(search_term),
                Deal.acquirer_name_display.ilike(search_term),
                Deal.sponsor_name_raw.ilike(search_term),
            )
        ).limit(limit).all()

        return {
            "query": q,
            "results": {
                "deals": [
                    {
                        "id": d.id,
                        "type": "deal",
                        "title": f"{d.acquirer_name_display or 'Unknown'} / {d.target_name_display or 'Unknown'}",
                        "subtitle": d.market_tag,
                    }
                    for d in deal_results
                ],
            },
            "total": len(deal_results),
        }
    finally:
        db.close()


@app.post("/api/pipeline/run")
async def run_pipeline():
    """
    Run the full processing pipeline.

    Steps:
    1. Cluster unclustered facts
    2. Reconcile financing
    3. Classify deals and events
    4. Calculate fees
    """
    from app.db.base import SessionLocal
    from app.services.deal_clusterer import cluster_facts
    from app.services.reconciler import reconcile_financing
    from app.services.classifier import classify_deals
    from app.services.attribution import calculate_fees

    db = SessionLocal()
    try:
        results = {}

        # Step 1: Cluster facts
        results['clustering'] = cluster_facts(db)

        # Step 2: Reconcile financing
        results['reconciliation'] = reconcile_financing(db)

        # Step 3: Classify
        results['classification'] = classify_deals(db)

        # Step 4: Attribution
        results['attribution'] = calculate_fees(db)

        return {
            "status": "completed",
            "results": results,
        }
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
