# Module 6 — Content Strategy

This module exists in **two coexisting versions** that share data slots in the pipeline:

| Version         | Entry file                                                                                                         | Pipeline slot   | Workflow style                                                                                                                                                                                    |
| --------------- | ------------------------------------------------------------------------------------------------------------------ | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **M6 (legacy)** | `src/ContentStrategy.jsx` (~2870 lines) plus `src/contentPrompts.js` (~1146 lines)                                 | `pipeline.m6`   | Manual copy-paste with Claude/Gemini. Three stages chained by clipboard.                                                                                                                          |
| **M6v2**        | `src/modules/contentStrategyV2/index.jsx` plus everything under that folder (`hooks/`, `lib/`, `panels/`, `data/`) | `pipeline.m6v2` | Campaign + tracks + AI-first article kanban. Calls AI providers directly through the Cloudflare Worker proxy with Gemini → Perplexity → Grok → Claude fallback. Has an admin/client portal split. |

Both versions persist via `usePipeline` / `updateModule` so localStorage + Firebase get the writes for free. M6v2 is the active build path; M6 stays parked because its prompts are carefully tuned and the user occasionally copies them out for ad-hoc Gemini/Claude sessions.

---

## 1. What M6 Does

The brief calls this a "3-stage content pipeline". For the legacy module, that's literally the stage labels: **Topics → Journalist Pack → Article**. For M6v2, it's reframed as **Perception Gaps → Topics → Articles → Client Review → Approved**, with article authoring done by the AI revision engine in-place.

The shared mission is to:

- Turn M1 questions and M2 perception gaps into high-quality editorial topics that read as journalist-pitched (never as marketing collateral).
- Produce a journalist pack and full article body for each topic.
- Keep the byline, vocabulary bans, citation rules, and lifecycle framing consistent so every piece pulls Sirion's narrative gravity from "post-signature specialist" toward "full-stack platform".
- Hand finished articles to M7 (Link Strategy) for placement on third-party domains.

---

## 2. M6 Legacy Workflow

`src/ContentStrategy.jsx` exposes 4 tabs, controlled by the `TABS` constant:

| Tab id            | Label           | Icon |
| ----------------- | --------------- | ---- |
| `topics`          | Topics          | 🎯   |
| `perception-gaps` | Perception Gaps | 🔍   |
| `pack`            | Journalist Pack | 📋   |
| `articles`        | Articles        | 📝   |

`STATUS_MAP` defines the topic status badges: `draft` (yellow), `pack-ready` (purple), `article-ready` (green), `transferred` (cyan).

A **tag filter strip** sits above the tabs. Users create tags (e.g. "April (6 Apr – 6 May)") with optional start/end dates; topics are tagged so a campaign can be scoped to a window. There's also an `Untagged` filter.

### Stage 1 — Topics

The user clicks "Generate Topic Prompt" → a modal asks for **mode**, **tag**, and **count (1–6)**. Three modes:

| Mode         | Source                   | Prompt builder                                         |
| ------------ | ------------------------ | ------------------------------------------------------ |
| `generate`   | M1 question bank         | `buildTopicPrompt(questions, company, count, opts)`    |
| `from-gaps`  | M2 content gaps          | `buildTopicFromGapsPrompt(gaps, company, count, opts)` |
| `format-own` | User's pasted raw topics | `buildFormatOwnTopicsPrompt(count)`                    |

The prompt is shown in a modal with a "Copy to Clipboard" button. The user pastes it into Claude/Gemini/ChatGPT externally, runs it, then comes back, clicks "Next: Paste AI Output", pastes the response, and `parseTopicsOutput()` parses it into structured topic objects which go into `pipeline.m6.topics`.

### Stage 2 — Journalist Pack

For any topic in `draft`, the user clicks "Generate Journalist Pack" → `buildJournalistPackPrompt(topic, company, questions, scanData, authorityData)` is shown → user pastes the AI response back → `parsePackOutput()` produces a `pack` object stored in `pipeline.m6.journalistPacks`. The topic flips to `pack-ready`.

### Stage 3 — Article

For any pack-ready topic, the user picks one of two modes:

| Mode         | Builder                                            | Use case                                              |
| ------------ | -------------------------------------------------- | ----------------------------------------------------- |
| Default      | `buildArticlePrompt(topic, pack, company, config)` | Generate article from scratch using the pack          |
| `format-own` | `buildFormatOwnArticlePrompt(topic)`               | User already has a draft — reformat it with citations |

The output gets parsed by `parseArticleOutput()` into an article object stored in `pipeline.m6.articles`. The topic moves to `article-ready`.

### Stage 4 — Humanize (post-article)

Optional follow-on. `buildHumanizePrompt(article)` wraps the article in an anti-AI-detection rewrite spec. Pasted back via the same modal pattern; the article body is overwritten and `humanized: true` is stamped.

### Transfer to Link Strategy

A "Transfer" action calls `handleTransferToLinks(topic)` which appends a record to `pipeline.m6.transfers` and flips the topic to `transferred`. M7 (legacy) reads from there.

### Manual Add Topic

A modal lets the user hand-author a topic with the same shape (headline, thesis, personas, publications, lifecycle, trigger, data hook, structure, score, status). It bypasses Stage 1.

### Perception Gaps Tab (the matcher surface)

This tab is a separate workflow that consumes `pipeline.m2.contentStrategyPayload` (pushed by M2's "Send to Content Strategy" button). It:

- Builds a venue index from M2 scan history (`buildVenueIndex` in `src/venueIndex.js`).
- Loads an optional Blog DB from Firestore (`src/blogDb.js`).
- Calls `rollupGapsByQuery()` to collapse raw gaps by `(qid, type)` across LLMs.
- For each rolled-up gap, the `GapRow` calls `recommendVenuesForGap()` to produce ranked venue recommendations.
- `generateArticleBrief()` produces a per-gap article brief that includes the selected venue.
- The brief and selection are persisted to `pipeline.m6.articleBriefs[gapId]` with `status: "new" | "draft" | "in-progress" | "done"`.

The Blog DB importer supports CSV/Excel template download, file upload, and JSON paste. It writes via `upsertBlogBatch` to a `blog_db` Firestore collection (handled in `src/blogDbImport.js`).

### Stats Strip

Five mini-tiles at the top of M6: Topics, Packs Ready, Articles Ready, Transferred, Avg Score.

---

## 3. M6v2 Workflow (Campaign + Tracks + AI-First)

M6v2 replaces the copy-paste loop with direct AI calls. It's the actively maintained surface.

### Campaigns

`src/modules/contentStrategyV2/data/campaigns.json` seeds **one campaign** today: `"sirion_perception_shift_2026"` — "Reposition from post-signature CLM specialist to full-stack platform". Each campaign carries:

- `id`, `clientId`, `name`, `subtitle`, `status`, `createdAt`
- `byline` ("Arpita Chakravorty"), `company` ("Sirion"), `sourceScans` (array of M2 scan IDs)
- `showTracks: false` — when false the per-track tabs are hidden and the campaign description block is shown instead.
- `segmentIds` — M1/M2 segment IDs whose gaps flow into this campaign. Empty = consume all.
- `description` — long-form campaign goal text.
- `monthlyPlacementBudget` — e.g. `{ high: { min: 1, daThreshold: 60, label: "DA 60+" }, mid: { min: 5, daRange: [40,59], label: "DA 40–59" } }`.
- `tracks[]` — perception objectives. The Sirion campaign has three: Full-Stack (increase, writeArticles), Pre-Signature (increase, writeArticles), Post-Signature (decrease, writeArticles=false → "track-only").

### View tabs (per campaign)

`TRACK_VIEWS`:

| id         | Label           | Phase | Client-hidden? |
| ---------- | --------------- | ----- | -------------- |
| `gaps`     | Perception Gaps | 1C    | yes            |
| `topics`   | Topics          | 1C    | yes            |
| `articles` | Articles        | 1B    | yes            |
| `review`   | Client Review   | 1C    | no             |
| `approved` | Approved        | 1C    | no             |

Client portal (`IS_CLIENT_PORTAL` build flag OR `auth.session.role === "client_portal"`) only sees Review + Approved.

### Access token banner

At the top of the module, an `AccessTokenBanner` displays when `sessionStorage` lacks an `xt_token`. Provider keys live on the Cloudflare Worker (`xtrusio-ai.thedevimapro.workers.dev`); browser needs an HMAC-signed token to call it. The banner offers a paste field as a manual fallback when login auto-exchange fails.

### Perception Gaps Panel (`PerceptionGapsPanel.jsx`)

- Pulls fresh gaps via `usePerceptionGaps(campaign, store)` hook (Firebase reads `m2_content_gaps` + `m2_scan_meta`).
- Resolves each gap's `sessionIds[]` → segment via `m2_scan_meta`, scoping by `campaign.segmentIds[]`.
- Computes a 5-factor priority score (weights locked 30/25/20/15/10):
  - 30% severity × frequency
  - 25% narrative alignment (gap lifecycle vs campaign tracks)
  - 20% persona reach (count of personas)
  - 15% buying-stage breadth (count of stages)
  - 10% business value tag (low/medium/high → 0.33/0.66/1.0)
- Severity numeric mapping: `absent: 1.0`, `incomplete: 0.85`, `high: 1.0`, `medium: 0.66`, `low: 0.33`.
- Each visible gap can be **dismissed** (hidden but recoverable), **enriched** (Gemini call to `enrichGap.js`), and **market-demand-estimated** (Gemini call to estimate monthly search volume).
- "Generate Topics" button runs `generateTopics({ campaign, gaps, gapDescriptions })` and calls `onTopicsGenerated` → switches to Topics tab.

### Topics Panel (`TopicsPanel.jsx`)

- Shows topics from `store.topicsForCampaign(campaign.id)`.
- Topics are FAQ-style or narrative-style (see `contentFormat` in §11).
- Each topic has actions: **Write Article** (seeds an article record with format-aware imports), **Discard**.
- Clicking "Write Article" calls `store.addArticle(...)` with status `"needs-revision"` and `importComments` pre-filled with format-specific instructions (see §9), then opens the editor.

### Articles List Panel (`ArticlesList.jsx`)

- Shows all articles for the campaign (or filtered by track if `showTracks: true`).
- Status kanban with these statuses:
  - `imported-pending` — bulk-imported, waiting for AI verdict
  - `imported-rejected` — AI judged the import didn't match style
  - `needs-revision` — drafts that need an AI rewrite
  - `revising` — AI rewrite in progress
  - `ready-for-client` — admin pushed to client review
  - `in-review` — client added comments, waiting for re-rewrite
  - `approved` — client signed off, ready for placement
  - `published` — live on a placement (manual stamp)

### Article Editor (`ArticleEditor.jsx`)

- Full-bleed editor (chrome hidden when an article is open).
- Shows the body, title, byline, word count, citations + sirionBacklinks.
- "Apply AI Revision" button calls `rewriteArticleWithFeedback({ rules, campaign, track, article, feedback })` from `revisionEngine.js`. The `feedback` text box is pre-filled (from import or from topic seed) but the user can rewrite it.
- Revisions are pushed into `article.revisions[]` history.
- "Push to Client Review" advances status.
- Style Rules can be opened in a side panel.
- DOCX export via `downloadArticleDocx()` from `exportArticle.js`.
- Plain-text-with-footnotes export via `articleAsPlainTextWithFootnotes()`.
- Clipboard copy via `copyArticleToClipboard()`.

### Client Review Panel (`ClientReviewPanel.jsx`)

- Renders articles with status `ready-for-client` / `in-review`.
- Client adds comments (`clientComments[]`); each comment has `id`, `text`, `addedAt`, `byClientId`, `status`.
- Approving an article advances it to `approved`. The client can also reject back to `needs-revision`.

### Approved Panel (`ApprovedPanel.jsx`)

- Shows approved + published articles.
- Admin pulls .docx files for outreach.
- Same surface visible to client (so they have a clean confirmation list of what they signed off).

### Style Rules Panel (`StyleRulesPanel.jsx`)

- The "client memory" surface. Active rules are auto-prepended to every AI prompt via `assemblePrompt()`.
- Add manually OR extract from sample text via `extractRulesFromText()` (Claude call).
- Rule scope: `client` | `campaign` | `track`. Rule status: `active` | `archived`.
- Rule shape: `{ id, rule, scope, campaignId?, trackId?, source, sourceCommentId?, addedAt, status, category }`.
- Categories: `tone | structure | vocabulary | formatting | argument | framing | other`.

### Import Modal (`ImportModal.jsx`)

- Onboarding flow — paste sample articles or upload `.docx`. Uses `parseDocxSections.js` to split.
- AI judges if each import "matches client voice"; if not, status flips to `imported-rejected`.

---

## 4. Every Prompt in `contentPrompts.js`

The legacy prompt library. All eight functions are exported. Prompt strings are quoted verbatim below where load-bearing; long blocks are truncated with `…` only when the omitted piece is repeated boilerplate already shown elsewhere.

### 4.1 `buildTopicPrompt(questions, company, topicCount, opts)`

**Purpose:** Stage-1 topic generator that fuses M1 question bank, M2 perception scan results, M2 content gaps, and M3 authority gaps into a "newsroom-grade" topic brief.

**Inputs:** array of M1 questions; `company` (display name); `topicCount`; `opts` = `{ scanData, authorityData, contentGaps, cluster?, persona?, lifecycle? }`.

**Construction:** the function pre-computes:

- A markdown table of every (filtered) question with persona, stage, cluster, lifecycle, intent.
- A "Perception Intelligence" block with overall mention/position/sentiment scores, a competitor dominance table, a "queries where COMPANY is absent or weak" table, and a citation map of company URLs already cited by AI.
- A "Content Gap Analysis" table (severity, lifecycle, priority, frequency, stages).
- An "Authority Domain Gaps" table (DA, target personas, buyer stages).

**Output format (verbatim purpose statement):**

> # Topic Generator — ${company} Perception-Driven Content Strategy
>
> ## Purpose
>
> You are a **newsroom-grade topic generator** with access to real AI perception data. Your job is to produce **${topicCount || "5-10"} white-labeled, journalist-ready article topics** that are STRATEGICALLY chosen to close the specific perception gaps identified below.
>
> These topics must:
>
> - **Never mention ${company}, any vendor name, or any product name.** They are pure category/industry angles.
> - Read as genuine editorial — the kind of piece a senior reporter at TechTarget, Legaltech News, or Spend Matters would pitch in a story meeting.
> - Create a natural "perception gap" where a full-lifecycle CLM platform becomes the logical answer — without ever saying so.
> - **Be driven by the data below** — not generic SEO topics. Every topic must trace to a specific visibility gap, competitor vulnerability, or uncovered buyer question.

**Method instructions (verbatim):**

> ### Step 1: Cross-reference ALL data sources
>
> For each potential topic, check:
>
> - Which buyer queries does it address? (Question Bank)
> - Where is ${company} absent/weak? (Perception Intelligence)
> - Which competitor narratives does it counter? (Competitor Dominance)
> - Which authority domains could publish it? (Authority Gaps)
> - Does existing ${company} content already cover this? (Citation Map — if a URL is heavily cited, that topic is ALREADY covered)
>
> ### Step 2: Prioritize by strategic impact
>
> Rank topics by:
>
> 1. **Perception gap severity** — Absent > Outranked > Weak
> 2. **Query volume** — How many buyer queries does this topic address?
> 3. **Competitor vulnerability** — Where does the #1 competitor have a weak narrative?
> 4. **Publication fit** — Can this realistically get placed on a DA60+ domain?
> 5. **Lifecycle correction** — Does it shift the narrative from post-signature → full-lifecycle?

**Output schema (verbatim):**

> ```
> ### Topic [N]: [Headline]
>
> **Editorial thesis:** [1-2 sentences]
> **Source questions:** [comma-separated question numbers from the bank]
> **Gaps addressed:** [which perception gaps this closes — reference gap numbers]
> **Competitor countered:** [which competitor narrative this undermines]
> **Target publications:** [2-3 publication names — reference authority domains if relevant]
> **Target personas:** [buyer personas this reaches]
> **Narrative layer:** [A: Category problem / B: Market proof / C: Solution bridge]
> **Newsworthiness trigger:** [what makes this timely]
> **Data hook:** [what research would make this irresistible]
> **Suggested structure:**
> 1. [Opening angle]
> 2. [Supporting evidence]
> 3. [Industry reframe]
> 4. [Where the market is heading]
> 5. [Decision framework or practical takeaway]
> **Newsworthiness score:** [1-10]
> **Perception impact:** [1-10 — how many absent/weak queries would this address?]
> **Audience breadth:** [1-10]
> **Publication fit:** [1-10]
> **Data strength:** [1-10]
> **Strategic priority:** [1-10]
> **Gap type:** [MISS / WRONG / WEAK]
> ```

**Constraints (verbatim):**

> - Output exactly **${topicCount || "5-10"} topics**.
> - At least 1 topic must target pre-signature lifecycle.
> - At least 1 topic must target agentic AI / automation cluster if generating 3+.
> - **Every topic must reference specific gaps or weak queries from the data above.** No generic topics.
> - No topic may be usable as-is for a product page or sales collateral.
> - Headlines must pass the "Would a journalist pitch this?" test.

**Tone (verbatim):**

> Write headlines the way Reuters, WSJ Pro, or TechTarget would — factual, specific, tension-driven.
> Avoid: "ultimate guide," "everything you need to know," "top 10," "how to choose," "best practices."
> Prefer: "why X is failing," "the hidden cost of Y," "what Z gets wrong about."

**Parser:** `parseTopicsOutput(rawText)` splits on `### Topic [N]:` markers, extracts each labeled field via regex (e.g. `**Editorial thesis:** …`), pulls integers out of score fields, parses comma/digit lists for `Source questions`, and stamps `id`, `productionReady: "Needs build"`, `status: "draft"`, `createdAt`.

**Special rules:** "no vendor mentions", journalist tone, severity-driven prioritisation, strict markdown header matching for parser.

---

### 4.2 `buildTopicFromGapsPrompt(gaps, company, topicCount, opts)`

**Purpose:** Like `buildTopicPrompt` but seeded from **content gaps** (not the question bank). Used when M2 has run and produced perception gaps that the user wants converted directly to topics.

**Construction:** Builds a gaps table (severity, lifecycle, priority 0-100, frequency, content type, stages), then attaches the same competitor-dominance + absent-queries blocks as `buildTopicPrompt`, plus an authority-gap block.

**Verbatim opening:**

> # Topic Generator from AI Perception Gaps — ${company}
>
> ## Purpose
>
> You are a **newsroom-grade topic generator** with access to real AI perception data. The user has run AI perception scans and identified **${(gaps || []).length} content gaps** — topics where ${company || "the company"} is either absent, outranked, or misrepresented in AI responses.
>
> Your job is to take these gaps — combined with the competitive intelligence below — and produce **${topicCount || "3-5"} white-labeled, journalist-ready article topics** that would close these specific perception gaps.

**Verbatim severity key:**

> **Severity key:** Absent = ${company} not mentioned at all. Outranked = mentioned but below competitors. Weak = mentioned but with incorrect/incomplete framing.
> **Content Type:** Website = needs on-site content. Blog = needs external guest post. Both = needs both.

**Verbatim method:**

> ### Step 1: Cluster gaps by editorial opportunity
>
> Group 2-4 related gaps that point to the same underlying industry tension. Don't create a 1:1 mapping of gap→topic.
>
> ### Step 2: Cross-reference with perception data
>
> For each potential topic cluster:
>
> - Which competitors dominate these queries? (Counter their narrative)
> - Which authority domains could publish this? (Close two gaps at once)
> - What's the severity? (Absent > Outranked > Weak)
>
> ### Step 3: Prioritize by impact
>
> Rank by: gap severity × priority score × frequency. High-frequency gaps appearing across multiple scans are more valuable than one-off findings.
>
> ### Step 4: Synthesize into journalist-ready topics
>
> Frame as a problem-first headline. Not "how to fix X" but "why X is failing" or "the hidden cost of Y."

The output schema is identical to `buildTopicPrompt` and uses the same parser. Constraints emphasize: every topic must trace to a gap number, at least one pre-signature topic, "Would Reuters run this?" headline test.

---

### 4.3 `buildFormatOwnTopicsPrompt(topicCount)`

**Purpose:** When the user already has raw topics (from blogs, AI conversations, or notes) and wants them scored + formatted into the canonical schema.

**Verbatim core:**

> # Format & Score Existing Topics
>
> You are a senior editorial strategist. The user will paste ${topicCount || "1-6"} raw article topics below. Your job is to:
>
> 1. **Analyze each topic seriously** — research the actual market, competitive landscape, and editorial coverage
> 2. **Calculate REAL scores** — do NOT hallucinate or guess numbers. Base every score on genuine analysis:
>    - **Perception Impact (1-10):** How much does this shift the "CLM = post-signature only" narrative toward full-lifecycle? 10 = fundamentally reframes the category. 1 = reinforces existing perception.
>    - **Audience Breadth (1-10):** How many distinct buyer personas (CIO, GC, CFO, CPO, VPLO, CTO, CM, PD) would genuinely read this? Count them honestly.
>    - **Publication Fit (1-10):** Would enterprise tech (DA80+), legal tech (DA60+), procurement (DA60+), or finance publications actually accept this angle? 10 = editor commissions on sight. 1 = rejected as vendor content.
>    - **Data Strength (1-10):** How much verifiable, citable data (analyst reports, regulatory deadlines, public benchmarks, case law) supports this topic? 10 = rich primary sources. 1 = opinion only.
>    - **Strategic Priority (1-10):** If a CMO could only publish 3 articles this quarter, how critical is this one for market positioning?
>    - **Newsworthiness (1-10):** How timely is this — tied to regulation, market event, technology shift, or failure pattern?
> 3. **Identify the gap type:** MISS (topic not covered in AI/market), WRONG (existing narrative is incorrect), or WEAK (coverage exists but shallow)

**Rules (verbatim):**

> - Do NOT inflate scores. A mediocre topic should get mediocre scores.
> - Do NOT invent data citations. If you can't find real supporting data, score Data Strength low and say so.
> - If a headline is weak (reads like marketing), rewrite it to pass the "Would Reuters run this?" test.
> - Be honest about Publication Fit — most vendor-adjacent topics score 4-6, not 8-10.

The output uses the same `### Topic [N]:` schema, parsed by `parseTopicsOutput()`. The user pastes their raw topics under the literal marker `[USER WILL PASTE THEIR TOPICS BELOW THIS LINE]`.

---

### 4.4 `buildFormatOwnArticlePrompt(topic)`

**Purpose:** When the user already has a draft article (e.g. ghost-written by an external writer) and wants it restructured into the canonical format with citations and metadata.

**Verbatim core:**

> # Format & Structure Existing Article
>
> You are a senior content editor. The user will paste a raw article draft below. Your job is to:
>
> 1. **Restructure it** into proper editorial format with clear H2/H3 sections
> 2. **Add citation references** — wherever a claim is made, add [N] numbered references. List all URLs at the bottom under ## References
> 3. **Calculate metadata** — word count, read time, suggested URL slug, meta description, keywords
> 4. **Maintain the author's voice** — do not rewrite the content, just restructure and add citations
> 5. **Flag any unsupported claims** — if a stat or claim has no source, mark it [NEEDS CITATION]

**Output format (verbatim):**

> ```
> META:
> Title: [article title]
> Meta Description: [~155 chars with primary keyword]
> Category: [Contract AI / Contract Management / Contract Analytics / etc.]
> URL Slug: [/library/category/slug/]
> Keywords: [comma-separated]
> Word Count: [number]
> Read Time: [X min read]
>
> ---
>
> # [Article Title]
>
> [Full article body with proper H2/H3 structure]
>
> [Citation references as [1], [2], etc. inline]
>
> ## References
>
> [1] Source Name — https://url
> [2] Source Name — https://url
> ...
> ```

**Rules (verbatim):**

> - Every statistic or external claim MUST have a [N] citation
> - References section at the bottom with full URLs
> - No Sirion links in the first 400 words
> - Keep the article's existing arguments — restructure, don't rewrite
> - If the article is too short (<800 words), note it but don't pad it

Parsed by `parseArticleOutput()` (same parser as the regular article prompt).

---

### 4.5 `buildJournalistPackPrompt(topic, company, questions, scanData, authorityData)`

**Purpose:** Stage-2 — produce a complete editorial brief for a chosen topic.

**Construction:** Pulls the source questions referenced in the topic, optionally appends a "Perception Gaps" block listing M2 MISS/WEAK queries and an "Authority Gaps" block of M3 domains.

**Verbatim task framing:**

> ## Your Task
>
> You are a senior editorial strategist. Produce a complete **Journalist Pack** for this topic — the kind of brief a managing editor would hand to a senior reporter before assigning the piece.

**Output format (verbatim):**

> ```
> ## Journalist Pack: [Headline]
>
> ### Executive Summary
> [3-4 sentences — the core argument, why now, who cares]
>
> ### Key Findings / Data Points
> [5-8 bullet points — each must cite a specific source, stat, or verifiable claim]
> [Mark each as: [VERIFIED] if from a named source, [NEEDS VERIFICATION] if estimated]
>
> ### Interview Targets
> [3-5 people or roles who should be quoted in the final article]
> [Include: name/title if known, or role description, and what angle they bring]
>
> ### Competing Coverage Analysis
> [List 3-5 existing articles that touch this topic]
> [For each: title, publication, URL if known, and how THIS piece differs]
>
> ### Suggested Outline
> 1. [Opening hook — specific scenario or data point]
> 2. [Problem definition — with evidence]
> 3. [Market context — who else is affected]
> 4. [Framework or original analysis]
> 5. [Expert perspective]
> 6. [Implications / what happens next]
> 7. [Practical takeaway for the reader]
>
> ### Publication Fit Matrix
> | Publication | Fit Score (1-10) | Why | Angle Adjustment Needed |
> |---|---|---|---|
>
> ### Risk Assessment
> - **Factual risk:** [What claims need extra verification?]
> - **Legal risk:** [Any defamation, NDA, or competitive sensitivity?]
> - **Timeliness risk:** [Could this become stale? What's the window?]
> - **Duplication risk:** [How close is existing coverage?]
>
> ### Recommended Word Count
> [Target word count and format: longform, analysis piece, feature, etc.]
>
> ### Urgency Rating
> [1-10, with explanation of timing factors]
> ```

**Constraints (verbatim):**

> - Every data point must be attributable to a named source or marked as needing verification.
> - No vendor names in the journalist pack — this is white-labeled editorial.
> - Write for a journalist audience, not a marketing team.
> - The pack should be usable by any publication — not just ${company}'s blog.

**Parser:** `parsePackOutput(rawText, topicId)` extracts each `### …` section into named fields (`executiveSummary`, `keyFindings`, `interviewTargets`, `competingCoverage`, `suggestedOutline`, `riskAssessment`) and stores the full `rawText`.

---

### 4.6 `buildArticlePrompt(topic, pack, company, config)`

**Purpose:** Stage-3 — write the full article from a topic + pack. Defaults: `authorName = "Arpita Chakravorty"`, `blogUrl = "sirion.ai/library/"`, `wordCount = "1500-1800"`.

**Verbatim style guide:**

> ### Style Rules:
>
> - Open with a felt business pain or vivid scenario — NEVER a definition
> - Em-dashes for parenthetical emphasis
> - Short declarative sentences as punctuation between longer analytical ones
> - Bold lead-ins in all bullet/numbered lists
> - No rhetorical questions in headings — headings are declarative
> - No exclamation marks — ever
> - Average paragraph: 3-4 sentences
> - Sentence length variation: 8-word sentences mixed with 35-word sentences
>
> ### Banned Words:
>
> "game-changer," "revolutionary," "cutting-edge," "best-in-class," "unlock," "leverage," "landscape," "streamline," "robust," "It's worth noting," "Interestingly," "In today's," "It remains to be seen," "At the end of the day"
>
> ### Preferred Language:
>
> "silently," "the result is...," "this isn't [X]—it's [Y]," "at scale," "enterprise-grade," "governance," "visibility," "accountability," "from [old state] to [new state]"

**Verbatim structure spec:**

> ## STRUCTURE
>
> 1. **Opening** (2-3 paragraphs) — Scenario-first. Concrete, visual, present-tense. This is happening NOW.
> 2. **H2: Problem Definition** — Why existing approaches fail. Steel-man the counterargument.
> 3. **H2: Forces / Evidence** — Market evidence, regulatory triggers, data points. All externally sourced.
> 4. **H2: Original Framework** — The article's intellectual contribution. Numbered, bold lead-ins.
> 5. **H2: How ${company}'s Full-Lifecycle Approach Bridges the Gap** — Natural bridge from problem to solution. NOT a product pitch. Show capabilities across pre-sig AND post-sig.
> 6. **H2: Readiness Checklist / Your Next Step** — Practical, pre-deployment. No explicit CTA.
> 7. **H2: FAQs** — 3-5 questions, 2-4 sentence answers each.

**Verbatim citation rules (the load-bearing block):**

> ## CITATION RULES — NUMBERED REFERENCE SYSTEM (MANDATORY)
>
> **Publishers need to create hyperlinks manually.** Therefore:
>
> 1. **In the article body**, every citation appears as a numbered reference in square brackets: [1], [2], [3], etc.
>    - Example: "...immutable audit trails that capture every approval event [1]..."
>    - The number goes AFTER the relevant phrase, not at the end of the sentence.
>    - Each unique URL gets ONE number. If the same source is cited twice, use the same number.
> 2. **At the end of the article** (before the META block), include a complete **References** section: …
> 3. **Format for each reference:** [N] Descriptive Label — Full URL
>    - The label should be human-readable (not just the URL)
>    - Include the full URL so publishers can copy-paste it directly
> 4. **Citation placement rules:**
>    - No ${company} links in first 400 words
>    - External citations in problem/evidence sections
>    - ${company} links in framework/solution sections only
>    - Maximum 3 ${company}-owned citations
>    - Minimum 60% external citations

**Verbatim perception-shift rules:**

> ## PERCEPTION SHIFT
>
> - The article's gravity must pull toward PRE-signature governance
> - Framework must SPAN the full lifecycle explicitly
> - ${company} section shows capabilities across BOTH pre and post phases
> - NEVER state "${company} is a full-lifecycle platform" — demonstrate it through expertise
> - NEVER use "Unlike other CLM platforms..."

The article must end with the META block. Parsed by `parseArticleOutput()`.

---

### 4.7 `buildHumanizePrompt(article)`

**Purpose:** Stage-4 — wrap a finished article in an anti-AI-detection rewrite.

**Verbatim opening:**

> You are an experienced, slightly cynical industry veteran writing a thought-leadership piece for a niche Substack. Your goal is to rewrite the provided text so that it reads as 100% human-authored. You must strictly adhere to the following mechanical and stylistic constraints:

**The 6 constraints (verbatim):**

> **1. Extreme Burstiness (Pacing & Rhythm):**
>
> - Shatter predictive sentence lengths. You must aggressively mix ultra-short sentences (2-5 words) with long, winding, complex sentences (30+ words).
> - Never use the same sentence structure or length three times in a row.
> - Use at least two single-sentence paragraphs for dramatic emphasis.
>
> **2. The Vocabulary Ban List (Zero Tolerance):**
>
> - You are strictly forbidden from using the following AI-tells: delve, testament, robust, tapestry, leverage, unlock, landscape, crucial, seamless, dynamic, pivotal, navigating, realm, multifaceted, underscore, or overarching.
> - Replace corporate jargon with plain, conversational English.
>
> **3. Structural Imperfections:**
>
> - Write the way people actually speak. It is mandatory to start at least three sentences with conjunctions like "But," "And," or "Because."
> - Use em-dashes—like this—to insert parenthetical thoughts or sudden shifts in logic.
>
> **4. Cognitive Framing & Stance:**
>
> - Do not write neutral, middle-of-the-road summaries. Take a definitive, opinionated stance.
> - Remove all "hedging" language (e.g., "It is important to consider," "While some may argue").
> - Introduce a highly specific, slightly gritty, or unexpected real-world analogy to explain the core concept, rather than relying on abstract generalizations.
>
> **5. Formatting:**
>
> - Avoid perfectly symmetrical lists. If you use bullet points, make one bullet a single word, and the next bullet three sentences long.
>
> **6. Preservation Rules:**
>
> - Keep ALL hyperlinks exactly as they appear in the original — do not remove, change, or rephrase anchor text for any link.
> - Keep ALL H1/H2/H3 heading structure intact — you may rephrase headings for punch but do not remove or reorder them.
> - Keep the META block at the end unchanged.
> - Keep all factual claims, citations, and source attributions exactly as written.
> - Maintain the same word count range (within 10% of original).

The pasted body overwrites the article body and stamps `humanized: true` + `humanizedAt`.

---

### 4.8 M6v2 prompts in `src/modules/contentStrategyV2/lib/promptAssembly.js`

These are the active V2 prompts. Each call goes through `assemblePrompt({ rules, campaign, track, task, payload })`, which prepends the system block:

> ## HOUSE STYLE RULES (must follow — these are non-negotiable)
>
> [active rules joined as bullets]
>
> ## CAMPAIGN CONTEXT
>
> Client: …
> Byline: …
> Campaign goal: …
>
> ## TASK
>
> …

#### Task: `rewrite-with-feedback`

Used by the article editor's "Apply AI Revision". Verbatim role + task:

> Senior content strategist for B2B SaaS, specialised in CLM industry. Active web researcher.
>
> Rewrite the article below incorporating the client's feedback. Keep the byline as ${campaign.byline}. The article belongs to the "${track.name}" track — ${track.tagline}.

The user block is a long instruction set (numbered 1–6) covering: address every concern, actively use web search, two distinct citation kinds (third-party citations as Markdown inline links and Sirion backlinks as anchored Sirion URLs with min 2 per article), plain prose only (no Markdown headings, no `**bold**`, Unicode bullets only), inline link format, end with a "Sources" section listing only third-party citations.

Verbatim output JSON requirement:

> Return strict JSON with NO additional text, NO Markdown fences:
>
> ```
> {
>   "title": "...",
>   "body": "... full article body, ending with a Sources section listing only third-party URLs",
>   "summary": "one-line summary of how the feedback was addressed overall",
>   "changes": [
>     { "concern": "...", "original": "...", "rewrite": "..." }
>   ],
>   "citations": [
>     { "title": "Deloitte AI Contract Report 2025", "url": "https://www2.deloitte.com/..." }
>   ],
>   "sirionBacklinks": [
>     { "anchorText": "AI-powered CLM platform", "url": "https://www.sirion.com/clm-platform/", "embedded": true },
>     { "anchorText": "post-signature obligation tracking", "url": "https://www.sirion.com/obligations/", "embedded": true }
>   ]
> }
> ```

**Special rules:** redirect URLs (vertexaisearch.cloud.google.com, google.com/url?q=, webcache.googleusercontent.com) are stripped. Sirion backlinks must be embedded in the body — `auditRevision()` warns if not.

#### Task: `generate-article-from-topic`

Verbatim role + task:

> Senior content strategist writing for Sirion (CLM software).
>
> Write an article on the topic below, byline ${campaign.byline}. Track: "${track.name}" — ${track.tagline}.

User block lists topic title, brief, gaps to close. Returns `{ title, body, metaDescription, wordCount, keywords }`.

#### Task: `suggest-topics-from-gaps`

Verbatim role + task:

> Editorial strategist proposing article topics.
>
> Propose 5–8 article topics for the "${track.name}" track that, taken together, would close the perception gaps below.

Returns `{ topics: [{ title, brief, addressesGaps: [0, 2] }] }` with 0-indexed gap references.

#### Topic generation prompts in `generateTopics.js`

Two format-specific passes (FAQ and narrative) run in parallel. Both share a base system:

> You are a senior B2B content strategist for Sirion (CLM software for enterprises).
> Given a list of perception gaps from an AI-search audit, propose article topics that would close them.
>
> RULES:
> • Group related gaps into ONE topic when an article could naturally address them together.
> Don't return one topic per gap if 3 gaps share a theme.
> • Each topic must be SPECIFIC, not generic. Bad: 'CLM Best Practices'.
> • Anchor each topic in the campaign goal. If a gap doesn't fit, skip it.
> • Each topic is for ONE primary persona (CFO, GC, CIO, Procurement Director, VP Legal Ops, VPLO).
> • Lifecycle classification: pre-sig | post-sig | full-stack | agentic.

FAQ-specific guidance (verbatim):

> FORMAT: FAQ for the client's own website (sirion.com).
> • Each topic title MUST be phrased as a direct USER QUESTION buyers actually type or speak.
> Examples: 'What ERP integrations does Sirion support for pre-signature workflows?',
> 'How does Sirion enforce post-signature obligations across vendors?',
> 'Which Sirion modules cover agentic contract review?'
> • The intent is AI-search optimisation: ChatGPT/Perplexity/Gemini extract exact-match
> answers from FAQ pages. The page must START with a direct, concise answer to the
> question, then expand with detail.
> • Word target: 600-1200 words (FAQ pages are tight; long-form belongs on third-party).
> • Tone: factual, product-grounded, declarative. NOT op-ed.

Narrative-specific guidance (verbatim):

> FORMAT: Narrative article for a third-party publication (Forbes, HBR, McKinsey-style outlets).
> • Each topic title is an editorial HEADLINE, not a question.
> Examples: 'Why CFOs Now Own Contract AI Risk',
> 'The Hidden Cost of Fragmented Pre-Signature Tools',
> 'Agentic CLM Will Reshape Procurement by 2027'.
> • Mix angles across the batch: data-led, contrarian, framework-led, prediction.
> Don't return 5 'How to do X' titles.
> • Word target: 1200-1800 words. Strong argument with data + cited sources.
> • Tone: editorial, opinion-led, industry-grounded. Sirion is mentioned in passing as
> proof points (anchor links), not as the centre of gravity.

JSON output schema:

> ```
> {
>   "topics": [
>     {
>       "title": "Working title (or QUESTION for FAQ format)",
>       "addressesGapIds": ["gap_id_1", "gap_id_2"],
>       "persona": "GC",
>       "lifecycle": "full-stack",
>       "angleHook": "One sentence on the editorial angle / what makes this fresh",
>       "wordCountTarget": 1500,
>       "rationale": "1-2 sentences on why this topic matters for the campaign and which gaps it closes"
>     }
>   ]
> }
> ```

`bucketGapsByPlacement()` routes gaps with `placement = "client-blog"` to the FAQ pass, `"third-party"` to the narrative pass, `"both"` to BOTH, and unknown to narrative.

#### Gap enrichment prompt in `enrichGap.js`

Per-gap call to label placement. Verbatim system:

> You are a B2B content strategist analysing a perception gap from an AI-search audit.
>
> INPUT: a topic that came up in buyer questions but the AI either failed to mention
> the client (severity=ABSENT) or covered it shallowly (severity=INCOMPLETE), plus context.
>
> OUTPUT a 2-4 sentence DESCRIPTION explaining:
> • What buyers expect to find on this topic
> • What's currently missing or wrong in AI responses about it
> • Why it matters for this client's perception
>
> Then CLASSIFY where the content should be published:
> • client-blog — Topic is product/brand-specific (features, case studies,
> integrations, internal processes). The client OWNS this asset
> on their own site.
> • third-party — Topic is generic industry/category (trends, regulation,
> best practices). Client gets credibility by appearing in a
> neutral publication, not by repeating it on their own site.
> • both — Topic has BOTH a generic angle (third-party hook piece) AND
> a deeper product-specific version (client blog deep-dive).

JSON: `{ description, placement, placementReason }`.

#### Style-rule extraction prompt in `extractRules.js`

Verbatim system:

> You analyze sample content — published articles, feedback emails, style guides, or editor comments — and extract reusable HOUSE STYLE RULES for an AI content writer who will generate future articles in the same voice.
>
> Each rule must be:
>
> - A single, actionable instruction (one rule = one decision the AI makes when writing)
> - Specific enough to guide concrete writing choices (NOT vague platitudes like "be clear" or "write well")
> - Generalizable across many future articles (NOT about one specific article)
> - Phrased as a directive: "Open every article with...", "Avoid...", "Use..."
> - 1–3 sentences maximum per rule
> - Where useful, include a short concrete example after the directive
>
> For each rule, propose:
>
> - scope: "client" (applies to all this client's content — DEFAULT)
>   | "campaign" (this campaign only — use when feedback specifically targets the campaign goal)
>   | "track" (one track only — use when feedback singles out a track's framing)
> - category: "tone" | "structure" | "vocabulary" | "formatting" | "argument" | "framing"
>
> Aim for 8–15 high-quality rules. Don't pad with weak rules. If the sample content yields fewer than 8 distinct patterns, return fewer — quality over quantity.

JSON: `{ "rules": [{ "rule": "...", "scope": "client", "category": "tone" }] }`.

---

## 5. Topic Object Shape

### Legacy M6 topic (`pipeline.m6.topics[i]`)

| Field                   | Type                          | Source                                                       |
| ----------------------- | ----------------------------- | ------------------------------------------------------------ |
| `id`                    | string                        | `topic_<timestamp>_<index>`                                  |
| `headline`              | string                        | First line of `### Topic [N]:`                               |
| `editorialThesis`       | string                        | `**Editorial thesis:** …`                                    |
| `sourceQuestions`       | int[]                         | digits parsed from `**Source questions:**`                   |
| `targetPublications`    | string                        | `**Target publications:**`                                   |
| `targetPersonas`        | string                        | `**Target personas:**`                                       |
| `narrativeLayer`        | string                        | `**Narrative layer:**`                                       |
| `newsworthinessTrigger` | string                        | `**Newsworthiness trigger:**`                                |
| `dataHook`              | string                        | `**Data hook:**`                                             |
| `suggestedStructure`    | string (multiline)            | `**Suggested structure:**` block                             |
| `score`                 | int                           | `**Newsworthiness score:**`                                  |
| `perceptionImpact`      | int \| null                   | `**Perception impact:**` (null when absent)                  |
| `audienceBreadth`       | int \| null                   | `**Audience breadth:**`                                      |
| `publicationFit`        | int \| null                   | `**Publication fit:**`                                       |
| `dataStrength`          | int \| null                   | `**Data strength:**`                                         |
| `strategicPriority`     | int \| null                   | `**Strategic priority:**`                                    |
| `gapType`               | "MISS"\|"WRONG"\|"WEAK"\|null | `**Gap type:**`                                              |
| `productionReady`       | string                        | Default "Needs build"                                        |
| `status`                | string                        | One of `draft`, `pack-ready`, `article-ready`, `transferred` |
| `tag`                   | string\|null                  | Optional tag id from `pipeline.m6.tags[]`                    |
| `createdAt`             | ISO timestamp                 | stamped at parse                                             |

### M6v2 topic (`pipeline.m6v2.topics[id]`)

| Field             | Type                                               | Notes                                                    |
| ----------------- | -------------------------------------------------- | -------------------------------------------------------- |
| `id`              | string                                             | `topic_<ts>_<rand>`                                      |
| `campaignId`      | string                                             | Active campaign                                          |
| `title`           | string                                             | FAQ → user question; narrative → headline                |
| `addressesGapIds` | string[]                                           | Gap ids closed                                           |
| `persona`         | string\|null                                       | One of CFO/GC/CIO/Procurement Director/VP Legal Ops/VPLO |
| `lifecycle`       | "pre-sig"\|"post-sig"\|"full-stack"\|"agentic"     |                                                          |
| `angleHook`       | string                                             | 1 sentence editorial angle                               |
| `wordCountTarget` | int                                                | Default 800 (FAQ) or 1500 (narrative)                    |
| `rationale`       | string                                             | Why this matters                                         |
| `contentFormat`   | "faq"\|"narrative"                                 | Critical — branches all downstream prompts               |
| `status`          | "candidate"\|"approved"\|"in-article"\|"discarded" |                                                          |
| `proposedAt`      | ISO timestamp                                      |                                                          |
| `articleId`       | string\|null                                       | When user clicks "Write Article"                         |

---

## 6. Journalist Pack Object Shape

`pipeline.m6.journalistPacks[i]`:

| Field               | Type          | Source section           |
| ------------------- | ------------- | ------------------------ |
| `id`                | string        | `pack_<ts>`              |
| `topicId`           | string        | Owning topic             |
| `executiveSummary`  | string        | `### Executive Summary`  |
| `keyFindings`       | string        | `### Key Findings`       |
| `interviewTargets`  | string        | `### Interview Targets`  |
| `competingCoverage` | string        | `### Competing Coverage` |
| `suggestedOutline`  | string        | `### Suggested Outline`  |
| `riskAssessment`    | string        | `### Risk Assessment`    |
| `rawText`           | string        | Full pasted output       |
| `status`            | string        | `"draft"`                |
| `createdAt`         | ISO timestamp |                          |

The Publication Fit Matrix and Recommended Word Count + Urgency Rating sections from the prompt are not stored as discrete fields — they live in `rawText` only.

The brief mentions `pitches[]`, `targetPublications[]`, `messagingAngles[]`, `competitivePositioning`, `timeline`, `difficulty` — none of these are extracted into discrete fields by the parser. They exist only as prose inside `executiveSummary` / `competingCoverage` / `riskAssessment`. (Treat as a future hook to enrich the parser.)

---

## 7. Article Object Shape

### Legacy M6 article (`pipeline.m6.articles[i]`)

| Field             | Type          | Source                                          |
| ----------------- | ------------- | ----------------------------------------------- |
| `id`              | string        | `article_<ts>`                                  |
| `topicId`         | string        | Owning topic                                    |
| `title`           | string        | From META block or first H1                     |
| `metaDescription` | string        | META `Meta Description:`                        |
| `category`        | string        | META `Category:`                                |
| `urlSlug`         | string        | META `URL Slug:`                                |
| `wordCount`       | int           | counted from body                               |
| `readTime`        | string        | META `Read Time:` or `${ceil(wc/250)} min read` |
| `keywords`        | string        | META `Keywords:`                                |
| `body`            | string        | Article body (markdown)                         |
| `rawText`         | string        | Full pasted text                                |
| `status`          | string        | `"draft"`                                       |
| `humanized`       | bool          | Set true after Stage-4 humanize                 |
| `humanizedAt`     | ISO timestamp |                                                 |
| `createdAt`       | ISO timestamp |                                                 |

The brief asks about `deck`, `byline`, `CTA`, `citations` as discrete fields — these are NOT extracted. The deck is inline in the body (the prompt asks for an opening scenario), the byline is supplied via `config.authorName` to `buildArticlePrompt`, the CTA is the "Readiness Checklist / Your Next Step" section in the body, and citations are the inline `[N]` markers + bottom References block parsed implicitly by the user reading the body.

### M6v2 article (`pipeline.m6v2.articles[id]`)

| Field                                                             | Type                                                 | Notes                                                                       |
| ----------------------------------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------- |
| `id`                                                              | string                                               | `art_<ts>_<rand>`                                                           |
| `campaignId`, `trackId`                                           | strings                                              |                                                                             |
| `title`, `body`                                                   | strings                                              |                                                                             |
| `status`                                                          | string                                               | One of the 8 kanban statuses (see §3)                                       |
| `source`                                                          | "imported"\|"ai-generated"\|"manual"\|"topic-seeded" |                                                                             |
| `byline`                                                          | string                                               | Inherited from campaign                                                     |
| `tags`                                                            | string[]                                             | Free-form                                                                   |
| `wordCount`, `readTime`, `metaDescription`, `urlSlug`, `keywords` | mixed                                                |                                                                             |
| `createdAt`, `updatedAt`, `importedAt`                            | ISO timestamps                                       |                                                                             |
| `importNotes`, `importComments`, `importVerdict`                  | strings                                              | Used during import flow                                                     |
| `revisions`                                                       | array                                                | History of `{ id, body, title, prompt, createdAt, source, triggerComment }` |
| `clientComments`                                                  | array                                                | `{ id, text, addedAt, byClientId, status }`                                 |
| `lastCitations`                                                   | array                                                | Third-party `{ title, url, isSirion: false }`                               |
| `lastSirionBacklinks`                                             | array                                                | `{ anchorText, url, embedded }`                                             |
| `lastSources`                                                     | array                                                | Combined back-compat array                                                  |
| `contentFormat`                                                   | "faq"\|"narrative"                                   | Inherited from seeded topic                                                 |
| `sourceTopicId`                                                   | string                                               | If topic-seeded                                                             |

---

## 8. M6v2 Article Kanban Statuses

| Status              | Meaning                                              | Where it appears       |
| ------------------- | ---------------------------------------------------- | ---------------------- |
| `imported-pending`  | Bulk-imported sample, awaiting AI verdict            | Articles list (admin)  |
| `imported-rejected` | AI judged it doesn't match style; needs human review | Articles list (admin)  |
| `needs-revision`    | Draft requiring AI rewrite                           | Articles list / editor |
| `revising`          | Rewrite in progress (transient)                      | Editor                 |
| `ready-for-client`  | Pushed to client review                              | Articles list + Review |
| `in-review`         | Client added comments                                | Review                 |
| `approved`          | Client signed off                                    | Approved               |
| `published`         | Live placement (manual stamp)                        | Approved               |

The brief mentions "draft → published → live" — those map to `needs-revision → published`. There is no separate `live` status; `published` is the terminal state.

---

## 9. AI Approval Workflow Steps (M6v2)

1. **Topic seeded → article record**. `addArticle` creates an article with `status: "needs-revision"`, `source: "topic-seeded"`, body = a brief, and `importComments` pre-filled with format-specific instruction. For FAQ topics:

   > Write a FAQ-style page for the client's own blog answering this question: "${topic.title}". The opening sentence MUST be a direct, concise answer to that question. Then expand with detail, examples, and one or two Sirion product references (with anchor links to sirion.com). Target persona: ${topic.persona || "general"}. Word count: ~${topic.wordCountTarget || 800} words. Tone: factual, declarative, NOT op-ed.

   For narrative topics:

   > Write a narrative article for a third-party publication on: "${topic.title}". Angle: ${topic.angleHook || "—"}. Target persona: ${topic.persona || "general"}. Lifecycle: ${topic.lifecycle || "full-stack"}. Word count: ~${topic.wordCountTarget || 1500} words. Tone: editorial, opinion-led, with industry data + cited sources. Sirion appears as proof points (anchor links), not the centre of gravity.

2. **User opens article editor → Apply AI Revision**. Calls `rewriteArticleWithFeedback({ rules, campaign, track, article, feedback })`. Provider cascade: Gemini (with `google_search` grounding, max 32768 tokens, 240s timeout) → Perplexity (sonar) → Grok (live search) → Claude (web_search_20250305). Each pass runs `normalizeRevision()` and proceeds on first body-bearing response.
3. **`auditRevision()` runs**. Returns `{ ok, warnings }`. Warnings include: body too short, < 2 Sirion backlinks, < 3 third-party citations, slug-style links, Sirion backlinks not embedded inline.
4. **Revision saved**. `article.body` overwritten; previous body archived in `article.revisions[]`; `lastCitations`, `lastSirionBacklinks`, `lastSources` updated.
5. **Push to Client Review** → status `ready-for-client`.
6. **Client adds comments** → status `in-review`. Comments live in `clientComments[]`.
7. **Each comment can become a style rule** via the "extract rule from comment" feature (uses `extractRulesFromText`).
8. **Re-rewrite** → user runs Apply AI Revision again with comments folded into the feedback box.
9. **Approve** → status `approved`. Article appears in Approved panel and is pickable by M7v2.
10. **Publish stamp** (manual) → status `published`.

---

## 10. Style Rule Library (`styleRules{}`)

Stored in `pipeline.m6v2.styleRules[id]`:

| Field             | Type                                                                            | Notes                                   |
| ----------------- | ------------------------------------------------------------------------------- | --------------------------------------- |
| `id`              | string                                                                          | `rule_<ts>_<rand>`                      |
| `rule`            | string                                                                          | The directive itself                    |
| `scope`           | "client"\|"campaign"\|"track"                                                   | Default `"client"`                      |
| `campaignId`      | string\|null                                                                    | Required when scope = campaign or track |
| `trackId`         | string\|null                                                                    | Required when scope = track             |
| `source`          | "manual"\|"extracted-from-comment"                                              |                                         |
| `sourceCommentId` | string\|null                                                                    | If extracted from a client comment      |
| `addedAt`         | ISO timestamp                                                                   |                                         |
| `status`          | "active"\|"archived"                                                            |                                         |
| `category`        | "tone"\|"structure"\|"vocabulary"\|"formatting"\|"argument"\|"framing"\|"other" |                                         |

`countApplicableRules(rules, campaignId, trackId)` powers the "12 rules active for this article" badges.

`assemblePrompt()` joins active rules as bullets, prepended to every system prompt as the non-negotiable "HOUSE STYLE RULES" block.

---

## 11. Gap-to-Article Mapping

Per the M6v2 store:

| Field               | Shape                                                                                       | Purpose                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `addressesGapIds[]` | on each topic + on each article (via topic linkage)                                         | Which gaps a topic / article closes                                     |
| `dismissedGapIds`   | `{ [campaignId]: [gapId, ...] }`                                                            | Per-campaign dismissed gaps; hidden from main list                      |
| `gapMarketDemand`   | `{ [gapId]: { searchVolumeMonthly, scanFrequency, lastEstimatedAt, source } }`              | Gemini-estimated monthly search volume + AI-scan frequency              |
| `gapDescriptions`   | `{ [gapId]: { description, placement, placementReason, manualPlacement, lastEnrichedAt } }` | AI-enriched description + placement classification with manual override |
| `lastGapRefresh`    | `{ [campaignId]: ISO }`                                                                     | Last time fresh gaps were pulled from Firebase                          |
| `topics`            | `{ [topicId]: Topic }`                                                                      | All proposed topics                                                     |

`bucketGapsByPlacement()` reads `manualPlacement || placement` per gap and routes to FAQ vs narrative buckets. A `placement = "both"` gap is fed into BOTH buckets to produce both formats.

---

## 12. Market Demand Estimation via Gemini

When a user expands a gap row, `setGapMarketDemand(gapId, demand)` caches a Gemini-estimated `{ searchVolumeMonthly, scanFrequency, lastEstimatedAt, source }`. The actual Gemini call lives in the gap panel's expand handler (not exhaustively re-quoted here; the call follows the standard `callGemini` cascade). The estimate is a soft signal — it's displayed alongside the priority score so the user can decide whether to escalate the gap.

---

## 13. Reads from Other Modules

### Legacy M6

- **`pipeline.m1.questions`** — primary input to `buildTopicPrompt`. Field key is `question.query` (with fallback to `question`/`text`/`q`).
- **`pipeline.m2`** — passed as `scanData` to topic + pack prompts. Computes mention/position/sentiment scores, competitor dominance, weak queries, citation map.
- **`pipeline.m2.contentGaps`** — input to `buildTopicFromGapsPrompt` and the gap analysis section in `buildTopicPrompt`.
- **`pipeline.m2.contentStrategyPayload`** — consumed by the Perception Gaps tab (matcher).
- **`pipeline.m3.prioritizedDomains`** — passed as `authorityData` to topic + pack prompts. Filtered to `priority >= 50 || da >= 60`.
- **`pipeline.meta.company`** — interpolated into every prompt as `${company}`.

### M6v2

- **Firebase `m2_content_gaps`** — direct read in `usePerceptionGaps`.
- **Firebase `m2_scan_meta`** — joined by `sessionIds` to resolve gap → segment.
- **`pipeline.m1` / `pipeline.m2` / `pipeline.m3`** — not directly read in V2; gaps are the only ingest path.

---

## 14. Outputs to `pipeline.m6` and `pipeline.m6v2`

### `pipeline.m6` (legacy)

| Field             | Shape                                                                                                                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `topics`          | Topic[] (see §5)                                                                                                                                         |
| `journalistPacks` | Pack[] (see §6)                                                                                                                                          |
| `articles`        | Article[] (see §7)                                                                                                                                       |
| `transfers`       | linkEntry[] — `{ id, title, domain, lifecycle, basedOn, audience, score, status: "planned", url, fromM6: true, topicId, articleWordCount, packSummary }` |
| `tags`            | `[{ id, label, startDate, endDate }]`                                                                                                                    |
| `articleBriefs`   | `{ [gapId]: { brief, selectedVenue, status, updatedAt } }` (Perception Gaps tab)                                                                         |
| `generatedAt`     | ISO timestamp of last write                                                                                                                              |
| `generationId`    | `m6_<ts>` — bumps on every write                                                                                                                         |

### `pipeline.m6v2`

| Field             | Shape                            |
| ----------------- | -------------------------------- |
| `articles`        | `{ [id]: Article }`              |
| `styleRules`      | `{ [id]: StyleRule }`            |
| `dismissedGapIds` | `{ [campaignId]: [gapId, ...] }` |
| `gapMarketDemand` | `{ [gapId]: MarketDemand }`      |
| `gapDescriptions` | `{ [gapId]: GapDescription }`    |
| `topics`          | `{ [id]: Topic }`                |
| `lastGapRefresh`  | `{ [campaignId]: ISO }`          |
| `generationId`    | numeric (Date.now() per write)   |

Note: campaigns are NOT stored in the pipeline — they live in the seed file `data/campaigns.json` and are read at module load.

---

## 15. Firestore Collections

### Legacy M6

- **`blog_db`** — written by the Blog DB importer (`upsertBlogBatch` in `blogDbImport.js`). Each row is a candidate guest-posting blog with metrics (DA, topical authority, etc.). Read by the Perception Gaps tab to power venue recommendations.
- **`m2_content_gaps`** — read indirectly via the `contentStrategyPayload`.

The brief mentions `m6_articles` and `m6_topics` — these collections **do not exist**. All M6/M6v2 article + topic data lives in the pipeline document, which the global persistenceManager flushes to Firebase as part of the pipeline blob.

### M6v2

- Reads `m2_content_gaps` and `m2_scan_meta` directly (in `usePerceptionGaps`).
- Writes nothing M6v2-specific to Firestore; pipeline-mediated only.

---

## 16. DOCX Export Logic

### Legacy `generateDocxBlob(article)` in `contentPrompts.js`

Uses the `docx` npm library. Pipeline:

1. **Meta header** — emits `Category: …`, `Word Count: …`, `Read Time: …`, etc., as gray small-text paragraphs, followed by a `———` separator.
2. **Inline formatter `fmt(text)`** — converts markdown patterns into `TextRun` arrays:
   - `**text**` → bold (Georgia 24)
   - `*text*` → italic
   - `[text](url)` → blue underlined "text" + small gray "(url)" so the publisher sees both
   - `[N]` → bold blue superscript citation marker
3. **Reference line formatter `fmtRef(text)`** — recognises lines like `[N] Label — https://url` inside the References section and renders the parts with distinct fonts/colors (the URL is blue underlined Calibri 20).
4. **Block parser** — line-by-line walks the body, skipping code fences, horizontal rules, the META block; emits `HEADING_1`, `HEADING_2`, `HEADING_3` for `#`, `##`, `###`/`####+`, bullets with Unicode `•`, and numbered list items with bold numerals. Once it sees `## References`, it switches the formatter to `fmtRef`.
5. Wraps in `Document`, packs to a Blob with the proper Word MIME type. Falls back to `Packer.toBuffer` if `Packer.toBlob` fails. Filename: `${title-slugified-60-chars}.docx`. If DOCX generation fails entirely, downloads as `.txt`.

### M6v2 `downloadArticleDocx()` in `lib/exportArticle.js`

Same library, more sophisticated:

- Uses `cleanArticleText()` to strip markdown markers, drop slug-only links, normalise bullets, drop duplicate title lines.
- Renders the Sources section from the structured `lastCitations` array (proper bullet list, title + URL) rather than parsing it from the body — the body's tail Sources section is stripped by `stripTailSourcesSection`.
- Sirion backlinks are kept inline in the body as `[anchor](url)` so the publisher preserves them as backlinks.

### Plain-text-with-footnotes export `articleAsPlainTextWithFootnotes()`

Converts inline `[anchor](url)` to numbered footnotes `[1]`, `[2]` for third-party citations. Sirion URLs are kept inline as `anchor (url)` so the publisher sees them. Two output sections: numbered "Sources" (third-party) and bulleted "Sirion Backlinks (please keep as published)".

### Clipboard copy

`copyArticleToClipboard()` writes the footnoted plain-text form to the clipboard; returns `true`/`false`.

---

## 17. Edge Cases

- **Clipboard workflow (legacy)** — Copy/paste depends on the user not editing the response. The parser is strict about `### Topic [N]:`, `### Section`, `**Field:**` markers; missing markers silently drop fields.
- **Hallucination in articles** — The article prompt forbids "Unlike other CLM platforms…" and explicit "Sirion is a full-lifecycle platform" claims. The humanize pass adds an extra preservation rule to keep all factual claims unchanged.
- **Citation accuracy** — The article prompt mandates max 3 Sirion-owned citations and ≥ 60% external. The DOCX formatter renders citation labels and full URLs side by side so publishers can copy the URL into a real hyperlink.
- **Redirect URL stripping (M6v2)** — `vertexaisearch.cloud.google.com/grounding-api-redirect`, `google.com/url?q=`, `webcache.googleusercontent.com` are stripped from sources and from inline body links by `stripRedirectLinksInBody`. Stripped links keep the anchor text so prose still flows.
- **Prose-only fallback (M6v2)** — If Gemini returns prose instead of JSON, `salvageProseAsRevision()` recovers the body and stuffs inline links into a sources array. Loses structured changes/sources but at least the user gets the article back.
- **Closure-batching bugs** — `useM6V2Store` documents that bulk inserts (`addArticles`, `addStyleRules`, `addTopics`) MUST be used instead of looping single inserts in one event handler — every iteration would otherwise read the same stale slice and only the last write would survive.
- **Mid-render persistence crash (M6v2)** — `usePerceptionGaps.refresh()` previously called `store.stampGapRefresh()` mid-fetch; that triggered a global pipeline update mid-render and caused an `insertBefore` React crash. The fix replaced it with local state.
- **Multi-pass topic generation** — `generateTopics` runs FAQ + narrative passes in parallel; each one independently falls back Gemini → Claude. If both fail, throws "Both AI passes failed. Try again — Gemini may be rate-limited."
- **Auth-error propagation (M6v2)** — `enrichOneBlog` re-throws auth/access errors so the global "access required" banner can handle them, while swallowing 502/504/parse errors as per-blog failures.
- **Token expiry (M6v2)** — Token banner re-shows whenever `sessionStorage.xt_token` is missing. Empty cleanup trigger: "Clear token" button.
- **Tag deletion** — Deleting an M6 tag nulls the `tag` field on every topic that referenced it (preserves the topics) and resets the active filter to "all" if the deleted tag was selected.
- **Stage degradation on delete** — Deleting a journalist pack flips its topic back to `draft`. Deleting an article flips its topic from `article-ready` back to `pack-ready`.
- **DATA_VERSION sensitivity** — The pipeline-wide `DATA_VERSION` constant in `PipelineContext.jsx` will wipe `pipeline.m6` and `pipeline.m6v2` from localStorage if bumped (but Firebase blob remains). Per CLAUDE.md, only bump when the data schema truly changes.

Relevant file paths:

- `/home/user/sirion-perception-shift/src/ContentStrategy.jsx`
- `/home/user/sirion-perception-shift/src/contentPrompts.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/index.jsx`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/hooks/useM6V2Store.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/hooks/usePerceptionGaps.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/lib/promptAssembly.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/lib/generateTopics.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/lib/revisionEngine.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/lib/extractRules.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/lib/enrichGap.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/lib/exportArticle.js`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/data/campaigns.json`
- `/home/user/sirion-perception-shift/src/modules/contentStrategyV2/panels/*.jsx`
