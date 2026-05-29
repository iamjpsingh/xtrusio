# Firestore Collections — Complete Schema Reference

Every Firestore collection used by the Xtrusio Growth Engine, in one place. For the full per-field meaning, see the per-module doc referenced in each section.

---

## How Documents Are Stored

- Firestore is accessed via **REST API** (not the SDK) — see `01_INFRASTRUCTURE.md` for `firebase.js` details
- Values are flattened to depth 3 via `toFsVal/fromFsVal` helpers (200K char cap, 500-element array threshold)
- Each module decides its own document ID convention (UUID, slug, scanId, etc.)
- `localStorage` mirrors all writes for crash safety + a 25% LRU eviction policy protects the canonical `xt_pipeline_snapshot` and `xt_data_version` keys
- 429 rate-limit errors trigger a 5-minute circuit breaker

---

## Master List Of Collections

| Collection         | Owner module | Purpose                                                | Doc ID convention                     |
| ------------------ | ------------ | ------------------------------------------------------ | ------------------------------------- |
| `pipelines`        | All          | Central pipeline state (single shared doc per company) | Company slug                          |
| `m1_questions_v2`  | M1           | Generated and imported questions                       | UUID                                  |
| `m1_personas`      | M1           | Researched persona profiles                            | UUID                                  |
| `m1_macros`        | M1           | Macro/topic clusters                                   | UUID                                  |
| `m1_company_intel` | M1           | Per-company intelligence findings                      | Company slug                          |
| `user_segments`    | M1/M2        | User-saved question segments                           | UUID                                  |
| `m2_scan_meta`     | M2           | Scan registry + 5 metrics scoreboard                   | scanId                                |
| `m2_scans`         | M2           | Legacy full scan blob (results-as-array)               | scanId                                |
| `m2_scan_results`  | M2           | Per-question per-scan results (granular)               | `{scanId}__{qid}`                     |
| `m2_scan_attempts` | M2           | Attempt log for resumability                           | `{scanId}__{qid}__{model}__{attempt}` |
| `m2_scan_runs`     | M2           | Baseline-specific run logs                             | scanId                                |
| `m2_sections`      | M2           | User-created and baseline report sections              | sectionId                             |
| `m2_content_gaps`  | M2           | Gap backlog for handoff to M3/M6                       | gapId                                 |
| `m2_questions`     | M2           | M2's own question library (Q-picker)                   | qid                                   |
| `m2_config`        | M2           | Question bank + calibration settings                   | "question_bank" (singleton)           |
| `m2_report_views`  | M2           | Saved filter views                                     | viewId                                |
| `m2_segments_v6`   | M2 V6        | V6-specific custom segments (separate from V5)         | segmentId                             |
| `analyses`         | M4           | Per-decision-maker analysis records (append-only)      | analysisId                            |
| `m6_articles`      | M6           | Article library (if persisted — usually pipeline-only) | articleId                             |
| `m6_topics`        | M6           | Topic library                                          | topicId                               |
| `m7_articles`      | M7           | Article tracking (if persisted)                        | articleId                             |
| `m7_domains`       | M7           | Blog catalog enrichment                                | domain slug                           |

**Note:** M3 (Authority Ring), M5 (CLM Advisor), Company Intel V1, Company Intel V2 do not write to Firestore directly. They consume from the pipeline doc + M2 collections.

---

## `pipelines` (THE Central Document)

The single shared state across every module. One doc per company.

**Top-level shape:**

- `m1` — Question Generator state
- `m2` — Perception Monitor state
- `m3` — Authority Ring state
- `m4` — Buying Stage Guide state
- `m5` — CLM Advisor state
- `m6` — Content Strategy (legacy)
- `m6v2` — Content Strategy V2
- `m7v2` — Link Strategy V2
- `intel` — Company Intelligence
- `meta` — Company name, URL, industry
- `dataVersion` — string like `"2026-04-16-v6"` (cache-bust marker)

**Stripped on write** (kept in localStorage but NOT in Firestore to save space):

- `m1.questions[]` (lives in `m1_questions_v2`)
- `m1.personaProfiles[]` (lives in `m1_personas`)
- M2 scan results (lives in `m2_scan_*`)

**Per-item LWW merge on save** for:

- `m6v2.articles{}` (by article ID)
- `m6v2.topics{}` (by topic ID)
- `m7v2.assignments{}` (by lastTouchAt)
- `m7v2.catalogEnrichment{}` (by enrichedAt)
- `m7v2.catalogOverrides` (additive union of arrays)

---

## M1 Collections

### `m1_questions_v2`

Per-question docs. ~30 fields per question.

Key fields: `id` (qid), `query` (text — NOT `q`/`text`/`question` — historic bug), `persona`, `stage`, `topic`, `intentType`, `cluster`, `lifecycle`, `source` (macro/micro/niche/manual), `searchVolume`, `personaFit`, `classification` (macro/micro), `confidence`, `enrichmentMeta`, `generated` flag, `createdAt`, `updatedAt`.

### `m1_personas`

Per-persona deep-research profiles.

Key fields: `id`, `name`, `title`, `company`, `linkedinJson` (cleaned), `psycheProfile`, `painPoints[]`, `priorities[]`, `clmReadiness` (1-10), `researchSummary`, `personalizedQuestionAngles[]`, `webFindings[]`, `m4AnalysisId` (back-ref to M4), `m4Stage`, `m4ReadinessScore`, `m4AnalyzedAt`, `createdAt`, `updatedAt`.

### `m1_macros`

Topic/macro clusters used for question grouping.

### `m1_company_intel`

Per-company intel findings (competitors, market position, recent news).

### `user_segments`

User-saved groupings of questions for filtering.

---

## M2 Collections (10 total)

### `m2_scan_meta`

Scan registry with the 5-metric scoreboard. One doc per scanId.

Key fields: `id` (scanId), `date`, `status` (running/complete/paused/failed), `scanMode` (api/manual/batch/excel), `scanType`, `llms[]`, `company`, `totalQueries`, `completedQueries`, `scores.fiveMetrics` (mention, shareOfVoice, sentiment, narrative, competitivePosition), `errors[]`, `cost`, `duration`, `retries`, `partialFailures`, `sectionId`, `sectionName`, `segmentId`, `segmentName`, `queryIds[]`, `createdAt`, `completedAt`.

### `m2_scans` (legacy)

Full scan blob with results as a flat array. Used by older code paths; `m2_scan_results` is the modern granular store.

### `m2_scan_results` (the V6-friendly store)

Per-question per-scan results. The atomic unit V6 reads.

Key fields: `_id` = `{scanId}__{qid}`, `scanId`, `qid`, `query`, `persona`, `stage`, `lifecycle`, `difficulty`, `analyses` (object keyed by LLM name).

`analyses[llm]` shape: `mentioned` (bool), `rank` (int|null), `sentiment` (positive/neutral/negative/absent), `response_snippet`, `full_response`, `vendors_mentioned[]` (name, position, sentiment, strength), `sources_cited[]` (url, type, snippet), `content_gaps[]`, `lifecycle_stage`, `lifecycle_rationale`, `sentiment_rationale`, `_mentionCorrected` (bool flag if cross-verification fired).

### `m2_scan_attempts`

Per-attempt log for resumability.

Key fields: `_id` = `{scanId}__{qid}__{model}__{attempt}`, `scanId`, `qid`, `model`, `attempt`, `status` (complete/failed/rate_limited), `vendor_mentioned`, `vendor_rank`, `sentiment`, `latency_ms`, `tokens_in`, `tokens_out`, `cost`, `error`, `retryAfter`, `createdAt`.

### `m2_scan_runs`

Baseline-specific internal run data.

### `m2_sections`

User-created and baseline report sections (named groups of questions).

### `m2_content_gaps`

Aggregated gap backlog with severity, priority score, scan_id, query_context. Pushed to M3 and M6.

### `m2_questions`

M2's own question library (separate from M1's m1_questions_v2 — used by the Q-picker UI).

### `m2_config`

Singleton doc with id="question_bank" — calibration settings, mention rate baseline, alert thresholds, narrative distribution expectations, presets.

### `m2_report_views`

Saved filter view configs (filter state snapshots).

### `m2_segments_v6` (V6-only)

Custom segments saved by V6 specifically — distinct from V5's collection so V6 can evolve independently.

Key fields: `id`, `name`, `scope`, `scanIds[]`, `qids[]`, `pickedLlms[]`, `isManualPick`, `createdAt`.

---

## M4 Collection

### `analyses`

Per-decision-maker analysis records. Append-only history (each rerun adds a new doc).

Key fields: `id`, `decision_maker` (name, title, company, location, tenure, previous_roles[], certifications[], linkedin_activity_signals[]), `company_profile` (industry, revenue, employees, HQ, recent_news), `analysis` (6 dimensions: tech_stack, hiring_patterns, digital_footprint, competitor_usage, decision_maker_signals, plus extra dim) each with findings + signals[] + score, `stage_scores` (awareness/consideration/discovery), `primary_stage`, `confidence`, `readiness_score` (1-10), `outreach_hook`, `recommended_actions[]`, `risk_factors[]`, `summary`, `personalization_notes`, `verifiedAt`, `createdAt`.

---

## M6 Collections

### `m6_articles` (optional)

Most M6 article state lives in `pipeline.m6.articles[]` and `pipeline.m6v2.articles{}`. This collection is used only when persisting article library separately.

### `m6_topics` (optional)

Same — usually pipeline-only.

---

## M7 Collections

### `m7_articles` (optional)

Article placement state. Usually pipeline-only.

### `m7_domains`

Blog catalog enrichment cache. Per-domain enriched metadata from AI provider web search (faviconUrl, niche, audienceFit, estTimeToIndex, sirionFit, country, priceUsd, DR, traffic).

---

## Domino Sub-Module Storage

Domino uses **in-browser persistence** (the `dominoStore`) backed by localStorage, NOT Firestore. The store has a pubsub for health monitoring (`subscribePersistenceHealth`).

**Stored in dominoStore:**

- `dominoCompanies` — per-vendor harvested company lists
- `dominoIndustries` — DEFAULT_INDUSTRIES taxonomy + AI-fetched
- `dominoSignals` — buying signals per industry/company

---

## Collections By Read/Write Pattern

| Module    | Reads                                                                               | Writes                                                                              |
| --------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| M1        | pipelines, m1_questions_v2, m1_personas, m1_company_intel, m1_macros, user_segments | m1_questions_v2, m1_personas, m1_macros, m1_company_intel, user_segments, pipelines |
| M2        | All m2\_\* collections, pipelines (m1 questions)                                    | All m2\_\* collections, pipelines (m2 slice)                                        |
| M3        | pipelines (m2 scan results, m2 gaps)                                                | pipelines (m3 slice)                                                                |
| M4        | pipelines (m1 personas), m1_personas                                                | analyses, pipelines (m4 slice), m1_personas (back-ref)                              |
| M5        | pipelines (m1 personas)                                                             | pipelines (m5 slice)                                                                |
| M6        | pipelines (m1 questions, m2 gaps), m6_articles, m6_topics                           | pipelines (m6, m6v2), m6_articles, m6_topics                                        |
| M7        | pipelines (m6 articles), m7_domains                                                 | pipelines (m7v2), m7_domains, m7_articles                                           |
| Intel V1  | pipelines (m2 scan results)                                                         | pipelines (intel slice)                                                             |
| Intel V2  | pipelines (m2), m2_scan_results, m2_scan_meta                                       | pipelines (intel slice), in-browser cache only                                      |
| Domino    | None (Firecrawl + AI provider web search)                                           | dominoStore (localStorage), in-memory state                                         |
| V6 Report | m2_scan_results, m2_scan_meta, m2_segments_v6                                       | m2_segments_v6                                                                      |

---

## Document ID Examples

| Collection       | Sample ID                                      |
| ---------------- | ---------------------------------------------- |
| pipelines        | `sirion`                                       |
| m1_questions_v2  | `Q47` or `qa-2026-04-15-abc123`                |
| m1_personas      | UUID v4                                        |
| m2_scan_meta     | `baseline_20260423_1718`, `manual-paste-12345` |
| m2_scan_results  | `baseline_20260423_1718__Q01`                  |
| m2_scan_attempts | `baseline_20260423_1718__Q01__claude__1`       |
| m2_segments_v6   | UUID v4                                        |
| analyses         | UUID v4                                        |
| m7_domains       | `hbr-org`, `zdnet-com`                         |

---

## Cross-Cutting Concerns

### Cache-Bust Mechanism

Bumping `DATA_VERSION` (in PipelineContext.jsx) wipes localStorage AND IndexedDB on next load. Only bump when the schema truly changes, never just for code changes.

### Append-Only Collections

`analyses` (M4) and `m2_scan_attempts` are append-only. Never delete records — history matters.

### Singleton Documents

`m2_config` always uses id="question_bank". `pipelines` always uses the company slug.

### Atomic IDs

All M2 result/attempt collections use composite keys (`{scanId}__{qid}__...`) to enable safe concurrent writes from parallel scan workers without read-modify-write races.

---

For the per-field schema of each Firestore document, see the per-module doc:

- M1 fields → `02_M1_QUESTION_GENERATOR.md`
- M2 fields → `03_M2_PERCEPTION_MONITOR.md`
- M4 fields → `05_M4_BUYING_STAGE_GUIDE.md`
- M6 fields → `07_M6_CONTENT_STRATEGY.md`
- M7 fields → `08_M7_LINK_STRATEGY.md`
- V6 segment shape → `12_M2_REPORT_V6.md`
