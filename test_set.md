This seed list is designed to battle-test every complex branch of your pipeline: **Bridge-to-Bond** transitions, **Private Targets** (no CIK), **Sponsor-backed LBOs**, and **Cross-border** complexities.

I recommend adding these to your `deliverables/seed_deals.json` and using them as the primary verification set for your coding agent.

### 1. The "Big Three" Complexity Tests

These deals cover the most difficult "Bridge-to-Bond" and "Sponsor" logic.

| Deal Name               | Acquirer (CIK)        | Target (CIK/Name)      | Why it's a test case                                                                            |
| ----------------------- | --------------------- | ---------------------- | ----------------------------------------------------------------------------------------------- |
| **Mars / Kellanova**    | Mars, Inc. (Private)  | Kellanova (0000055986) | **Private Acquirer:** Tests ability to parse a public target's DEFM14A to find a private buyer. |
| **Broadcom / VMware**   | Broadcom (0001730168) | VMware (0001124615)    | **Massive Debt:** A $28.4B term loan. Tests heavy table parsing in EX-10.1.                     |
| **Elon Musk / Twitter** | X Holdings (Private)  | Twitter (0001418091)   | **Sponsor/Margin Loan:** Tests 13D/A filings and "equity commitment" extraction.                |

---

### 2. Specialized Debt & LevFin (Sponsor vs. Strategic)

Use these to verify your **Classification Engine** (IG vs. HY/LevFin).

| Deal Name                   | Acquirer CIK             | Target Name             | Financing Type                                                                    |
| --------------------------- | ------------------------ | ----------------------- | --------------------------------------------------------------------------------- |
| **Kimberly-Clark / Kenvue** | 0000055785               | Kenvue (0001944048)     | **Strategic / IG:** $48.7B deal. Tests Investment Grade bond extraction.          |
| **CD&R / Sealed Air**       | Clayton, Dubilier & Rice | Sealed Air (0001011109) | **LBO / Sponsor:** Tests "Sponsor" tagging and Term Loan B parsing.               |
| **Flutter / Snaitech**      | 0001815555               | Snaitech (Private)      | **Bridge-to-Bond:** $1.75B bridge facility intended for bond takeout.             |
| **3G Capital / Skechers**   | 3G Capital (Private)     | Skechers (0001065837)   | **Take-Private:** Tests "Sponsor-backed" inference for a major consumer brand.    |
| **Walgreens / Sycamore**    | Sycamore Partners        | Walgreens (0001618921)  | **Private Credit:** Tests extraction from press releases when banks are bypassed. |

---

### 3. High-Volume Strategic (Advisory & Multi-Tranche Bonds)

Use these to verify the **Revenue Attribution** and **Bank Normalization** logic.

| Deal Name                  | Acquirer CIK | Target CIK       | Why it's a test case                                                          |
| -------------------------- | ------------ | ---------------- | ----------------------------------------------------------------------------- |
| **Synopsys / Ansys**       | 0000883241   | 0001013462       | **Multi-Advisor:** Tests "Lead" vs "Co-advisor" revenue splits.               |
| **Chevron / Hess**         | 0000004347   | 0000047330       | **Mega-Deal:** All-stock, but with significant debt refinancing/bridge needs. |
| **J.M. Smucker / Hostess** | 0000091538   | 0001644487       | **Bridge/Bond:** Classic mid-cap financing package.                           |
| **Nasdaq / Adenza**        | 0001120193   | Adenza (Private) | **Acquisition Vehicle:** Tests "Merger Sub" identification.                   |
| **IBM / Confluent**        | 0000051143   | 0001699838       | **Tech M&A:** High-speed deal with typical investment grade bond bridge.      |

---

### 4. Edge Cases (Private Targets & Niche Structures)

Use these to test the **Preamble Heuristics** and **Table Normalization**.

| Deal Name                     | Acquirer CIK | Target Name     | Complexity                                                            |
| ----------------------------- | ------------ | --------------- | --------------------------------------------------------------------- |
| **Nippon Steel / U.S. Steel** | Nippon Steel | 0000101871      | **Cross-border:** $16B bridge loan from a Japanese bank consortium.   |
| **Pfizer / Seagen**           | 0000078003   | 0001060736      | **Multi-Security:** Mix of cash, short-term paper, and $31B in bonds. |
| **ServiceNow / Armis**        | 0001373715   | Armis (Private) | **Private Target:** Tests Preamble name extraction logic.             |
| **Palo Alto / CyberArk**      | 0001327567   | 0001598101      | **Cybersecurity:** Tests software-sector specific fee assumptions.    |
| **Cencora / OneOncology**     | 0001140850   | OneOncology     | **Minority Stake:** Tests partial acquisition and JV financing logic. |

---

### Integration Test Example

When providing these to your coding agent, format one as an "expected result" test case:

**Test Case: Flutter Entertainment / Snaitech (2025)**

* **Filing:** 6-K or 8-K announcing the acquisition (Sept/Oct 2024–2025).
* **Expected Atomic Facts:** * Entity: "Flutter Entertainment plc" (Acquirer)
* Entity: "Snaitech" (Target)
* Financing: "$1.75 billion bridge facility"
* Clustering: Link Bridge to Snaitech Acquisition deal.
* Classification: `instrument_family: bridge`, `market_tag: HY_Bond` (due to high-yield refinancing language).
