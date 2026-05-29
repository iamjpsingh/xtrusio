# Master Prompts Index

Every LLM prompt in the Xtrusio Growth Engine, in one table. For the verbatim text of each prompt, jump to the per-module doc cited in the rightmost column.

---

## Summary By Module

| Module                | # Prompts | Notes                                                                                          |
| --------------------- | --------- | ---------------------------------------------------------------------------------------------- |
| M1 Question Generator | 11        | Heavy LLM use — questions, personas, similar targets, CSV mapping, classification              |
| M2 Perception Monitor | 6         | Main scan, batch scan, individual rescan, normalize, repair, scan content URL                  |
| M3 Authority Ring     | 0         | NO prompts — pure reference data                                                               |
| M4 Buying Stage Guide | 4         | LinkedIn cleanup, full analysis, verification, outreach                                        |
| M5 CLM Advisor        | 0         | NO prompts — deterministic scoring engine                                                      |
| M6 Content Strategy   | 10+       | Topics (multiple variants), packs, articles, humanize, format-own, gap-to-article, AI feedback |
| M7 Link Strategy      | 3         | Blog enrichment, article-to-blog matching, free-text CSV parsing                               |
| Company Intel V1      | 2         | Manual Gemini paste prompts                                                                    |
| Company Intel V2      | 12+       | News, vendor share, analyst rankings, current events, trends, digest, opportunities, actions   |
| Domino                | 5+        | Company extract, URL verification, industry taxonomy, signal sweeps                            |

**Total: ~50+ distinct prompts across the system**

---

## M1 Question Generator (11 prompts)

| Prompt                            | File                  | Purpose                                       | Output                                                                                     | Doc |
| --------------------------------- | --------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------ | --- |
| `LINKEDIN_CLEANUP_PROMPT`         | QuestionGenerator.jsx | Strip noise from raw LinkedIn paste           | Clean JSON profile <2000 chars                                                             | 02  |
| `PERSONA_RESEARCH_PROMPT`         | QuestionGenerator.jsx | Deep psyche profile + pain + readiness        | psycheProfile, painPoints[], priorities[], clmReadiness 1-10, personalizedQuestionAngles[] | 02  |
| `FIND_SIMILAR_PROMPT`             | QuestionGenerator.jsx | Find 8-10 lookalike decision makers           | suggestions[] with name, title, company, LinkedIn URL, confidence                          | 02  |
| `QUESTION_GEN_SYSTEM`             | QuestionGenerator.jsx | Generate 15-25 buyer-intent questions         | companyIntel + questions[] tagged by persona/stage/cluster/lifecycle                       | 02  |
| `buildPersonaQuestionPrompt`      | QuestionGenerator.jsx | Per-persona question generation               | Same as above, single-persona focus                                                        | 02  |
| `PAIN_TO_QUESTIONS_PROMPT`        | QuestionGenerator.jsx | Convert Yin-Matrix pain points to questions   | Question array tied to pain category                                                       | 02  |
| `CSV_MAPPING_PROMPT`              | QuestionGenerator.jsx | AI fallback for CSV column → field mapping    | column-to-field map                                                                        | 02  |
| Cluster recalibration prompt      | QuestionGenerator.jsx | Re-bucket questions into clusters             | qid → cluster map                                                                          | 02  |
| Enrichment classification prompt  | QuestionGenerator.jsx | Classify intentType, personaFit, etc.         | Enrichment metadata per question                                                           | 02  |
| `AI_PROMPT_TEMPLATE` (manual add) | QuestionGenerator.jsx | UI helper for user-pasted question            | Single question structured                                                                 | 02  |
| `BUCKET_DETECTION_PROMPT`         | QuestionGenerator.jsx | Match scan results to Yin-Matrix tech buckets | bucket assignments per question                                                            | 02  |

---

## M2 Perception Monitor (6 prompts)

All in `src/manualScanPrompts.js`.

| Prompt                     | Purpose                                              | Key instructions                                                      | Output format                                                                                                                                 | Doc |
| -------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| `generatePrompt`           | Main scan prompt for manual paste mode               | "FRESH SESSION", "MANDATORY WEB SEARCH", "20-50% mention rate target" | `=== Q01 ===` blocks with FULL_RESPONSE, SIRION_MENTIONED, SIRION_POSITION, SENTIMENT, LIFECYCLE_STAGE, VENDORS_RANKED, SOURCES, CONTENT_GAPS | 03  |
| `buildBatchPrompt`         | Zero-context batch prompt (no company name anywhere) | Pure unbiased perception                                              | Same blocks, simpler (no LIFECYCLE_STAGE)                                                                                                     | 03  |
| `generateIndividualPrompt` | Re-scan one question for one LLM                     | Same format, single qid                                               | Same                                                                                                                                          | 03  |
| `normalizeWithAI`          | Recovery prompt — restructure messy pasted text      | Sent to Claude API to reformat                                        | Parser-compatible `=== Q01 ===` blocks                                                                                                        | 03  |
| `repairWithAI`             | Repair partial/broken pastes                         | Patches missing fields                                                | Field updates only                                                                                                                            | 03  |
| `scanContentUrl`           | Verify Sirion presence on a specific URL             | Used by M3 to back-check                                              | mentioned/notMentioned + evidence snippet                                                                                                     | 03  |

**Per-AI variants (`AI_NOTES`):**

- Claude: web_search tool optional
- Gemini: native grounding
- ChatGPT: enable browsing
- Grok: realtime mode
- Perplexity: native search

---

## M3 Authority Ring (0 prompts)

M3 is **pure reference data**. Domain verification is done via Boolean Google searches like `"sirion" site:hbr.org` (manual, not automated). M3 does not call any LLM.

---

## M4 Buying Stage Guide (4 prompts)

All in `src/BuyingStageGuide.jsx`.

| Prompt                    | Purpose                                                     | Output                                                                                                                                                                                                              | Doc |
| ------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| `LINKEDIN_CLEANUP_PROMPT` | Same as M1's — strip LinkedIn noise                         | Clean JSON profile                                                                                                                                                                                                  | 05  |
| `ANALYSIS_PROMPT`         | Deep sales intelligence on one decision maker               | 6-dimension JSON: tech_stack, hiring_patterns, digital_footprint, competitor_usage, decision_maker_signals, plus stage_scores + readiness_score 1-10 + outreach_hook + recommended_actions[4-5] + risk_factors[3-4] | 05  |
| `VERIFICATION_PROMPT`     | Fact-check the analysis for stale data                      | corrections[] with severity, original_claim, corrected_claim, evidence                                                                                                                                              | 05  |
| `OUTREACH_PROMPT`         | Generate outreach plan with waste metrics + lifecycle stage | Outreach plan JSON                                                                                                                                                                                                  | 05  |

**Strict rules:**

- Signals: 4-5 per dimension, 3-7 words tag-style
- Outreach hook: max 3 sentences
- Recommended actions: 4-5, max 15 words, start with verb
- Risk factors: 3-4, max 15 words

---

## M5 CLM Advisor (0 prompts)

M5 is **deterministic** — uses `calcScores()` against 15 hard-coded vendors with weighted-base + capped-context-adjustment formula. No LLM calls.

---

## M6 Content Strategy (10+ prompts)

### Legacy M6 — `src/contentPrompts.js`

| Prompt                        | Purpose                                                | Special rules                                                                      | Doc |
| ----------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------------------------- | --- |
| `buildTopicPrompt`            | Generate 5-10 editorial topics closing perception gaps | NEVER mention vendors, pure editorial, persona/stage/lifecycle attribution         | 07  |
| `buildTopicFromGapsPrompt`    | Generate topics directly from M2 contentGaps[]         | Auto-link to gap IDs                                                               | 07  |
| `buildJournalistPackPrompt`   | Pitch templates + publication list per topic           | 3-5 pitch variants, M3 domain integration, timeline + difficulty                   | 07  |
| `buildArticlePrompt`          | Generate 2,000-3,500 word publication-ready article    | No vendor mentions, citation rules, perception-shift block, banned/preferred vocab | 07  |
| `buildHumanizePrompt`         | Refine AI-generated text for less detection            | 6 anti-AI-detection constraints                                                    | 07  |
| `buildFormatOwnTopicsPrompt`  | Convert user-pasted Markdown topics to JSON            | Schema match                                                                       | 07  |
| `buildFormatOwnArticlePrompt` | Convert user-pasted article to JSON                    | Schema match                                                                       | 07  |

### M6v2 — `src/m6v2/promptAssembly.js`, `generateTopics.js`, `enrichGap.js`, `extractRules.js`

| Prompt                                     | Purpose                                    | Doc |
| ------------------------------------------ | ------------------------------------------ | --- |
| `rewrite-with-feedback`                    | AI revision based on user feedback         | 07  |
| `generate-article-from-topic`              | One-shot article generation in V2 workflow | 07  |
| `suggest-topics-from-gaps`                 | Topic suggestions from M2 gaps             | 07  |
| `generateTopics` (FAQ + narrative formats) | Format-specific topic gen                  | 07  |
| `enrichGap`                                | 2-4 sentence description of an M2 gap      | 07  |
| `extractRules`                             | Extract style rules from sample articles   | 07  |

---

## M7 Link Strategy (3 prompts)

In `src/m7v2/`.

| Prompt                    | Purpose                                                                     | Provider cascade                                    | Doc |
| ------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------- | --- |
| `enrichOneBlog`           | Enrich a single blog with niche, audience fit, est time-to-index, sirionFit | Gemini → Perplexity → Grok → Claude                 | 08  |
| `matchArticleToBlogs`     | Match an article to top placement candidates                                | 4-priority weights + hard constraints + JSON schema | 08  |
| `parseFreeTextWithGemini` | CSV import fallback — parse free-text blog list                             | Same cascade                                        | 08  |

**Note:** Firecrawl is NOT integrated in M7 (despite docs sometimes saying so). All enrichment uses native AI provider web search.

---

## Company Intelligence V1 (2 prompts)

In `src/CompanyIntelligence.jsx`.

| Prompt                        | Purpose                       | Doc |
| ----------------------------- | ----------------------------- | --- |
| Manual Gemini paste prompt #1 | Generate AI position summary  | 09  |
| Manual Gemini paste prompt #2 | Generate market pulse summary | 09  |

Both are user-copies-to-clipboard then pastes Gemini response back. No API integration in V1.

---

## Company Intelligence V2 (12+ prompts)

### Lens 3 — Market Pulse (`src/intelV2/marketPulsePrompts.js`)

| Prompt                                              | Purpose                                     | Output                                                                               | Doc |
| --------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------ | --- |
| `NEWS_SYSTEM` + `buildNewsUser`                     | Find news in last N hours affecting CLM     | title, summary, source_url, category (Threat/Opportunity/Neutral), impact_score 1-10 | 10  |
| `VENDOR_SHARE_SYSTEM` + `VENDOR_SHARE_USER`         | CLM market share by vendor                  | vendor name, share_pct, year, yoy_change, confidence, source_url                     | 10  |
| `ANALYST_RANKINGS_SYSTEM` + `ANALYST_RANKINGS_USER` | Gartner Magic Quadrant, Forrester Wave, IDC | firm, rank (Leader/Strong Performer/Contender), report_url                           | 10  |
| `CURRENT_EVENTS_SYSTEM` + `CURRENT_EVENTS_USER`     | Recent events affecting market position     | event list with impact assessment                                                    | 10  |
| `TRENDS_SYSTEM` + `buildTrendsUser`                 | Market trend signals                        | trend list with direction + magnitude                                                | 10  |
| `NEWS_SYSTEM_GEMINI` + `buildAINewsUser`            | Gemini-specific AI news                     | News list filtered for AI/automation                                                 | 10  |
| `DIGEST_SYSTEM` + `buildDigestUser`                 | Synthesize all news into a single digest    | One-page summary with action items                                                   | 10  |

### Lens 4 — Opportunities (`src/intelV2/opportunitiesPrompts.js`)

| Prompt                        | Purpose                                    | Doc |
| ----------------------------- | ------------------------------------------ | --- |
| `OPP_SYSTEM` + `buildOppUser` | 8-10 white-space positioning opportunities | 10  |

Output: title, type (theme_gap/question_gap/persona_gap/content_gap), description, evidence, demand, competitor_strength, recommended_play, effort_hours, opportunity_score, monthly_mentions_gained, suggested_placement.

### Lens 5 — Actions (`src/intelV2/actionsPrompts.js`)

| Prompt                                | Purpose                        | Doc |
| ------------------------------------- | ------------------------------ | --- |
| `ACTIONS_SYSTEM` + `buildActionsUser` | Prioritized weekly action list | 10  |

Output: tier (critical/watch/opportunity), title, rationale, recommended_play, effort, owner, action_score, target_channel.

**Score formula:** `impact × 0.5 + urgency × 0.3 + ease × 0.2`
**Tiers:** critical (score ≥ 8), watch, opportunity. Max 8 actions total.
**Channels:** internal_blog / external_blog / press_release / analyst_briefing / social / internal_only.

---

## Domino Sub-Module (5+ prompts)

### Company Prompts (`src/intelV2/domino/companyPrompts.js`)

| Prompt                                | Purpose                                                | Doc |
| ------------------------------------- | ------------------------------------------------------ | --- |
| `EXTRACT_SYSTEM` + `buildExtractUser` | Extract customers from vendor case-study page markdown | 11  |
| `verifyCompanyUrls`                   | Verify customer URLs are correct                       | 11  |
| `reverifyCompanyDeep`                 | Deep re-verification with web search                   | 11  |
| `harvestCompaniesAcrossVendors`       | Run extraction across all 10 source vendors            | 11  |
| `buildCompanyBatchUser`               | Batch company analysis                                 | 11  |

`VENDOR_CUSTOMER_PAGES` — hardcoded list of case-study URLs for 10 vendors.

### Industry Prompts (`src/intelV2/domino/industryPrompts.js`)

| Prompt                               | Purpose                                   | Doc |
| ------------------------------------ | ----------------------------------------- | --- |
| Industry SYSTEM + buildUser          | Fetch industry taxonomy                   | 11  |
| `verifyProfileUrls`                  | Verify industry profile URLs              | 11  |
| `reverifyProfileDeep`                | Deep re-verification                      | 11  |
| `SYS_INDUSTRY` + `buildIndustryUser` | Industry analysis                         | 11  |
| `fetchIndustryTaxonomy`              | Get DEFAULT_INDUSTRIES with deeper fields | 11  |

### Signal Prompts (`src/intelV2/domino/signalPrompts.js`)

| Prompt                   | Purpose                          | Doc |
| ------------------------ | -------------------------------- | --- |
| `sweepSignalsByIndustry` | Find buying signals per industry | 11  |
| `sweepSignalsByCompany`  | Find buying signals per company  | 11  |

`SIGNAL_TYPES` (8 types): hiring, regulation, M&A, leadership-change, tech-purchase, partnership, funding, expansion.

---

## Provider Routing

All LLM prompts go through `src/claudeApi.js` which routes to the Cloudflare Worker (`xtrusio-ai.thedevimapro.workers.dev`).

| Function         | Default model    | Timeout | Use case                              |
| ---------------- | ---------------- | ------- | ------------------------------------- |
| `callClaudeFast` | Claude Haiku     | 60s     | Classification, JSON extraction       |
| `callClaude`     | Claude Sonnet 4  | 120s    | Full research with web search         |
| `callClaudeChat` | Claude Sonnet 4  | 60s     | Multi-turn raw text                   |
| `callGemini`     | Gemini 2.5 Flash | 60s     | Web grounding, classification         |
| `callOpenAI`     | GPT-4o           | 60s     | General purpose                       |
| `callGrok`       | Grok 4 Latest    | 60s     | Realtime info                         |
| `callPerplexity` | Sonar            | 60s     | Citation-heavy answers                |
| `callFirecrawl`  | N/A              | 60s     | Web scraping with main-content filter |

JSON parsing uses 4 strategies: direct parse → markdown fence strip → strategy-stacked fallback → mid-response truncation repair.

---

## Common Output Patterns

| Pattern                             | Used by              | Example                                                                                                              |
| ----------------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `=== Q01 ===` blocks                | M2 manual scan       | Multi-question structured output                                                                                     |
| `FULL_RESPONSE_START / END` markers | M2                   | Wraps freeform LLM answer                                                                                            |
| JSON-only response                  | M1, M4, M6, Intel V2 | Single object or array                                                                                               |
| Markdown topic blocks               | M6 buildTopicPrompt  | One block per topic with frontmatter-style fields                                                                    |
| Source URLs with type tags          | M2, Intel V2         | url, type (vendor_page/review_site/analyst/comparison_blog/legal_tech_roundup/directory/news/category_page), snippet |
| Sentiment normalization             | M2, Intel V2         | positive / neutral / negative / absent                                                                               |
| Lifecycle stage normalization       | M2, M4, Intel V2     | pre-signature / post-signature / full-stack / not_mentioned                                                          |

---

## Anti-Hallucination Patterns Across The System

| Pattern                                                       | Where used             |
| ------------------------------------------------------------- | ---------------------- |
| Mention cross-verification (claim YES → search response text) | M2                     |
| Source URL allowlist/rejectlist                               | Intel V2 news          |
| Sirion.ai existing content verification                       | Intel V2 opportunities |
| 2-3 max search budget per verification                        | M4 VERIFICATION_PROMPT |
| "If unsure, leave it out" instruction                         | M2 generatePrompt      |
| Source diversity required                                     | Intel V2 vendor share  |

---

For verbatim text of any prompt, jump to the doc cited in the rightmost column of each table.
