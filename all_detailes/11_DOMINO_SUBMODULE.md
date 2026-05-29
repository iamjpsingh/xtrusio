# 11 — Domino Submodule (`intelV2/domino/*`)

**Files:** `src/intelV2/domino/DominoLens.jsx`, `CompanyUniverseView.jsx`, `IndustryProfilesView.jsx`, `SignalFeedView.jsx`, `DominoForceGraph.jsx`, `DominoGrids.jsx`, `DominoInsights.jsx`, `PersistenceIndicator.jsx`, `companyPrompts.js`, `industryPrompts.js`, `signalPrompts.js`, `dominoStore.js`, `dominoTypes.js`, `dominoLiveDataset.js`, `dominoMockData.js`.

Domino is **Lens 6** of Company Intelligence V2 — a **predictive correlation engine** that tracks CLM-using industries, the companies inside them, and signals (M&A, regulatory, AI adoption, etc.) moving through both. Different from the other five lenses: those answer "where Sirion stands" or "what to do this week"; Domino answers "where the market is going in the next 1-6 months" and pre-routes content briefs to M6 ahead of the cascade.

---

## 1. What Domino Does

End-to-end pipeline:

1. **Block B — Industry taxonomy.** One Gemini-grounded call returns 15 IndustryProfile records (size, regulatory drivers, complexity, signal priorities, named customer wins). Persisted to `intel_v2_domino_industries`.
2. **Block C — Company harvest.** Walks 10 CLM vendor case-study pages via Firecrawl, extracts named customers, dedups across vendors, tags by industry. Persisted to `intel_v2_domino_companies`.
3. **Block D — Signal sweep.** Per-industry (or per-company batch when Block C has data) Perplexity calls return last-7-day signal hits (M&A / regulatory / AI adoption / exec move / cost pressure / vendor consolidation / RFP / CLM hire). Persisted to `intel_v2_domino_signals`.
4. **Block E — Visualisations.** Force-directed graph (centrepiece) and heatmap (industries × signal types).
5. **Insights** — Auto-derived plays from active predictions + heat spikes + dormant correlation pairs.

The lens uses live data via `buildLiveDominoDataset()` when available, falls back to deterministic `buildMockDominoDataset(seed=42)` so designs don't shimmer between page loads.

---

## 2. The 4 Views (UI tabs in `DominoLens.jsx`)

The lens stacks vertically:

1. **Header card** — Brand-bg gradient with title "DOMINO — MARKET DYNAMICS · Lens 6", description, and `PersistenceIndicator` badge in the top-right.
2. **Status pills** — Industries / Companies Tracked / Signals This Period / Active Predictions counts.
3. **Tracked signal types** card — Grid of 8 signal type cards (label + description from `SIGNAL_TYPES`).
4. **Force-graph color legend** card — Entity-type and heat colour swatches.
5. **Industry Profiles view** (Block B) — Empty state CTA → loaded grid of 15 industry cards.
6. **Company Universe view** (Block C) — Empty state CTA → grouped list of harvested companies by industry.
7. **Signal Feed view** (Block D) — Empty state CTA → list of last 30 signal hits.
8. **DominoVisualizationPanel** — Toggle between Force graph and Heatmap, then `DominoInsights`.

The "view toggle" inside the visualisation panel:

| Id        | Label       | Description                        |
| --------- | ----------- | ---------------------------------- |
| `force`   | Force graph | Multi-entity network (centrepiece) |
| `heatmap` | Heatmap     | Industries × signal types          |

(The header counts a "Company Universe / Industry Profiles / Signal Feed" trio of UI panels — these are the data-management blocks. The visualisation panel is the analysis output.)

---

## 3. Prompts — Verbatim

### 3.1 `companyPrompts.js` — Block C (company harvest)

#### `VENDOR_CUSTOMER_PAGES`

The default Firecrawl scrape URLs (overridable in UI):

```
sirion:      "https://www.sirion.ai/customer-stories/"
icertis:     "https://www.icertis.com/customers/"
ironclad:    "https://ironcladapp.com/case-studies/"
agiloft:     "https://www.agiloft.com/case-studies/"
docusign:    "https://www.docusign.com/customer-stories"
conga:       "https://conga.com/customer-stories"
linksquares: "https://linksquares.com/customer-stories/"
malbek:      "https://www.malbek.io/case-studies"
evisort:     "https://www.evisort.com/customers"
juro:        "https://juro.com/customers"
```

#### `EXTRACT_SYSTEM`

> ```
> You extract structured customer references from B2B SaaS case-study pages. Every entry you return must be backed by a direct quote or named reference in the input markdown — never invent customers. Output strict JSON.
> ```

#### `buildExtractUser(vendorName, vendorHomepage, markdown)`

Per-vendor extraction prompt (slices markdown to 18000 chars, adds truncation note if needed):

> ```
> You are reading the markdown content of vendor "${vendorName}"'s public customer / case-study page (homepage: ${vendorHomepage}).
>
> Extract every named customer mentioned in this page. For each customer, return:
> {
>   "company_name":     "exact public name as written",
>   "industry_id":      "best-fit id from the list below",
>   "industry_name":    "best-fit name from the list below",
>   "evidence_snippet": "<= 50 words quoted from the page that proves this is a real customer reference",
>   "vendor_relation_type": "case_study" | "logo_only" | "press_release" | "earnings_mention",
>   "case_study_url":   "specific case-study URL if a sub-link is visible, else null",
>   "confidence":       "high" | "medium" | "low"
> }
>
> Industry id options:
> ${industriesList}
>
> Confidence rubric:
> - high   = customer named in a full case-study with quote/results
> - medium = customer named in a logo bar PLUS at least one corroborating mention elsewhere on the page
> - low    = customer named in a logo bar only, no corroborating evidence
>
> Constraints:
> - Only public, verifiable references — every entry must trace to a quote in the input markdown.
> - Skip generic "trusted by 500+ companies" claims with no names.
> - De-dupe (one entry per company).
> - If the same customer appears in multiple case studies, list once with the most-specific URL.
> - Skip parent-vendor names (e.g. don't list ${vendorName} itself).
>
> Markdown input:
> """
> ${markdown.slice(0, 18000)}
> """
> ${markdown.length > 18000 ? `\n[TRUNCATED — full page is ${markdown.length} chars]\n` : ""}
>
> Return strict JSON: { "vendor": "${vendorName}", "customers": [...] }
> ```

#### `harvestCompaniesAcrossVendors({onProgress})`

- Sequential (one vendor at a time) to avoid Firecrawl rate limits.
- Per vendor: `callFirecrawl(url, {onlyMainContent: true})` → markdown. If markdown < 200 chars, log error + skip.
- Then `researchCall(EXTRACT_SYSTEM, buildExtractUser(...), {providers: PROVIDER_CHAINS.SYNTHESIS_PREMIUM, timeoutMs: 90000, maxTokens: 8192})`.
- Stamps each customer: `source_vendor_id, source_vendor_name, source_url, captured_at`.
- Reports progress through 4 phases: `scraping`, `extracting`, `extracted`, then final `done`.

**Dedup pass** (after all vendors):

- Key: lowercased company_name.
- Existing entry: pushes another entry to `vendor_references` array; upgrades confidence if higher (high=3 / medium=2 / low=1).
- Final company shape: `{id (slug), name, industry_id, industry_name, region: null, size_revenue_usd: null, size_employees: null, current_clm_vendor (picked via pickPrimaryVendor preferring case_study > press_release > earnings_mention > logo_only), current_vendor_source_url, vendor_signal: "loyal", vendor_relation_type, evidence_snippet, confidence, vendor_references, source_urls (array), added_at, last_seen_signal_at: null}`.

#### `verifyCompanyUrls(company)` — cheap verify

HEAD-request every `source_urls` entry. Falls back to GET no-cors. Reachable if status 0 / 200-399 / type "opaque". Returns `{total, alive, dead, deadUrls, checkedAt}`.

#### `reverifyCompanyDeep(company)` — deep verify

Cross-source verification call:

System prompt:

> ```
> You are a fact-checker. Given a claim that a named company is a CLM-software customer of a named vendor, you research independently and return your verdict with a different supporting URL than the one provided.
> ```

User prompt:

> ```
> Claim:
> - Company: ${company.name}
> - Industry: ${company.industry_name || "?"}
> - Currently uses: ${company.current_clm_vendor || "?"}
> - Original evidence URL: ${company.current_vendor_source_url || "?"}
> - Original snippet: "${(company.evidence_snippet || "").slice(0, 300)}"
>
> Independently verify whether ${company.name} is actually a CLM customer of ${company.current_clm_vendor || "any tracked vendor"}, and if so, find a DIFFERENT supporting URL than the one above (e.g. press release, earnings call mention, news article, vendor blog, third-party review).
>
> Return strict JSON:
> {
>   "verdict":         "supported" | "contested" | "unsure",
>   "supporting_url":  "verifiable URL or null",
>   "supporting_quote":"<= 30 words from the new source",
>   "note":            "1-sentence — what you found"
> }
> ```

Provider: `RESEARCH_PREMIUM`, timeout 60s, maxTokens 2048.

### 3.2 `industryPrompts.js` — Block B (industry taxonomy)

#### `SYSTEM`

> ```
> You are a B2B SaaS market researcher for a CLM (Contract Lifecycle Management) intelligence platform. You produce structured, source-attributed industry profiles. Every quantitative claim must carry a source URL + publication date. Omit fields you cannot verify rather than guess.
> ```

#### `buildUser()`

Lists the 15 industries from `DEFAULT_INDUSTRIES` (numbered) and asks for each in same order:

> ```
> Profile each of the 15 CLM-using industries below for use in a predictive correlation engine. Return them in the SAME ORDER they appear here (the list is already sorted by CLM-adoption depth, descending).
>
> Industries:
> ${list}
>
> For each industry, return:
> {
>   "id":                          "use the id from the list above",
>   "name":                        "use the name from the list above",
>   "size_global_usd":             number | null,
>   "size_year":                   integer | null,
>   "size_source_url":             "verifiable URL",
>   "size_source_name":            "publication name",
>   "clm_adoption_maturity":       "early" | "growing" | "mature" | "saturated",
>   "maturity_rationale":          "1-2 sentences",
>   "typical_use_cases":           ["short phrase", "..."],
>   "regulatory_drivers":          [{ "name": "regulation name", "year": 2020, "source_url": "..." }],
>   "procurement_complexity":      1-10,
>   "complexity_rationale":        "1 sentence",
>   "vendor_count_per_company":    "thousands" | "hundreds" | "tens",
>   "primary_buyer_persona":       ["role 1", "role 2"],
>   "signal_priorities":           ["m_a", "regulatory_change", "ai_adoption", "exec_move", "cost_pressure", "vendor_consolidation", "rfp_signal", "clm_hire"],
>   "active_competitors":          ["Sirion", "Icertis", ...],
>   "notable_customer_wins":       [{ "company": "...", "vendor": "...", "year": 2024, "source_url": "..." }],
>   "source_urls":                 ["..."]
> }
>
> Constraints:
> - size_global_usd: ONLY the OPERATING size of the industry (loan origination for banking, prescription drug revenue for pharma, etc.) — NOT GDP. Cite the specific report.
> - regulatory_drivers: list 2-5 specific named regulations per industry, with year of enactment and a verifiable URL.
> - typical_use_cases: 3-6 concrete CLM use-cases for the industry (e.g., banking: "ISDA master agreements", "MSA with vendors", "regulatory filings").
> - primary_buyer_persona: the C-level / VP-level role most likely to lead a CLM purchase in that industry.
> - signal_priorities: pick 3-5 of the 8 signals that matter most for THIS industry.
> - active_competitors: 3-5 CLM vendors who already serve this industry well, ordered by visible market presence.
>   • Use CURRENT company names. If a vendor was acquired, list under the parent (Apttus → Conga; Lexion → Ironclad; Selectica → Apttus → Conga; Determine → Corcentric).
>   • EXCLUDE Sirion itself from active_competitors. Sirion is the target company — it does not compete with itself.
> - notable_customer_wins: 2-4 named public CLM deployments at SPECIFIC named companies (e.g., "JPMorgan", "Pfizer", "BMW"). Each must cite a verifiable URL.
>   • SKIP this row entirely if you cannot name the specific company. NEVER return placeholders like "Fortune 500 bank", "Top pharma", or "Major insurer". Empty array is acceptable; placeholders are not.
> - Skip any field you cannot substantiate from public sources — do not return placeholders.
> - Mark data >5 years old with "stale": true.
>
> Return strict JSON: { "industries": [...] }
> - 15 entries, in the same order as my list.
> - No prose outside the JSON.
> - Every URL must be a real publicly-reachable page (we will HEAD-request to verify).
> ```

#### `fetchIndustryTaxonomy()`

Provider: `RESEARCH_PREMIUM`, timeoutMs 240000 (4 min), maxTokens 16384. Stamps each profile with `last_refreshed_at` + `_provider`.

#### `verifyProfileUrls(profile)` — cheap verify

Same HEAD-request pattern as company verify, but iterates `collectUrls(profile)` which gathers `size_source_url` + every `regulatory_drivers[].source_url` + every `notable_customer_wins[].source_url` + every `source_urls[]`.

#### `reverifyProfileDeep(profile)` — deep verify

System:

> ```
> You are a fact-checker. You will be given a CLM industry profile claim. Your job is to research independently and report whether each material claim holds up. Be conservative — say "unsure" rather than guess.
> ```

User:

> ```
> Profile to verify (industry: ${profile.name}):
>
> Claims:
> - maturity: ${profile.clm_adoption_maturity || "?"} (rationale: ${profile.maturity_rationale || "n/a"})
> - size_global_usd: ${profile.size_global_usd || "?"} (year ${profile.size_year || "?"})
> - regulatory_drivers: ${(profile.regulatory_drivers || []).map(r => r.name).join("; ") || "?"}
> - notable_customer_wins: ${(profile.notable_customer_wins || []).map(w => `${w.company} on ${w.vendor}`).join("; ") || "?"}
>
> For each claim, return:
> {
>   "claim": "...",
>   "verdict": "supported" | "contested" | "unsure",
>   "supporting_url": "verifiable URL or null",
>   "note": "1-sentence — what you found"
> }
>
> Return strict JSON: { "verifications": [...] }
> ```

Provider: `RESEARCH_PREMIUM`, timeout 90s, maxTokens 4096.

### 3.3 `signalPrompts.js` — Block D (signal sweep)

#### `SYS_INDUSTRY` (used for both industry-level and company-batch sweeps)

> ```
> You are a signal-extraction engine for CLM market intelligence. You scan the last 7 days of public news and return only events that match one of 8 specific signal types affecting named companies in a given industry. Every event must carry a verifiable URL — no speculation, no fabrication.
> ```

#### `buildIndustryUser(industry)` — fallback when companies aren't yet harvested

> ```
> Find news / filings / press releases / earnings mentions / job postings from the LAST 7 DAYS that match one of these 8 signal types AND affect named companies in the industry "${industry.name}":
>
> ${SIGNAL_LIST}
>
> For each signal hit, return:
> {
>   "industry_id":         "${industry.id}",
>   "company_name":        "exact named company affected",
>   "signal_type":         "one of the 8 ids above",
>   "headline":            "short factual sentence (<= 15 words)",
>   "summary":             "2 sentences: what happened + why it matters",
>   "source_url":          "verifiable URL",
>   "source_name":         "publication or organization name",
>   "source_date":         "ISO 8601",
>   "disruption_score":    1-5,
>   "score_rationale":     "1 sentence — anchor to the rubric",
>   "clm_relevance":       "low" | "medium" | "high",
>   "clm_relevance_rationale": "1 sentence"
> }
>
> Disruption score rubric (be calibrated, not generous):
> 1 = background noise (generic press release)
> 2 = mildly relevant (low-level hire, vague AI commitment)
> 3 = worth tracking (named CLM vendor in earnings, mid-level CLM hire)
> 4 = high signal (RFP published, CLM deployment announced, named acquisition)
> 5 = category-defining (multi-business-unit CLM consolidation, 8+-figure named deal)
>
> Constraints:
> - 7-day window strict. Skip older items.
> - Each entry must name a SPECIFIC company. Skip generic "the industry is..." statements.
> - Skip items with disruption_score 1 (noise) — only return 2+.
> - Cap at 12 entries per industry.
> - Sort by disruption_score descending.
>
> Return strict JSON: { "industry_id": "${industry.id}", "signals": [...] }
> ```

`SIGNAL_LIST` is `SIGNAL_TYPES.map(s => ` - ${s.id}: ${s.label} — ${s.description}`).join("\n")` (the 8 types listed below).

#### `buildCompanyBatchUser(companies)` — preferred when Block C has data

> ```
> Scan the LAST 7 DAYS of public news / filings / press releases / earnings calls / job postings for each of the named companies below. Return only events matching one of 8 specific signal types.
>
> Companies:
> ${list}
>
> Signal types:
> ${SIGNAL_LIST}
>
> For each signal hit, return:
> {
>   "company_id":          "from the input list",
>   "company_name":        "...",
>   "industry_id":         "from the input list",
>   "signal_type":         "one of the 8 ids",
>   "headline":            "short factual sentence (<= 15 words)",
>   "summary":             "2 sentences: what happened + why it matters",
>   "source_url":          "verifiable URL",
>   "source_name":         "publication / org name",
>   "source_date":         "ISO 8601",
>   "disruption_score":    1-5,
>   "score_rationale":     "1 sentence",
>   "clm_relevance":       "low" | "medium" | "high",
>   "clm_relevance_rationale": "1 sentence"
> }
>
> Disruption rubric: same as before (1 noise → 5 category-defining). Skip 1s.
>
> Constraints:
> - 7-day window strict.
> - Skip if URL not verifiable.
> - If a company has no qualifying signals in the window, omit it from the response (don't return empty entries).
> - Cap at 5 hits per company.
>
> Return strict JSON: { "signals": [...] }
> ```

#### `sweepSignalsByIndustry({industries, onProgress})`

Loops industries sequentially. Provider: `RESEARCH_PREMIUM`, timeout 90s, maxTokens 4096. Stamps each signal with `industry_id` (defaulting to `ind.id`), `company_id = slug(company_name)`, `captured_at`, and `id = signalId(s, industryId)` (= `${slug(company_name)}_${signal_type}_${date.slice(0,10)}`, or `industry_id_signal_type_unk` fallback).

#### `sweepSignalsByCompany({companies, batchSize=25, onProgress})`

Chunks companies into batches of 25. Per batch: `RESEARCH_PREMIUM`, timeout 120s, maxTokens 8192. Same stamping/id pattern.

---

## 4. `dominoTypes.js` — Constants

### `DEFAULT_INDUSTRIES` (15 entries, descending CLM-adoption depth)

| Tier | id                       | name                                     |
| ---- | ------------------------ | ---------------------------------------- |
| 1    | banking_capital_markets  | Banking & Capital Markets                |
| 1    | pharmaceuticals_lifesci  | Pharmaceuticals & Life Sciences          |
| 1    | technology               | Technology (SaaS, Hardware)              |
| 1    | insurance                | Insurance                                |
| 2    | healthcare_providers     | Healthcare Providers                     |
| 2    | manufacturing_industrial | Manufacturing — Industrial               |
| 2    | energy_utilities         | Energy & Utilities                       |
| 2    | professional_services    | Professional Services                    |
| 2    | telecommunications       | Telecommunications                       |
| 3    | logistics_supply_chain   | Logistics, Supply Chain & Transportation |
| 3    | government_public_sector | Government & Public Sector               |
| 3    | manufacturing_cpg        | Manufacturing — Consumer Goods (CPG)     |
| 3    | retail_ecommerce         | Retail & E-commerce                      |
| 4    | real_estate_construction | Real Estate & Construction               |
| 4    | media_entertainment      | Media, Entertainment & Telecom Services  |

Tier 1 = mature, highest CLM spend; Tier 2 = heavy adopters, rising spend; Tier 3 = growing adoption; Tier 4 = selective adoption.

### `SIGNAL_TYPES` (8 entries)

| id                     | label                | description                                                             |
| ---------------------- | -------------------- | ----------------------------------------------------------------------- |
| `m_a`                  | M&A                  | Acquisition / merger / divestiture involving a tracked company          |
| `regulatory_change`    | Regulatory           | New regulation affecting contract terms or counterparty mgmt            |
| `ai_adoption`          | AI Adoption          | Public commitment to deploying GenAI / agentic AI at scale              |
| `exec_move`            | Exec Move            | New CFO / GC / CIO / Chief Procurement Officer                          |
| `cost_pressure`        | Cost Pressure        | Layoffs, cost-cut programs, restructuring                               |
| `vendor_consolidation` | Vendor Consolidation | Public statement about reducing vendor count                            |
| `rfp_signal`           | RFP Signal           | Public RFP for CLM or contract automation                               |
| `clm_hire`             | CLM Hire             | Hiring Contract Operations / Digital Contract Mgr / AI Procurement Lead |

### `NODE_COLORS`

| Key    | Hex       | Label    | Description                    |
| ------ | --------- | -------- | ------------------------------ |
| RED    | `#f87171` | Spiking  | ≥1σ above 8-week trailing mean |
| YELLOW | `#fbbf24` | Elevated | Signal-active, monitor closely |
| GREEN  | `#4ade80` | Stable   | Within trailing baseline       |
| GRAY   | `#7a7a94` | No data  | No recent signal observations  |

### `SOURCE_VENDORS` (10 — pages scraped in Block C)

`sirion, icertis, ironclad, agiloft, docusign (DocuSign CLM), conga, linksquares, malbek, evisort, juro` — each with its `name` and `homepage`.

### Type definitions (JSDoc only — no runtime type system)

`IndustryProfile`, `TrackedCompany`, `SignalHit`, `MatrixSnapshot`, `CorrelationLink`, `DominoPrediction` — see `dominoTypes.js` for full property lists. Notable shapes:

- `SignalHit.id` = `${company_id}_${signal_type}_${ISOdate}`.
- `CorrelationLink.id` = `${A}_${B}_${signal}_${lag}` with `correlation` Pearson r [-1,1], `lag_weeks` integer, `sample_size` weeks of overlapping data.
- `DominoPrediction` includes `leading_industry_id`, `leading_signal`, `leading_week`, `spike_magnitude_sigma`, `trailing_industry_id`, `expected_intensity_change`, `expected_arrival_week`, `confidence` 0-1, `evidence_event_urls`, optional `narrative` (Gemini-humanized 60-90 word strategic narrative), `content_angle`, `suggested_persona`, `suggested_assets`, `verified` bool, `materialized` bool|null.

---

## 5. `dominoStore.js` — Persistence

### State shape

Six logical collections, each with `save(item)` / `load(id)` / `loadAll()`:

| Helper               | Firestore collection               |
| -------------------- | ---------------------------------- |
| `dominoIndustries`   | `intel_v2_domino_industries`       |
| `dominoCompanies`    | `intel_v2_domino_companies`        |
| `dominoSignals`      | `intel_v2_domino_signals`          |
| `dominoSnapshots`    | `intel_v2_domino_matrix_snapshots` |
| `dominoCorrelations` | `intel_v2_domino_correlations`     |
| `dominoPredictions`  | `intel_v2_domino_predictions`      |

Pattern: writes go to localStorage first (always succeeds — `LS_PREFIX = "xt_domino_"` with per-collection key list), then Firestore (best-effort). Reads merge Firestore (authoritative) over localStorage (fallback).

Each save adds `id` and `last_saved_at` ISO timestamp. `lsListIds` maintains a `xt_domino_<collection>_keys` JSON list per collection so `loadAll` can iterate them.

### Persistence health pubsub (`subscribePersistenceHealth(fn)`)

Module-level `_health` counters:

```
{
  firebaseEnabled: FIREBASE_ENABLED,
  fbWriteOk: number,
  fbWriteFail: number,
  lastFbError: string|null,
  lastFbErrorAt: ISO|null,
  lastSyncAt: ISO|null
}
```

`save()` updates `fbWriteOk` / `fbWriteFail` / `lastSyncAt` / `lastFbError` after each Firestore attempt and notifies all listeners. Never throws — local copy succeeded, app should keep working. The `PersistenceIndicator` UI component subscribes to this.

---

## 6. `dominoLiveDataset.js` vs `dominoMockData.js`

### Live (`buildLiveDominoDataset`)

Loads industries / companies / signals from store in parallel. Returns `null` if `industries.length < 5` (caller then falls back to mock). If industries exist but no signals, calls `shapeWithoutSignals(...)` returning all-grey nodes so the user sees real industry names in the graph even before the first signal sweep.

Heat computation:

```
RELEVANCE_WEIGHT = { high: 1.0, medium: 0.6, low: 0.3 }
heat = min(1, sum(disruption_score × clm_relevance_weight) / 30)
```

Heat colour bands: `>= 0.75 RED, >= 0.5 YELLOW, >= 0.2 GREEN, else GRAY`.

Returns `{industries, companies, signals, correlationPairs: [], predictions: [], generatedAt, source: "live" | "live_no_signals"}`. Predictions and correlation pairs are NOT computed here — that needs Phase 2 (cross-industry lag detection over 6+ months of data).

### Mock (`buildMockDominoDataset(seed=42)`)

Deterministic via `mulberry32` PRNG.

`COMPANIES_BY_INDUSTRY` map embeds 5-8 sample companies per industry (e.g., banking: JPMorgan Chase / Bank of America / HSBC / Morgan Stanley / Goldman Sachs / Citigroup / Barclays / Deutsche Bank).

Generation:

- Industries: hot-bias (+0.4 base heat) for `banking_capital_markets, pharmaceuticals_lifesci, insurance, technology`.
- Companies: each gets `heat = min(0.95, ind.heat × 0.7 + rand × 0.4)` and a randomly chosen vendor from `SOURCE_VENDORS` (or null).
- Signals: `numHits = floor(co.signalsThisPeriod)` per company, picking random signal type, random date in last 30 days, score 1-5, `clm_relevance` derived from score (≥4 high, ≥2 medium, else low).
- 13 hard-coded `correlationPairs` (e.g., banking → insurance via regulatory_change at 0.78 corr, 5w lag).
- 3 hard-coded predictions:
  - banking → insurance via regulatory_change, 0.78 confidence, 5w arrival, narrative around Basel IV.
  - technology → professional_services via ai_adoption, 0.65 confidence, 3w arrival.
  - retail_ecommerce → logistics_supply_chain via vendor_consolidation, 0.71 confidence, 3w arrival.

Returns same shape as live, with `seed: 42` field added.

---

## 7. Firecrawl Scraping Flow

Used in Block C only. Per vendor:

1. `callFirecrawl(url, {onlyMainContent: true})` → returns `{markdown, ...}`.
2. If `markdown.length < 200`, log error `"Page returned <200 chars of markdown"` and skip.
3. Otherwise call `researchCall(EXTRACT_SYSTEM, buildExtractUser(name, homepage, markdown))`.
4. Stamp results with vendor metadata.
5. Continue to next vendor (sequential, no parallel — Firecrawl rate limit avoidance).

Errors are accumulated into the `errors` array (`{vendor, stage: "scrape" | "extract", error}`) and shown in `ErrorsBlock` UI without halting the pass.

---

## 8. Force Graph (`DominoForceGraph.jsx`)

Built on `react-force-graph-2d` (canvas, 60fps for hundreds of nodes). Centerpiece visualisation.

### Topology

- **Center node** `__center__` labelled "CLM", type=category, val=30, brand purple.
- **Industry nodes** — One per industry. `val = 8 + heat × 16`, colour from `heatColor`. Linked to centre.
- **Company nodes** — One per company. `val = 4 + heat × 6`. Linked to parent industry.
- **Correlation links** — Cross-industry edges where `|corr| >= 0.4`. Green tint for positive, red for negative. Width = `1 + corr × 4`. Optional labels (`"78% (5w lag)"`).
- **Prediction nodes** — One synthetic node per prediction (`pred_<id>`) labelled `"→ ${weeks}w"`. Two arrow links: leading_industry → pred_node → trailing_industry. Red, isPrediction:true, arrows on.

### Rendering

- `drawNode(node, ctx, globalScale)` — Custom canvas:
  - Halo for spiking (`heat > 0.7`): outer arc at 1.6× radius, `color + "33"` translucent fill.
  - Main circle at colour, 1.5/scale stroke in bg colour.
  - Labels only at `globalScale > 1.3`, OR for category/industry nodes (always), OR for hovered.
  - Font size scales: category 14, industry 11, others 9 — divided by globalScale.
- `lookupNode(ref)` — Robust resolver since recharts/d3-sankey resolves source/target to objects after init.

### Controls

- **Edge labels** toggle (top-right) — Shows `(78% / 5w lag)` text on correlation edges.
- **Zoom to fit** button — `fgRef.current?.zoomToFit(400, 60)`.
- **Bottom-left legend** — Entity-type swatches (Industry / Company / Prediction) + heat colour swatches.
- **Hover info card** (top-left when hovering) — Type label, name, industry/signals/vendor/heat/signalCount/narrative depending on node type.

### Interactions

- `onNodeHover` updates `hoveredNode` state.
- `onNodeClick` → `fgRef.current?.centerAt(node.x, node.y, 600)` (smooth pan).
- `d3VelocityDecay: 0.4`, `cooldownTicks: 120` — settle animation parameters.

---

## 9. Heatmap (`DominoGrids.jsx` — `DominoHeatmap`)

Pure-CSS table, industries × signal types.

- Rows: industries (in `dataset.industries` order).
- Columns: 8 signal types from `SIGNAL_TYPES`.
- Cell value: sum of `disruption_score` across all signals matching `(industry_id, signal_type)`.
- Cell intensity: `ratio = cellValue / max`. Colour bands: `> 0.65 RED, > 0.35 YELLOW, > 0 GREEN, else GRAY`. Background uses `${color}${alpha}` where alpha = `round((0.15 + ratio × 0.85) × 255).toString(16)` — so even small values are visible, full intensity at peak.
- Cell tooltip: `${industry.name} × ${signal.label}: ${v} disruption-points`.

(Also exports `DominoAdjacency` — industries × industries correlation matrix — but `DominoLens.jsx` doesn't currently render this view, only Force + Heatmap toggles.)

---

## 10. Insights (`DominoInsights.jsx`)

Auto-derives plays from the dataset. Three sources:

### 10.1 Per active prediction → "Pre-empt" play

For each `dataset.predictions` entry:

- Tier: `confidence >= 0.7 ? critical, >= 0.5 ? watch, else opportunity`.
- Score: `round(confidence × 10)`.
- Title: `"Pre-empt ${trailing_industry_name}: ${shortenAngle(content_angle)}"` (or generic fallback).
- Timing: `"${expected_arrival_weeks}w window"`.
- Rationale: prediction.narrative.
- Recommended play: `"Publish: '${content_angle}'. Target ${suggested_persona || trailing_industry_name}. Be in front of the cascade — Sirion's content lands while ${trailing_industry_name} buyers are first noticing the shift."`
- Effort: medium, Owner: Content Lead.
- Urgency = arrival ≤ 4w → 9, ≤ 8w → 7, else 5. Ease: 6.
- Evidence: `{label: "${leading} ${signal} spike", source: "domino_signal"}`.

### 10.2 Spiking industries not covered by a prediction → "Watch" play

For up to 2 industries with `heat >= 0.7` not already in any prediction:

- Tier: watch. Score: `round(heat × 10)`.
- Title: `"Watch ${name} — heat ${pct}%"`.
- Recommended play: `"Set a 2-week alert: re-check ${name} signal density next pull. If still ≥0.7, promote to active monitoring and brief the AR team."`.
- Effort: low, Owner: Analyst Relations. Urgency 5, Ease 9.

### 10.3 Strong dormant correlation pairs → "Pre-position" play

For up to 2 pairs with `|corr| >= 0.55` not yet predicted:

- Tier: opportunity. Score: `max(5, round(|corr| × 9))`.
- Title: `"Pre-position ${to.name} content — ${pct}% historical link to ${from.name}"`.
- Timing: `"${lag_weeks}w typical lag"`.
- Recommended play: `"Build an evergreen ${to.name}-targeted content asset on ${signal_label}. When ${from.name} next spikes, you publish in 24h instead of 24 days."`.
- Effort: medium, Owner: Content Lead. Urgency 3, Ease 6.

### Sort + cap

`tierOrder = {critical: 0, watch: 1, opportunity: 2}`, then `score desc`. Capped at 8.

### `InsightCard` UI

Same design language as Lens 5 Action cards. Each has:

- Tier badge ("ACT NOW" red / "PRE-EMPT" yellow / "OPPORTUNITY" green).
- Title with score on the right.
- Rationale + "RECOMMENDED PLAY:" box.
- Attribute chips (effort / owner / persona / confidence%).
- "Copy as MD" + "+ Send to Content Strategy" buttons.
- "Send to Content Strategy" calls `transferActionToM6(action, {source: "domino_insights"})` after adapting the insight into the action shape (channel defaults to `external_blog`, `_provider: "domino_mock"`).
- "Copy as MD" calls `actionToMarkdown(...)` from `handoffM6.js`.

---

## 11. Persistence Indicator UI (`PersistenceIndicator.jsx`)

Small pill subscribed to `subscribePersistenceHealth`. Three states:

| Condition                            | Colour  | Label                           | Reason text                                  |
| ------------------------------------ | ------- | ------------------------------- | -------------------------------------------- | ---------- | ------------------------------------------------------------- |
| `!firebaseEnabled`                   | red     | Local only                      | Firebase not configured (no project ID)      |
| Idle (no writes attempted)           | textDim | Idle                            | No writes attempted yet this session         |
| `fbWriteFail > 0 && (fbWriteOk === 0 |         | fbWriteFail > fbWriteOk × 0.5)` | yellow                                       | Local only | Firestore writes failing — security rules likely not deployed |
| Otherwise                            | green   | Firebase ✓                      | `${fbWriteOk}` writes succeeded this session |

Click to toggle a popover showing: Firebase enabled status, write counters, last sync time, last error message (in red), and a "Fix:" instruction telling the user to publish `firestore.rules` via Firebase Console (mentioning the repo's rules file already includes the 6 Domino collections).

---

## 12. Cross-Vendor Search ("Which companies use Sirion + Icertis")

`harvestCompaniesAcrossVendors` produces a deduped list where each company entry has `vendor_references: [{vendor, url, type, confidence}, ...]`. The `CompanyCard` UI renders the "SEEN UNDER N VENDORS" sub-section when `vendor_references.length > 1`, listing each vendor + relation type + confidence + source link. This is how Domino surfaces multi-vendor relationships — there's no dedicated cross-vendor query UI, but the data shape supports filtering for multi-vendor companies (`companies.filter(c => c.vendor_references.length >= 2)`).

The single-card view also shows the chosen `current_clm_vendor` (picked via `pickPrimaryVendor` ordering: case_study > press_release > earnings_mention > logo_only).

---

## 13. Target Prospect Generation

Domino doesn't have a dedicated "target prospect" output endpoint — that emerges from the data:

- The Company Universe view groups by industry + filterable by confidence (`high`/`medium`/`low`).
- Each company carries `current_clm_vendor` so users can scan for displacement opportunities (e.g., filter to non-Sirion vendors).
- The Insights panel surfaces per-industry "watch" cards when heat spikes.
- The Predictions (Phase 2) will surface `trailing_industry` as the next-cascade target ahead of the move.
- M6 handoff via `transferActionToM6` carries the play + persona + suggested channel into Content Strategy where target audiences are made explicit.

---

## 14. Edge Cases

### Private customers missed

The harvest only sees what's on public case-study pages. Companies under NDA (common in banking / pharma) won't appear unless the vendor publishes a redacted case. Logo-only references get `confidence: low` and can be filtered out.

### Firecrawl timeouts

`callFirecrawl` failures are caught per-vendor and pushed into `errors` array (`{vendor, stage: "scrape", error}`). The harvest continues with the next vendor — it never bails. Errors are surfaced in the UI via `ErrorsBlock` (limit 5 visible).

If markdown comes back smaller than 200 chars (often happens with Firecrawl bot blocks), the entry gets `error: "Page returned <200 chars of markdown"` and the vendor is skipped.

### URL liveness false negatives

`verifyProfileUrls` and `verifyCompanyUrls` use HEAD with no-cors fallback to GET. Some sites block HEAD entirely and the no-cors response gives status 0 — treated as reachable. Others return 403 specifically to bots — these falsely appear dead. Users can re-run "Find independent source" / "Deep re-research" to confirm via a different provider.

### Block C requires `/api/scrape` worker route

The empty-state UI explicitly notes: `"Requires the worker to expose /api/scrape. Your dev's deploying it tomorrow — button stays inert until the route returns 200."`

### Block D fallback

If Block C hasn't run (`< 25 companies`), Block D falls back to `sweepSignalsByIndustry` (one Perplexity call per industry). Once `>= 25` companies exist, switches to `sweepSignalsByCompany` in batches of 25 — way better signal granularity but more calls. Block B (industries) is required regardless — UI shows "Run Block B (industry taxonomy) first" and disables the sweep button.

### Live data insufficient → falls back to mock

`buildLiveDominoDataset` returns `null` if `industries.length < 5`; visualisation panel detects this and uses `mockDataset`. The "LIVE DATA · N signals" badge becomes "MOCK DATA · seed 42" so users always know which they're looking at.

### Industries exist but no signals

Renders `shapeWithoutSignals(...)` — all-grey nodes so the user sees real industry names in the graph even before the first signal sweep. Heat = 0, signalsThisPeriod = 0.

### Predictions + correlations are mock-only currently

Live dataset returns empty `correlationPairs: []` and `predictions: []` — Phase 2 work. `DominoInsights` still surfaces "watch" plays for spiking industries even without predictions, so the lens isn't entirely dependent on the mock data for value.

### Persistence indicator yellow ≠ broken

Firestore rules likely not deployed yet. Local data is fine; users won't lose anything. The popover surfaces the actual `lastFbError` (truncated to 200 chars) so devs can diagnose.

### Hallucinated customers

The `EXTRACT_SYSTEM` mandates "Every entry you return must be backed by a direct quote or named reference in the input markdown — never invent customers." Plus the deep-verify path (`reverifyCompanyDeep`) requires a different supporting URL than the original — catches cases where the model invents a customer that's actually only in a vendor's TAM listicle.

### Industry taxonomy placeholders

The industry prompt explicitly forbids placeholders like "Fortune 500 bank" / "Top pharma" / "Major insurer" and instructs "Empty array is acceptable; placeholders are not." The `notable_customer_wins` field is allowed to be empty rather than fabricated.

### Acquisition history mapping

The industry prompt's `active_competitors` constraint specifies CURRENT names with parent mapping: `Apttus → Conga; Lexion → Ironclad; Selectica → Apttus → Conga; Determine → Corcentric` and `EXCLUDE Sirion itself from active_competitors`.
