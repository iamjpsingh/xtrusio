# Data Flow Map — Cross-Module Connections

How data moves through the Xtrusio Growth Engine. This document is the canonical reference for who reads what, who writes what, and what triggers what.

---

## High-Level Architecture

```
                       Cloudflare Worker (xtrusio-ai.thedevimapro.workers.dev)
                                        │
                                        │ AI proxy
                                        ▼
       ┌──────────────────────────────────────────────────────────┐
       │  Claude • OpenAI • Gemini • Grok • Perplexity • Firecrawl │
       └──────────────────────────────────────────────────────────┘
                                        ▲
                                        │
                              claudeApi.js (browser)
                                        │
       ┌────────────────────────────────┼────────────────────────────────┐
       │                                │                                │
   M1, M2, M4, M6, M7         Intel V1/V2, Domino                 V6 Report
       │                                │                                │
       ▼                                ▼                                ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                       PipelineContext (React)                          │
 │   - Single source of truth                                             │
 │   - reducer: updateModule, hydrate, reset                              │
 │   - INITIAL_STATE shape (m1/m2/m3/m4/m5/m6/m6v2/m7v2/intel/meta)       │
 └────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                           persistenceManager.js
                       (1.5s debounce, retry backoff)
                                        │
                  ┌─────────────────────┴────────────────────┐
                  ▼                                          ▼
            localStorage                              Firebase Firestore
          (sync, instant)                           (async, durable)
                                                            │
                                                            ▼
                                                  ┌──────────────────┐
                                                  │  pipelines       │
                                                  │  m1_questions_v2 │
                                                  │  m1_personas     │
                                                  │  m2_scan_meta    │
                                                  │  m2_scan_results │
                                                  │  m2_scan_attempts│
                                                  │  m2_segments_v6  │
                                                  │  analyses (M4)   │
                                                  │  ...             │
                                                  └──────────────────┘
```

---

## Module-To-Module Data Flow

### M1 → M2 (Questions To Scan)

**What flows:** Questions, segments, scan triggers
**Mechanism:** M1 writes to `pipeline.m1.questions[]`. M2 reads on mount + hot-reloads via PipelineContext subscription.
**Specifics:**

- `pipeline.m1.questions[]` — every question with metadata
- `pipeline.m1.segments[]` — user-saved groupings
- `pipeline.m1.pendingSegment` / `pipeline.m1.scanBatch` — auto-launches M2 scan when set
- `pipeline.meta.company` — target company name (defaults to "Sirion")

### M1 → M4 (Personas To Analyze)

**What flows:** Persona profiles for sales intelligence
**Mechanism:** M4 reads `pipeline.m1.personaProfiles[]` and `pipeline.m1.personas[]`. Also reads from `m1_personas` Firestore collection.
**Back-ref:** M4 writes back to `m1_personas[id]` with `m4AnalysisId`, `m4Stage`, `m4ReadinessScore`, `m4AnalyzedAt`.

### M1 → M6 (Questions As Topic Seeds)

**What flows:** Questions filtered by cluster/persona/lifecycle for topic generation
**Mechanism:** M6 reads `pipeline.m1.questions[]` and filters at topic-generation time.

### M1 → Intel (Persona context)

**What flows:** Persona profiles for buyer-persona display in V1/V2.

### M2 → M3 (Content Gaps Drive Outreach)

**What flows:** Content gaps + perception scores
**Mechanism:**

- `pipeline.m2.contentGaps[]` (in-pipeline) and `m2_content_gaps` (Firestore) feed M3
- User manually selects gaps in M2 Settings → "Push to M3" button transfers them
- M3 uses gap severity + persona context to prioritize domain outreach

### M2 → M4 (Scan Results For Stage Scoring)

**What flows:** Persona-filtered scan results
**Mechanism:** M4 reads `pipeline.m2.scanResults` and filters to questions relevant to a specific decision maker's persona/stage.

### M2 → M6 (Gaps As Topic Candidates)

**What flows:** Content gaps with severity, demand estimation
**Mechanism:**

- `pipeline.m2.contentGaps[]` → M6v2 ingests as topic seeds via `buildTopicFromGapsPrompt`
- M6v2 caches `gapMarketDemand{}` (Gemini-estimated search volume) and `gapDescriptions{}` (AI-enriched 2-4 sentence descriptions)
- M6v2 tracks `dismissedGapIds{}` per campaign so the user can snooze gaps

### M2 → Intel V2 Position Lens

**What flows:** Scan results power Position + Competitors lenses
**Mechanism:** Intel V2 reads `m2_scan_results` directly via `loadCombinedScanDocs(scanIds)`. The lens computes mention rate + sentiment per stage per LLM.

### M2 → V6 Report

**What flows:** All scan data for visualization
**Mechanism:** V6 reads `m2_scan_results` (granular) and `m2_scan_meta` (registry). Filters with `useActiveDocs` 6-step pipeline (scope → segment → persona → stage → CLM stage → text).

### M2 → M1 (Feedback)

**What flows:** Best scan results back to M1
**Mechanism:** M2 saves best scan to `pipeline.m2.scanResults` + `pipeline.m2.scannedAt`. M1's dashboard can show "Last scan: 62% visibility".

### M3 → M6 (Authority Domains For Publication Targeting)

**What flows:** Prioritized domain list
**Mechanism:** M6's `buildJournalistPackPrompt` reads `pipeline.m3.prioritizedDomains[]` to recommend target publications.

### M3 → M7 (Domain Priority For Link Sequencing)

**What flows:** DA scores + tier classifications
**Mechanism:** M7's blog catalog cross-references M3 domain priorities for placement sequencing.

### M4 → M5 (Stage Maturity → Sales Messaging)

**What flows:** Buying stage maturity scores
**Mechanism:** M5 reads `pipeline.m4.companyBuckets` and `pipeline.m4.latestStage` to inform messaging recommendations.
**Note:** M5 wiring is currently a placeholder — minimal actual integration.

### M4 → M1 (Persona Back-Ref)

**What flows:** Analysis ID + readiness score back to persona record
**Mechanism:** M4 writes `m4AnalysisId`, `m4Stage`, `m4ReadinessScore`, `m4AnalyzedAt` back to the persona doc.

### M5 → M6 (Strategic Themes For Content)

**What flows:** Top recommendations
**Mechanism:** Currently minimal — M5 outputs top-5 vendor IDs to `pipeline.m5.recommendations`.

### M6 → M7 (Articles To Place)

**What flows:** Completed articles
**Mechanism:**

- M6 articles flow to M7v2 via the "Send to Link Strategy" action
- M7v2 reads `pipeline.m6v2.articles{}` and creates `pipeline.m7v2.assignments{}` records

### M6 + M7 → Intel (Authority Signals)

**What flows:** Published article + link placement counts
**Mechanism:** Intel V1's market pulse can show recent published assets.

### Intel V2 → M6 (Opportunity & Action Handoff)

**What flows:** Top opportunities and actions
**Mechanism:** `transferOpportunityToM6()` and `transferActionToM6()` push selected items to M6 as topic candidates. Also `actionToMarkdown()` and `actionToSlack()` for sharing.

### Domino → Intel V2 (Customer-Vendor Map)

**What flows:** Per-vendor customer lists
**Mechanism:** Intel V2's Lens 2 (Competitors) can use Domino data to show competitor customer counts.

---

## Quick Reference: Pipeline Slices

| Slice   | Owner       | Key fields                                                                                                                                      |
| ------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `meta`  | All         | company, url, industry                                                                                                                          |
| `m1`    | M1          | questions[], personas[], personaProfiles[], decisionScores, yinMatrix, generationId, generatedAt                                                |
| `m2`    | M2          | scanResults, scores (5 metrics), contentGaps[], personaBreakdown[], stageBreakdown[], recommendations[], scanProgress                           |
| `m3`    | M3          | prioritizedDomains[], gapMatrix, outreachPlan, personaDomainMap, gapCount, strongCount                                                          |
| `m4`    | M4          | analyses[], latestStage, latestReadiness, companyBuckets{}, generationId                                                                        |
| `m5`    | M5          | recommendations[], leadData (placeholder), generatedAt                                                                                          |
| `m6`    | M6 (legacy) | topics[], journalistPacks[], articles[], transfers[], tags[], articleBriefs{}                                                                   |
| `m6v2`  | M6 V2       | articles{}, styleRules{}, topics{}, dismissedGapIds{}, gapMarketDemand{}, gapDescriptions{}, lastGapRefresh{}                                   |
| `m7v2`  | M7 V2       | assignments{}, monthPlans{}, samples[], samplesSeeded, catalogEnrichment{}, catalogOverrides{}                                                  |
| `intel` | Intel       | companyName, companyUrl, industry, overview, productsServices[], targetMarket, competitors[], decisionMakers[], buyerPersonas[], marketPosition |

---

## Trigger Events

### What Causes A Save

- Any `updateModule()` call → debounced 1.5s → localStorage immediate, Firebase async
- `beforeunload` event → best-effort flush
- `visibilitychange` (tab hidden) → best-effort flush

### What Causes A Reload

- Tab focus → focus-refresh fetches latest from Firebase, per-item LWW merge
- Initial mount → hydration order: Firebase → localStorage → INITIAL_STATE

### What Triggers A Scan (M2)

- User clicks "Run Scan" button (API mode)
- User clicks "Run in [AI]" then pastes response (manual mode)
- User uploads Excel file
- M1 sets `pipeline.m1.scanBatch` or `pipeline.m1.pendingSegment` (auto-trigger)

### What Triggers A Persona Analysis (M4)

- User runs analysis from M4 UI
- User clicks "Analyze" on a persona in M1's persona library

---

## Cross-Module Race Conditions & Mitigations

| Scenario                                  | Risk                          | Mitigation                                           |
| ----------------------------------------- | ----------------------------- | ---------------------------------------------------- |
| Two tabs both editing M6v2 articles       | Last-write-wins clobber       | Per-article LWW merge by lastModifiedAt              |
| Two tabs both editing M7v2 assignments    | Same                          | Per-assignment LWW by lastTouchAt                    |
| Parallel M2 scan workers writing same qid | Concurrent write race         | Atomic doc IDs `{scanId}__{qid}__{model}__{attempt}` |
| User closes tab mid-scan                  | Lost partial results          | beforeunload flushes; m2_scan_attempts already saved |
| StrictMode mounts twice                   | PM destroyed, never recreated | `pmRef.current = null` in cleanup forces re-init     |
| Firebase 429 rate limit                   | All saves fail in cascade     | 5-minute circuit breaker + retry backoff             |

---

## App Routing (App.jsx)

| Path            | Module                       | Notes                                    |
| --------------- | ---------------------------- | ---------------------------------------- |
| `/`             | Dashboard                    | Score gauges, leaderboards, donuts       |
| `/intel`        | Company Intelligence V1      | 4-tab dashboard                          |
| `/intel-v2`     | Company Intelligence V2      | 5 lenses + Domino                        |
| `/questions`    | M1 Question Generator        | Questions + Persona Research             |
| `/perception`   | M2 Perception Monitor        | 8+ tabs including V6 Report              |
| `/authority`    | M3 Authority Ring            | 40+ domain database                      |
| `/buying-stage` | M4 Buying Stage Guide        | Per-decision-maker analysis              |
| `/advisor`      | M5 CLM Advisor               | 3-step vendor scoring wizard             |
| `/content`      | M6 Content Strategy (legacy) | Copy-paste workflow                      |
| `/content-v2`   | M6 Content Strategy V2       | Kanban + AI workflow                     |
| `/links`        | M7 Link Strategy V2          | BlogGallery + ArticlesSection + Calendar |
| `/links-legacy` | M7 Link Strategy (legacy)    | Read-only dashboard                      |
| `/settings`     | Settings                     | Auth, API keys, theme                    |

Hash-based routing. Sub-tabs supported (e.g., `#/perception/scan`).

Build flag `VITE_PORTAL_MODE=client` strips internal modules from the bundle for client_portal users.

---

## Connection Diagram (ASCII)

```
                       Cloudflare AI Proxy
                              │
                              ▼
   ┌───────────────────────────────────────────────────────────┐
   │ M1 ──questions──► M2                                      │
   │  │                 │                                      │
   │  │                 ├──gaps──► M3 (outreach)              │
   │  │                 │                                      │
   │  │                 ├──gaps──► M6 (content topics)        │
   │  │                 │                                      │
   │  │                 ├──results──► Intel V2 Lens 1+2       │
   │  │                 │                                      │
   │  │                 └──results──► V6 Report               │
   │  │                                                        │
   │  ├──personas──► M4 ──readiness──► M5                     │
   │  │              ▲                  │                      │
   │  │              │                  ▼                      │
   │  │              └──back-ref──── M1 personas              │
   │  │                                                        │
   │  └──questions──► M6 ──articles──► M7                     │
   │                                                           │
   │ M3 ──domains──► M6 (publication targeting)               │
   │ M3 ──priorities──► M7 (link sequencing)                  │
   │                                                           │
   │ Intel V2 ──opportunities/actions──► M6                   │
   │ Domino   ──customer maps──► Intel V2 Lens 2              │
   └───────────────────────────────────────────────────────────┘
```

---

## End-To-End Example: A New Buyer Question Becomes A Published Article

1. **M1** — User pastes a CFO LinkedIn profile → `PERSONA_RESEARCH_PROMPT` runs → 5 personalized question angles generated → user accepts 3 → questions saved to `m1_questions_v2`
2. **M1 → M2** — User clicks "Send to M2" → `pipeline.m1.scanBatch` set → M2 hot-reloads
3. **M2** — User clicks "Run Scan" → all 3 questions go through `generatePrompt` for Claude/Gemini/ChatGPT → results saved to `m2_scan_results`
4. **M2** — One question shows 0% mention rate + competitor dominance → flagged as content gap → saved to `pipeline.m2.contentGaps[]`
5. **M2 → M3** — User pushes gap to M3 → M3 prioritizes Forbes Council outreach (DA 96)
6. **M2 → M6** — User pushes gap to M6v2 → `buildTopicFromGapsPrompt` generates 5 topic candidates
7. **M6v2** — User picks one → `buildJournalistPackPrompt` generates pitch templates targeting Forbes
8. **M6v2** — User runs `buildArticlePrompt` → 2,800-word article generated
9. **M6 → M7** — Article sent to M7v2 → `matchArticleToBlogs` runs → top 5 placement candidates
10. **M7v2** — User assigns to Forbes (high-DA, $250 budget slot in next month plan)
11. **Intel V2** — Article counted in Lens 5 Actions ("article published" signal)
12. **Future M2 scan** — Mention rate for that question expected to climb after the article goes live

This is the full life cycle. Every cross-module hand-off is captured above.
