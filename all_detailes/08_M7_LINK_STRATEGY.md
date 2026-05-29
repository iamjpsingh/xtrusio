# Module 7 — Link Strategy

This module also exists in **two coexisting versions**:

| Version         | Entry file                                                                                                                                                                     | Pipeline slot                                               | Purpose                                                                                                                                                                    |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **M7 (legacy)** | `src/LinkStrategy.jsx` (~430 lines) plus `src/modules/linkStrategy/panels/AwaitingPlacementPanel.jsx` and the matcher in `src/modules/linkStrategy/lib/matchArticleToBlogs.js` | `pipeline.m6.transfers` (read-only); writes none of its own | Pulls article pipeline from M6 (legacy) and renders a flat dashboard plus a "Verification Protocol" reminder. The Awaiting Placement panel inside it bridges to M6v2 → M7. |
| **M7v2**        | `src/modules/linkStrategyV2/index.jsx` plus everything under that folder                                                                                                       | `pipeline.m7v2`                                             | Full kanban: domain catalog (54 blogs) + AI matcher + per-article candidate list + 3-month calendar with budget bars. Active build path.                                   |

Both versions reach the user via the global app shell (`src/App.jsx`), which routes module IDs `m7` and `m7v2`.

---

## 1. What M7 Does (Backlink Placement Planning)

The module's job is to take **approved articles** and decide which **third-party blogs** should publish each one, with explicit budget caps. The end goal is to convert content output into measurable AI-perception shift via cited backlinks.

In words used by the file headers:

- "Approved articles get matched to guest-posting domains. Click an article to see Gemini's top 3 picks with rationale." (M7v2)
- "Perception Gap → Article → Publish → Verify" (M7 legacy header)

---

## 2. Legacy M7 Workflow

`src/LinkStrategy.jsx` is largely a read-only dashboard:

### Sections (top → bottom)

1. **Header** — module label + tagline + sentence summary of pipeline counts (`X articles in pipeline. Y ready, Z published.`).
2. **Awaiting Placement panel** (M6v2 → M7 bridge) — `AwaitingPlacementPanel.jsx` from `src/modules/linkStrategy/panels/`. This is the only mutable surface. It fetches client-approved articles from `pipeline.m6v2.articles`, runs a Gemini-powered match against the 54-blog catalog (`src/modules/linkStrategy/data/blogCatalog.json`), and shows top 3-5 fit sites per article with rationale.
3. **Lifecycle Bias card** — pulls `pipeline.m2.scanResults` through `computeReportMetrics()` and shows the Pre-Sig / Post-Sig / Full-Stack percentages of AI mentions. If post-sig dominates, it prints a red warning: "Post-signature bias detected. {X}% of AI responses frame {company} in post-signature context. Content strategy should prioritize pre-signature articles."
4. **What We're Targeting card** — narrative + counters (Articles, Pre-Sig, Full-Stack, Published).
5. **Perception Gaps from M2 Scans card-grid** — shows up to 8 of `pipeline.m2.contentGaps` with lifecycle badges, priority scores, and stage chips. "+ N more gaps" footer.
6. **Article Pipeline list** — every topic from `pipeline.m6.topics` rendered as an expandable row with status, lifecycle, persona, score, and a `✓ Topic → ✓/○ JP → ✓/○ Article` mini progress indicator. Tag filter at top.
7. **Verification Protocol** — 4-step grid (Baseline Scan → Publish Articles → Re-Scan → Measure Shift) with hardcoded copy explaining how to prove ROI.
8. **Strategy Rules** — 6 hardcoded bullets:
   - "Every link leads with pre-sig or full-stack language"
   - "Zero links reinforce post-signature narrative"
   - "Anchor text always includes lifecycle positioning"
   - "Each link traces to an M2 perception gap or M6 content topic"
   - "2-3 pre-sig + 2-3 full-stack per month (balanced mix)"
   - "Re-scan benchmark queries after each batch to measure shift"

### Status badge config

```
draft, planned        → gray
pack-ready            → yellow
article-ready         → orange
transferred           → cyan
published, live       → green
```

### Lifecycle badge mapping

- `lifecycle.includes("pre")` → green "PRE-SIG"
- `lifecycle.includes("full")` → purple "FULL-STACK"
- otherwise → orange "POST-SIG"

### Writes

**None.** Legacy M7 only reads from `pipeline.m2`, `pipeline.m6`, and (via the embedded panel) `pipeline.m6v2`. It does not stamp any state of its own.

### Awaiting Placement panel logic

- Pulls all articles with status `approved` from `pipeline.m6v2.articles`.
- For each, calls the matcher in `src/modules/linkStrategy/lib/matchArticleToBlogs.js` against the 54-blog catalog.
- Renders a row per article: title, byline, word count, then a horizontal scroll of top blog candidates with score, rationale, costUsd. A "Mark as transferred to M7v2" button hands off the assignment to the V2 store.

---

## 3. M7v2 Workflow (Kanban + Domain Catalog + Calendar)

`src/modules/linkStrategyV2/index.jsx` stacks three sections vertically:

### Section A — `BlogGallery` (`panels/BlogGallery.jsx`)

- A filterable card grid showing all 54 catalog domains plus any `addedBlogs` overrides.
- Per-card metadata: domain, URL, DR, DA, traffic, country, priceUsd, country flag.
- AI enrichment badges: niche, audience fit, AI citation strength (HIGH/MED/LOW), Sirion fit (GOOD/OKAY/NOT) with rationale.
- "Re-evaluate fit" button wipes the entire enrichment cache (`store.clearAllEnrichment()`) and triggers a fresh batch enrichment pass on next gallery visit.
- Filtering: by sirionFit verdict, AI strength, country, DA range, niche. Search by domain.
- Summary charts at the top (DR distribution, country mix, fit distribution).
- Admin can add a blog manually (`AddBlogModal`) or bulk-upload via `ImportBlogsModal` (CSV or free-text + Gemini parser).
- Per-blog notes (≤1000 chars) and tags (≤40 chars each, max one per tag string) editable in-place. Stored in `pipeline.m7v2.catalogOverrides.notes / .tags`.
- Soft-remove: clicking remove on a seed-catalog domain adds it to `removedDomains[]`; manually-added blogs are removed completely.

### Section B — `ArticlesSection` (`panels/ArticlesSection.jsx`)

- Pulls approved articles from `pipeline.m6v2.articles`.
- For each article, renders an `ArticleTreeCard` showing the article title and a 3-fork tree of its top 3 candidate blogs.
- "Re-match" button per article re-runs `matchArticleToBlogs()` (Gemini → Perplexity → Grok → Claude cascade).
- Clicking a candidate sets `assignment.selectedDomain`. The selection drives budget and calendar.
- Out-of-budget standout (score ≥ 85) shown as a separate "Override" pill below the in-budget candidates.

### Section C — `CalendarGrid` (`panels/CalendarGrid.jsx`)

- 3-month plan grid (`monthsAhead(3)` from `budgetCalc.js`).
- Each month tile renders one `MonthSlot.jsx` per slot type:
  - 1× **High-DA slot** ($250 cap, DA ≥ 60)
  - 5× **Mid-DA slots** ($200 each, DA 40-59)
- Total monthly cap: $800.
- Drag an article into a slot → `fillSlot(plan, tier, articleId)` returns a new plan; saved via `store.upsertMonthPlan(plan)`.
- Live budget bar shows `budgetSpent / budgetCap` with red flash when over.
- Removing an article from a slot calls `removeSlot(plan, articleId)`.

### Admin price toggle

At the top of the module shell, an Eye/EyeOff button toggles `showPrices`. Hidden by default for client portal users (`IS_CLIENT_PORTAL` build flag OR session role `client_portal`). Toggle propagates to all 3 panels.

---

## 4. Prompts in M7

### Legacy M7 (the page itself)

**No prompts.** The page reads pipeline data only.

### Awaiting Placement matcher (`matchArticleToBlogs.js` in `src/modules/linkStrategy/lib/`)

This file exists and is referenced by the legacy panel. It mirrors the V2 matcher (see §4.M7v2) — same Gemini-first prompt, same JSON shape. (Not re-quoted here to avoid duplication; the V2 prompt is the canonical version.)

### M7v2 prompts

#### Catalog enrichment — `enrichOneBlog(blog)` in `lib/enrichCatalog.js`

Provider cascade Gemini (with `google_search` grounding) → Perplexity (sonar) → Grok (live search) → Claude (web_search).

Verbatim system prompt:

> You are a B2B content distribution analyst evaluating guest-posting websites for Sirion (CLM software vendor — sells AI-powered contract lifecycle management to enterprise legal, procurement, and IT decision-makers).
>
> For each candidate domain, USE WEB SEARCH to read the site, then return the following fields:
>
> niche — 2-4 words ('SaaS marketing', 'legal industry news', 'tech publication')
> audienceFit — 4-8 words describing typical readers
> aiCitationStrength — HIGH | MED | LOW
> estTimeToIndex — '3-7 days' / '7-14 days' / '14-30 days'
> estTimeToAiCite — typical lag from publication to AI tools citing it
> qualityNotes — 1 sentence editorial read
> sirionFit — GOOD | OKAY | NOT
> sirionFitReason — 1 sentence (≤25 words) explaining the verdict
>
> ── SIRION FIT — BE GENEROUS. DEFAULT TO OKAY. ──────────────────
>
> Sirion's content (AI in contracts, B2B SaaS, enterprise legal/procurement) can land on a wide range of sites. The catalog is curated, so most domains are workable. Reserve NOT only for domains that clearly cannot host a B2B/tech thought-leadership piece.
>
> GOOD — directly relevant: legal industry publications (leaders-in-law, lawyersclubindia, usattorneys), enterprise tech / SaaS / AI publications (TechCrunch, SiliconReview, TechBullion, feedough, contentstudio, dataconomy), business + executive press (HBR, Forbes, BBN Times, European Business Review), procurement / supply chain.
>
> OKAY — the DEFAULT for everything else: any tech publication, any business publication, any general SaaS / digital / startup site, any enterprise software adjacent. If a tech-savvy decision-maker MIGHT read it occasionally, it's OKAY. Don't overthink.
> Examples: technology.org, e-architect, mostlyblogging, openpr, ranktracker, postunreel, virlpep, slidesasser, netnewsledger, digitalconnectmag, etc.
>
> NOT — STRICT NO-NO ONLY. The audience is so off-niche that placing CLM content there would be embarrassing. Use this category sparingly:
> • General consumer news portals targeting a non-business audience (Israel National News, Daily Trust)
> • Local-interest / regional non-English audience (eyeofriyadh, country-specific consumer news)
> • Hard off-vertical: sports (topendsports, femalecricket, spoiltertv), food (newyorkstreetfood), entertainment-only, parenting, fitness
> • Crypto-only, gaming-only, or single-vertical with no enterprise crossover
>
> When in doubt → OKAY, not NOT. We'd rather have too many OKAYs than reject a workable domain.
>
> sirionFitReason should be specific and concrete: e.g. 'Tech audience overlaps with enterprise buyers; CLM-AI frame fits.' OR 'General national news portal — audience too consumer-focused for B2B CLM content.'

User prompt is per-domain:

> ## DOMAIN: ${blog.domain}
>
> URL: ${blog.url}
> DR: ${blog.dr ?? "?"} · DA: ${blog.da ?? "?"} · Traffic: ${blog.traffic ?? "?"}
> Country: ${blog.country ?? "Unknown"}
>
> Look up this domain. Read its content. Return strict JSON, no Markdown fences:
>
> ```
> {
>   "niche": "...",
>   "audienceFit": "...",
>   "aiCitationStrength": "HIGH" | "MED" | "LOW",
>   "estTimeToIndex": "...",
>   "estTimeToAiCite": "...",
>   "qualityNotes": "...",
>   "sirionFit": "GOOD" | "OKAY" | "NOT",
>   "sirionFitReason": "..."
> }
> ```

The shaper is permissive — partial responses are kept with sensible defaults (`aiCitationStrength` → "MED", `sirionFit` → "OKAY", `estTimeToIndex` → "7-14 days"). Auth errors propagate; other errors fall through to the next provider.

Batch enrichment (`enrichBlogsLazy`) runs sequentially with a 600ms gentle pace and accepts an `AbortSignal` so an unmount cancels rather than burning quota.

#### Article-to-blog matcher — `matchArticleToBlogs(...)` in `lib/matcher.js`

Same Gemini → Perplexity → Grok → Claude cascade.

Verbatim system prompt:

> You are a B2B content distribution strategist matching articles to guest-posting domains.
>
> PRIORITIES (in order, weights):
>
> 1. Topic + audience fit (60%)
> 2. AI citation strength tag (20%) — strongly favor HIGH-tagged domains
> 3. Tier match — DR/DA fits the slot type (10%)
> 4. Dedup penalty — avoid [USED] domains UNLESS they are HIGH-tagged AND topic fit > 85 (10%)
>
> HARD CONSTRAINTS:
> • Slot type needed: ${slotTypeNeeded}.
>     high-da picks must have DR >= 60 (or DA >= 60 if known)
>     mid-da picks should have DR 40-69
>   • Per-pick cost cap: $${slotCap} (slot cap)
> • Month budget remaining: $${budgetRemaining}. Selected pick must fit.
>
> OUTPUT BUDGET — be concise:
> • rationale: 1 sentence, max 25 words. State the key fit, no padding.
> • angleHook: 1 sentence, max 20 words. The specific angle, nothing else.
> • Do NOT repeat blog metadata (DR/DA/traffic) in rationale — those are visible to the user already.
> • Don't add fields that aren't in the schema.
>
> USE WEB SEARCH to verify each candidate's actual editorial focus before scoring.
> Return strict JSON, no Markdown fences. If fewer than 3 valid candidates exist,
> return what you have plus a 'warning' field.

User block (verbatim core):

> ## TARGET MONTH: ${targetMonth} | SLOT: ${slotTypeNeeded} | BUDGET REMAINING: $${budgetRemaining}
>
> ## ARTICLE
>
> Title: ${article.title || "(untitled)"}
> Track: ${article.track?.name || "—"} (${article.track?.tagline || "—"})
>
> ## ARTICLE BODY (truncated to 8000 chars)
>
> [body slice]
>
> ## CANDIDATE BLOGS (${catalog.length} total — pick top 3 within constraints)
>
> [blog lines: index, domain, [USED] flag if applicable, DR/DA/traffic/country/$/AI:strength/niche]
>
> ## TASK
>
> Pick the top 3 best-fit blogs for this article respecting the hard constraints above.
> For each: domain (exactly as listed), score 0-100,
> rationale (1 sentence, ≤25 words — name the fit, no padding),
> angleHook (1 sentence, ≤20 words — the specific angle to lead with).
>
> If a blog scores >=85 on topic fit but exceeds the slot cap, include it
> in 'outOfBudgetButRecommended' so the user can override.

Return JSON:

> ```
> {
>   "matches": [
>     { "domain": "...", "score": 87, "rationale": "...", "angleHook": "..." },
>     { "domain": "...", "score": 80, "rationale": "...", "angleHook": "..." },
>     { "domain": "...", "score": 72, "rationale": "...", "angleHook": "..." }
>   ],
>   "outOfBudgetButRecommended": null | { "domain": "...", "score": 88, "rationale": "...", "angleHook": "..." },
>   "warning": null | "string explaining if fewer than 3 found"
> }
> ```

`shapeMatchResponse(result, ctx)`:

- Drops hallucinated domains (any `domain` not in the catalog).
- Computes `withinBudget = cost <= slotCap && cost <= budgetRemaining`.
- Top 3 = within-budget, sorted by score desc.
- Out-of-budget standout = the matcher's explicit `outOfBudgetButRecommended` OR the highest-scoring (≥ 85) match that didn't fit.
- Warning auto-fills "only N within-budget candidate(s) found" if fewer than 3.

#### CSV / free-text bulk import — `csvImport.js`

Two paths:

- `parseCsvText()` — direct CSV parse with header detection. Recognises `domain | url | dr | da | traffic | country | priceUsd | price | niche | tags`.
- `parseFreeTextWithGemini()` — Gemini-first cascade (Gemini → Perplexity → Grok → Claude) for messy / unstructured pastes.

Verbatim AI system prompt:

> Extract a list of guest-posting domains from the user's pasted text.
> The text may be CSV, TSV, a column from Excel, an email body, or a plain list.
> For each row return: domain (required, lowercase, no protocol/path),
> url (default to https://<domain>), dr (number or null), da (number or null),
> traffic (string like '21.8K' or null), country (string or null),
> priceUsd (number or null), niche (string or null), tags (array of strings).
> Skip blank rows / headers / commentary. Return strict JSON only — no Markdown fences.

Returns `{ rows: [{ domain, url, dr, da, traffic, country, priceUsd, niche, tags }], warning }`.

---

## 5. Article Status Flow

The brief asks about "draft → pack-ready → article-ready → transferred → published → live". Mapping by version:

### Legacy M7 view of the flow

The M7 page reads from `pipeline.m6.topics[].status` so the visible statuses are the M6 legacy ones: **draft → pack-ready → article-ready → transferred → published → live**. The transitions are driven by M6 (legacy), not by M7. M7 only displays them.

### M7v2 view of the flow

M7v2 reads from `pipeline.m6v2.articles` filtered to `status: "approved"`. The 8 M6v2 statuses (`imported-pending → imported-rejected | needs-revision → revising → ready-for-client → in-review → approved → published`) are documented in detail in `07_M6_CONTENT_STRATEGY.md` §8. M7v2 only consumes the `approved` and `published` states.

### Per-assignment workflow inside M7v2

- `status: "pending-selection"` — matcher just produced candidates, user hasn't picked one.
- `status: "selected"` — user clicked a candidate; `selectedDomain` set; ready to slot into a month plan.
- `status: "scheduled"` — placed in a month slot.
- `status: "outreach"` — admin marked outreach started (manual).
- `status: "live"` — publisher confirmed live URL.

(These are the implicit values; the actual store accepts any string in `assignment.status` — there's no enum enforced in code.)

---

## 6. Domain Catalog Structure

`src/modules/linkStrategy/data/blogCatalog.json`:

| Field        | Type          | Notes                                                                                |
| ------------ | ------------- | ------------------------------------------------------------------------------------ |
| `source`     | string        | Provenance, e.g. "AI_Guest_Posting_Websites_Consolidated (2).xlsx — sheet: websites" |
| `importedAt` | ISO timestamp | When the catalog was imported                                                        |
| `count`      | int           | 54                                                                                   |
| `blogs[]`    | array         | One per domain                                                                       |

Each blog object:

| Field             | Type                      | Notes                                          |
| ----------------- | ------------------------- | ---------------------------------------------- |
| `id`              | string                    | Same as `domain` (lowercased)                  |
| `domain`          | string                    | e.g. `1873magazine.com`                        |
| `url`             | string                    | Full URL                                       |
| `dr`              | int \| null               | Domain Rating (Ahrefs-style)                   |
| `da`              | int \| null               | Domain Authority (Moz). Often null in catalog. |
| `traffic`         | string \| null            | e.g. `"21.8K"`, `"199.5K"`                     |
| `country`         | string \| null            | e.g. `"USA"`, `"Unknown"`                      |
| `priceUsd`        | int \| null               | Per-placement cost (e.g. 130, 240, 250)        |
| `sirionFit`       | "GOOD" \| "OKAY" \| "NOT" | Pre-seeded verdict (overridable by enrichment) |
| `sirionFitReason` | string                    | Pre-seeded rationale                           |

Mostly internal metric coverage (DR + traffic + country + priceUsd). DA is usually `null` because the source spreadsheet only had DR. Names are publishing platforms (e.g. `bbntimes.com`, `europeanbusinessreview.com`, `thesiliconreview.com`).

The brief mentions "internal + external domains" — there is no internal/external split in the catalog. All 54 are external publishing destinations. There is also no `category`, `targetPersonas`, `expectedPlacementDate`, or `difficulty` field in the seed JSON — those are added at enrichment time (see §11).

---

## 7. Per-Domain Metadata (After Enrichment)

`pipeline.m7v2.catalogEnrichment[domain]`:

| Field                 | Type                      | Notes                                                                           |
| --------------------- | ------------------------- | ------------------------------------------------------------------------------- |
| `domain`              | string                    | Echoed                                                                          |
| `niche`               | string                    | 2-4 words ("SaaS marketing", "legal industry news", "tech publication")         |
| `audienceFit`         | string                    | 4-8 words ("CIOs, CFOs, enterprise legal teams")                                |
| `aiCitationStrength`  | "HIGH" \| "MED" \| "LOW"  | Defaults to "MED"                                                               |
| `estTimeToIndex`      | string                    | "3-7 days" / "7-14 days" / "14-30 days"                                         |
| `estTimeToAiCite`     | string                    | Lag from publication to AI tools citing                                         |
| `qualityNotes`        | string                    | 1-sentence editorial read                                                       |
| `sirionFit`           | "GOOD" \| "OKAY" \| "NOT" | Defaults to "OKAY"                                                              |
| `sirionFitReason`     | string                    | ≤200 chars                                                                      |
| `measuredCitationLag` | null                      | Reserved for future measured value                                              |
| `enrichedAt`          | ISO timestamp             |                                                                                 |
| `source`              | string                    | "gemini-estimate" / "perplexity-estimate" / "grok-estimate" / "claude-estimate" |

The brief mentions DA, category, target personas, expected placement date, difficulty as per-domain metadata. Of these:

- **DA** lives in the seed catalog (often `null`).
- **Category** maps to `niche`.
- **Target personas** maps to `audienceFit`.
- **Expected placement date** is implicit in `estTimeToIndex` + `estTimeToAiCite`.
- **Cost** lives in the seed as `priceUsd`.
- **Difficulty** is not modelled as a discrete field. The closest signal is `sirionFit + aiCitationStrength + DR` viewed together.

---

## 8. Firecrawl Integration

**Not implemented.** The codebase does not import or invoke any Firecrawl client. Domain enrichment is performed by the four AI providers (Gemini → Perplexity → Grok → Claude) through the existing Cloudflare Worker proxy in `src/claudeApi.js`. The web grounding is each provider's native tool (`google_search` for Gemini, native search for Perplexity, baked-in `live_search` for Grok, `web_search_20250305` for Claude).

If Firecrawl is on the roadmap, it would slot in either:

- As an additional provider tier above Gemini for HTML extraction, or
- As a one-shot "fetch + summarise" before any provider call.

Treat as a **future hook**.

---

## 9. Assignment Record Shape

`pipeline.m7v2.assignments[articleId]`:

| Field                       | Type                  | Notes                                                           |
| --------------------------- | --------------------- | --------------------------------------------------------------- |
| `articleId`                 | string                | Foreign key to `pipeline.m6v2.articles`                         |
| `targetMonth`               | "YYYY-MM" \| "auto"   | "auto" until placed in a slot                                   |
| `tier`                      | "high-da" \| "mid-da" | Slot type the matcher targeted                                  |
| `status`                    | string                | See §5                                                          |
| `matchedAt`                 | ISO timestamp         | When candidates were generated                                  |
| `candidates[]`              | array                 | Top 3 (or fewer) from matcher                                   |
| `outOfBudgetButRecommended` | object \| null        | Score ≥ 85 standout that didn't fit                             |
| `warning`                   | string \| null        | "only N within-budget candidates found" or matcher-supplied     |
| `selectedDomain`            | string \| null        | The candidate the user picked                                   |
| `lastTouchAt`               | ISO timestamp         | Implicit via `updatedAt` on the slice                           |
| `providerUsed`              | string                | "gemini" / "perplexity" / "grok" / "claude"                     |
| `fallback`                  | bool \| string        | False if Gemini succeeded; otherwise a chain of failure reasons |

Each candidate inside `candidates[]`:

| Field          | Type           | Notes                                                            |
| -------------- | -------------- | ---------------------------------------------------------------- |
| `domain`       | string         | From catalog                                                     |
| `url`          | string         | From catalog                                                     |
| `score`        | int (0-100)    | AI score                                                         |
| `rationale`    | string         | ≤25 words, the fit                                               |
| `angleHook`    | string         | ≤20 words, the lead angle                                        |
| `costUsd`      | int            | From catalog                                                     |
| `dr`           | int \| null    | From catalog                                                     |
| `da`           | int \| null    | From catalog                                                     |
| `traffic`      | string \| null | From catalog                                                     |
| `country`      | string \| null | From catalog                                                     |
| `withinBudget` | bool           | `costUsd <= slotCap && costUsd <= budgetRemaining` at match time |

---

## 10. Month Plan Shape

`pipeline.m7v2.monthPlans[yearMonth]` (yearMonth is "YYYY-MM" e.g. "2026-05"):

| Field           | Type       | Notes                                   |
| --------------- | ---------- | --------------------------------------- |
| `yearMonth`     | string     | Key, also stored on the record          |
| `budgetCap`     | int        | Default $800 (`MONTH_BUDGET_CAP_USD`)   |
| `slots.highDa`  | object     | `{ capUsd: 250, articleId: null }`      |
| `slots.midDa[]` | array of 5 | each `{ capUsd: 200, articleId: null }` |

Helper functions in `budgetCalc.js`:

- `emptyMonthPlan(yearMonth)` — fresh plan with all slots open.
- `openSlots(plan, "high-da" | "mid-da")` — count of empty slots.
- `fillSlot(plan, tier, articleId)` — returns new plan with first open slot filled.
- `removeSlot(plan, articleId)` — returns new plan with article cleared from any slot.
- `budgetSpent(plan, assignmentsByArticleId)` — sums `selectedDomain.costUsd` across all filled slots.
- `budgetRemaining(plan, ...)` — clamped to ≥ 0.
- `isOverBudget(plan, ...)` — bool.
- `currentYearMonth()` and `monthsAhead(n)` — date helpers.

The brief asks about `articles[]`, `domains[]`, `dates` fields. These don't exist as discrete arrays — articles are referenced by `articleId` inside slots, the chosen domain is read from each slot's article's assignment, and the only date concept is `yearMonth`.

---

## 11. Catalog Enrichment Record Shape

(Documented in §7.) Includes `niche`, `audienceFit`, `aiCitationStrength`, `estTimeToIndex`, `estTimeToAiCite`, `qualityNotes`, `sirionFit`, `sirionFitReason`, `enrichedAt`, `source`.

**No `faviconUrl` field** is stored — the gallery uses `https://www.google.com/s2/favicons?domain=...` directly in markup if it renders favicons at all.

**No `category`** as a discrete field — `niche` plays that role.

**`targetPersonas[]`** is not a normalised array — `audienceFit` is a free-form string.

---

## 12. Catalog Overrides

`pipeline.m7v2.catalogOverrides`:

| Field            | Shape                                                          | Purpose                                       |
| ---------------- | -------------------------------------------------------------- | --------------------------------------------- |
| `addedBlogs[]`   | Array of blog objects (same shape as catalog seed) + `addedAt` | Manually-added domains not in the 54-row seed |
| `notes`          | `{ [domain]: string }`                                         | Per-blog admin notes (≤1000 chars)            |
| `tags`           | `{ [domain]: string[] }`                                       | Per-blog tag chips (≤40 chars each, deduped)  |
| `removedDomains` | string[]                                                       | Soft-removed seed-catalog domains             |

`addBlog`, `removeBlog`, `setBlogNotes`, `setBlogTags` are the corresponding store actions in `useLSv2Store`. Adding a domain that was previously soft-removed automatically un-removes it.

---

## 13. Sample Articles Seeding

`src/modules/linkStrategyV2/data/sampleArticles.json` ships with two pre-canned sample articles ("Why CFOs Now Own Contract AI Risk", "Vendor Scorecards: How to Pick CLM in 2026") each with a fully-populated `assignment` object so a user with zero approved articles still sees the matching UI working end-to-end.

Each sample carries:

| Field                                   | Type         | Notes                                                                              |
| --------------------------------------- | ------------ | ---------------------------------------------------------------------------------- |
| `id`                                    | "sample-N"   |                                                                                    |
| `isSample`                              | true         | Flagged so they're never treated as real articles                                  |
| `title`, `byline`, `wordCount`, `track` | strings/ints |                                                                                    |
| `assignment`                            | object       | Pre-built with 3 candidates, `selectedDomain: null`, `status: "pending-selection"` |

The `samplesSeeded` boolean in `pipeline.m7v2.samplesSeeded` flips to `true` after `markSamplesSeeded()` runs, ensuring the seed only happens once per pipeline.

---

## 14. Reads from Other Modules

### Legacy M7

- `pipeline.m2.scanResults` — for lifecycle bias card (computed via `computeReportMetrics()`).
- `pipeline.m2.scores` — sentiment + visibility numbers.
- `pipeline.m2.contentGaps` — for the perception gap card-grid.
- `pipeline.m6.topics` / `pipeline.m6.journalistPacks` / `pipeline.m6.articles` / `pipeline.m6.tags` — full article pipeline.
- `pipeline.m6v2.articles` (via the embedded panel) — approved articles bridging into V2 matcher.
- `pipeline.meta.company` — used in copy.

### M7v2

- `pipeline.m6v2.articles` — only articles with `status: "approved"` (and `published` for read-only display).
- `pipeline.m3.prioritizedDomains` — **not directly read** in the V2 panels. Authority gap data flows into M6v2 topic generation, not into M7v2.
- `pipeline.m2.contentGaps` — **not directly read** in V2.

Despite the brief implying tight coupling to M2/M3, M7v2 treats articles as the unit of work and depends only on M6v2's article output.

---

## 15. Outputs to `pipeline.m7v2`

| Field               | Shape                                                           |
| ------------------- | --------------------------------------------------------------- |
| `assignments`       | `{ [articleId]: AssignmentRecord }`                             |
| `samples`           | sampleArticle[] (the two pre-canned demos when `samplesSeeded`) |
| `monthPlans`        | `{ [yearMonth]: MonthPlan }`                                    |
| `catalogEnrichment` | `{ [domain]: EnrichmentRecord }`                                |
| `catalogOverrides`  | `{ addedBlogs[], notes{}, tags{}, removedDomains[] }`           |
| `samplesSeeded`     | bool — flips true after the demo seed                           |
| `generationId`      | numeric (Date.now() per write)                                  |

Bulk writes (`upsertAssignments`, `upsertEnrichments`) merge multiple records in one slice mutation to avoid the React closure-trap bug documented in M6v2's store.

---

## 16. Firestore Collections

**No M7-specific Firestore collections.** Like M6, all writes route through the pipeline document, which the global persistenceManager mirrors to Firestore as part of the pipeline blob.

The legacy panel may indirectly depend on the same `blog_db` collection M6 uses (via `fetchBlogDb` in `src/blogDb.js`) when the Awaiting Placement panel needs richer per-blog data, but M7v2 itself loads the catalog from the bundled JSON seed.

---

## 17. Edge Cases

- **Firecrawl timeouts** — n/a (Firecrawl not integrated). Provider timeouts are 30s for enrichment, 180s for matching, 240s for revision.
- **Manual assignment burden** — Every approved article needs a human click to choose a candidate and a drag to land it in a slot. There is no "auto-assign best 6 articles to next month" button; a future "auto-pack month" function is an obvious extension.
- **Stale DA scores** — DA is fetched once at catalog import time and never refreshed. If a domain's authority drops, the matcher won't notice. The "Re-evaluate fit" button refreshes the AI enrichment but does NOT re-fetch DR/DA from the underlying spreadsheet.
- **Hallucinated domains** — `shapeMatchResponse()` filters out any candidate whose `domain` isn't in the catalog. If the AI invents `"sirion-perfect-fit-blog.com"`, it's silently dropped; if all 3 picks are hallucinated, `candidates.length = 0` and the warning fires.
- **Out-of-budget standouts** — Surfaced as a separate "Override" pill so the user knows there was a higher-scoring option above the slot cap. Picking it bypasses budget enforcement (the user is explicitly choosing to exceed the cap).
- **Provider chain timing** — A complete cascade can take up to 240s × 4 = 960s in the worst case (if all four providers time out). In practice Gemini succeeds 90%+ of the time per Gaurav's notes.
- **Auth error propagation** — Same pattern as M6v2: auth/access errors re-throw to trigger the global access-required banner instead of failing per-domain silently.
- **Aborted batch enrichment** — `enrichBlogsLazy` accepts an `AbortSignal`; an unmount cancels mid-batch instead of burning quota on orphan calls.
- **Closure-trap bug** — Documented in `useLSv2Store`; mitigated by `upsertAssignments` and `upsertEnrichments` bulk forms.
- **Mid-render pipeline writes** — Same risk as M6v2; the store doesn't write inside `useEffect` setState handlers.
- **DR vs DA mismatch** — The catalog has DR for nearly every row but DA for almost none. The matcher's hard constraint says "high-da picks must have DR >= 60 (or DA >= 60 if known)" — i.e. it accepts either. This is intentional given the data sparsity.
- **Soft-removed re-add** — Adding a domain that was previously soft-removed automatically un-removes it. No accidental double-state.
- **Sample articles drift** — The seeded samples carry hardcoded `costUsd` values (e.g. $250 high-DA cap exactly). If the cap constants change, the samples will look weird; treat the sample seed as a frozen demo dataset.
- **Tag length limit** — 40 chars per tag, deduped per domain. Longer tags get truncated silently.
- **Note length limit** — 1000 chars per blog note. Longer text gets truncated silently.
- **No undo on slot drag** — Dragging an article into a wrong slot requires manually removing it via `removeSlot`. No multi-step undo stack.
- **Client portal price hiding** — `IS_CLIENT_PORTAL` build flag (or session role) hides prices everywhere — gallery cards, candidate lists, calendar bars. Admins can toggle via the Eye/EyeOff button in the header.

Relevant file paths:

- `/home/user/sirion-perception-shift/src/LinkStrategy.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategy/panels/AwaitingPlacementPanel.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategy/lib/matchArticleToBlogs.js`
- `/home/user/sirion-perception-shift/src/modules/linkStrategy/data/blogCatalog.json`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/index.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/hooks/useLSv2Store.js`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/lib/budgetCalc.js`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/lib/csvImport.js`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/lib/enrichCatalog.js`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/lib/matcher.js`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/data/sampleArticles.json`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/BlogGallery.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/ArticlesSection.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/ArticleTreeCard.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/CalendarGrid.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/MonthSlot.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/AddBlogModal.jsx`
- `/home/user/sirion-perception-shift/src/modules/linkStrategyV2/panels/ImportBlogsModal.jsx`
