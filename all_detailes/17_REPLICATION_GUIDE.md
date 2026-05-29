# Replication Guide — Rebuild From Scratch

This is the step-by-step rebuild guide for someone cloning the Xtrusio Growth Engine into a new project. Follow phases in order. Each phase yields a working partial system before moving to the next.

---

## Prerequisites

| Requirement                                                                   | Why                     |
| ----------------------------------------------------------------------------- | ----------------------- |
| Node.js 18+ + npm                                                             | Vite build chain        |
| Firebase project (Firestore)                                                  | Persistence layer       |
| Cloudflare Pages account                                                      | Deployment target       |
| Cloudflare Worker for AI proxy                                                | Securely store API keys |
| API keys: Anthropic, OpenAI, Google Gemini, Perplexity, Grok (xAI), Firecrawl | LLM and scraping calls  |
| GitHub repo (auto-deploy from main → Cloudflare)                              | CI/CD                   |

---

## Recommended Build Order (10 Phases)

### Phase 0 — Project Skeleton

1. `npm create vite@latest <project-name> -- --template react`
2. Install dependencies: `react`, `recharts`, `lucide-react` (icons)
3. Set up project structure:
   ```
   src/
   ├── components/
   ├── data/         (constants like Q_BANK, vendor lists)
   ├── m2/           (M2 sub-modules including reportV6)
   ├── m6v2/         (M6 V2 prompt assembly)
   ├── m7v2/         (M7 V2 logic)
   ├── intelV2/      (Intel V2 + Domino)
   ├── PipelineContext.jsx
   ├── persistenceManager.js
   ├── firebase.js
   ├── claudeApi.js
   ├── ThemeContext.jsx
   ├── AuthContext.jsx
   └── App.jsx
   ```

### Phase 1 — Infrastructure (read `01_INFRASTRUCTURE.md`)

Build in this order:

1. **firebase.js** — Firestore REST wrapper. Functions: `save`, `update`, `getAll`, `getById`, `saveWithId`, `getAllPaginated`, `delete`, `test`. Add 429 circuit breaker (5min cooldown), localStorage cache with 25% LRU.
2. **claudeApi.js** — Cloudflare Worker proxy client. Functions: `callClaude`, `callClaudeFast`, `callClaudeChat`, `callGemini`, `callOpenAI`, `callGrok`, `callPerplexity`, `callFirecrawl`. Session token via URL hash → sessionStorage.
3. **persistenceManager.js** — 1.5s debounce queue, retry backoff [5s, 15s, 30s], beforeunload + visibilitychange hooks, snapshot stripping rules, per-item LWW merge for M6v2 articles + M7v2 assignments.
4. **PipelineContext.jsx** — Reducer with INITIAL_STATE, DATA_VERSION, focus-refresh subscription, hydration order (Firebase → localStorage → INITIAL_STATE).
5. **ThemeContext.jsx** — T_DARK and T_LIGHT key sets (must match), mode toggle.
6. **AuthContext.jsx** — Roles (admin, client, client_portal), `canTab(module, tabId)`, BUILTIN_ACCOUNTS.
7. **App.jsx** — 13-entry MODULES route table, hash-based routing, sidebar nav, Dashboard with score gauges + leaderboards + donuts.

**Validation:** App should load with empty pipeline state, no console errors, dark mode working.

### Phase 2 — M1 Question Generator (read `02_M1_QUESTION_GENERATOR.md`)

Build in this order:

1. Create `src/data/yinMatrix.js` (TECH_BUCKETS, PAIN_CATEGORIES, PAIN_LIBRARY).
2. Create `Q_BANK` constant with 230+ benchmark questions.
3. Create persona definitions (8 CLM personas with influence weights).
4. Create cluster definitions (9 clusters), stage definitions (5 stages), lifecycle definitions (3 stages).
5. **Build all 11 prompts** (LINKEDIN_CLEANUP, PERSONA_RESEARCH, FIND_SIMILAR, QUESTION_GEN_SYSTEM, etc.) — copy verbatim from doc 02.
6. Build the Questions tab UI: filter dropdowns, question grid, generate button, CSV import, export.
7. Build the Persona Research tab UI: paste textarea, cleanup → research → similar flow.
8. Build the Decision Matrix tab UI: bubble chart, scoring grid, manual scores.
9. Wire Firestore: `m1_questions_v2`, `m1_personas`, `m1_macros`, `m1_company_intel`, `user_segments`.
10. Wire `exportToM2()` to push to `pipeline.m1.scanBatch`.

**Validation:** Generate 10 questions, paste a LinkedIn profile, see clean → research → similar flow work end-to-end.

### Phase 3 — M2 Perception Monitor (read `03_M2_PERCEPTION_MONITOR.md`)

This is the largest module (~7500 lines). Build in this order:

1. **Build all 6 prompts** in `src/manualScanPrompts.js` (generatePrompt, buildBatchPrompt, generateIndividualPrompt, normalizeWithAI, repairWithAI, scanContentUrl) — copy verbatim from doc 03.
2. Build the parser with all 6 fallback levels.
3. Build the mention cross-verification logic.
4. Wire all 10 Firestore collections (m2_scan_meta, m2_scans, m2_scan_results, m2_scan_attempts, m2_scan_runs, m2_sections, m2_content_gaps, m2_questions, m2_config, m2_report_views).
5. Build the 5-metric calculator (Visibility, Narrative, Share of Voice, Sentiment, Competitive Position).
6. Build supporting libraries: `baselineScanner.js` (computeSegmentation), `narrativeClassifier.js` (rollUpNarrativeAcrossAnalyses), `personaBuckets.js` (BUCKET_ORDER, BUCKET_WEIGHTS, bucketOf, weighted visibility).
7. Build all 8+ tabs: Scan, Summary, Report, Report V2-V5, Report V6, Trajectory, Trajectory V2, Settings.
8. Implement the 4 scan modes: API scan (parallel workers), manual paste (clipboard prompt + paste-back), batch (10-question chunks), Excel upload.
9. Implement resume-on-interrupt logic.
10. Wire client_portal role restrictions.
11. Build M3 push button + M6 push button for content gaps.

**Validation:** Run a manual paste scan with 5 questions, see all 5 metrics computed, see V6 dashboard render.

### Phase 4 — V6 Report Sub-Module (read `12_M2_REPORT_V6.md`)

Build separately as `src/m2/reportV6/`:

1. `constants.js` — LLMS_ALL, V6_DEFAULT_SCANS, SCOPE_OPTIONS, STAGE_OPTIONS, COMPANY, LLM_LABELS, LLM_COL, STATUS_META.
2. `data/loadCombined.js` and `data/scanCatalog.js` — multi-scan loader with mergeBaselines (earliest-wins) + mergeAugmenting.
3. `compute.js` — computeLeaderboard, computePersonaStageMatrix, computeCitationDomains, computeLossPatterns, computeDataCredibility.
4. `helpers.js` — dominantStageForDoc, sentimentLetter, cellInfo, appendixStatus, etc.
5. `filters/useActiveDocs.js` — 6-step filter pipeline.
6. `filters/` — ScanPicker, LlmPicker, ScopeToggle, SegmentFilter components.
7. `sections/` — All 10 visualization components.
8. `segmentSave.js` — buildSegmentPayload + m2_segments_v6 collection.
9. `htmlExport.js` — Self-contained HTML download.
10. `index.jsx` — Mount inside PerceptionMonitor's reportv6 tab.

**Validation:** V6 tab renders, ScanPicker shows scans, all 9 sections display, HTML export works.

### Phase 5 — M3 Authority Ring (read `04_M3_AUTHORITY_RING.md`)

Mostly hardcoded data, no LLM integration:

1. Create `AUTHORITY_DOMAINS[]` array (40+ domain objects with all fields: name, da, aiCitationWeight, category, sirionPresence, personasAffected, buyerStagesInfluenced, approach, difficulty, costRange, timeline, narrativeGap, keyUrls, tier).
2. Create `OUTREACH_METHODS[]` (research_partnership, guest_article, council_membership, sponsored_content, webinar, case_study, etc.).
3. Build the UI: domain table with filters (status, approach, cost, persona, stage), expandable rows, per-domain detail view.
4. Wire `pipeline.m3.prioritizedDomains`, `personaDomainMap`, `aiCitedDomains`.
5. Special handling for Microsoft AI First Movers page (DA 96).

**Validation:** Browse 40+ domains, filter by tier, see narrative gaps and outreach methods.

### Phase 6 — M4 Buying Stage Guide (read `05_M4_BUYING_STAGE_GUIDE.md`)

1. **Build all 4 prompts** (LINKEDIN_CLEANUP, ANALYSIS, VERIFICATION, OUTREACH) verbatim from doc 05.
2. Build the analysis flow: paste LinkedIn → cleanup → analyze (Claude with web search) → verify → display.
3. Build the 6-dimension result UI: tech_stack, hiring_patterns, digital_footprint, competitor_usage, decision_maker_signals, plus stage_scores.
4. Implement strict word-limit enforcement for outreach_hook (3 sentences), recommended_actions (4-5 × 15 words), risk_factors (3-4 × 15 words), signals (4-5 × 3-7 words).
5. Wire `analyses` Firestore collection (append-only).
6. Wire back-ref to `m1_personas[id]` (m4AnalysisId, m4Stage, m4ReadinessScore, m4AnalyzedAt).
7. Build buying maturity radar visualization.

**Validation:** Analyze one decision maker, see 6 dimensions populated, see persona record back-linked.

### Phase 7 — M5 CLM Advisor (read `06_M5_CLM_ADVISOR.md`)

No prompts — deterministic only:

1. Create the 15-vendor catalog with verbatim taglines (Sirion, Icertis, Ironclad, Agiloft + 5 Strong Performers + 6 Notable).
2. Build the 3-step wizard: Profile → Assessment → Results.
3. Implement `calcScores()` — weighted-base + capped-context-adjustment formula across persona/industry/size/maturity/priority dimensions.
4. Build HTML report download.
5. Wire `pipeline.m5.recommendations` (top 5 vendor IDs + scores).

**Validation:** Run a 3-step assessment, see top-5 vendor ranking, download HTML report.

### Phase 8 — M6 Content Strategy (read `07_M6_CONTENT_STRATEGY.md`)

This is the most complex module. Build in two halves:

**M6 Legacy:**

1. Build all prompts in `src/contentPrompts.js` — buildTopicPrompt, buildJournalistPackPrompt, buildArticlePrompt, buildHumanizePrompt, buildFormatOwnTopicsPrompt, buildFormatOwnArticlePrompt, buildTopicFromGapsPrompt.
2. Build the 3-stage pipeline UI: Topics → Pack → Article.
3. Each stage uses copy-paste with Claude (no API integration in legacy).
4. Wire `pipeline.m6.topics`, `journalistPacks`, `articles`.
5. DOCX export logic.

**M6v2:**

1. Build `src/m6v2/promptAssembly.js`, `generateTopics.js`, `enrichGap.js`, `extractRules.js` with all V2 prompts.
2. Build the kanban UI with 8 statuses (draft → published → live).
3. Build the AI approval workflow (draft → AI revision → user approves → publish).
4. Build the gap-to-article flow: M2 gaps → enriched descriptions → topic candidates → articles.
5. Build market demand estimation via Gemini (cached in `gapMarketDemand{}`).
6. Build style rule library UI.
7. Wire `pipeline.m6v2.articles{}`, `topics{}`, `styleRules{}`, `dismissedGapIds{}`, `gapMarketDemand{}`, `gapDescriptions{}`.
8. DOCX export with redirect URL stripping + Sirion backlink preservation.

**Validation:** Generate 5 topics, build a journalist pack, generate one article, push to M7.

### Phase 9 — M7 Link Strategy (read `08_M7_LINK_STRATEGY.md`)

1. Create the 54-blog catalog seed data (with DR + traffic + country + priceUsd + sirionFit).
2. Build the 3 prompts: enrichOneBlog, matchArticleToBlogs, parseFreeTextWithGemini — verbatim from doc 08.
3. Implement provider cascade (Gemini → Perplexity → Grok → Claude).
4. Build BlogGallery view with enrichment UI.
5. Build ArticlesSection with assignment management.
6. Build 3-month CalendarGrid with $800 budget cap (1 high-DA $250 + 5 mid-DA $200).
7. Wire `pipeline.m7v2.assignments{}`, `monthPlans{}`, `samples[]`, `samplesSeeded`, `catalogEnrichment{}`, `catalogOverrides{}`.
8. Implement hallucinated-domain filtering on assignments.

**Validation:** Enrich 5 blogs, match an article, schedule into a month plan within budget.

### Phase 10 — Company Intelligence (read `09_*` and `10_*`)

**V1:**

1. Build 4-tab UI: AI Position / Market Pulse / Alerts / Market Data.
2. Build the 2 manual Gemini paste prompts.
3. Wire M2 self-load fallback (loadCombinedScanDocs).

**V2:**

1. Build `src/intelV2/intelCache.js` with TTLs (NEWS 1d, MARKET_DATA 30d, TRENDS 14d, OPPORTUNITIES 14d, ACTIONS 7d).
2. Build news pipeline: aggregate → dedup → analyze → archive (newsAggregator, newsDedup, newsAnalysis, newsArchive).
3. Build subscriptions: CURATED_TOPIC_CHIPS, DEFAULT_SUBSCRIPTIONS, googleNewsRSS integration.
4. Build all 12+ prompts (NEWS, VENDOR_SHARE, ANALYST_RANKINGS, CURRENT_EVENTS, TRENDS, DIGEST, OPP, ACTIONS) verbatim.
5. Build the 5 lenses: Position, Competitors, Market Pulse, Opportunities, Actions.
6. Build snapshotStore (capture/load).
7. Build handoff to M6: transferOpportunityToM6, transferActionToM6, actionToMarkdown, actionToSlack.
8. Build researchLog + ResearchLogPanel + researchCall (PROVIDER_CHAINS).
9. Build hallucination guards (host allowlist/rejectlist).

### Phase 11 — Domino Sub-Module (read `11_DOMINO_SUBMODULE.md`)

1. Create `dominoTypes.js` with DEFAULT_INDUSTRIES (15 with tiers), SIGNAL_TYPES (8), NODE_COLORS (4), SOURCE_VENDORS (10).
2. Create `dominoStore.js` with persistence pubsub (subscribePersistenceHealth).
3. Build all prompts in companyPrompts.js, industryPrompts.js, signalPrompts.js verbatim.
4. Build VENDOR_CUSTOMER_PAGES hardcoded list.
5. Build harvestCompaniesAcrossVendors orchestration.
6. Build 4 views: CompanyUniverseView, IndustryProfilesView, SignalFeedView, DominoForceGraph.
7. Build DominoGrids (heatmap), DominoInsights (derived), PersistenceIndicator (UI).
8. Wire to Intel V2's Lens 2 (Competitors).

---

## Cloudflare Worker Setup (AI Proxy)

The worker URL is `xtrusio-ai.thedevimapro.workers.dev`. You'll need your own.

1. Create a new Cloudflare Worker.
2. Add environment secrets: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `PERPLEXITY_API_KEY`, `XAI_API_KEY` (Grok), `FIRECRAWL_API_KEY`.
3. Implement endpoints for each provider that the browser's claudeApi.js will call.
4. Implement session token validation (URL hash `?c=<clientId>&t=<token>` → sessionStorage `xt_token`).
5. Update `claudeApi.js` worker URL constant.

**Why a worker:** Browser cannot hold API keys safely. Worker holds keys, validates session token, proxies the call.

---

## Firebase Setup

1. Create Firebase project.
2. Enable Firestore in production mode.
3. Set security rules (read/write authorized only).
4. Create the 22 collections listed in doc 14.
5. Set environment variables in Cloudflare Pages: `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_PROJECT_ID`.

---

## Cloudflare Pages Setup

1. Connect GitHub repo to Cloudflare Pages.
2. Build command: **EMPTY** (do NOT use `pnpm run build` — project uses npm and pre-built dist/).
3. Output directory: `dist` (set in `wrangler.toml`).
4. Environment variables: Firebase keys above.
5. Deploy command: `npx wrangler deploy`.

**Critical:** Build the dist locally with `npx vite build`, commit `dist/` to repo, push to main. Cloudflare auto-deploys committed dist.

---

## Validation Checklist (After Full Build)

- [ ] Dashboard loads with no console errors
- [ ] M1: Generate 10 questions, paste LinkedIn, run persona research
- [ ] M2: Run manual paste scan with 5 questions, see all 5 metrics
- [ ] V6 Report: All 9 sections render, HTML export works
- [ ] M3: Browse 40+ domains, filter by tier
- [ ] M4: Analyze one decision maker end-to-end
- [ ] M5: Run 3-step assessment, see top-5 ranking
- [ ] M6: Generate topic → pack → article
- [ ] M7: Enrich blogs, match article, schedule placement
- [ ] Intel V1: Both manual paste prompts work
- [ ] Intel V2: All 5 lenses load
- [ ] Domino: Harvest companies from one vendor case study
- [ ] Theme toggle: Light mode renders correctly
- [ ] Client portal mode: Restricted tabs hidden
- [ ] Build clean: `npx vite build` finishes with zero errors
- [ ] Deploy: Push to main, verify live URL works

---

## Common Build Gotchas

| Pitfall                                                    | Fix                                             |
| ---------------------------------------------------------- | ----------------------------------------------- |
| `pmRef.current` stays truthy after StrictMode unmount      | null it in cleanup                              |
| Question field is `q`/`text`/`question` instead of `query` | Always `query` — historic bug fixed in M1       |
| Bumping DATA_VERSION wipes user data                       | Only bump when schema truly changes             |
| Theme keys missing in light mode                           | T_DARK and T_LIGHT must have IDENTICAL keys     |
| 429 from Firebase storms                                   | 5-minute circuit breaker prevents cascade       |
| dist/ in .gitignore                                        | Must commit dist/ for Cloudflare auto-deploy    |
| `pnpm run build` set as Cloudflare build cmd               | Project uses npm — set build cmd to EMPTY       |
| API keys in browser                                        | Always proxy through Worker — never expose keys |
| M2 V6 reads m2_segments_v6                                 | DON'T reuse v5 collection                       |
| Mention cross-verification missed                          | Auto-correct YES → NO if name not in response   |

---

## Time Estimate

A team of 2-3 senior engineers can rebuild this in **8-12 weeks**:

- Phases 0-1 (Infrastructure): 1 week
- Phase 2 (M1): 2 weeks
- Phase 3-4 (M2 + V6): 3-4 weeks (the heart of the system)
- Phase 5 (M3): 0.5 week (mostly data entry)
- Phase 6 (M4): 1 week
- Phase 7 (M5): 0.5 week (deterministic, no LLM)
- Phase 8 (M6): 2 weeks (most complex content pipeline)
- Phase 9 (M7): 1 week
- Phase 10 (Intel V1+V2): 2 weeks
- Phase 11 (Domino): 1 week
- Buffer + integration testing: 1-2 weeks

---

## Final Notes

1. **Read CLAUDE.md** at the project root for the project rules and known pitfalls before starting.
2. **Use the source bundles** (`V6_BUNDLE_FOR_CLONE.txt`, `MARKET_PULSE_BUNDLE_FOR_CLONE.txt`, `INTELV2_BUNDLE_FOR_CLONE.txt`) for direct code reference if needed.
3. **Test at 125% browser zoom** — that's the user's default.
4. **Always verify with `npx vite build`** before saying anything is done.
5. **Open the actual URL in incognito** after deploy to bypass browser cache.
6. **Never modify** `sirion-v2/` or `sirion-v3/` — those are old archived versions.
7. **Commit pre-built `dist/`** — Cloudflare doesn't run a build step.

You now have everything needed to rebuild the entire Xtrusio Growth Engine in a clean project. Good luck.
