# M2 Report V6 — Complete Specification

This document describes every piece of `src/m2/reportV6/` so a separate engineering team can rebuild Report V6 from scratch without reading the source. No code is reproduced — only behavior, data, formulas, and structural rules are described.

---

## 1. What V6 Is

Report V6 is the current production "perception report" inside Module 2 (Perception Monitor). It is a **read-only visualization layer** that sits on top of the Firestore collection `m2_scan_results`. V6 does not write any scan data, does not call any LLM, and never mutates pipeline state. It only reads scan documents, applies user-driven filters, computes aggregations in-browser, and renders a multi-section report.

### Why V6 exists (vs V2 / V3 / V4 / V5)

- **V2** is the original board-ready single-scan report. It picks one scan from the picker and shows reconciliation + 5 sections.
- **V3 / V4 / V5** progressively layered on a hardcoded baseline-pair scan combination, an LLM picker, augmenting-scan merging for Grok / Perplexity, and a Hand-pick segment workflow.
- **V6** is V5 reorganized into ~17 small files plus four important upgrades:
  1. **Dynamic scan source** — the user picks which scan(s) to load via a `ScanPicker` instead of being locked to the V3 baseline pair. The default still loads the baseline pair so V6's first-open numbers are byte-identical to V3/V5.
  2. **Single source of truth for filters** — every section reads from `activeDocs` produced by the `useActiveDocs` hook. No section applies its own filter.
  3. **Per-question raw-response drill-down** — a `RawScanModal` lets the user click any row in the Query Summary table and read the actual `analyses[llm].full_response` text the LLM produced (data was always stored, V3/V5 just never surfaced it).
  4. **Modular sections** — adding or removing a section is one JSX line in `index.jsx`.

### Parity guarantee

V6 with `(scanSource = baseline pair, scope = baseline154, no persona/stage/clmStage/text filter, all 5 LLMs detected)` produces compute output that is byte-identical to V5 / V3 — the file-split refactor does not change any math.

---

## 2. Constants — `constants.js`

All constants are exported from one module so any file can import the same values.

### `LLMS_ALL`

List of every LLM the platform supports today, in detection-and-display order.

| Index | LLM ID       | Label (`LLM_LABELS`) | Brand color (`LLM_COL`)  |
| ----- | ------------ | -------------------- | ------------------------ |
| 0     | `claude`     | "Claude"             | `#10b981` (emerald)      |
| 1     | `gemini`     | "Gemini"             | `#f59e0b` (amber)        |
| 2     | `openai`     | "ChatGPT"            | `#3b82f6` (blue)         |
| 3     | `grok`       | "Grok"               | `#fb923c` (orange-coral) |
| 4     | `perplexity` | "Perplexity"         | `#f472b6` (pink)         |

Adding a sixth LLM requires appending here plus extending `LLM_LABELS` and `LLM_COL`. Every section reads off the dynamic active-LLM list, so no per-section edits are needed.

### Baseline scan IDs

- `SCAN_35Q` = `"baseline_20260423_1718"` — V3's locked 35-question baseline (Apr 23, 17:18). LLMs: claude, gemini, openai. Covers Q001–Q035.
- `SCAN_119Q` = `"baseline_20260423_2229"` — V3's locked 119-question baseline (Apr 23, 22:29). Covers Q036–Q154.
- `BASELINE_PAIR` = `[SCAN_35Q, SCAN_119Q]` — V3 parity pair.

### `V6_DEFAULT_SCANS`

Equal to `[...BASELINE_PAIR]`. The V6 ScanPicker pre-selects these on first open. Combined the two scans cover 154 qids × 3 baseline LLMs (claude, gemini, openai). Grok and Perplexity get filled in automatically by `mergeAugmenting` from any newer scan that ran them — yielding all 5 LLMs by default while still letting the LLM picker filter back to the V3-byte-identical 3-LLM subset.

### `LLM_LABELS`

Object mapping each `LLMS_ALL` ID to a human-readable label. See table above.

### `LLM_COL`

Object mapping each `LLMS_ALL` ID to a brand hex color. See table above. Used everywhere a per-LLM color is needed: leaderboard cells, citation tables, picker chips, radar polygons, distribution stacks.

### `COMPANY`

Hardcoded value `"Sirion"`. The "target company" the report measures visibility for. Used by every section that needs to highlight the target row, label tiles, etc.

### `STAGE_OPTIONS`

The four CLM-stage filter values surfaced in the SegmentFilter dropdown. Bucket names match what `narrativeClassifier.rollUpNarrativeAcrossAnalyses` emits.

| ID               | Label            |
| ---------------- | ---------------- |
| `All`            | "All CLM Stages" |
| `pre_signature`  | "Pre-Signature"  |
| `post_signature` | "Post-Signature" |
| `full_stack`     | "Full-Stack CLM" |

### `STAGE_TIE_ORDER`

Tie-break order when a single question has equal narrative votes across LLMs. Order: `["full_stack", "pre_signature", "post_signature", "unclassified"]`. Deterministic so the same scan always classifies the same way.

### `STATUS_META`

The three statuses for a question's overall mention coverage across the active LLMs.

| Status   | Label    | Icon | Color     | Background  |
| -------- | -------- | ---- | --------- | ----------- |
| `strong` | "STRONG" | ✓    | `#059669` | `#10b98122` |
| `weak`   | "WEAK"   | ⚠    | `#d97706` | `#f59e0b22` |
| `lost`   | "LOST"   | ✗    | `#dc2626` | `#dc262622` |

### `SIRION_OWNED_DOMAINS`

List `["sirion.com", "sirion.ai", "sirionlabs.com"]` used by `isOwnedDomain` to flag self-citations in the Citation Domain Authority section.

### `SCOPE_OPTIONS`

Three-way scope toggle exposed by `ScopeToggle`.

| ID            | Label                    | Behavior                                        |
| ------------- | ------------------------ | ----------------------------------------------- |
| `all`         | "All questions in scan"  | Pass through whatever the active scans returned |
| `baseline154` | "154 baseline questions" | Filter to docs whose qid is Q001–Q154           |
| `baseline35`  | "35 baseline questions"  | Filter to docs whose qid is Q001–Q035           |

---

## 3. Section Components

All sections receive `T` (theme token object), `activeDocs` (the filter-resolved doc list from `useActiveDocs`), and `llms` (the active LLM list). Some additionally receive `recon` (the V2-shape reconciliation object).

### § 0 — `HeroHeader.jsx`

- **Props**: `T`, `isClientPortal`, `activeLlms`, `activeDocs`, `scopeLabel`, `scanCompletedAt`, `selectedScans`.
- **Shows**: A small uppercase eyebrow ("Report V6 · dynamic scan source · modular sections" for admins; comma-separated LLM names for client_portal), the scope label as a 22-pt heading, a one-line summary of "{N} questions · {LLM list} · target company: Sirion", a fine-print line with last-scan freshness ("Latest scan: Apr 30 · 14:22"), the count of scans loaded, and the local "report rendered" timestamp.
- **CredibilityBadge** (sub-component): a coloured pill that shows `coveragePct%` and "{X}/{X} LLMs · {N} errors". Click to expand a panel with: `present / totalExpected` tuples, a per-LLM grid showing `present/total (pct%)` plus missing/error counts when applicable, an "LLMs with gaps" hint, and a "Per-analysis richness" line listing percentages of mentioned analyses with sentiment captured, with rank captured, and percentages of present analyses with vendors[] / sources[].
- Color of the credibility pill: green ≥ 95 %, orange ≥ 80 %, red below 80 %.

### Question Table (control-panel companion) — `QuestionTable.jsx`

- **Hidden entirely** for `client_portal` role.
- **Purpose**: Show every doc currently in scope so the user can either inspect what filters resolved to, or hand-pick rows for a custom segment.
- **Toolbar**: "Select visible (N)", "Clear selection", and a counter that reads either "{N} ticked · these will be saved if you click 'Save current view as segment'" or "0 ticked · save will use the filter-resolved qid set".
- **Table**: Sticky header, scrollable to 360 px max-height. Columns: ✓ checkbox, QID (mono font), Query, Persona, Stage, Source. The Source column shows "35Q" / "119Q" tag if the doc came from a baseline scan, "—" otherwise.

### § 1a — `BuyingCenterMix.jsx`

- **Shows**: Ron's 55 / 35 / 10 weighted visibility framework. Big headline number is the buying-center-weighted percentage (Procurement weight × Procurement pct + Legal weight × Legal pct + Other weight × Other pct).
- Three audience cards — Procurement, Legal, Other. Each card has: bucket label (color-coded), weight percent and "most important audience" / "second priority audience" / "secondary stakeholders" tag, raw bucket pct as a 26 px mono number, plain-English mapping ("Sirion shows up in about 4 out of 5 answers"), and a denominator footer "{questions} × {numLLMs} = {total} attempts · Sirion was named in {mentioned} of them".
- Footer line beneath the headline: "raw visibility (unweighted) is {rawPct}%", surfaced from `recon.visibility.pct`.

### § 1b — `PersonaStageHeatmap.jsx`

- **Shows**: 2D heatmap of Sirion mention rate. Rows = personas (grouped by Procurement / Legal / Other bucket); columns = stages (Pre-Sig / Post-Sig / etc.).
- Each cell = `mentioned / total (pct%)` across all (Q × LLM) tuples for that persona × stage. Cell color ramp: ≥ 90 % `#10b981`, ≥ 70 % `#22c55e`, ≥ 50 % `#eab308`, ≥ 25 % `#f97316`, < 25 % `#ef4444`. Empty cells get a neutral background.
- Each bucket gets a thin colored separator row between persona groups, labeled "PROCUREMENT · weight 55% · 4 personas" (etc.). Personas inside a bucket are sorted by total volume.
- Legend shows the five color stops with their percentage thresholds.

### § 2b — `Leaderboard.jsx`

- **Shows**: Top 10 vendors by total citation count across the active LLMs.
- Columns: Vendor (with target indicator if it equals "Sirion"), one column per active LLM (per-LLM cite count, brand color), Total, Distribution (a stacked horizontal bar segmenting per-LLM contribution).
- Hovering a row reveals an absolute-positioned tooltip card showing: total citations, share of voice, unique queries the vendor was cited in, per-LLM count + percentage, median rank, and sentiment counts (P/N/A). Sirion's row stays highlighted with a teal tinted background.
- Footer: "{totalOccurrences} total vendor-name occurrences across {N} queries × {M} LLMs · top {K} shown".

### § 2c — `CitationDomains.jsx`

- **Shows**: Top 25 domains AI cited across all (Q × LLM) tuples.
- Columns: # (rank), Domain, one column per active LLM, Total, Queries (count of unique qids the domain appeared in), Owned? badge.
- Owned-domain rows (matching `SIRION_OWNED_DOMAINS`) get a green tinted background and a "✓ Owned" pill. Non-owned rows get a "3rd-party" pill.
- Header subline: "{totalDistinct} distinct domains · {totalCitations} citations · Sirion-owned: {ownedTotal} ({ownedPct}%)" — owned percent in green if > 0, red if 0.

### § 5b — `StageComparisonRadar.jsx`

- **Shows**: 3-axis radar chart (Pre-Signature / Post-Signature / Full-Stack) using Recharts. One bold solid teal triangle for the all-LLM aggregate, plus one faint dashed polygon per active LLM in that LLM's brand color.
- Each axis percentage = bucket count / frameable mentions for that source.
- Header reads "{frameableCount} frameable mentions across Pre-Sig / Post-Sig / Full-Stack" and a right-aligned monospace "Pre {x} · Post {y} · Full {z}".
- Body chart is 380 px tall, 78% outer-radius, 0–100% radial axis with `%` tick formatter. Tooltip and legend pull standard Recharts colors.
- Source: `narrative.label` on each (Q × LLM) analysis. Denominator: frameable mentions (mentioned analyses with a prose paragraph, computed by `narrativeClassifier.rollUpNarrativeAcrossAnalyses`).

### § 7 — `LossPatterns.jsx`

- **Shows**: Top 15 (Q × LLM) tuples where Sirion lost cleanly and a competitor cleanly won — sorted by computed severity score (formula in compute section below). Hidden when there are no losses.
- Header summary: "{N} total losses · {absent} absent · {ranked4plus} ranked 4+ · {compAt1} with competitor at #1".
- Columns: QID, Query, Persona, Stage, LLM (brand logo), Sirion status pill ("Absent" red or "Rank #N" orange), Top Competitor (name, mono `#rank` tag, sentiment letter pill).
- Card has a `borderLeft: 4px solid red` to signal it's the priority-action section.

### § 6 — `QuerySummary.jsx`

- **Shows**: Per-query mention/rank/sentiment table — one row per doc.
- **Collapsed by default** behind a chevron. Header reads "Query Summary · Strong {N} · Weak {N} · Lost {N}". Click expands.
- Three count chips at top of expanded view ("Strong: N (pct%)", etc.).
- Table columns: QID, Query, Persona, Stage, one column per active LLM (cell uses `cellInfo` to render `#rank P/N/A` or `✗` or `—`), Status pill.
- **Click any row** → opens `RawScanModal` for that doc.

### `RawScanModal.jsx` (drill-down)

- **NEW in V6**. Modal overlay opened by clicking a row in QuerySummary.
- **Header**: QID + persona + stage in mono caps, then the query in 16 px bold, then a close ✕ button. ESC closes.
- **Tabs**: One tab per LLM that has data for this question. Tab shows brand logo + label. Active tab gets a 3 px brand-color underline.
- **Body** (per active tab):
  - Outcome chip: "MENTIONED · #rank" green + sentiment letter pill, or "ABSENT" red, or "NO DATA" grey on error.
  - Optional `answer_length` mono chip.
  - "TRUNCATED" orange pill when `analysis.truncated` is true.
  - Vendors named: chip cluster, each chip showing optional `#position` mono prefix, vendor name, sentiment letter color-tinted. Sirion chips get a teal ring.
  - Citations: domain chips deduplicated via `domainOf`.
  - Raw response: pre-wrap text block from `analysis.full_response` (falls back to `response_snippet`). If neither is stored: italic "Raw response not stored for this analysis."

---

## 4. Filter Components

### `ScanPicker.jsx` (admin-only, hidden for client_portal)

- Multi-select dropdown over the entire `m2_scan_meta` catalog (loaded by `loadScanCatalog`).
- Trigger button shows a smart summary string:
  - "V6 default · 154Q × 5 LLMs" when the two `V6_DEFAULT_SCANS` are selected and nothing else.
  - "V3 parity · 35Q + 119Q baseline" when only the V3 `BASELINE_PAIR` is selected.
  - "{label}" when exactly one scan is selected.
  - "{N} scans selected" otherwise.
- Dropdown body lists every catalog item as a checkbox row; pinned defaults are shown first with a `★ ` prefix, then V3 baselines with `🔒 ` prefix and a "V3 parity" divider, then "Other scans (newest first)" divider with the rest.
- Each catalog row optionally shows a mono LLM list under the label ("claude · gemini · openai").
- Selecting zero scans triggers a fallback to `V6_DEFAULT_SCANS` so the report always has data.

### `LlmPicker.jsx`

- Toggleable chip row over the LLMs actually present in the loaded scans (`allDetectedLlms`).
- Each chip shows a small color square + label; active chips fill with brand-color background tint and brand-color text.
- Default state (`pickedLlms === null`) means "every detected LLM is active."
- Clicking a chip drops/restores it. If toggling produces "all selected" or "none selected", the picker resets to `null`. A "Reset" button appears whenever a non-null subset is active.
- Subtitle: "{activeLlms} of {allDetectedLlms} active".
- Hidden completely when no LLMs were detected.

### `ScopeToggle.jsx`

- Three chip buttons in a row showing the three `SCOPE_OPTIONS` ("All / 154 baseline / 35 baseline"). Each chip shows the option label plus a parenthetical count of how many docs would match.
- Selected chip gets a teal border + tinted background.
- Selecting any chip also resets `segment` back to `"scope"` so the chip choice isn't silently overridden by a saved segment.

### `SegmentFilter.jsx`

- Four side-by-side controls with a Reset button:
  1. Free-text input (placeholder "Filter by text or QID…").
  2. Persona `<select>` (options derived from `activeDocs`).
  3. Stage `<select>` (options derived from `activeDocs`).
  4. CLM-stage `<select>` populated from `STAGE_OPTIONS`.
- Reset button restores `{ text: "", persona: "All", stage: "All", clmStage: "All" }`.

---

## 5. `useActiveDocs` Hook — `filters/useActiveDocs.js`

The composer that makes V6's "single source of truth" rule possible. Every section reads `activeDocs` from this hook — never the raw `docs` array.

### Pure helpers (also exported standalone for tests)

- `qidNumber(qid)` — parse "Q001" → integer 1. Returns null when the qid does not match the strict `^Q0*(\d+)$` shape.
- `buildDocStageMap(docs, llms)` — produce a `Map<qid, dominantStage>` by calling `dominantStageForDoc` for every doc.
- `resolveAllowedQids(docs, scope, segment, customSegments)` — produce the set of qids permitted by the scope chip OR by the active custom segment. Custom segment overrides scope.
- `applySubFilters(docs, allowedQids, filters, docStageMap)` — apply persona / stage / clmStage / text filters on top of the qid allow-list.
- `computeActiveDocs(args)` — runs the whole pipeline pure (used by tests).

### Filter pipeline (left → right)

1. **Scope**: `baseline35` → qids 1–35; `baseline154` → qids 1–154; `all` → every loaded qid.
2. **Segment**: a saved custom segment's `qids` array (when `segment !== "scope"`) overrides scope.
3. **Persona**: single-select dropdown match (`d.persona === filters.persona`) when not "All".
4. **Stage**: same pattern (`d.stage === filters.stage`) when not "All".
5. **CLM stage**: compares `dominantStageForDoc(d, llms)` to `filters.clmStage` when not "All".
6. **Text**: substring match on `qid + " " + query`, case-insensitive.

### Critical rule

The **LLM picker is intentionally NOT in this pipeline.** It filters the compute layer (which `analyses[llm]` slices to read), not the docs themselves. Every doc still carries every LLM's analysis in memory; the picker just narrows what gets counted in leaderboard / sentiment / citation aggregation.

### Hook return

The React-facing `useActiveDocs` returns `{ activeDocs, docStageMap }`, each memoized on the obvious dependencies.

---

## 6. Compute Functions — `compute.js`

All functions are pure: they take docs and the active LLM list and return JSON-shaped data. No React, no JSX. With `(baseline pair scans + 154 questions + LLMs = ["claude","gemini","openai"])` they produce byte-identical numbers to V3 / V5.

### `computeLeaderboard(docs, topN, llms)`

Walks every (Q × LLM) analysis. For each entry of `analyses[llm].vendors_mentioned`, parses with `parseVendorLoose`, canonicalizes the name with `canonicalVendor` (imported from ReportV2.jsx), and tallies into a per-vendor `Map` keyed by lowercase canonical name.

For each tally row it tracks: per-LLM occurrence counts (`perLlm[llm]++`), total, set of unique qids, an array of `position`/`rank` values, sentiment counts (`positive` / `neutral` / `negative`).

After the walk, for each vendor it derives:

- `queryCount` = size of the qid set.
- `medianRank` = median of the ranks array (rounded to 1 decimal for even counts).
- `shareOfVoice` = `total / totalOccurrences * 100` (1 decimal).

Returns `{ top: top-N rows by total descending, totalOccurrences, sirionShare, sirionRow }`.

### `computePersonaStageMatrix(docs, llms)`

For every doc with both `persona` and `stage`, walks every active LLM's analysis. Increments `cell[persona|stage].total` for any non-error analysis, and `cell[persona|stage].mentioned` when `analyses[llm].mentioned` is true.

Returns `{ personas: sorted array, stages: sorted array, cell: { "{persona}|{stage}": { total, mentioned } } }`.

### `computeCitationDomains(docs, llms, topN = 25)`

Walks every (Q × LLM) tuple. For each entry of `analyses[llm].cited_sources` (or `sources_cited` as a fallback), extracts a www-stripped lowercase domain via `domainOf`. Tallies per domain: total, perLlm map, set of unique qids, owned flag (via `isOwnedDomain`).

Returns `{ top: top-N rows, totalDistinct, totalCitations, ownedTotal }`.

### `computeDataCredibility(docs, llms)`

Walks every (Q × LLM) tuple. Tracks four counts per LLM (`total`, `present`, `error`, `mentioned`) plus four cross-LLM richness counts:

- `withRank` — mentioned analyses with a numeric `rank`.
- `withSentiment` — mentioned analyses with any `sentiment` value.
- `withVendors` — present analyses with a non-empty `vendors_mentioned` array.
- `withSources` — present analyses with a non-empty `cited_sources` array.

Returns `{ totalExpected, present, errors, coveragePct = present/totalExpected, perLlm (with computed missing = total − present), questions, activeLlms, richness: { mentioned, withRankPct, withSentimentPct, withVendorsPct, withSourcesPct } }`.

### `computeLossPatterns(docs, llms)`

Walks every (Q × LLM) tuple. A row is a "loss" if Sirion was not mentioned, or Sirion was mentioned at rank ≥ 4. For each loss it inspects the analysis's vendor list, drops the Sirion entry, requires the top remaining vendor to have rank ≤ 3 and non-negative sentiment.

Severity score:

- `sirionPenalty` = 100 if Sirion was absent, else `max(0, sirionRank − 3) × 20`.
- `compBoost` = `(4 − topCompetitorRank) × 30` + 20 if competitor sentiment is positive.
- `score` = `sirionPenalty + compBoost`.

Returns rows sorted by score descending. Each row carries: `qid`, `query`, `persona`, `stage`, `llm`, `sirionStatus` ("Rank #N" or "Absent"), `sirionAbsent`, `topCompetitor` (canonical), `topCompetitorRank`, `topCompetitorSentiment`, `score`.

---

## 7. Helpers — `helpers.js`

### `dominantStageForDoc(doc, llms = LLMS_ALL)`

Per-question dominant CLM stage. Plurality vote across the active LLMs' `analyses[llm].narrative.label` values, restricted to mentioned analyses. Ties broken in `STAGE_TIE_ORDER` order. Returns `"unclassified"` if no LLM mentioned the company.

### `sentimentLetter(sentiment)`

Single-character display: `"positive" → "P"`, `"negative" → "N"`, anything else → `"A"` (covers neutral, absent, missing).

### `cellInfo(doc, model)`

Render-info object for the Query Summary table:

- `{ state: "error", label: "—", color: "#a1a1aa" }` when analysis is missing or errored.
- `{ state: "absent", label: "✗", color: "#dc2626" }` when not mentioned.
- `{ state: "mentioned", label: "{#rank or ✓} {sentimentLetter}", color: "#059669" }` otherwise.

### `appendixStatus(doc, llms)`

Returns `"strong"` if every active LLM mentioned the company, `"weak"` if at least one but not all did, `"lost"` if none did.

### `appendixSummary(docs, llms)`

Aggregates `appendixStatus` across all docs. Returns `{ strong, weak, lost, total, strong_pct, weak_pct, lost_pct }`.

### `domainOf(source)`

Defensive domain extractor. Sources arrive in three shapes from `m2_scan_results`:

1. An object `{ domain, url, … }` — straightforward read.
2. A JSON-encoded string of that object — happens for ~100 % of sources in the V6 default fixture (5 733 / 5 733). V3/V4/V5's older `domainOf` returned null for these, which is why their Citation Domain section was empty in production. V6 detects strings starting with `{`, JSON-parses them, then reads `domain` or `url`.
3. A bare URL string — parsed via `new URL(...).hostname`.

All return values are www-stripped and lowercased. Returns `null` when the source is unreadable.

### `isOwnedDomain(domain)`

True when `domain` exactly equals or ends with any of `SIRION_OWNED_DOMAINS`.

### `formatNow()`

Local-date + local-time-with-minute formatter for the "report rendered at …" stamp.

### `parseVendorLoose(v)`

Same shape problem as `domainOf`. Returns the input if it is already an object, JSON-parses it if it is a string, returns `null` on failure so callers can skip cleanly.

---

## 8. Data Layer — `data/loadCombined.js`

### `loadScanDocs(scanId)` (private)

Hits Firestore REST `runQuery` against the `m2_scan_results` collection with a `where scanId == {scanId}` filter, limit 500, and decodes every returned document via `fromFsDoc`.

### `mergeBaselines(baselineBatches)`

Given an array-of-arrays (one per picked baseline scan, in user-priority order), groups by qid and unions the LLM analyses. **Earliest-wins per (qid × llm)**: if the user picked two scans that both have, say, `claude` for Q001, the scan earlier in `scanIds` keeps its `claude` analysis and the later scan only contributes LLMs the earlier one didn't have.

V6 default behavior: Apr 25 first contributes `claude/gemini/openai` for all 154 qids; Apr 30 second contributes `grok/perplexity` for all 154 qids — no conflict, result is 154 deduped docs each with all 5 LLM analyses.

### `mergeAugmenting(baselineDocs, augmentDocs, baselineLlms)`

Newest-wins per (qid × llm) merge for augment scans. Sorts augment docs oldest-first by `completed_at || created_at`. Then for every doc, only LLMs not already in `baselineLlms` are eligible for augmentation. The last (newest) augment doc's analysis for that LLM wins on `Map.set`.

Returns the baseline docs with newly-augmented `analyses` keys spliced in.

### `planAugmentLoad(baselineLlms, allMetaIds, baselineScanIds)`

Pure decision function. Computes `missingLlms = LLMS_ALL minus baselineLlms`. If empty → returns `{ needed: false, scanIds: [], missingLlms: [] }`, letting the caller skip the augment fetch entirely. Otherwise returns `{ needed: true, scanIds: every meta ID minus baselines, missingLlms }`.

V6 default hits the short-circuit (Apr 25 + Apr 30 already covers all 5 LLMs), saving roughly 3 Firestore round-trips per fresh load.

### `detectLlms(docs)`

Returns `LLMS_ALL` filtered to those with at least one non-error analysis in the doc set.

### `loadCombinedDocs(scanIds = V6_DEFAULT_SCANS)`

Top-level loader the React component calls. Steps:

1. If `scanIds` is empty → fall back to `V6_DEFAULT_SCANS`.
2. In parallel: load every baseline scan via `loadScanDocs` and load `m2_scan_meta` via `db.getAllPaginated`.
3. Dedupe + union the baseline batches via `mergeBaselines`.
4. Detect LLMs on the merged baseline (`baselineLlms`).
5. Decide augment plan via `planAugmentLoad`.
6. If needed, parallel-load augment scans and merge via `mergeAugmenting`.
7. Compute `completedAt` = the latest `completed_at || created_at` across baseline + augment docs.
8. Return `{ docs, baselineScanIds, baselineLlms, completedAt }`.

---

## 9. Scan Catalog — `data/scanCatalog.js`

### `loadScanCatalog()`

Loads every entry from `m2_scan_meta` via `db.getAllPaginated`. For each meta record extracts `id` (or `scan_run_id` / `_id`), `completed_at` (or `created_at`), and an optional `llms` array.

Then assembles the picker order:

1. **`V6_DEFAULT_SCANS`** — pinned at top, marked `isDefault: true`, pre-selected on first open.
2. **`BASELINE_PAIR`** (V3) — pinned next, marked `isV3Baseline: true`, for users who explicitly want V3-parity numbers.
3. **All other scans** — newest-first by `completed_at`.

### `labelFor(meta)`

Friendly label rendering rule:

- `SCAN_35Q` → "V3 Baseline 35Q · {date}"
- `SCAN_119Q` → "V3 Baseline 119Q · {date}"
- `V6_DEFAULT_SCANS[0]` → "V6 Full 154Q (3 LLMs) · {date}"
- `V6_DEFAULT_SCANS[1]` → "V6 Grok+Perplexity 154Q · {date}"
- Anything else → `"{scan_name || name || id} · {date}"`

Each catalog entry returned: `{ id, label, isDefault, isV3Baseline, completed_at, llms }`.

---

## 10. Segment Save — `segmentSave.js`

### `resolveSegmentQids(selectedQids, activeDocs)`

- If the user has ticked ≥ 1 row in the QuestionTable → returns the exact ticked set as an array (V3/V5-style hand-pick segment).
- Otherwise → returns the deduplicated list of `activeDocs` qids in encounter order (V6's filter-driven default).

### `buildSegmentPayload({ name, scope, scanIds, qids, pickedLlms, isManualPick })`

Builds the Firestore document for `m2_segments_v6`. Captures enough context to restore the exact same view later:

- `name` — trimmed user-chosen name (required).
- `scope` — active scope toggle ID at save time.
- `scanIds` — copy of the active scan source list.
- `qids` — copy of the resolved qid list.
- `llms` — array clone of the LLM picker state, or `null` for "all detected".
- `source` — `"manual_pick"` if the qids came from `selectedQids`, else `"filter_view"` (UI hint only).
- `created_at` — ISO timestamp.

### Flow inside `index.jsx`

- "Save segment" button is admin-only (hidden for client_portal).
- It prompts for a name, then resolves qids, then `db.save(SEGMENTS_COLL, data)` where `SEGMENTS_COLL = "m2_segments_v6"`. The new doc is added to the local `customSegments` state and immediately becomes the active segment chip.
- A delete button (✕) next to each saved chip calls `db.delete(SEGMENTS_COLL, segId)` after a `confirm`.
- Clicking a segment chip switches the segment and, when the segment was saved with a non-null `llms` array, restores the LLM picker selection.

---

## 11. HTML Export — `htmlExport.js`

### `exportV6Html({ activeDocs, llms, recon, segmentation, personaStageMatrix, scopeLabel })`

Assembles a self-contained HTML document for download.

Steps:

1. Build a synthetic `run` object containing scope label, question count, model list, `mode: "v6-dynamic"`.
2. Call V2's `buildReportV2Html` to get the V2 base document (header, reconciliation pyramid, hero tiles, Visibility, ShareOfVoice, Sentiment, Positioning, Lifecycle).
3. Build six V6-only HTML strings:
   - Buying-Center Mix (§ 1a) via `buildBuyingCenterHtml`.
   - Persona × Stage Heatmap (§ 1b) via `buildPersonaStageHeatmapHtml`.
   - Visibility Leaderboard (§ 2b) via `buildLeaderboardHtml`.
   - Citation Domain Authority (§ 2c) via `buildCitationDomainsHtml`.
   - Loss Patterns (§ 7) via `buildLossPatternsHtml`.
   - Query Summary appendix (§ 6) via `buildAppendixHtml`.
4. Splice the strings into V2's HTML around two well-known marker comments:
   - After `<!--VIS_END-->` → 1a + 1b
   - After `<!--SOV_END-->` → 2b + 2c
   - Before `</body>` → 7 + 6
5. Trigger download via `triggerHtmlDownload` with filename `{scopeLabel}_ReportV6_{YYYYMMDD}.html`.

### Exported HTML styling

Inlined palette object `C` mirrors V2's. `escHtml` escapes `&<>"'`. `pctToWords` mirrors the in-app phrase ladder ("almost every answer", "about 4 out of 5", etc.) so the exported file has the same plain-English copy.

The exported HTML is a complete `<!DOCTYPE html>` page — no external CSS or JS, safe to email.

---

## 12. Firestore Collections Used

| Collection        | Read or Write         | Purpose                                                                                                                                                        |
| ----------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `m2_scan_results` | Read only             | Per-question scan documents. One doc per (scanId × qid). Keyed `{scanId}__{qid}`.                                                                              |
| `m2_scan_meta`    | Read only             | One doc per scan run. Used by `scanCatalog` to populate the ScanPicker and by `loadCombined` to plan augment loads.                                            |
| `m2_segments_v6`  | Read + Write + Delete | V6's saved custom segments. Independent of V5's `m2_segments_v5` collection — V6 segments include `scopeId` and `scanIds` on top of the qids + llms V5 stored. |

V6 never writes to `m2_scan_results` or `m2_scan_meta`.

---

## 13. Client Portal Mode Behavior

When `useAuth().session.role === "client_portal"`:

- **Hidden**: ScanPicker, Saved-segment chips, Save-segment button, QuestionTable, Export-HTML button.
- **Visible**: HeroHeader (with eyebrow text replaced by a comma-separated LLM list instead of "Report V6 · dynamic scan source · modular sections"), ScopeToggle, LlmPicker, SegmentFilter, and every report section.
- The scan source is locked to `V6_DEFAULT_SCANS` (the user can't change it because they can't see the picker, but the loader still loads the default set).
- Sidebar nav label switches from "Report V6" to "Perception Report".

---

## 14. `m2_scan_results` Document Shape

This is the single doc shape every V6 file reads. It is produced by `baselineScanner.runOneAttempt` and stored once per (scanId × qid). Key fields:

| Field                         | Type       | Notes                                                                         |
| ----------------------------- | ---------- | ----------------------------------------------------------------------------- |
| `scanId` (or `scan_id`)       | string     | Scan run identifier — used as the `where` filter in `loadScanDocs`.           |
| `qid`                         | string     | "Q001"–"Q154" (or whatever the underlying question bank emits).               |
| `query`                       | string     | The actual question text the LLM answered.                                    |
| `persona`                     | string     | Persona this question targets (CIO, Procurement Director, etc.). May be null. |
| `stage`                       | string     | Buyer-stage tag (PRE-SIGN, etc.). May be null.                                |
| `created_at` / `completed_at` | ISO string | Used for newest-wins merging and freshness display.                           |
| `analyses`                    | object     | Map of `llm → analysis`. One key per LLM the scan covered.                    |

### `analyses[llm]` sub-shape (per-LLM analysis)

| Field                                     | Type         | Notes                                                                                                                                                                                                                            |
| ----------------------------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_error`                                  | string       | Truthy when the LLM call failed — every section skips errored analyses.                                                                                                                                                          |
| `mentioned`                               | bool         | True when the LLM named Sirion in its answer.                                                                                                                                                                                    |
| `rank`                                    | number\|null | Sirion's competitive rank when present in an ordered list.                                                                                                                                                                       |
| `sentiment`                               | string       | "positive" / "neutral" / "negative" / "absent".                                                                                                                                                                                  |
| `narrative.label`                         | string       | One of `pre_signature` / `post_signature` / `full_stack` / `unclassified`. Drives the radar and the CLM-stage filter.                                                                                                            |
| `vendors_mentioned`                       | array        | Each entry either an object or a JSON-string. Vendor objects carry `name`, `position` (or `rank`), `sentiment`, `framing`. Required canonicalization via `canonicalVendor` to merge "Docusign" / "Docusign CLM" into one bucket. |
| `cited_sources` (alt: `sources_cited`)    | array        | Sources the LLM cited. Each entry an object `{ domain, url, … }`, a JSON-string of that object, or a bare URL string — `domainOf` handles all three.                                                                             |
| `full_response` (alt: `response_snippet`) | string       | The actual LLM prose. RawScanModal renders this verbatim. May be empty for older scans.                                                                                                                                          |
| `answer_length`                           | number       | Optional character count shown in the modal.                                                                                                                                                                                     |
| `truncated`                               | bool         | Optional — drives the "TRUNCATED" pill in the modal.                                                                                                                                                                             |

---

## 15. How V6 Mounts in PerceptionMonitor

In `src/PerceptionMonitor.jsx`:

- The valid-tabs whitelist includes `"reportv6"` alongside `"scan"`, `"summary"`, `"report"`, `"reportv2"` … `"reportv5"`, `"trajectoryv2"`, `"trajectory"`, `"settings"`.
- The sidebar nav item for V6 is registered with the icon `FileBarChart2` and label `"Perception Report"` for `client_portal` users / `"Report V6"` for everyone else.
- The render block is a one-liner: when `nav === "reportv6"`, render `<ReportV6 T={T} />`. The component receives the page-level theme tokens via the `T` prop.

That is the entire integration — V6 is fully self-contained inside `src/m2/reportV6/` and only depends on the global theme, `firebase`, `AuthContext`, `narrativeClassifier`, `baselineScanner.computeSegmentation`, `personaBuckets`, and the V2 module for shared section components.
