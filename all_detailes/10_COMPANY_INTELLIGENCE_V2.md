# 10 — Company Intelligence V2 (`CompanyIntelligenceV2.jsx` + `intelV2/*`)

**Files:** `src/CompanyIntelligenceV2.jsx` (~3389 lines) and the `src/intelV2/` directory (`marketPulsePrompts.js`, `opportunitiesPrompts.js`, `actionsPrompts.js`, `intelCache.js`, `snapshotStore.js`, `newsAggregator.js`, `newsAnalysis.js`, `newsArchive.js`, `newsDedup.js`, `newsSubscriptions.js`, `googleNewsRSS.js`, `handoffM6.js`, `researchCall.js`, `researchLog.js`, `ResearchLogPanel.jsx`, `opportunityArchive.js`).

V2 is the strategic intelligence workbench that succeeded V1. It is built around a **five-lens architecture** (plus a sixth Domino lens documented separately) where every number is auditable via hover tooltips, every AI call is logged in a floating terminal, and every fetch is TTL-bounded with a Refresh-only invalidation discipline.

---

## 1. What V2 Does

- Mounts as a single component (`CompanyIntelligenceV2`) which renders a top bar (time-range + stage filter + Refresh), a "Brief" hero card summarising AI perception, a `LensTabs` strip, and one of six lens panels.
- Loads M2 scan data on mount via `loadCombinedScanDocs()` (the same source Report V5 uses — directly from `m2_scan_results`/`m2_scan_meta` Firestore collections), bypassing the stale `pipeline.m2.scanResults` summary.
- Computes derived state via memoised helpers: `funnel`, `matrix`, `insights`, `brief`, `landscape`, `ownership`, `competitorInsights`.
- Each lens panel is a separate component that consumes either the local computed state or pulls fresh data via `useAsyncLensData` + `getCachedOrFetch`.
- A floating `ResearchLogPanel` is mounted globally so any lens action shows up live with provider, latency, retries, and error.
- All AI work goes through `researchCall(systemPrompt, userMessage, opts)` which walks an ordered provider list, applies exponential-backoff retries on transient errors (5xx / 429 / overload / timeout), runs JSON-repair passes for Gemini, and logs every attempt.
- All persistence (cache + snapshots + archives) defaults to Firestore with localStorage fallback, so dev (no project ID) and offline still work.

---

## 2. The 5 Lenses (Overview)

`LENSES` constant in `CompanyIntelligenceV2.jsx`:

| Id              | Label         | Blurb                                                                                  |
| --------------- | ------------- | -------------------------------------------------------------------------------------- |
| `position`      | Position      | Where we stand: AI visibility, share of voice, narrative, funnel by stage.             |
| `competitors`   | Competitors   | Per-competitor profiles, head-to-head, narrative ownership.                            |
| `pulse`         | Market Pulse  | Auto-fed news (daily Gemini cron), market data, analyst movements.                     |
| `opportunities` | Opportunities | White-space themes, gap queries, persona blind spots.                                  |
| `actions`       | Actions       | Prioritized plays this week, with rationale and owner.                                 |
| `domino`        | Domino        | Predictive correlation engine — industry × company × signal force graph (see file 11). |

The active lens is local React state (`useState("position")`); switching tabs is purely client-side and no AI calls fire on tab change — only on Refresh.

---

## 3. Lens 1 — Position

Pure local computation from M2 scan docs — no AI calls. Three derived structures:

### 3.1 `computeStageRates(scanResults)` — funnel data

Walks `scanResults.results`, buckets by lowercase `stage`, counts per LLM analyses where `mentioned` is true. Returns:

- For each canonical buyer-journey stage that has data, in order: `awareness, discovery, consideration, validation, decision`:
  - `id`, `label` (title-cased)
  - `score` (% of analyses where Sirion was mentioned)
  - `total`, `mentioned`
  - `width` from `FUNNEL_WIDTHS = [100, 86, 72, 58, 44]` (visual narrowing trapezoid).
  - `hint` ("X/Y mentions across N LLMs")
- Fallback: if no canonical stages match, returns whatever stages exist with computed widths.

### 3.2 `computeStageLLMMatrix(scanResults)` — Stage × LLM matrix

Returns:

```
{
  stages: [{ id, label, total, mentioned, score }, ...],
  llms:   [{ id, label, logo, mono, total, mentioned, score }, ...],
  cells:  { "<stageId>|<llmId>": { rate, mentioned, total } },
  overall: { score, total, mentioned }
}
```

LLMs are ordered per `MATRIX_LLM_ORDER = ["claude", "gemini", "openai", "grok", "perplexity"]`. Logos come from `LLM_META` (Claude / Gemini / OpenAI assets imported as SVGs; Grok / Perplexity have monogram fallbacks `Gk` / `Px`).

### 3.3 `computeBriefStats(funnel, scanResults)` — hero stats

Returns `{ company: "Sirion", overallScore, strongestStage, weakestStage, questionCount, llmCount }`. `overallScore` is the simple average of stage scores. The Brief card displays the company, the overall 0-100 score (colour-coded by `scoreColor`), strongest/weakest stage names + scores, and a footnote with question + LLM counts.

### 3.4 Visualisations

- **`Brief`** — Gradient brand-bg card with left brand stripe; shows last-scan date if available.
- **`FunnelSankey`** — 3-column Recharts Sankey chart: Stage → LLM → Outcome (Mentioned / Missed). Custom node + link renderers; flows coloured by stage on the left half and by outcome (green/red) on the right half. `nodeSort` disabled on d3-sankey so funnel order is preserved. Tooltip shows source → target with analysis count.
- **`Funnel`** — Trapezoid bands (widths from `FUNNEL_WIDTHS`) with stage colour border; clickable to expand `StageDrillDown`. Each band shows: chevron, stage label, sample count + mention count, big score, fill bar, then a row of per-LLM strips (one per LLM) with logo/monogram + mini bar + rate.
  - Footer of each band shows top non-Sirion competitor in that stage (from `computeTopCompetitorPerStage`) with a "BEATS SIRION HERE" / "SIRION LEADS" badge.
  - Overall row at bottom: total mentions count and brand-coloured % score.

### 3.5 `StageDrillDown` (per-stage expansion)

Click a funnel band to reveal:

- Filter pills: "All questions" + one per LLM ("X missed", count = questions where that LLM did NOT mention Sirion).
- Question cards sorted by lowest Sirion coverage first. Each card shows: qid, persona, query text, coverage like "1/3 LLMs", per-LLM ✓/✗ chips, "Mentioned instead:" line listing top competitors with counts.
- "Show LLM responses" button expands the actual response snippets per LLM (reads `analyses[lid].response_snippet`, `framing`, `sentiment`).
- "Copy question" button.
- Capped at top 12 results visible.

### 3.6 `computeGapInsights(matrix)` — auto-derived "Where the gaps are"

Up to 4 short colour-tagged bullets:

1. Worst single cell with sample ≥ 3 (red — "Worst gap: …")
2. Largest LLM spread within a stage when ≥ 15 points (yellow — "X leads Y at Z by N points — distribution gap, not a brand gap.")
3. Funnel-shape pattern: top-of-funnel deficit if last - first ≥ 25 (yellow), late-funnel deficit if first - last ≥ 25 (yellow).
4. Saturated cell at ≥ 90% (green — "already saturated, low leverage from more investment here.")

Rendered via `GapInsights` with red/yellow/green tone styling and a `GAP/WATCH/STRONG` label badge.

### 3.7 Scoring colours

- `scoreColor(s)`: green ≥ 60, yellow ≥ 40, red otherwise.
- `scoreColorForCompetitor(rate)`: green ≥ 55, yellow ≥ 30, red otherwise (tighter thresholds because any competitor at 30%+ is significant).

### 3.8 Sentiment by Stage / by LLM

Sentiment is **not** explicitly broken out in V2's Position lens — it's tracked at the per-question drill-down level (`p.sentiment` rendered alongside framing in the expanded LLM response panel). Stage and LLM columns aggregate `mentioned` counts, not sentiment counts. (V1 had a "Positive Sentiment" hero stat; V2 dropped it from the headline metrics.)

---

## 4. Lens 2 — Competitors

Pure local computation from scan docs.

### 4.1 `computeCompetitiveLandscape(docs)`

Walks every `doc.analyses[llm]`. Reads three vendor arrays per analysis: `supported_vendors`, `unsupported_vendors`, `hallucinated_vendors`. Per vendor (case-normalised via `normalizeVendor` — special-cases `docusign / docu sign` → "DocuSign", `docusign clm` → "DocuSign CLM", `sap ariba` → "SAP Ariba"), aggregates supported / unsupported / hallucinated counts. De-duplicates within an analysis via per-LLM `seen` Sets.

Returns:

```
{
  entries:  [Sirion + topN competitors] sorted by mentionRate desc,
  topCompetitors: ranked.slice(0, TOP_COMPETITOR_COUNT=6),  // min 3 mentions
  sirionRate, totalAnalyses,
  hallucinatedTop: top 3 with hallucinated >= 2
}
```

Each competitor row: `name, supported, unsupported, hallucinated, total, mentionRate, proofRate (= supported/total)`. Rows with `total < MIN_VENDOR_MENTIONS=3` are dropped as long-tail noise.

### 4.2 `computeStageOwnership(docs, competitors)`

For each canonical stage, computes per-vendor mention rate using the same denominator (analyses count at that stage). Returns `{ stages: [{id, label, cells: {Vendor: rate%}, owner}], players: [Sirion, ...top6] }`. Sirion uses `mentioned`; competitors use union of supported + unsupported (deduped per analysis).

### 4.3 `computeCompetitorInsights(landscape, ownership)`

Up to 5 colour-coded "strategic plays":

- **ATTACK** (red) — biggest gap where any competitor leads Sirion at any stage by > 10 pts.
- **DEFEND** (green) — biggest lead Sirion has at any stage vs any competitor by > 10 pts.
- **OPPORTUNITY** (yellow) — competitor with `proofRate < 55` and `mentionRate >= 5` ("vulnerable positioning, ripe for displacement with stronger citations.")
- **HALLUCINATED** (yellow) — top hallucinated vendor with `count >= 2` ("AI invents 'X' as a competitor… Content opportunity to claim that imagined space.")

### 4.4 Visualisations

- **`CompetitorLeaderboard`** — Horizontal bar list. Sirion row has brand background + "YOU" tag. Each row: vendor name, mention rate bar (coloured by `scoreColor`), with-proof % chip (green/yellow/red).
- **`HeadToHead`** — Butterfly chart: Sirion bars right-aligned growing leftward (purple), top competitor bars left-aligned growing rightward (red). Centre column is the stage label. Footer counts wins per side.
- **`StageOwnership`** — Grid: rows = stages, columns = Sirion + top 6 competitors. Cells coloured by `scoreColorForCompetitor`. Owner cell has 2px solid border + ★ corner badge.
- **`CompetitorInsights`** — Same coloured-tone box pattern as `GapInsights` with `ATTACK / DEFEND / OPPORTUNITY / HALLUCINATED` label badges (92px min-width).

---

## 5. Lens 3 — Market Pulse

The most complex lens. Two sub-systems wired together: (a) a **News Feed** that aggregates from three sources and supports filtering + on-demand digest synthesis, and (b) a collapsible **Market Leader Scorecard** with vendor share / capital flow / analyst rankings / trends.

### 5.1 News pipeline

```
loadSubscriptions()  →  aggregateNews({windowDays})  →  dedupNewsItems()  →  archiveNewsItems()  →  rendered
                                                    ↓ on-demand
                                              analyzeNewsFeed(items)  →  DigestPanel
```

Multi-source fan-out via `Promise.allSettled` in `aggregateNews`:

1. **Google News RSS** (`fetchGoogleNewsRssBatch(queries, {windowDays, concurrency: 4})`) — one query per competitor + each industry term + each custom topic, capped at 12 queries to stay under Google's 429 threshold.
   - Competitor / custom topic queries get a CLM-context boolean group appended:
     `(CLM OR "contract management" OR "contract lifecycle" OR legaltech OR "legal tech" OR SaaS)`.
   - Industry terms pass through unmodified.
   - Routed through worker `/api/rss?url=...` (host allowlisted to news.google.com only).
2. **Gemini grounded** (`["gemini-pro-grounded", "gemini-flash-grounded"]`).
3. **Perplexity Sonar Pro** (`["perplexity-pro", "perplexity"]`).

Source diversity acts as a confidence signal — each item that survives dedup carries `sources: [...]` showing which systems corroborated it.

### 5.2 CLM relevance + hard-reject filters

`CLM_RELEVANCE_TERMS` (must include at least one in title/summary):
`clm, contract, contracting, agreement, legal tech, legaltech, saas, software, vendor, platform, agentic, procurement, ai, artificial intelligence, obligation, renewal, compliance, negotiation, redline, esignature, e-signature, docusign, sirion, icertis, ironclad, agiloft, conga, evisort, linksquares, malbek, juro, summize, contractpodai, leah, gartner, forrester, idc`.

`HARD_REJECT_TERMS` (drop if matched AND no relevance term present):
`drunk driving, monk, bullpen, closer, home run, world cup, cricket, football, rugby, tennis, basketball, cup final, monsoon, flood, earthquake, hurricane, typhoon, bomber planes, air strike, missile, election, electoral, vote, ballot, campaign rally, celebrity, actor, actress, concert tour, music festival, horoscope, zodiac, astrology`.

(Catches "Ironclad Closer" the baseball pitcher, "Conga" the dance, election-software contracts share-name overlap, etc.)

### 5.3 News dedup (`dedupNewsItems`)

Three-layer:

1. **URL hash** — exact same URL.
2. **Canonical URL** — strips tracking params (`utm_*, gclid, fbclid, mc_cid, mc_eid, yclid, msclkid, _hsenc, _hsmi, ref, ref_src, feature, oc`), lowercases host, strips trailing slash.
3. **Title similarity** — normalised Jaccard ≥ 0.8 on word tokens (length ≥ 3 chars after punctuation strip).

Merge strategy keeps the earliest `published_date`, the longer-publisher-name title, the longer summary, and unions the `sources` arrays. `corroboration = sources.size`. Output sorted by published_date desc, then by corroboration desc as tiebreaker.

### 5.4 News archive (`archiveNewsItems`)

Saves each item to Firestore collection `intel_v2_news_archive` keyed by URL hash (`urlHash` is djb2 hash → base36). Schema: `{id, title, summary, source_url, source_name, published_date, category, affects, impact_score, impact_rationale, first_seen_at, last_seen_at, fetch_count}`. Implementation note: previously did GET-then-PATCH per item (which spammed 404s in console for new items); now writes directly via `saveWithId` — `first_seen_at` is re-stamped per fetch (deemed acceptable trade-off).

### 5.5 News subscriptions (`newsSubscriptions.js`)

Single Firestore doc: `intel_v2_config/news_subscriptions`.

`DEFAULT_SUBSCRIPTIONS`:

```
{
  competitors:    ["Icertis", "Ironclad", "Agiloft", "DocuSign CLM", "Conga"],
  industry_terms: ["contract lifecycle management", "agentic CLM"],
  custom_topics:  []
}
```

Limits: `MAX_COMPETITORS = 8`, `MAX_INDUSTRY = 4`, `MAX_TOPICS = 10`. On first load, if the doc doesn't exist, V2 seeds defaults (auto-seed write tagged `updated_by: "auto-seed"`) so the 404 doesn't recur.

`CURATED_TOPIC_CHIPS`:

```
"Agentic CLM", "AI in legal tech", "M&A activity", "Funding rounds",
"Product launches", "Gartner Magic Quadrant", "Forrester Wave",
"Pricing changes", "Customer wins", "Executive moves"
```

The `SubscriptionsModal` admin UI lets users add/remove chips per category, with chip caps and inline validation.

### 5.6 Verbatim prompts — `marketPulsePrompts.js`

Top-level constants:

- `TARGET_COMPANY = "Sirion"`
- `COMPETITORS = ["Icertis", "Ironclad", "Agiloft", "DocuSign", "Conga", "LinkSquares", "Malbek", "Evisort", "Juro"]`
- `FRESH_NEWS_DAYS = 30`, `FRESH_CAPITAL_DAYS = 365`.

#### `NEWS_SYSTEM`

> ```
> You are a CLM industry analyst tracking competitor moves and market signals for Sirion's marketing leadership. You produce structured, source-attributed news intelligence — never speculation, always with verifiable URLs.
> ```

#### `buildNewsUser(windowHours = 168)`

> ```
> Find news from the last ${windowHours} hours that could materially affect Sirion's competitive position in the CLM (Contract Lifecycle Management) market.
>
> What to track:
> - Direct competitors: ${COMPETITORS.join(", ")}
> - Sirion itself
> - CLM-adjacent moves from large platforms (Salesforce, SAP, ServiceNow, Oracle) in contract or procurement
> - Analyst coverage (Gartner Magic Quadrant, Forrester Wave, IDC) when they shift CLM positioning
> - Funding rounds, M&A, executive moves at any of the above
> - AI-in-CLM / Agentic CLM trend coverage
>
> For each news item, return:
> {
>   "title":            "short factual headline",
>   "summary":          "2-3 sentences: what happened and why it matters to Sirion",
>   "source_url":       "verifiable URL",
>   "source_name":      "publication or company",
>   "published_date":   "ISO 8601",
>   "category":         "Threat" | "Opportunity" | "Neutral",
>   "affects":          "primary entity affected (company name or 'Industry')",
>   "impact_score":     1-10,
>   "impact_rationale": "one sentence explaining the score"
> }
>
> Category rules:
> - Threat: helps a Sirion competitor or hurts Sirion directly
> - Opportunity: weakens a competitor, validates Sirion's positioning, or opens new white space
> - Neutral: industry context, no immediate competitive read
>
> Impact score rubric:
> 1-3:   minor / informational ("competitor hires VP of marketing")
> 4-6:   notable, worth tracking ("competitor launches new feature")
> 7-9:   significant, calls for response ("competitor enters our home turf banking vertical with named pilot")
> 10:    existential or category-defining ("Microsoft acquires Icertis")
>
> Return strict JSON: { "items": [...], "window_used_hours": ${windowHours}, "items_found": N }
>
> Constraints:
> - Skip if URL not verifiable — do not fabricate.
> - If <3 items found in ${windowHours}h, double the window and report the new value in window_used_hours.
> - Skip Sirion's own marketing announcements (CMO already knows them).
> - Skip generic 'Top 10 CLM' listicles unless they reposition vendors.
> - Sort by impact_score descending.
> - Return at most 12 items.
> ```

#### `VENDOR_SHARE_SYSTEM`

> ```
> You are a CLM market researcher serving a CMO. You return vendor revenue share with diverse, verifiable source URLs — every row sourced independently, never a single anchor citation. If you cannot source a vendor independently, omit it.
> ```

#### `VENDOR_SHARE_USER`

> ```
> Return vendor market-share data for the Contract Lifecycle Management (CLM) software category.
>
> CRITICAL — SOURCE DIVERSITY IS MANDATORY:
> Each vendor row MUST cite a DIFFERENT source URL than the others. If all
> your rows would cite the same Mordor Intelligence / IDC / Gartner
> landing page, you have not done the research — those are category
> overviews, not per-vendor share studies. A vendor row's source must be
> ONE of:
>   - That vendor's own ARR disclosure (vendor blog, press release, 10-K)
>   - A funding round announcement giving an implied valuation/ARR (Crunchbase, TechCrunch, vendor PR)
>   - A specific named-vendor analyst report or press article
>   - A Gartner / Forrester / IDC piece that names this vendor by share %
>
> If you can only find ONE source URL that names all vendors generically
> (e.g., a "Top 10 CLM" listicle or a TAM report), DO NOT use it for
> multiple rows — pick at most ONE row from it and find independent
> sources for the rest.
>
> Required fields:
>
> 1. category_context (one row, compact):
>    { tam_usd, year, cagr_pct, cagr_period, source_url, source_name }
>
> 2. vendor_market_share: [{
>      name, share_pct (number, REQUIRED), year,
>      yoy_change_pct: number or null,
>      confidence: "high" | "medium" | "low" (REQUIRED),
>      source_url, source_name
>    }]
>
>    PURE-PLAY CLM ONLY. Vendors to research independently:
>      Icertis, Ironclad, Agiloft, Conga, DocuSign CLM, Malbek, Evisort,
>      ContractPodAI, LinkSquares, Juro, Summize, SirionLabs.
>
>    For parent conglomerates (SAP, Oracle, IBM) name the CLM line:
>    "SAP Ariba CLM", "Oracle Contract Management", never bare parent.
>
>    confidence rules:
>    - "high":   share_pct comes from a named analyst's CLM market-share study
>    - "medium": share_pct from press coverage citing the analyst, or from
>                vendor's own disclosed ARR vs. TAM math (different math
>                per vendor, not all from one TAM anchor)
>    - "low":    author estimate from independent sources (e.g.,
>                Crunchbase funding-implied valuation × revenue multiple).
>                Each "low" row's source_name MUST contain different math
>                and a different source_url than the other rows.
>
>    Return AT LEAST 5 vendors (target 6-10). Quality > quantity. Better
>    to return 5 well-sourced rows than 10 fabricated ones. If you cannot
>    find diverse sources for at least 5 vendors, return what you have
>    and let the section be smaller.
>
>    Include ${TARGET_COMPANY} if any reasonable revenue estimate exists
>    from a real funding round / press coverage. Do NOT substitute
>    AI-perception rates for revenue share.
>
> Sort vendor_market_share by share_pct descending.
>
> Return strict JSON: { "category_context": {...}, "vendor_market_share": [...] }
> ```

#### `ANALYST_RANKINGS_SYSTEM`

> ```
> You are a CLM market researcher. You return analyst rankings (Gartner Magic Quadrant, Forrester Wave, IDC MarketScape) ONLY with verifiable source URLs from the actual analyst firms or named press coverage. You do NOT attribute one analyst firm's content to another. You do NOT cite generic "buyers guide" PDFs as if they were Gartner MQ or Forrester Wave reports.
> ```

#### `ANALYST_RANKINGS_USER`

> ```
> Return analyst-firm rankings for the CLM (Contract Lifecycle Management) category.
>
> CRITICAL — DOMAIN VERIFICATION IS MANDATORY:
> Each analyst block's source_url MUST come from the analyst's own domain
> or from named tier-1 press coverage of that specific report:
>   - gartner_mq      → gartner.com OR press citing the specific report
>                        year (Reuters, Bloomberg, Forbes, TechCrunch,
>                        prnewswire.com / businesswire.com vendor PR
>                        naming "named a Leader in the Gartner Magic
>                        Quadrant for CLM <year>")
>   - forrester_wave  → forrester.com OR same press tier
>   - movements       → vendor PR or analyst-cited press coverage of
>                        a specific quadrant change
>
> DO NOT cite mgiresearch.com, mordorintelligence.com, marketsandmarkets.com,
> or "Top N CLM Buyers Guide" PDFs as if they were Gartner MQ or Forrester
> Wave — those are different reports from different firms.
>
> If you cannot find a verifiable source for gartner_mq, OMIT the
> gartner_mq block (do not fabricate). Same for forrester_wave.
> Returning ONLY movements is fine if neither full report is verifiable.
>
> Schema:
> {
>   "gartner_mq": {
>     year, leaders: [string], visionaries: [string],
>     challengers: [string], niche_players: [string],
>     source_url, source_name
>   } | null,
>   "forrester_wave": {
>     year, leaders: [string], strong_performers: [string],
>     contenders: [string], source_url, source_name
>   } | null,
>   "movements": [{
>     vendor, from_quadrant, to_quadrant, year, source_url, source_name
>   }]
> }
>
> Most recent published year only. ACTUAL named vendors per tier — do
> not synthesize tier membership across years.
>
> Return strict JSON.
> ```

#### `CURRENT_EVENTS_SYSTEM`

> ```
> You are a CLM industry researcher tracking current events — funding rounds, M&A, product launches, executive moves. You return real, recent, sourced events. Each event must cite a specific article, press release, or Crunchbase profile — NOT a generic category report.
> ```

#### `CURRENT_EVENTS_USER`

> ```
> Return current-events data for the CLM (Contract Lifecycle Management) software category.
>
> CRITICAL — every event must cite a SPECIFIC article or press release.
> Do NOT cite Mordor Intelligence, MarketsAndMarkets, or Gartner category
> reports — those are sizing/landscape documents, not event coverage.
> Use TechCrunch / Reuters / Bloomberg / Crunchbase profile pages /
> vendor blog posts / business wire press releases for each event.
>
> Schema:
>
> 1. capital_flow: [{
>      event_type: "funding" | "acquisition" | "ipo" | "exec_move",
>      company, counterparty: string|null,
>      amount_usd: number|null, round: string|null,
>      date, source_url, source_name
>    }]
>    — Last 18 months. CLM vendors + direct adjacents (Salesforce CLM,
>      SAP Ariba CLM, Workday Contract).
>    — Funding >= $5M; all M&A regardless of size; C-level / founder
>      exec moves at named CLM vendors.
>    — TARGET: 4-8 events. The CLM space has had multiple in 18 months;
>      if you find 0, you didn't search hard enough.
>    — Acceptable sources: TechCrunch, Reuters, Bloomberg, Crunchbase,
>      PitchBook articles, vendor PR releases on prnewswire.com /
>      businesswire.com.
>
> 2. recent_launches: [{
>      company, product_or_feature, date, source_url, source_name
>    }]
>    — Last 9 months, competitors only. Skip Sirion's own launches.
>    — TARGET: 3-6 launches. Source must be a vendor blog post,
>      product page, or product-launch press release — NOT a market
>      report listing the launch in passing.
>
> Sort capital_flow by date descending. Sort recent_launches by date
> descending. Every item must include source_url and verifiable date.
>
> Return strict JSON: { "capital_flow": [...], "recent_launches": [...] }
> ```

#### `TRENDS_SYSTEM`

> ```
> You are a market analyst who assesses qualitative shifts in public discussion of B2B software topics. Make best-effort calls based on coverage volume, news cadence, search-trend signals, and analyst commentary. "Unknown" is the LAST resort, not a default — if the topic gets any meaningful coverage at all, you can call rising/flat/declining with appropriate confidence.
> ```

#### `buildTrendsUser(extraTopics = [])`

Base topics: `"Agentic CLM", "AI in contract lifecycle management", "Generative AI for legal", TARGET_COMPANY` (capped at 8 total once `extraTopics` are appended).

> ```
> For each topic, assess the change in public conversation volume over the last 90 days vs the prior 90 days.
>
> Topics:
> ${all.map(t => `- "${t}"`).join("\n")}
>
> For each:
> {
>   "topic": "...",
>   "direction": "rising" | "flat" | "declining",      // make a call — see rules below
>   "magnitude_pct_estimate": number,                   // best estimate, even if rough
>   "confidence": "high" | "medium" | "low",
>   "evidence": [{ "snippet": "...", "source_url": "..." }]   // 2-3 items
> }
>
> How to call direction (use these heuristics):
> - News volume: more articles in last 90d than prior 90d → rising; fewer → declining; ~same → flat
> - Search-interest signals (Google Trends, etc., when accessible)
> - Analyst report cadence (more Gartner / Forrester coverage = rising)
> - Vendor-launch density on the topic
>
> Confidence calibration:
> - high: clear cadence shift backed by 3+ evidence items
> - medium: directional signal but limited evidence
> - low: gut call from sparse coverage — STILL fine to return, just flag low
>
> Only return "direction": "unknown" if you literally cannot find ANY recent coverage of the topic at all. This should be very rare for the topics listed above (CLM/AI is a hot space).
>
> Return strict JSON: { "topics": [...] }
> ```

#### `NEWS_SYSTEM_GEMINI` (in `newsAggregator.js`)

> ```
> You are a CLM industry analyst tracking competitor moves and market signals for Sirion's marketing leadership. You produce structured, source-attributed news intelligence — never speculation, always with verifiable URLs. STRICT TOPIC FILTER: only Contract Lifecycle Management (CLM), legaltech, contract automation, e-signature, procurement-contract, or directly-CLM-adjacent enterprise SaaS news. Reject sports, politics, celebrity, weather, regional crime, election results — even if they share a competitor name (e.g., "Ironclad" the baseball pitcher, "Conga" the dance, "Agiloft" homophones).
> ```

#### `buildAINewsUser({windowDays, competitors, industryTerms, customTopics})` (aggregator)

> ```
> Find news from the last ${windowDays} days that could materially affect Sirion's competitive position in the CLM (Contract Lifecycle Management) market.
>
> Topics / entities to track (these are the configured watch list — make sure each gets some coverage if relevant news exists):
> ${trackList.map(t => `  - "${t}"`).join("\n")}
>
> CRITICAL — TOPIC SCOPE:
> Only return news that is materially about ONE of:
>   • A CLM vendor's product, funding, M&A, leadership move, or analyst placement
>   • A CLM-adjacent enterprise software move (procurement, e-signature, legal AI, agentic AI in legal/contracts)
>   • Analyst-firm reports on CLM (Gartner MQ, Forrester Wave, IDC MarketScape for CLM)
>   • Contract/legal/procurement industry trend pieces with named vendors
>
> REJECT outright (do NOT include in output):
>   • Sports, baseball, cricket, football — even if a competitor name appears as an adjective
>   • Election results, government announcements unrelated to procurement contracts
>   • Celebrity / entertainment / lifestyle pieces
>   • Weather, disaster, crime stories
>   • Generic AI / tech pieces with no contract or CLM angle
>   • Stories that name a competitor only as an adjective (e.g., "ironclad security" describing election integrity)
>
> For each accepted news item return:
> {
>   "title": "short factual headline",
>   "summary": "2-3 sentences: what happened and why it matters to Sirion",
>   "source_url": "verifiable URL (publisher direct, not aggregator redirect)",
>   "source_name": "publication or company",
>   "published_date": "ISO 8601",
>   "category": "Threat" | "Opportunity" | "Neutral",
>   "affects": "primary entity affected (company name or 'Industry')",
>   "impact_score": 1-10,
>   "impact_rationale": "one sentence explaining the score",
>   "matched_topic": "which configured topic this matches (use exact string from the list above)"
> }
>
> Constraints:
> - Skip if URL not verifiable — do not fabricate.
> - Skip Sirion's own marketing announcements (CMO already knows them).
> - Skip generic 'Top 10 CLM' listicles unless they reposition vendors.
> - Sort by impact_score descending. Return at most 15 items.
> - It is BETTER to return fewer high-quality CLM-relevant items than to pad the list with tangential tech news.
>
> Return strict JSON: { "items": [...] }
> ```

#### `DIGEST_SYSTEM` (in `newsAnalysis.js`)

> ```
> You are a CMO's weekly market intelligence analyst for Sirion (a CLM software vendor). You read raw news items and produce a tight, decision-grade digest: what changed, who's threatening, where the openings are, and what to do this week. You never repeat what's in the items verbatim; you synthesize patterns ACROSS items.
> ```

#### `buildDigestUser(items, windowDays)`

Compacts the first 60 items to `{n, title, source, date, category, affects, impact, summary (200 chars), sources_corroborating}` then:

> ```
> Synthesize a weekly market intelligence digest for Sirion's CMO. Window: last ${windowDays} days. ${items.length} news items.
>
> INPUT ITEMS (compact form, [n] = index for reference):
> ${JSON.stringify(compact, null, 2)}
>
> Produce a STRICT JSON response with this shape:
>
> {
>   "exec_summary": "1 paragraph (3-5 sentences). What's the big picture this week? What changed? Tie it to Sirion's competitive context.",
>
>   "top_threats": [
>     {
>       "threat": "short headline of the threat",
>       "explanation": "2-3 sentences: what's happening and why Sirion should care",
>       "recommended_response": "1-2 sentences: a CONCRETE marketing/positioning action Sirion should take",
>       "evidence_item_indexes": [n, n]
>     }
>     // 3 items, ordered most urgent first
>   ],
>
>   "top_opportunities": [
>     {
>       "opportunity": "short headline",
>       "explanation": "2-3 sentences",
>       "recommended_response": "1-2 sentences",
>       "evidence_item_indexes": [n]
>     }
>     // 2 items
>   ],
>
>   "suggested_plays": [
>     "Concrete play 1 (one sentence, action verb start, e.g., 'Publish a comparison page targeting Ironclad Q3 customers...')",
>     "Concrete play 2",
>     "Concrete play 3"
>     // 3-5 plays
>   ],
>
>   "competitor_pattern_notes": "1 short paragraph IF you spot a multi-vendor pattern (e.g., 'Three competitors shipped agentic features this week, suggesting category convergence on autonomous CLM'). Empty string otherwise."
> }
>
> Rules:
> - "evidence_item_indexes" MUST be valid indexes from the input list (1-based). Each threat/opp must cite at least one evidence item.
> - Threats outrank opportunities in priority.
> - Suggested plays must be ACTIONABLE for a marketing team this week, not generic ("do better content").
> - If the week's news is genuinely uneventful, say so in exec_summary rather than padding.
>
> Return strict JSON only. No prose outside the JSON.
> ```

### 5.7 Hallucination guard validators

Three host-allowlist functions in `marketPulsePrompts.js`:

- **`ANALYST_HOSTS`** allowlist: `gartner.com, forrester.com, idc.com, reuters.com, bloomberg.com, forbes.com, techcrunch.com, prnewswire.com, businesswire.com, globenewswire.com, wsj.com, ft.com, venturebeat.com`.
- **`GENERIC_REPORT_HOSTS`** rejectlist: `mordorintelligence.com, marketsandmarkets.com, grandviewresearch.com, fortunebusinessinsights.com, mgiresearch.com, researchandmarkets.com, alliedmarketresearch.com, imarcgroup.com`.

`validateVendorShareDiversity(rows)` — rejects entire section if unique-host ratio < 0.6 OR unique hosts < 4 (when 6+ rows) OR > 2 rows cite generic-report hosts. Throws `Error.code = "NO_USEFUL_DATA"`.

`validateAnalystDomains(rankings)` — drops `gartner_mq` / `forrester_wave` blocks whose source_url isn't in `ANALYST_HOSTS`; filters movements similarly. Returns "rejected" only if nothing survives.

`validateCurrentEvents(capitalFlow, recentLaunches)` — drops entries from generic-report hosts. Returns "rejected" if both arrays end up empty.

### 5.8 fetchMarketData parallel orchestration

`fetchMarketData()` runs all three sub-fetches in parallel via `Promise.allSettled`:

| Sub-fetch                 | Provider chain            | Reasoning                                                          |
| ------------------------- | ------------------------- | ------------------------------------------------------------------ |
| `_fetchVendorShare()`     | `RESEARCH_VERIFIED`       | Gemini Pro grounded leads → Google Search returns diverse domains. |
| `_fetchAnalystRankings()` | `RESEARCH_VERIFIED`       | Must hit gartner.com / forrester.com / IDC.                        |
| `_fetchCurrentEvents()`   | `RESEARCH_CURRENT_EVENTS` | Perplexity Pro purpose-built for live news.                        |

Bad analyst response doesn't kill good vendor data. If all three reject, throws `NO_USEFUL_DATA`. If all three failed with auth-expired-pattern errors (case-insensitive match on "access link required|access revoked|access link has expired|ai access expired|\b401\b") returns `AUTH_EXPIRED` instead.

### 5.9 Lens 3 UI components

- **Filters** at top of news panel: window pills (7/30/90d), source pills (All / Google / Gemini / Perplexity with counts), competitor multi-pills (from `subs.competitors`), topic multi-pills (from `subs.industry_terms + custom_topics + CURATED_TOPIC_CHIPS`, deduped, capped at 14).
- **`AggregatedNewsItem`** card — category badge, "affects", date, multi-sources corroboration badge ("✓ N sources" green when N > 1), big impact score with /10 suffix, title, summary, impact rationale, source pills row, source URL link.
- **"Analyze this feed"** button → `handleAnalyze` calls `analyzeNewsFeed` which fires `DIGEST_SYSTEM`+`buildDigestUser` via `SYNTHESIS_PREMIUM`. Result cached implicitly via `setDigest` (no Firestore cache for digests — per-call only).
- **`DigestPanel`** — Brand-bg gradient card with: exec summary paragraph, top threats list (red border-left cards), top opportunities (green border-left cards), suggested plays (ordered list), competitor pattern notes if present.
- **Market Leader Scorecard** (collapsed by default; separate `scorecardEpoch` so its Refresh is decoupled from news Refresh):
  - `VendorShareBlock` — Treemap chart with per-vendor categorical colour from `VENDOR_PALETTE = ["#0ea5e9","#f97316","#10b981","#ec4899","#eab308","#8b5cf6","#14b8a6","#ef4444","#6366f1","#84cc16","#f59e0b"]` (Sirion always brand purple `#a78bfa`). Each tile shows name + share% + YoY delta if present. Source attribution chips below treemap.
  - `CapitalFlowBlock` — Timeline cards, type badge (FUNDING green, M&A red, IPO purple, EXEC yellow), date, company + counterparty, amount.
  - `AnalystBlock` — Cards for Gartner MQ tiers (Leaders / Visionaries / Challengers / Niche) and Forrester Wave tiers (Leaders / Strong Performers / Contenders), plus a Recent Movements list. Hides when empty.
  - `CategoryContextStrip` — TAM + CAGR + year + source link in a compact strip.
  - `TrendsBlock` — Per-topic mini cards with arrow direction (▲ rising green / ▼ declining red / → flat) and magnitude estimate. Hides "unknown" topics; hides block entirely if all are unknown.

---

## 6. Lens 4 — Opportunities

White-space synthesis lens. One Gemini call that reads the existing matrix + landscape + ownership + recent news and returns up to 10 opportunities. Score formula:

```
opportunity_score = round(demand_weight × 0.50 + vulnerability_weight × 0.30 + play_clarity_weight × 0.20)
```

### 6.1 `OPP_SYSTEM`

> ```
> You are a content strategist for Sirion's marketing team. You analyze AI-perception scan data and competitor data to surface UNCLAIMED POSITIONING ANGLES — places Sirion could plant a flag with a clear content play. You are specific, action-oriented, and never recommend a play whose first step you cannot describe.
>
> CRITICAL VERIFICATION REQUIREMENT — before recommending any opportunity, you MUST verify it against Sirion's existing content using web search. Specifically:
>
> 1. For each candidate play, run a web search like:
>      site:sirion.ai "<key topic phrase from the play>"
>    or use your grounded-search tool to look up sirion.ai for that topic.
> 2. If the asset already exists on sirion.ai (a published guide, comparison, case study, etc. that covers the same angle), you have two options:
>      a) DROP the opportunity — don't recommend something Sirion already has.
>      b) REFRAME it as an extension/upgrade of the existing asset, with the existing URL noted.
> 3. Never invent claims about what Sirion has or doesn't have. If you can't verify, say so honestly in verification_evidence.
>
> This verification step is non-negotiable. A CMO will lose trust in this tool if it suggests building something Sirion already published.
> ```

### 6.2 `buildOppUser({matrix, landscape, ownership, news})`

The model never sees the raw 154-question dataset; only aggregated digests:

> ```
> Below is Sirion's AI-perception data. Find the top 8-10 opportunities sorted by leverage.
>
> DATA INPUTS:
>
> A. Stage × LLM matrix — Sirion's mention rate per buyer-stage:
> ${matrixSummary}
>
> B. Sirion's mention rate by LLM:
> ${llmSummary}
>
> C. Top 6 competitors — overall mention rate + how often they're cited with proof:
> ${competitorList}
>
> D. Stage ownership — who owns each buyer-journey stage:
> ${ownershipLines}
>
> E. Recent market news (last 7 days, top 5):
> ${newsSummary}
>
> For each opportunity, return:
> {
>   "title":              "4-6 word imperative phrase",
>   "type":               "theme_gap" | "question_gap" | "persona_gap" | "content_gap",
>   "description":        "2 sentences: what the gap is and why it's open",
>   "evidence":           [{"label":"...", "source":"scan|news|inferred"}],
>   "estimated_demand":   "high" | "medium" | "low",
>   "demand_rationale":   "1 sentence",
>   "competitor_strength":"none" | "weak" | "moderate",
>   "competitor_rationale":"1 sentence",
>   "recommended_play":   "specific 2-3 sentence move",
>   "effort_estimate":    "low" | "medium" | "high",
>   "effort_hours_estimate": number,        // rough total hours to execute the play
>   "opportunity_score":  1-10,
>   "score_breakdown": {
>     "demand_weight":         1-10,
>     "vulnerability_weight":  1-10,
>     "play_clarity_weight":   1-10
>   },
>   "opportunity_rationale": "1 sentence explaining the score",
>
>   // — ROI ("follow the money") block —
>   "impact_estimate":   1-10,              // expected lift in Sirion's mention rate / share of voice if executed
>   "monthly_mentions_gained": number,      // back-of-envelope projection: extra AI mentions/mo if executed (be conservative; flag low confidence)
>   "roi_dollar_gloss":  "string",          // single-line $-value gloss if substantiable; "—" if not
>   "roi_confidence":    "low" | "medium" | "high",
>
>   // — Content Strategy handoff hints —
>   "suggested_placement":     "internal_blog" | "external_blog" | "third_party" | "both",
>   "placement_rationale":     "1 sentence: why this channel",
>   "primary_persona":         "string|null",   // dominant buyer persona this serves
>   "stage":                   "Awareness" | "Discovery" | "Consideration" | "Validation" | "Decision",
>
>   // — REQUIRED Sirion.ai verification (see CRITICAL VERIFICATION REQUIREMENT in system) —
>   "already_exists_on_sirion": true | false,        // Did your search find this on sirion.ai?
>   "verification_search_url":  "string",            // The site:sirion.ai search URL you used
>   "verification_evidence":    "string",            // 1-2 sentences on what you found / didn't find
>   "existing_sirion_asset_url": "string|null"       // If already_exists_on_sirion: the existing URL
> }
>
> SCORE FORMULA (you compute, but show your work in score_breakdown):
> opportunity_score = round(
>   demand_weight        * 0.50 +
>   vulnerability_weight * 0.30 +
>   play_clarity_weight  * 0.20
> )
>
> Where:
> - demand_weight: 10 if theme/question shows in 20+ scan questions, 6 if 10-19, 3 if <10. Calibrate against news volume too.
> - vulnerability_weight: 10 if no competitor >40% on this gap, 7 if one weak (<55%), 4 if entrenched (>=55%).
> - play_clarity_weight: 10 if play is one specific publishable asset, 6 if requires research, 3 if vague.
>
> Return strict JSON: { "opportunities": [...] }, sorted by opportunity_score desc. Limit 10. No duplicates.
> ```

### 6.3 Output schema (per opportunity)

| Field                       | Type                       | Notes                                                         |
| --------------------------- | -------------------------- | ------------------------------------------------------------- |
| `title`                     | 4-6 word imperative phrase |                                                               |
| `type`                      | enum                       | `theme_gap` / `question_gap` / `persona_gap` / `content_gap`  |
| `description`               | 2 sentences                |                                                               |
| `evidence`                  | array of `{label, source}` | source ∈ scan, news, inferred                                 |
| `estimated_demand`          | enum                       | high / medium / low                                           |
| `demand_rationale`          | 1 sentence                 |                                                               |
| `competitor_strength`       | enum                       | none / weak / moderate                                        |
| `competitor_rationale`      | 1 sentence                 |                                                               |
| `recommended_play`          | 2-3 sentences              |                                                               |
| `effort_estimate`           | enum                       | low / medium / high                                           |
| `effort_hours_estimate`     | number                     | UI maps low→4h, medium→16h, high→60h                          |
| `opportunity_score`         | 1-10                       | computed via the formula                                      |
| `score_breakdown`           | object                     | `{demand_weight, vulnerability_weight, play_clarity_weight}`  |
| `opportunity_rationale`     | 1 sentence                 |                                                               |
| `impact_estimate`           | 1-10                       | Drives Y axis on Priority Quadrant                            |
| `monthly_mentions_gained`   | number                     | Drives dot size on Priority Quadrant                          |
| `roi_dollar_gloss`          | string                     | "—" if not substantiable                                      |
| `roi_confidence`            | enum                       | low / medium / high                                           |
| `suggested_placement`       | enum                       | internal_blog / external_blog / third_party / both            |
| `placement_rationale`       | 1 sentence                 |                                                               |
| `primary_persona`           | string\|null               |                                                               |
| `stage`                     | enum                       | Awareness / Discovery / Consideration / Validation / Decision |
| `already_exists_on_sirion`  | bool                       |                                                               |
| `verification_search_url`   | string                     |                                                               |
| `verification_evidence`     | string                     |                                                               |
| `existing_sirion_asset_url` | string\|null               |                                                               |

### 6.4 Provider chain + post-filter

`fetchOpportunities` uses `PROVIDER_CHAINS.RESEARCH_PREMIUM` (live web — verification searches need access), `timeoutMs: 240000`, `maxTokens: 16384`. After return, items are filtered: `already_exists_on_sirion === true` items are dropped UNLESS the title starts with `update|extend|expand|refresh|upgrade|deepen` (case-insensitive — that means the model reframed it). Best-effort archive via `archiveOpportunitySession` to `intel_v2_opportunities_history/<sessionId>` (sessionId = ISO timestamp) plus per-opportunity record in `intel_v2_opportunities_seen/<contentHash>` tracking `first_seen_at`, `last_seen_at`, `occurrence_count`, `latest_score`.

### 6.5 UI

- **Card view (default)** — `OpportunityCard`s in 320px-min grid. Each card has a coloured top stripe (green ≥7, yellow ≥5, red otherwise), type tag, title, score with `ScoreTooltip`, description, "PLAY:" box, attribute chips (demand/competitor/effort/channel), `VerificationChip` (green "✓ verified vs sirion.ai" / yellow "↻ already on sirion.ai (reframed)" / grey "not verified"), ROI line, score rationale, "+ Send to Content Strategy" button.
- **Table view** — `OpportunityTable` with columns Score / Type / Title / Demand / Competitor / Effort / ROI / Channel / Verified / action.
- **Priority quadrant** — `OpportunityPriorityChart` Recharts ScatterChart: X = effort hours, Y = impact, dot size = monthly mentions gained. Reference lines at x=16, y=5 split into ↖ QUICK WINS / ↗ MAJOR PROJECTS / ↙ FILL-INS / ↘ THANKLESS labels.

---

## 7. Lens 5 — Actions

Meta-synthesis lens. Reads insights from the prior four lenses (positionInsights + competitorInsights + recent news + opportunities) and produces 5-8 prioritised plays. Score formula:

```
action_score = round(impact × 0.50 + urgency × 0.30 + ease × 0.20)
```

### 7.1 `ACTIONS_SYSTEM`

> ```
> You are Sirion's CMO chief-of-staff. You translate analytical findings into a prioritized weekly action list — what to personally do, in order of leverage. You write imperative, specific actions a marketing exec can do or delegate this week. You never invent data — every action ties back to a specific input below.
> ```

### 7.2 `buildActionsUser({positionInsights, competitorInsights, news, opportunities})`

> ```
> Synthesize the top 5-8 actions for this week from the inputs below.
>
> INPUTS:
>
> 1. Position-lens gaps:
> ${formatInsights(positionInsights)}
>
> 2. Competitor plays:
> ${formatInsights(competitorInsights)}
>
> 3. News in the last 7 days (Threats + Opportunities only, top 5):
> ${formatNews(news.filter(n => n.category === "Threat" || n.category === "Opportunity"))}
>
> 4. Top 5 white-space opportunities:
> ${formatOpps(opportunities)}
>
> OUTPUT TIERS:
> - "critical"     (1-2 items): if not addressed this week, materially worsens position
> - "watch"        (3-4 items): monitor; one check-in this week
> - "opportunity"  (2-3 items): plays to consider when capacity allows
>
> For each action:
> {
>   "tier":               "critical" | "watch" | "opportunity",
>   "title":              "imperative phrase, 4-8 words",
>   "rationale":          "1 sentence anchored in specific data above",
>   "evidence_links":     [{"label":"...", "url_or_ref":"..."}],
>   "recommended_play":   "2-3 sentences of concrete steps",
>   "effort_estimate":    "low" | "medium" | "high",
>   "owner_suggestion":   "CMO" | "Content Lead" | "PR" | "Product Marketing" | "Analyst Relations",
>   "action_score":       1-10,
>   "score_breakdown": {
>     "impact":  1-10,
>     "urgency": 1-10,
>     "ease":    1-10
>   },
>   "action_rationale":   "1 sentence on the score",
>
>   // — Channel routing for downstream automation —
>   "target_channel":     "internal_blog" | "external_blog" | "press_release" | "analyst_briefing" | "social" | "internal_only",
>   "channel_rationale":  "1 sentence on why this channel"
> }
>
> CHANNEL DEFAULTS (use unless rationale clearly says otherwise):
> - Brand-defining content (pillar pages, category narratives) → external_blog
> - Quick reactions to news / competitor moves → social or external_blog
> - Internal directives (brief sales, brief support) → internal_only
> - Analyst-targeted plays (Gartner / Forrester moves) → analyst_briefing
> - Company news (funding, hires, M&A) → press_release
>
> SCORE FORMULA:
> action_score = round(
>   impact  * 0.50 +
>   urgency * 0.30 +
>   ease    * 0.20
> )
>
> Where:
> - impact = how much this would move Sirion's position. Tie to a specific number from the inputs (e.g. "would close the Awareness × Claude gap of 24 points").
> - urgency = time pressure. 10 if a competitor is actively widening a gap right now, 6 if quarterly, 3 if evergreen.
> - ease = inverse of effort. 10 if low (<4h), 6 if medium (1-3 days), 3 if high (1+ week).
>
> Constraints:
> - Tier "critical" requires action_score >= 8.
> - Sort within each tier by action_score descending.
> - No more than 8 total actions.
> - No duplicate plays — if Position and Competitors both surface the same fix, merge into one action and cite both as evidence.
>
> Return strict JSON: { "actions": [...] }
> ```

### 7.3 Tiers + score discipline

- **critical** (1-2 items, requires `action_score >= 8`).
- **watch** (3-4 items).
- **opportunity** (2-3 items).
- Cap 8 total. Sorted within each tier by action_score desc.

### 7.4 Channels enum

`internal_blog`, `external_blog`, `press_release`, `analyst_briefing`, `social`, `internal_only`.

### 7.5 Provider + UI

`fetchActions` uses `PROVIDER_CHAINS.SYNTHESIS_PREMIUM` (`gemini-pro` → `claude-fast` → `openai`) — pure synthesis, no live web needed. `timeoutMs: 180000`, `maxTokens: 16384`.

UI groups items by tier. Each `ActionCard`: tier badge, title, score with `ScoreTooltip`, rationale, "PLAY:" box, attribute chips, channel rationale, score rationale, three buttons: Copy as MD (calls `actionToMarkdown`), Copy for Slack (`actionToSlack`), + Send to Content Strategy (`transferActionToM6`).

---

## 8. Cache TTLs (`intelCache.js`)

Single Firestore collection `intel_v2_cache` keyed by stable string id. Each entry: `{computed_at, ttl_ms, data}`. Falls back to localStorage with prefix `xt_intelv2_cache_`.

```
NEWS_24H        =  1 day
MARKET_DATA_30D = 30 days   // vendor share / analyst position
TRENDS_14D      = 14 days
OPPORTUNITIES   = 14 days
ACTIONS         =  7 days
```

Legacy aliases: `MARKET_DATA_7D` re-aliased to 30d, `TRENDS_7D` re-aliased to 14d.

The actual lens cache keys used in V2:

- News feed: `news_feed_${windowDays}d` with TTL `NEWS_FEED_TTL = 60 * 60 * 1000` (1 hour — news feels live without burning every refresh, separate from the file's `NEWS_24H`).
- Market scorecard: `market_pulse_scorecard` with `MARKET_DATA_30D`.
- Trends: `market_pulse_trends` with `TRENDS_14D`.
- Opportunities: `opportunities_v1` with `OPPORTUNITIES`.
- Actions: `actions_v1` with `ACTIONS`.

Note (caller spec mentioned 24h/4h/12h/12h, but the actual constants are as listed above). The `useAsyncLensData` hook is **cache-only on mount** (returns `status: "no_cache"` with no AI call if cache empty). Refresh = bump `forceEpoch` → bypasses cache.

---

## 9. Snapshot Store (`snapshotStore.js`)

Daily snapshot persistence in Firestore collection `intel_v2_snapshots`, doc id = `YYYY-MM-DD` (idempotent — same day overwrites). Falls back to localStorage prefix `xt_intelv2_snapshot_` capped at 90 days (oldest evicted).

### `captureSnapshot(payload)`

Writes a doc with `date`, `captured_at`, plus payload fields:

```
{
  vendor_share, ai_share_of_voice, stage_scores, overall_score,
  news_count_by_category, capital_flow_count, _provider
}
```

Best-effort: localStorage first (always works), then Firestore. Never throws.

### `loadSnapshots(days = 30)`

Reads recent snapshots from both stores (Firestore overwrites local for authoritative copy). Returns oldest → newest.

V2 calls `captureSnapshot` automatically inside `MarketPulseLens` whenever `scorecard.status === "ready"` and `sirionLandscape` is loaded — feeds vendor share, ai share of voice (built from landscape entries), per-stage scores, overall score, news counts grouped by category, capital flow count, and provider tag.

---

## 10. Handoff to M6 (`handoffM6.js`)

**Stub bridge** to Content Strategy v2. Currently builds payload + console.logs + alert("…stub fired"); the actual write into `pipeline.m6v2.topics` is wired up later.

### Mapping helpers

`STAGE_TO_LIFECYCLE`: every stage (Awareness/Discovery/Consideration/Validation/Decision) → `"pre-signature"`.

`PLACEMENT_TO_TRACK`: `internal_blog`/`internal_only` → `"client-blog"`, `external_blog`/`third_party`/`press_release`/`analyst_briefing`/`social` → `"third-party"`, `both` → `"both"`.

### `buildOpportunityHandoff(opp, sourceMeta)` payload

`{sourceModule: "intel_v2_opportunities", sourceCapturedAt, sourceMeta:{gemini_provider, score_breakdown, opportunity_score, ...}, title, angleHook (recommended_play || description), description, addressesGapIds (evidence labels), persona, stage, lifecycle, placement, placementRationale, estimatedDemand, competitorStrength, effortEstimate, effortHoursEstimate, roiDollarGloss, monthlyMentionsGained, alreadyExistsOnSirion, existingSirionAssetUrl, verificationSearchUrl, verificationEvidence}`.

### `buildActionHandoff(action, sourceMeta)` payload

`{sourceModule: "intel_v2_actions", ..., title, angleHook (recommended_play || rationale), description (rationale), placement, placementRationale, targetChannel, effortEstimate, ownerSuggestion, evidenceLinks}`.

### `transferOpportunityToM6(opp)` / `transferActionToM6(action)`

Build payload, console.info it, return `{ok: true, queued: true, payload, _stub: true}`.

### `actionToMarkdown(action)` — copy-to-MD format

Generates a markdown doc with `# title` / Tier · Score · Owner · Effort · Channel / `## Why this matters` (rationale) / `## Recommended play` / `## Evidence` (markdown links) / `## Score breakdown` (Impact/Urgency/Ease lines) / footer `_Source: Xtrusio Company Intel V2 — generated YYYY-MM-DD_`.

### `actionToSlack(action)` — Slack block

`*[TIER] title* · score/10` + blockquote rationale + `*Play:*` line + owner/effort/channel line.

---

## 11. Research Log (`researchLog.js`, `ResearchLogPanel.jsx`)

In-memory + localStorage event log for AI calls. `MAX_ENTRIES = 200`, `LS_KEY = "xt_research_log_v1"`. Restored on module load.

### `logResearchCall(entry)`

Stamps `t: Date.now()`, unshifts to `_logs`, persists, notifies all subscribers. Entry types: `start`, `attempt_start`, `attempt_ok`, `attempt_fail`, `success`, `failure`. Optional fields: `callId`, `provider`, `ms`, `totalMs`, `error`, `summary`, `repaired`, `retries`.

### `subscribeToLogs(fn)`

Adds listener to `_listeners` Set, immediately fires with current state, returns unsubscribe.

### `clearLogs()`

Empties array, persists, notifies.

### `ResearchLogPanel`

Floating bottom-right pill ("AI logs · N · M live") that expands into a 720px terminal panel showing the last 200 entries. Each row: timestamp, symbol (▶ start, · attempt, ✓ ok, ✗ fail, ■ end), type label, provider, latency, total time, repair flag, retry counter, summary. Pill colour: yellow if any active calls, red if last failure, green if last success, grey idle. Pulse animation on the dot when calls live.

---

## 12. Research Call (`researchCall.js`)

The unified AI helper. Walks `opts.providers` in order, returns first success. Each provider gets up to 3 exponential-backoff retries on transient errors (5xx / 429 / overload / timeout) at 1s / 2s / 4s waits. For Gemini-only: a malformed-JSON response triggers one repair pass via `repairAndParse(rawText)` which strips code fences, fixes smart quotes / trailing commas / unescaped newlines, and balances braces.

### Provider IDs

| Id                      | Backend                                                              | Notes                          |
| ----------------------- | -------------------------------------------------------------------- | ------------------------------ |
| `perplexity-pro`        | `callPerplexity({model: "sonar-pro"})`                               | Real-time web, highest quality |
| `perplexity`            | `callPerplexity({model: "sonar"})`                                   | Real-time web, cheap           |
| `gemini-pro`            | `callGemini({model: "gemini-2.5-pro"})`                              | No grounding                   |
| `gemini-pro-grounded`   | `callGemini({model: "gemini-2.5-pro", tools: [{google_search:{}}]})` |                                |
| `gemini-flash-grounded` | `callGemini({tools: [{google_search:{}}]})`                          | Cheap live web                 |
| `gemini-flash`          | `callGemini({})`                                                     | No grounding                   |
| `claude-research`       | `callClaude` (Sonnet 4 + web_search built-in)                        |                                |
| `claude-fast`           | `callClaudeFast` (Sonnet 4, no tools, JSON synthesis)                |                                |
| `openai`                | `callOpenAI` (GPT-4o, no grounding)                                  | Synthesis only                 |

### `PROVIDER_CHAINS`

| Chain                     | Order                                                              | Use case                                                        |
| ------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------- |
| `RESEARCH_PREMIUM`        | `perplexity-pro` → `gemini-pro-grounded` → `perplexity`            | Live-web, world-class. News, opportunities (need verification). |
| `RESEARCH_FAST`           | `perplexity` → `gemini-flash-grounded`                             | Trends-cost-conscious.                                          |
| `RESEARCH_VERIFIED`       | `gemini-pro-grounded` → `perplexity-pro` → `gemini-flash-grounded` | Vendor share, analyst rankings. Diverse domain returns.         |
| `RESEARCH_CURRENT_EVENTS` | `perplexity-pro` → `gemini-pro-grounded` → `perplexity`            | Capital flow, product launches.                                 |
| `SYNTHESIS_PREMIUM`       | `gemini-pro` → `claude-fast` → `openai`                            | Pure synthesis no web. Actions.                                 |
| `SYNTHESIS`               | `gemini-flash` → `openai`                                          | Older preset, kept for compat.                                  |

OpenAI is **never** put in a research chain — it has no live web access and would return training-cutoff content (this caused the 2023-dated "news" the user saw).

`isRetryable(errMsg)` regex: `\b(503|502|504|500|429|rate limit|timed out|timeout|temporarily unavailable|overload|service unavail)\b`.

Each call gets a `callId = "rc_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 6)` for tracing through the log panel.

---

## 13. Cross-LLM Provider Chains (Summary)

(See section 12 above — same content.)

---

## 14. Firestore Collections Used

| Collection                                                                                                        | Purpose                           | Doc id pattern                                                                                                         |
| ----------------------------------------------------------------------------------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `intel_v2_cache`                                                                                                  | TTL-bounded lens cache            | stable string (e.g. `news_feed_7d`, `market_pulse_scorecard`, `opportunities_v1`, `actions_v1`, `market_pulse_trends`) |
| `intel_v2_snapshots`                                                                                              | Daily snapshots                   | `YYYY-MM-DD`                                                                                                           |
| `intel_v2_news_archive`                                                                                           | Permanent news ledger             | `urlHash(source_url)` (djb2 → base36)                                                                                  |
| `intel_v2_config/news_subscriptions`                                                                              | Admin subscription doc            | fixed                                                                                                                  |
| `intel_v2_opportunities_history`                                                                                  | Opportunity session snapshots     | sessionId = ISO timestamp                                                                                              |
| `intel_v2_opportunities_seen`                                                                                     | Per-opportunity occurrence ledger | content hash of `type                                                                                                  | title.lowercase` |
| `intel_v2_domino_industries` / `_companies` / `_signals` / `_matrix_snapshots` / `_correlations` / `_predictions` | Domino lens data (see file 11)    | per-collection ids                                                                                                     |

The M2 source data is read from existing `m2_scan_meta` and `m2_scan_results` (via `loadCombinedScanDocs` in `m2ScanLoader.js`).

---

## 15. Client Portal Mode Behaviour

V2 doesn't have an explicit "client portal" toggle, but several behaviours are tuned for it:

- **Cache-first mount** (`useAsyncLensData` runs cache-only on mount, returns `status: "no_cache"` instead of auto-firing AI — "Logging in doesn't auto-run AI calls anymore — those cost tokens").
- **AUTH_EXPIRED panel** (`AuthExpiredPanel`) renders when researchCall returns the auth-expired error code, instead of surfacing raw "Access link required" worker errors. Includes a "Sign out and reload" button that clears `localStorage.xt_auth_session` + `sessionStorage.xt_token` + `sessionStorage.xt_client` and reloads.
- **Persistence indicator** (in Domino, file 11) tracks Firestore write health so users know whether they're seeing real saved data or local-only.
- **Source-attribution** everywhere: every news item has source_url chips, every market data block has visible source links — designed for client trust.

---

## 16. Edge Cases

### M2 staleness

`pipeline.m2.scanResults` is a stale/compacted summary on most tenants. V2 instead calls `loadCombinedScanDocs()` to read directly from `m2_scan_results` collection (~154 docs canonical). If load fails, sets `loadError` and renders error card; if empty, the Brief shows the empty state and lenses gracefully degrade (e.g., `CompetitorsLens` shows "No competitor data yet" CTA).

### News hallucination

Three-layer defence:

1. Per-source CLM-relevance keyword filter + hard-reject term filter at aggregator level.
2. Cross-source dedup — items found by multiple providers gain corroboration count.
3. URL diversity validators in `fetchMarketData` reject sub-sections where every row cites the same generic-report host.

If all three news sources return zero items the aggregator throws `NO_USEFUL_DATA` rather than caching emptiness.

If all three sub-sources fail with auth-expired errors, throws `AUTH_EXPIRED` so the lens shows the friendly panel instead of "All 3 sub-sections failed".

### Opportunity false positives

The OPP_SYSTEM mandates a `site:sirion.ai "topic"` verification search. Items where `already_exists_on_sirion === true` are dropped UNLESS the model reframed the title with `update|extend|expand|refresh|upgrade|deepen` prefix.

### Action tier inflation

Prompt explicitly enforces `Tier "critical" requires action_score >= 8`. The synthesis prompt is also told to merge duplicates if Position and Competitors surface the same fix, citing both as evidence.

### Empty trends / trends bail-out

`fetchTrends` refuses to cache a result where every topic is "flat 0%" with no evidence (`directional === 0 && totalEvidence < 2`). Throws `NO_USEFUL_DATA`.

### Empty digest

`analyzeNewsFeed` validates that at least one of exec_summary / threats / opportunities is non-empty; otherwise refuses to cache (`NO_USEFUL_DATA`).

### Race condition in scan load

`captureSnapshot` only fires when both `scorecard.status === "ready"` AND `sirionLandscape` is non-null — prevents writing a snapshot with half the data.

### StrictMode double mount

The `useAsyncLensData` hook tracks `lastForceEpochRef` so a StrictMode-induced re-mount doesn't re-trigger a fetch as if it were a Refresh.

### Stale market scorecard doesn't replace good data

If `_section_status` shows partial failure (e.g., vendor share rejected, analyst OK), V2 keeps the OK section and surfaces a per-section error message rather than wiping everything. `_provider` is tagged `mixed:vendor=fail/analyst=gemini-pro-grounded/events=perplexity-pro` so the cache log explains what happened.
