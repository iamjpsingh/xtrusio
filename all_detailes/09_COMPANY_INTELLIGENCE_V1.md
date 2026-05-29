# 09 — Company Intelligence V1 (`CompanyIntelligence.jsx`)

**File:** `src/CompanyIntelligence.jsx` (~972 lines)

V1 is the original "Sirion Intelligence" dashboard — a four-tab strategic overview built on top of the M2 Perception Monitor scan data, with two manual Gemini-pasted enrichment flows for fresh market news and reference data. It is a self-contained component: it reads from `pipeline.m2.scanResults` (or self-loads from Firestore as a fallback) and writes only to `pipeline.intel.marketPulse` / `pipeline.intel.marketData`. It is the predecessor to V2's five-lens architecture.

---

## 1. What V1 Does

- Renders a **single-page, four-tab dashboard** for one company (defaulting to "Sirion") summarising AI perception across LLMs.
- Pulls live numbers from the M2 Perception Monitor scan: visibility %, average rank, sentiment, competitor mentions, narrative ownership.
- Augments those scan-derived numbers with **manual market intelligence**: the user clicks a button, copies a generated prompt into Gemini (with web search), pastes the JSON response back, and V1 parses + persists it.
- Computes "Strategic Alerts" by joining M2 narrative ownership with the latest Market Pulse news.
- All charts use Recharts (Bar charts, Radar chart, custom progress bars).
- Has both dark and light theme support (T_DARK / T_LIGHT objects).
- Reads from / writes to PipelineContext via `usePipeline()` and `updateModule("intel", { ... })`.

---

## 2. UI Sections (Tabs)

V1 is organised into **four tabs**, controlled by `activeTab` state. The tab strip sits beneath the header.

| Tab id      | Label        | Icon         | Purpose                                                                                                |
| ----------- | ------------ | ------------ | ------------------------------------------------------------------------------------------------------ |
| `position`  | AI Position  | crystal-ball | Default landing. Hero stats + perception map + competitor leaderboard.                                 |
| `pulse`     | Market Pulse | satellite    | News feed populated by Gemini paste flow. Cards categorised Threat / Opportunity / Neutral.            |
| `alerts`    | Alerts       | warning      | Auto-derived strategic alerts (cross-references M2 + Market Pulse). Badge shows critical count.        |
| `reference` | Market Data  | bar-chart    | Vendor revenue estimates, analyst rankings, product launches, funding — also from a Gemini paste flow. |

### 2.1 Tab 1 — AI Position

Renders only when M2 scan data is present (`hasM2Data === true`); otherwise shows an empty state with a "Go to Perception Monitor" CTA.

**Sub-sections (numbered SectionHeaders):**

- **01 — AI Visibility Overview.** Four hero cards in a 4-column grid:
  - Visibility (% — colour: green ≥ 70, yellow ≥ 40, red otherwise)
  - Avg Rank (`#N` — colour: green ≤ 2, yellow ≤ 3.5, red otherwise)
  - Positive Sentiment (% positive of total)
  - Competitors Tracked (count)
  - Below: per-platform horizontal progress bars (one row per LLM in `scanData.llms`).
- **02 — Perception Map.** Two side-by-side cards:
  - **Perception Radar** (Recharts RadarChart) — one polygon per vendor, axes from `radarData` (lifecycle themes normalised 0-10).
  - **Narrative Ownership Table** — per-theme rows showing Theme, Owner (top vendor + count), Sirion count, total weight, Action badge (DEFEND/COMPETE/ATTACK/IGNORE).
- **03 — Competitor Leaderboard.** Two-column layout:
  - Ranked list of vendors with frequency and avg rank, Sirion highlighted.
  - Recharts BarChart (vertical layout) of mentions per vendor.
- **04 — Visibility Gaps.** Only renders if `insights.losing` has entries. Per-question rows showing `ABSENT` or `#rank`, the query text, and the winning competitors with vendor-coloured tags.

### 2.2 Tab 2 — Market Pulse

- Header section + a button: **"Scan Market"** (or "Cancel" when the prompt panel is open).
- Last-scan timestamp shown if `marketPulseAt` exists.
- When toggled, opens a panel showing:
  - Step 1: Read-only textarea containing the generated prompt + "Copy Prompt" button.
  - Step 2: Editable textarea for pasting Gemini's response + "Parse & Save" button.
  - On parse error, surfaces a red error message.
- News rendering when `marketPulse.length > 0`:
  - Summary strip with three pill badges — Threats, Opportunities, Neutral — coloured red / green / textDim.
  - Two-column grid of news cards. Each card has:
    - Header strip with category icon + label and competitor pill (if present).
    - Headline (bold), summary, source + date, optional source URL link with arrow icon.

### 2.3 Tab 3 — Alerts

- Section header + (when alerts exist) a row of three pill badges: Critical / Watch / Opportunity counts.
- Otherwise an empty state ("Run a Perception Scan first" or "No alerts — run a Market Pulse scan…").
- Alert cards have a coloured left border (red / yellow / green), a circular dot icon, the priority badge, the source tag (right-aligned), then title + description.

### 2.4 Tab 4 — Market Data Reference

- Header + **"Refresh Market Data"** button (or "Cancel"). Shows last-updated timestamp.
- Same paste flow as Market Pulse (different prompt, different parser — JSON object instead of array).
- When `marketData` is present, renders distinct visual sub-blocks:
  - **Market Size hero card** (gradient background) showing Current Value / Projected / CAGR with a chained icons row and the source URL.
  - **Revenue Estimates** — vertical list with vendor-coloured horizontal bars scaled to the largest revenue. "Private" placeholder when `r.revenue` contains "not public".
  - **Analyst Rankings** — per analyst block (Gartner / Forrester / IDC) showing the year + named leaders rendered as numbered pill badges.
  - **Recent Product Launches** — 2-column grid of cards: vendor name, date pill, product name, description.
  - **Funding & Acquisitions** — 2-column grid of cards: vendor name, date, amount in green, type tag.

---

## 3. Prompts (Verbatim)

V1 uses two prompt builders. Both insert the company name and the top 6 competitor names plus the current month/year.

### 3.1 `buildMarketPulsePrompt(companyName, competitors)`

> ```
> You are a CLM market intelligence analyst. Search the web for the latest news and developments in the Contract Lifecycle Management (CLM) market as of ${month}.
>
> Focus on these companies: ${companyName}, ${compList}
>
> Search for:
> 1. Product launches, feature announcements, AI capabilities
> 2. Funding rounds, acquisitions, partnerships
> 3. Analyst reports (Gartner, Forrester, IDC)
> 4. Customer wins, case studies
> 5. Market trends affecting CLM positioning
>
> Return your findings as a JSON array. Each item must have this exact structure:
> [
>   {
>     "headline": "Brief headline of the news item",
>     "source": "Publication or source name",
>     "url": "Full URL to the article",
>     "date": "YYYY-MM-DD or approximate date",
>     "category": "Threat" or "Opportunity" or "Neutral",
>     "competitor": "Company name this is about, or null if general market",
>     "summary": "2-3 sentence summary of what happened and why it matters",
>     "theme": "Which CLM theme this relates to (e.g., AI automation, post-signature, compliance, etc.)"
>   }
> ]
>
> Category guidelines:
> - "Threat": Competitor gaining ground (new product, funding, analyst recognition)
> - "Opportunity": Favorable development for ${companyName} (market shift toward their strengths, competitor weakness)
> - "Neutral": General market movement
>
> Return ONLY the JSON array, no other text. Include 10-15 items minimum. Search the actual web — do not make up news.
> ```

`compList` is `competitors.slice(0, 6).map(c => c.name).join(", ")`.

### 3.2 `buildMarketDataPrompt(companyName, competitors)`

> ```
> I need verified, current data points for a CLM market intelligence report (${month}). For each item, provide the EXACT number and the SOURCE URL where you found it.
>
> Companies to cover: ${companyName}, ${compList}
>
> Return as JSON with this structure:
> {
>   "marketSize": { "current": "$X.XB", "projected": "$X.XB", "cagr": "X%", "source": "URL" },
>   "revenueEstimates": [
>     { "vendor": "Name", "revenue": "$XM", "year": "2025/2026", "source": "URL", "public": true/false }
>   ],
>   "analystRankings": [
>     { "analyst": "Gartner/Forrester/IDC", "report": "Report name", "leaders": ["Name1", "Name2"], "year": 2025, "source": "URL" }
>   ],
>   "productLaunches": [
>     { "vendor": "Name", "product": "Product name", "date": "YYYY-MM", "description": "Brief", "source": "URL" }
>   ],
>   "funding": [
>     { "vendor": "Name", "amount": "$XM", "type": "Series X / Acquisition", "date": "YYYY-MM", "source": "URL" }
>   ],
>   "domainAuthority": [
>     { "domain": "example.com", "da": 45, "source": "Moz/Ahrefs" }
>   ]
> }
>
> For each answer, cite the exact URL. If data is not publicly available, mark public: false. Do not estimate — say "NOT PUBLIC" if unknown.
> Return ONLY the JSON, no other text.
> ```

---

## 4. Vendor "Comparison Matrix" Behaviour

V1 does **not** render a head-to-head comparison matrix as such — that was added in V2 (`HeadToHead` + `StageOwnership`). Instead V1 has:

- A **Competitor Leaderboard** (Section 03) showing each competitor's frequency (`freq`) and average rank, with Sirion pinned in a coloured highlight row, and a horizontal Recharts BarChart of mentions for the top 8 competitors.
- A **Narrative Ownership Table** (Section 02) — one row per theme/cluster:
  - Theme name (cluster label from M1 questions or M2's `cw` / `lifecycle` field, fallback "General").
  - Owner: top vendor + count, capped at 10 chars with "..." truncation, vendor-coloured.
  - Sirion's count for that theme (green if Sirion owns, teal if Sirion has any presence, red if zero).
  - Total mentions across all vendors.
  - Strategy badge:
    - **DEFEND** (green) — Sirion is the owner.
    - **COMPETE** (blue) — Sirion has ≥ 60% of the owner's count.
    - **ATTACK** (orange) — Sirion present but trailing significantly.
    - **IGNORE** (textDim) — total mentions ≤ 2 (low-signal theme).

`narrativeThemes` is computed by walking every analysis on every result, grouping by cluster, then ranking vendors per cluster. Limited to top 7 by total mentions.

---

## 5. Radar Chart (Sirion vs Icertis vs Ironclad)

`computePerceptionRadar` (imported from `scanStats.js`, not in V1 itself) returns the data shape consumed by the radar:

- Each row in `radarData` has `axis` (the lifecycle theme name) plus one numeric column per vendor.
- The radar polygon vendors are derived dynamically: `radarKeys = Object.keys(radarData[0]).filter(k => k !== "axis")`.
- Colours are looked up from a hard-coded `VENDOR_COLORS` map. Unknown vendors fall back to `[T.teal, T.orange, T.brand]` cycling.
- `VENDOR_COLORS` includes Sirion (teal), Icertis (yellow), Ironclad (orange), Agiloft, DocuSign, Contract Works, Conga, Juro, LinkSquares, Evisort.
- Recharts components: `RadarChart` with `outerRadius="70%"`, `PolarGrid`, `PolarAngleAxis` on `axis`, `PolarRadiusAxis` (domain 0-10), one `<Radar>` per vendor with stroke + fill at 15% opacity.
- Domain is normalised 0-10. Subtitle: "Mention strength per lifecycle theme (normalized 0-10)".

---

## 6. Narrative Breakdown

The `narrativeThemes` useMemo combines two data sources:

1. **`pipeline.m1.questions`** for the canonical cluster name (`q.cluster`) per question id (`r.qid`).
2. **`scanData.results`** for the per-LLM `analyses[lid].vendors_mentioned` arrays.

For each `(cluster, vendor)` pair, the count is the number of analyses where that vendor appeared. Sirion is identified via case-insensitive substring match on `companyName`. Themes are sorted by `totalMentions` descending and capped at 7.

The same `narrativeThemes` array also drives the **Strategic Alerts** logic (Tab 3):

- For each **Attack** theme (Sirion is weak), generate a "watch" or "critical" alert. Critical if there's a related news item in `marketPulse` whose `theme` matches the first word of the cluster name.
- For each market-pulse threat where the named competitor owns a non-Sirion narrative theme, generate a **critical** alert.
- For each market-pulse opportunity, generate an **opportunity** alert.
- For each theme where Sirion is the owner with `totalMentions >= 10`, generate an **opportunity** alert ("Strong position on…").

Alerts are sorted critical → watch → opportunity.

---

## 7. Reads From M2 + Manual Market Intelligence

### 7.1 Reads (data inputs)

- **Primary:** `pipeline.m2.scanResults` — expected shape `{ llms: string[], results: ScanResult[], date }`.
- **Fallback (self-load):** When the pipeline is empty, V1's mount effect calls `db.getAllPaginated("m2_scan_meta")` and `db.getAllPaginated("m2_scan_results")`, groups results by `scanId`, builds scan objects, picks the one with the most results, and:
  - Sets a local `localScanData` state, AND
  - Syncs back to pipeline via `updateModule("m2", { scanResults: { llms, results, date }, scannedAt: best.date })`.
  - Wrapped in try/catch — failures log a warning but don't crash.
- `pipeline.m1.questions` — for cluster lookups in narrative themes.
- `pipeline.intel.marketPulse` + `pipeline.intel.marketPulseAt` — persisted news.
- `pipeline.intel.marketData` + `pipeline.intel.marketDataAt` — persisted reference data.

### 7.2 Computed stats (via imports from `scanStats.js` / `scanEngine.js`)

- `computeRptStats(results, llms, companyName)` → `{ visibility, ranking, sentiment, competitors, sirion }`
- `computeCompMentions(scanData)`
- `computeCompFeatures(scanData)`
- `computeCompetitorInsights(scanData, compMentions, compFeatures, companyName)` → includes a `losing` array used for "Visibility Gaps".
- `computePerceptionRadar(scanData, companyName)` — radar input.
- `computeScores(results, llms)` from `scanEngine` — used during Firestore self-load when meta lacks scores.

---

## 8. Outputs (Display Only, No Persistent Storage Beyond Pipeline Intel Slice)

V1 writes only to the pipeline `intel` slice (the same persistence path PipelineContext uses for `localStorage` + Firebase via `persistenceManager`):

- `updateModule("intel", { marketPulse: validNewsItems, marketPulseAt: ISOnow })` — when "Parse & Save" succeeds in the Market Pulse tab.
- `updateModule("intel", { marketData: parsedObject, marketDataAt: ISOnow })` — when "Parse & Save" succeeds in the Market Data tab.

Everything else is **display-only** — no copy/export buttons, no handoff to other modules. The dashboard is purely consumptive: scan data in, alerts and visualisations out.

Parser behaviour (both flows):

- Strips Markdown code fences (` ```json ` / ` ``` `).
- Substrings to the first `[`/`{` and last `]`/`}` in case the model wraps with explanatory prose.
- For Market Pulse, requires an array; filters items to those with `headline + category`.
- For Market Data, requires an object (not array).
- On parse failure, sets a red error message; the textarea stays populated so the user can retry.

---

## 9. How V1 Differs from V2

| Aspect             | V1 (`CompanyIntelligence.jsx`)                         | V2 (`CompanyIntelligenceV2.jsx`)                                                                                                    |
| ------------------ | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| Architecture       | 4 tabs in one component                                | 5 lenses (+1 Domino) routed at the top via `LensTabs`                                                                               |
| Lenses             | Position / Pulse / Alerts / Reference                  | Position / Competitors / Market Pulse / Opportunities / Actions / Domino                                                            |
| Data freshness     | Manual paste into Gemini (single prompt per tab)       | Multi-provider AI calls (`researchCall`) with TTL-bounded cache and Refresh button                                                  |
| News pipeline      | Single Gemini prompt, hand-pasted JSON                 | `aggregateNews` fans out to Google News RSS + Gemini grounded + Perplexity, then dedups                                             |
| Source diversity   | None                                                   | `validateVendorShareDiversity`, `validateAnalystDomains`, `validateCurrentEvents` reject hallucinated single-source rows            |
| Snapshots          | None                                                   | `captureSnapshot` writes daily docs to `intel_v2_snapshots`                                                                         |
| Opportunities lens | Doesn't exist                                          | Dedicated lens with verified-vs-sirion.ai check, score formula `demand×0.5 + vulnerability×0.3 + play_clarity×0.2`                  |
| Actions lens       | Replaced by ad-hoc "Strategic Alerts" computed locally | Dedicated lens via `fetchActions` with `impact×0.5 + urgency×0.3 + ease×0.2` and tier discipline                                    |
| Domino lens        | Doesn't exist                                          | Predictive correlation engine (industries × companies × signals via Firecrawl harvest + Perplexity sweeps)                          |
| Loading UX         | Synchronous render                                     | `LoadingStickman` SVG with asymptotic % indicator                                                                                   |
| Caching            | None — manual paste each time                          | `getCachedOrFetch` to Firestore + localStorage with per-lens TTLs (24h news, 30d market data, 14d trends/opportunities, 7d actions) |
| Provider routing   | Gemini only (manual)                                   | `PROVIDER_CHAINS.RESEARCH_PREMIUM / RESEARCH_VERIFIED / RESEARCH_CURRENT_EVENTS / SYNTHESIS_PREMIUM`, with retries and JSON repair  |
| Theme              | T_DARK / T_LIGHT in component                          | Same pattern, with shadow-only premium tokens (`radius`, `radiusSm`, `radiusLg`, `shadow`, `shadowSm`)                              |
| Output handoff     | None                                                   | `transferOpportunityToM6`, `transferActionToM6`, `actionToMarkdown`, `actionToSlack`                                                |
| Auth handling      | None                                                   | `AuthExpiredPanel` rendered when researchCall returns `AUTH_EXPIRED`                                                                |
| Telemetry          | None                                                   | `ResearchLogPanel` floating terminal showing every AI call                                                                          |
| Empty cache UX     | Manual paste flow always available                     | `NoCachePrompt` ("Logging in doesn't auto-run AI calls anymore — those cost tokens")                                                |
| Subscriptions      | Hard-coded vendor map                                  | `loadSubscriptions` / `saveSubscriptions` Firestore-backed admin modal with `CURATED_TOPIC_CHIPS` and `DEFAULT_SUBSCRIPTIONS`       |

In short: V1 was a manual, scan-driven dashboard. V2 is an automated, multi-source intelligence workbench where every number is auditable via `ScoreTooltip` and every prompt has hallucination guards.
