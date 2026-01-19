"""
SEC EDGAR API Client with mandatory User-Agent compliance and rate limiting.

SEC Requirements:
- User-Agent must include application name and admin email
- Rate limiting: 10 requests per second max
- Exponential backoff on 429/403 responses
"""
import time
import hashlib
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings


class SECRateLimitError(Exception):
    """Raised when SEC rate limit is hit."""
    pass


class SECBlockedError(Exception):
    """Raised when SEC blocks the request (403)."""
    pass


class EdgarClient:
    """
    Client for SEC EDGAR API with compliance requirements.

    Features:
    - Mandatory User-Agent header
    - Rate limiting (10 req/sec)
    - Exponential backoff on 429/403
    - Response caching by URL
    """

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.SEC_BASE_URL
        self.user_agent = settings.sec_user_agent
        self.rate_limit_requests = settings.SEC_RATE_LIMIT_REQUESTS
        self.rate_limit_window = settings.SEC_RATE_LIMIT_WINDOW

        # Rate limiting state
        self._request_times: list[float] = []
        self._cache: dict[str, tuple[str, datetime]] = {}
        self._cache_ttl = 3600  # 1 hour cache

        # HTTP client
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client with required headers."""
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    def _wait_for_rate_limit(self):
        """Enforce rate limiting by waiting if necessary."""
        now = time.time()
        # Remove old request times
        self._request_times = [
            t for t in self._request_times
            if now - t < self.rate_limit_window
        ]

        if len(self._request_times) >= self.rate_limit_requests:
            # Wait until oldest request expires
            sleep_time = self.rate_limit_window - (now - self._request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._request_times.append(time.time())

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL."""
        return hashlib.md5(url.encode()).hexdigest()

    def _get_cached(self, url: str) -> Optional[str]:
        """Get cached response if valid."""
        key = self._get_cache_key(url)
        if key in self._cache:
            content, cached_at = self._cache[key]
            if (datetime.utcnow() - cached_at).total_seconds() < self._cache_ttl:
                return content
            del self._cache[key]
        return None

    def _set_cached(self, url: str, content: str):
        """Cache response."""
        key = self._get_cache_key(url)
        self._cache[key] = (content, datetime.utcnow())

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((SECRateLimitError, httpx.TimeoutException)),
    )
    def fetch(self, url: str, use_cache: bool = True) -> str:
        """
        Fetch content from SEC EDGAR.

        Args:
            url: Full URL or path relative to SEC base
            use_cache: Whether to use cached responses

        Returns:
            Response content as string

        Raises:
            SECRateLimitError: On 429 response
            SECBlockedError: On 403 response
            httpx.HTTPError: On other HTTP errors
        """
        # Normalize URL
        if not url.startswith("http"):
            url = urljoin(self.base_url, url)

        # Check cache
        if use_cache:
            cached = self._get_cached(url)
            if cached is not None:
                return cached

        # Rate limit
        self._wait_for_rate_limit()

        # Make request
        client = self._get_client()
        response = client.get(url)

        # Handle rate limiting and blocking
        if response.status_code == 429:
            raise SECRateLimitError(f"Rate limited by SEC: {url}")
        if response.status_code == 403:
            raise SECBlockedError(
                f"Blocked by SEC (403). Check User-Agent compliance: {self.user_agent}"
            )

        response.raise_for_status()
        content = response.text

        # Cache successful response
        if use_cache:
            self._set_cached(url, content)

        return content

    def fetch_filing_index(self, accession_number: str, cik: str) -> str:
        """
        Fetch filing index page.

        Args:
            accession_number: e.g., "0001193125-24-012345"
            cik: Company CIK (padded to 10 digits)
        """
        # Format accession number (remove dashes for URL)
        acc_no_fmt = accession_number.replace("-", "")
        cik_padded = cik.zfill(10)
        url = f"/Archives/edgar/data/{cik_padded}/{acc_no_fmt}/{accession_number}-index.htm"
        return self.fetch(url)

    def fetch_document(self, cik: str, accession_number: str, document_name: str) -> str:
        """
        Fetch a specific document from a filing.

        Args:
            cik: Company CIK
            accession_number: Filing accession number
            document_name: Document filename
        """
        acc_no_fmt = accession_number.replace("-", "")
        cik_padded = cik.zfill(10)
        url = f"/Archives/edgar/data/{cik_padded}/{acc_no_fmt}/{document_name}"
        return self.fetch(url)

    def search_filings(
        self,
        cik: str,
        form_types: list[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for filings using EDGAR full-text search API.

        Args:
            cik: Company CIK
            form_types: List of form types (e.g., ["8-K", "S-4"])
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of filing metadata dicts
        """
        # Use submissions endpoint for company filings
        cik_padded = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        content = self.fetch(url)

        import json
        data = json.loads(content)

        filings = []
        recent = data.get("filings", {}).get("recent", {})

        if not recent:
            return filings

        # Zip together the filing data
        accession_numbers = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        descriptions = recent.get("primaryDocDescription", [])

        for i, (acc, form, date, doc, desc) in enumerate(
            zip(accession_numbers, forms, filing_dates, primary_docs, descriptions)
        ):
            # Filter by form type
            if form_types and form not in form_types:
                continue

            # Filter by date range
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue

            filings.append({
                "accession_number": acc,
                "form_type": form,
                "filing_date": date,
                "primary_document": doc,
                "description": desc,
                "cik": cik,
                "company_name": data.get("name"),
            })

        return filings

    def get_company_info(self, cik: str) -> dict:
        """Get company information from SEC."""
        cik_padded = cik.zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        content = self.fetch(url)

        import json
        data = json.loads(content)

        return {
            "cik": cik,
            "name": data.get("name"),
            "sic": data.get("sic"),
            "sic_description": data.get("sicDescription"),
            "tickers": data.get("tickers", []),
            "exchanges": data.get("exchanges", []),
        }

    def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Singleton instance
_client: Optional[EdgarClient] = None


def get_edgar_client() -> EdgarClient:
    """Get singleton EDGAR client instance."""
    global _client
    if _client is None:
        _client = EdgarClient()
    return _client
