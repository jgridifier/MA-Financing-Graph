## Prompt for Coding Agent: SEC-EDGAR M&A + Debt Financing App (Regex-First, Private Target + Sponsor Heuristics, Visual Text Extraction, Human-in-the-Loop PDFs, End-to-End Tests)

### Objective

Build an end-to-end web application (FastAPI backend + frontend) that ingests **real SEC EDGAR filings** and enables users to search M&A deals and see:

* deal parties and timeline
* M&A advisor banks and roles
* debt financing events (loans/bonds/bridge) and underwriting/arranging syndicates + roles
* specialized classification (sponsor vs non-sponsor LevFin; HY vs IG; bond vs loan; TLB vs RCF; bridge-to-bond)
* modeled advisory vs underwriting revenue attribution by bank (config-driven)

All outputs must be **evidence-backed** (citations/snippets/table cell coordinates). **No synthetic or fake data**.

---

# 1) Pipeline Logic (Strict Separation of Concerns)

**Key Rule:** Document processing and extraction emits **Atomic Facts only**. It must **not** attempt to create Deals.

**Stages**

1. Ingestion → raw filings/docs/exhibits
2. Document Processor → parse HTML/text/PDF + extract tables to Table IR
3. Atomic Fact Extraction → emit facts with evidence (no deal_id yet)
4. Deal Clusterer (Deal Builder) → creates/updates Deals by clustering facts (stateful)
5. Reconciler → links financing events to Deals using deal_id
6. Classifier → tags sponsor/LevFin and product taxonomy
7. Attribution Engine → modeled fees using JSON config

**Mental model**

* Document Processor: “I see a document; I extract facts.”
* Clusterer: “I group facts into deals and assign deal_id.”
* Reconciler: “I attach financing facts to deals.”

---

# 2) Atomic Fact Extraction (Document-Level): Private Target Heuristics (CRITICAL)

### Problem

Many deals have **private targets** (no CIK). If clustering depends only on (Acquirer CIK + Target CIK), it fails and financing reconciliation breaks.

### Required Change

Implement a “Party Identification in Absence of CIK” subtask in Atomic Fact Extraction. Mandatory for **EX-2.1** and **8-K Item 1.01**.

---

## 2A) Critical Sub-Task: Party Identification in Absence of CIK

When parsing EX-2.1 (Merger Agreement) and/or 8-K Item 1.01 and **no Target CIK is found**, extract the Target legal name from the agreement **preamble and definitions**.

### Step 0 (MANDATORY): Visual Text Extraction + Normalization (to avoid EDGAR HTML traps)

#### Crucial Implementation Note: Visual Text Extraction

Do **not** rely on `<p>` tags. EDGAR HTML is often non-semantic and uses `<div>`, `<font>`, `<br><br>`, etc.

You must implement a `VisualTextExtractor` that:

* Iterates over HTML elements and emits a “visual text” buffer.
* Inserts `\n\n` (double newlines) at block-level boundaries and visual separators:

  * tags: `div`, `p`, `br`, `tr`, `li`, `h1-h6`, `table` (start/end), and between table rows
* Strips **formatting tags** but preserves inner text:

  * remove/unwrap: `b`, `strong`, `i`, `em`, `font`, `span`, `u`, `sup`, `sub`
* Normalizes whitespace:

  * collapse multiple spaces/tabs to single spaces
  * collapse more than 2 newlines down to `\n\n`
* **Normalizes punctuation before regex**:

  * Replace smart quotes and apostrophes with ASCII:

    * `“ ”` → `"`
    * `‘ ’` → `'`
  * Replace en/em dashes with ASCII hyphen:

    * `– —` → `-`
  * Replace non-breaking space `\xa0` with space

* **Table Cell Handling**: When iterating `td` or `th` tags, append a **space** or **pipe** (`|`) to the buffer at the end of the cell, *unless* the cell already ends in punctuation or a newline. This prevents "PartyAPartyB" fusion.

Run all preamble regex only on this normalized “visual text” buffer. Use only the first **5,000 characters** of this buffer for preamble extraction.

### Step 1: Identify the “Preamble Paragraph”

* For EX-2.1:

  * Search the first 5,000 chars of visual text for:

    * “AGREEMENT AND PLAN OF MERGER” or “PLAN OF MERGER”
    * and “by and among” / “by and between”
* For 8-K Item 1.01:

  * Search for the first paragraph describing the definitive agreement (“entered into an Agreement and Plan of Merger…”), again using visual text.

### Step 2: Apply Regex/Pattern Heuristics for Party Lists

Implement patterns (case-insensitive, whitespace-flexible) from **Appendix A**:

* `PREAMBLE_PARTY_LIST` to capture the party span after “by and among/between …”
* `DEFINED_TERM_ROLE` to capture role definitions like (the "Company"), ("Parent"), etc.

### Step 3: Assign Roles and Pick the Private Target

If Target CIK is missing, define:

* `target_name_raw`: full legal name extracted
* `target_name_display`: lightly cleaned for UI
* `target_name_normalized`: normalized string used for clustering/reconciliation

**Normalization rules**

* Strip common suffixes/noise:

  * Inc, Incorporated, Corp, Corporation, LLC, L.L.C., Ltd, Limited, Co., Company, LP, L.P., LLP, PLC
* Remove trailing jurisdictional descriptors:

  * “a Delaware corporation”, “a [State] limited liability company”
* Collapse whitespace; trim punctuation; keep meaningful tokens

**Role assignment logic**

* If an entity is explicitly defined as “Company”, treat as **Target** (highest confidence).
* If a 3-party list exists and only one party is labeled “Company”, select that as target.
* If definitions are missing but list has three parties:

  * treat the last party in “..., and [Party C]” as target candidate with lower confidence.

### Step 4: Emit Atomic Facts

Emit:

* `PartyMention` facts for each party extracted with role hints and evidence snippet offsets.
* `PartyDefinitionFact` for labeled roles:

  * payload includes: `party_name_raw`, `party_name_normalized`, `role_label` (Company/Parent/Merger Sub), `confidence`

**Acceptance criteria**

* For private-target deals, the clusterer must be able to form a Deal Key using:

  * `(acquirer_cik, target_name_normalized)`.
  
## 2B) Date Extraction
Extract the "**Agreement Date**" from the Preamble.

Heuristic: Look for the phrase "dated as of [Date]" or "entered into on [Date]" within the first 1,000 characters of the visual text buffer.

**Normalization**: Convert all extracted dates to ISO 8601 (`YYYY-MM-DD`).

**Fact**: Emit a `DealDateFact` linked to the document.

---

# 3) Sponsor Entity Logic: Sponsor is a Deal Attribute, Not a Signatory (CRITICAL)

### Problem

PE sponsors are rarely signatories. If extracted only from signatory blocks, sponsor will be missed.

### Required Change

Implement sponsor identification as a **Deal-level contextual tag** derived from documents.

## 3A) Sponsor vs Non-Sponsor Tagging: Sponsor Entity Logic

### Step 1: Search Locations (High-yield sections)

Search:

* “Background of the Merger” (S-4 / DEFM14A)
* Press release exhibits (EX-99.*)
* Equity Commitment Letter exhibits (often EX-10.*)
* sometimes 8-K Item 1.01 narrative

### Step 2: Sponsor Name Recognition Approach (Two-tier)

**Tier 1: Seed list exact/alias match (required)**
Maintain a seed list (expandable):
Blackstone, KKR, Apollo, Carlyle, Thoma Bravo, TPG, Advent, Bain Capital, Warburg Pincus, Silver Lake, Vista Equity, Clayton Dubilier & Rice (CD&R), CVC, EQT, Brookfield, Permira.

Detect these names/aliases in context windows around:

* “affiliates of”, “managed by”, “funds affiliated with”, “sponsor”, “financial sponsor”, “private equity”

Emit `SponsorMentionFact` with evidence.

**Tier 2: Pattern-based extraction (required)**
If no seed sponsor found, detect sponsor-backed structure via patterns (Appendix A `SPONSOR_AFFILIATION`):

* “funds managed by [X]”
* “affiliates of [X]”
* “portfolio company of [X]”
* “financial sponsor” (supporting evidence; do not force a sponsor_name unless an entity is captured)

If pattern captures an entity not in seed list:

* store `sponsor_name_raw`
* mark `unresolved_sponsor_entity=true` for later curation

### Context Window Definition (MANDATORY)

When searching for sponsor keywords or patterns:

* Extract a **context snippet** of +/- **150 characters** around the match.
* **Negative phrase constraint**: do not treat as sponsor evidence if snippet contains negations like:

  * “not a financial sponsor”
  * “independent of any sponsor”
  * “no sponsor”
* Store context snippet in `deal.sponsor_evidence` (doc pointers + snippet text).

### Step 3: Storage Model (explicit)

Store sponsor separately from acquirer:

* `deal.sponsor_name_raw`
* `deal.sponsor_name_normalized`
* `deal.sponsor_confidence`
* `deal.sponsor_evidence` (doc pointers + context snippet)
* `deal.sponsor_entity_id` (nullable; resolve via alias table if possible)

Do not conflate sponsor with “Merger Sub” or the legal acquirer entity.

### Step 4: Sponsor-backed Classification Output

Set:

* `deal.is_sponsor_backed ∈ {true,false,unknown}`
  based on:
* positive sponsor mentions or equity commitment references → true
* explicit strategic acquirer language without sponsor signals → false (conservative; default unknown if unclear)

---

# 4) Deal Clusterer: Deal Keys and Incremental Updates

### Deal Key Construction Rules

A Deal must have a stable clustering key:

1. Preferred: `(acquirer_cik, target_cik)`
2. If target_cik missing: `(acquirer_cik, target_name_normalized)`
3. If acquirer_cik missing (rare): `(acquirer_name_normalized, target_name_normalized)` and flag `NeedsReview`.

### Join Logic for Financing Reconciliation

Financing documents may reference:

* target name
* acquisition vehicle name
* sponsor name
* acquirer name

Reconciler must use:

* `target_name_normalized` match as **strong** signal
* `sponsor_name` match as **weak-to-moderate** supporting evidence only

### Stateful Clustering Lifecycle (required)

Implement a `DealClusteringService` that runs periodically or on-demand and:

* scans `atomic_fact` where `deal_id IS NULL`
* attaches to existing deals by key matching
* creates CandidateDeals when no match exists
* if match exists but deal is closed/locked, flag manual review
* supports merging CandidateDeals (audit trail) if later filings show same deal

Deals must have states:

* `CANDIDATE`, `OPEN`, `CLOSED`, `LOCKED`, `NEEDS_REVIEW`

---

# 5) Table Parsing Strategy (Robust EDGAR Tables + Role Column Heuristic)

Retain mandated table extraction:

* Try `pandas.read_html(..., flavor="bs4")` first
* fallback custom extraction
* build a canonical **Table IR** expanding rowspan/colspan
* header heuristics required

**Add required heuristic: Role-column detection**
If one column has high density of role keywords (bookrunner, underwriter, arranger, agent), treat as `role_column` and map adjacent bank names to that role.

---

# 6) Golden Test Set Requirement (Do Not Enumerate Here)

You will be provided externally with a seed set of deals/CIKs/date ranges that exercise:

* private target extraction from EX-2.1
* sponsor identification via contextual tagging
* bond underwriter table extraction
* loan arranger extraction from credit agreement exhibits

Integration tests must run ingestion + parsing + fact extraction + clustering + reconciliation and assert:

* at least one private target extracted via preamble heuristic
* at least one sponsor identified via contextual tagging
* at least one financing event with ≥1 underwriter/arranger extracted with evidence pointers

See `test_set.md` for instructions on the specific deals for the test set.

---

# 7) Human-in-the-Loop for Material PDF Exhibits

### Problem

Commitment letters and credit agreements are frequently PDFs and may be unreadable/scanned. Missing these breaks financing extraction.

### Required Behavior

If an exhibit is **material** (description/filename matches: Credit Agreement, Commitment Letter, Bridge, Debt Financing, Underwriting Agreement, Indenture) and is PDF:

1. Attempt PDF text extraction with `pdfplumber`.
2. If extraction fails or is low quality:

   * Create a `ProcessingAlert` record:

     * `alert_type=UNPARSED_MATERIAL_EXHIBIT`
     * include exhibit link, filing accession, and fields needed (facility type, amount, participants, roles, purpose)
3. UI must display alerts and allow a user to manually input missing data.
4. Manual inputs must be stored as `MANUAL` facts with audit metadata (user, timestamp, note) and feed:

   * reconciler
   * classifier
   * attribution engine

---

# 8) Regex Quality Requirements (Mandatory Deliverables)

Because EDGAR narrative text is messy, regex quality is a first-class deliverable.

### Mandatory Deliverables

1. **Centralized Regex Pack**

   * Implement `regex_pack.py` with named compiled patterns from Appendix A
   * Document each pattern and intended scope

2. **Regex Regression Test Harness**

   * Include “golden snippets” fixtures for:

     * EX-2.1 preamble variants
     * Item 1.01 definitive agreement paragraph variants
     * sponsor mention variants
   * Tests must validate:

     * correct target extraction (raw + normalized)
     * correct role label extraction (Company/Parent/Merger Sub)
     * correct sponsor mention extraction, including negative phrase exclusion

3. **Observability for Regex Failures**

   * On failure to extract private target from EX-2.1 preamble:

     * create `ProcessingAlert` `FAILED_PRIVATE_TARGET_EXTRACTION`
     * store a pointer to the preamble window (hash + doc pointer) or first N characters (sanitized)

---

# 9) Revenue Attribution Schema (Config-Driven, Fail-Fast)

Use a JSON configuration file loaded at runtime:

* app fails to start if missing/invalid
* attribution bps selected based on classifier `market_tag`
* do not hardcode bps in code

Minimum required schema:

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
    "Term_Loan_B": 200,
    "Other_Loan": 125,
    "Bridge": 150,
    "Unknown": 100
  },
  "role_splits": {
    "bond": {
      "joint_bookrunner": 0.45,
      "bookrunner": 0.40,
      "co_manager": 0.15
    },
    "loan": {
      "lead_arranger": 0.50,
      "joint_lead_arranger": 0.35,
      "admin_agent": 0.05,
      "other": 0.10
    },
    "advisory": {
      "lead": 0.60,
      "co_advisor": 0.40
    }
  },
  "thresholds": {
    "fuzzy_bank_match_min": 92
  }
}
```

---

# 10) SEC User-Agent Compliance (Fail-Fast)

Hard requirement:

* All HTTP requests to SEC must include:

  * `User-Agent: {APP_NAME} {ADMIN_EMAIL}`
* `APP_NAME` and `ADMIN_EMAIL` are environment variables.
* The application must fail to start if either is missing.

**Format**: The User-Agent string **must** follow this exact format for testing: MAFinancingApp jgridley.mailinglists@gmail.com (The SEC is extremely strict. If you don't follow their exact format, they will block the IP immediately with a 403 Forbidden response).

**Validation**: The app **must** assert that the email address is valid and the string format is correct on startup annd fail to start if either are missing.

Also implement:

* rate limiting + exponential backoff for 429/403 responses
* caching by accession/document URL

---

# 11) Success Criteria (Keep These)

Implementation is successful only if:

1. Ingest real EDGAR filings for at least **20 real M&A deals** across multiple issuers and build searchable deal objects.
2. For at least **10 deals**, correctly extract **≥1 financial advisor** with a citation snippet.
3. For at least **10 deals**, identify **≥1 financing event** and extract **≥1 underwriter/arranger** with citation snippet(s).
4. Reconciliation produces matched financing with confidence + explanation.
5. UI supports search, deal pages, advisors/underwriters, EDGAR source links.
6. No synthetic data; everything grounded with traceable evidence.
7. Backend includes caching/rate limiting and does not get blocked by SEC endpoints under normal usage.
8. Reproducible dev setup (Docker Compose) running backend + worker + frontend + DB.

At the ennd your development cycle, a user should be able to clone the repo and launch the app locally with just a few commands.

---

# 12) Implementation Notes (Keep These)

Preferred stack:

* Python: FastAPI, httpx/requests, BeautifulSoup/lxml, RapidFuzz, SQLAlchemy, Alembic
* Jobs: RQ/Redis
* DB: Postgres
* Frontend: Next.js/React

---

# 13) Deliverables (Include “Golden Loop” Integration Test Harness)

### Repo deliverables

* `backend/`, `frontend/`, `docker-compose.yml`, `README.md`
* Unit tests:

  * table extraction tests using real EDGAR HTML samples
  * bank resolver tests (alias + fuzzy threshold)
  * regex pack tests (Appendix A patterns)
* Integration tests:

  * ingestion + parsing + atomic facts + clustering + reconciliation

### Integration Test: The “Golden Loop” (MANDATORY)

Implement a generic integration test function:

* `test_end_to_end_flow(seed_case)`

  * ingests filings for provided seed case (CIK/date range/doc type)
  * runs the full pipeline
  * asserts:

    * a Deal exists with `target_name_normalized == expected_target` (or target_cik where applicable)
    * at least one Financing Event is linked to that Deal
    * financing participants include an expected underwriter/arranger list element (role-aware if provided)

**Note:** Seed data for the integration test will be provided externally; the test function must be generic and accept the seed structure.

---

# 14) Minimal Additions to Data Model (Support Heuristics)

**Atomic facts**

* `PartyDefinitionFact`:

  * `party_name_raw`, `party_name_normalized`, `role_label`, `confidence`, evidence
* `SponsorMentionFact`:

  * `sponsor_name_raw`, `sponsor_name_normalized`, `confidence`, evidence, `source_pattern`

**Deal fields**

* `deal.target_name_normalized` (nullable if target CIK exists)
* `deal.sponsor_name_normalized` + evidence/confidence
* `deal.is_sponsor_backed`

---

# 15) One additional “don’t guess” instruction

For private target extraction, do not infer target name from PR headings alone. Prefer:

* EX-2.1 preamble (visual text buffer)
* defined “Company” label
* 8-K Item 1.01 definitive agreement paragraph
  Fallback sources may be used only with lower confidence and must be flagged.

---

## Appendix A: Mandatory Regex Pattern Specifications (Must Implement in `regex_pack.py`)

The `regex_pack.py` module must implement (at minimum) these compiled patterns with unit tests. All patterns must be compiled with appropriate flags (typically `re.IGNORECASE`, and `re.DOTALL` where specified), and must assume **prior normalization** of smart quotes/dashes to ASCII via `VisualTextExtractor`.

### A1) PREAMBLE_PARTY_LIST

**Target:** Matches party list in preamble: “by and among [Party A], [Party B], and [Party C] …”
**Spec:** Case-insensitive; must tolerate arbitrary whitespace/newlines; must stop at the first sentence terminator.

Recommended pattern:

```regex
(?is)\bby\s+and\s+(?:among|between)\b\s+(?P<party_span>.+?)(?:\.\s|;\s)
```

Post-processing requirement:

* `party_span` must be split into parties using a parentheses-aware splitter (do not split inside parentheses).
* Prefer splitting on `, and` / `and` near end for last party.

### A2) DEFINED_TERM_ROLE

**Target:** Captures defined-term role labels such as:

* `(the "Company")`
* `("Purchaser")`
* `(hereinafter "Parent")`
* `(hereinafter referred to as the "Company")`

**Spec:** Must match parentheses wrappers with optional lead-in words and quote style; relies on smart quote normalization.

Recommended pattern:

```regex
(?is)\(\s*(?:the\s+|hereinafter\s+|hereinafter\s+referred\s+to\s+as\s+|referred\s+to\s+as\s+)?["'](?P<label>[A-Za-z0-9][A-Za-z0-9\s\-]{0,40})["']\s*\)
```

Usage requirement:

* Run this near party mentions; map label values to canonical role hints:

  * Company → target-side
  * Parent/Buyer/Purchaser → acquirer-side
  * Merger Sub → acquisition vehicle

### A3) SPONSOR_AFFILIATION

**Target:** Sponsor linkage phrases:

* “affiliates of [PE Firm]”
* “funds managed by [PE Firm]”
* “portfolio company of [PE Firm]”

**Spec:** Capture sponsor firm name as a group; stop at punctuation or conjunction.

Recommended pattern:

```regex
(?is)(?:affiliates\s+of|funds\s+managed\s+by|portfolio\s+company\s+of)\s+(?P<sponsor>[A-Z][A-Za-z0-9\s,&.\-]{2,80}?)(?:\.|,|;|\s+and\b|\s+\))
```

### A4) CURRENCY_AMOUNT

**Target:** Money amounts such as:

* `$500,000,000`
* `$1.5 billion`
* `$750 million`

**Spec:** Capture numeric and optional scale word/abbrev.

Recommended pattern:

```regex
(?i)\$\s?(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<scale>billion|million|b|m)?
```

Post-processing requirement:

* Convert to numeric value in dollars when scale present:

  * million/m → *1e6
  * billion/b → *1e9

---

## Appendix B: Mandatory Text Normalization Rules (Enforced by VisualTextExtractor)

Before any regex:

* smart quotes: `“ ”` → `"`, `‘ ’` → `'`
* dashes: `– —` → `-`
* non-breaking spaces: `\xa0` → space
* strip/unwrap inline formatting tags and preserve text content
* normalize whitespace and newlines
