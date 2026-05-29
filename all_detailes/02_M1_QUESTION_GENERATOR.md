# 02 - M1 QUESTION GENERATOR

This document covers `src/QuestionGenerator.jsx` (~6,500 lines) and the
auxiliary file `src/data/yinMatrix.js`. M1 is the first module in the
Xtrusio growth pipeline. It generates buyer-intent questions, researches
decision makers, scores Sirion against per-persona evaluation criteria,
and exports everything to M2.

---

## 1. Plain-English Overview

M1 builds a comprehensive bank of buyer-intent questions that real CLM
decision makers might type into AI assistants (ChatGPT, Perplexity, Claude,
Gemini). Questions can come from four tiers:

1. A static seed bank `Q_BANK` of 50+ pre-written questions.
2. A static `BENCHMARK_QUESTIONS` set of 10 ground-truth queries used by
   M2 to track baseline visibility over time.
3. A static `PERCEPTION_TARGETS` map of 20 strategic queries (FIX / VOID /
   REINF) derived from the March 2026 baseline scan.
4. AI-generated questions per persona, hyper-personalized when a researched
   persona profile is available.

After generation the bank is "enriched" by an AI classifier that assigns
`personaFit`, `bestPersona`, `intentType`, `volumeTier`, and `criterion`
(linking back to one of the per-persona Decision Matrix criteria).

The Persona Research tab lets users import LinkedIn paste / CSV / web
research, runs an AI psychology profiler, and auto-generates 5 questions
per persona's pain points.

The Decision Matrix tab has two sub-views: the Yin Matrix (multi-persona
account attack grid driven by AI tech-stack detection) and the Evaluation
Scorecard (per-persona Sirion scoring across weighted criteria, with an
auto-grade button that pulls scores from M2 scan results).

Everything generated is persisted to the pipeline doc (m1.questions),
the dedicated `m1_questions_v2` Firestore collection, the `m1_personas`
collection, and to the IndexedDB knowledge base for fast local access.
The full bank is auto-exported to M2 via `pipeline.m1.questions` 1.5
seconds after any change.

---

## 2. The Three Tabs

### 2.1 Tab Navigation Bar

A row of three buttons at the top:

- **Questions** - default; always accessible.
- **Decision Matrix** - locked for `client` role. Lock icon shown when
  `auth.canTab("m1", "matrix")` is false.
- **Persona Research** - same locking pattern. Tab label includes a
  badge showing `personaProfiles.length` when there are saved profiles.

Below the tabs is a horizontal divider.

### 2.2 Auto-Generation Banner (above all tabs)

When `autoGenMsg` is set (e.g. after pain-point question gen completes),
a green-bordered card fades in with a checkmark, the message text, and
the line "Pain points auto-converted to buyer-intent questions and
added to your library". Auto-dismisses after 5-8 seconds.

### 2.3 Questions Tab UI

#### Target Personas (2-column grid)

8 buttons, sorted by `influence` descending. Each shows:

- Avatar (Pravatar URL).
- Persona label + influence percentage badge.
- Single-line description.
- Toggling toggles `activePersonas` set; resets `generated` to false (forces re-generation).

#### Topic Clusters (Bubble Chart)

SVG force-relaxed bubble chart built from `effectiveClusters` (CLUSTERS_META
merged with any AI-recalibrated weights). Bubble radius scales with
`weight` (44-82px). 120 force-relaxation iterations push overlapping
circles apart with gentle gravity toward center. Rising-trend clusters
get a small green up-arrow badge in the upper right. Hover shows a
floating tooltip with description, "why" copy, evidence (if calibrated),
and a horizontal weight bar.

A "Recalibrate" link runs `handleRecalibrate()` which calls
`callClaude` with a prompt asking for current market importance scores
(0-100) and trends per cluster. Cooldown is 30 days; counter shows next
allowed date.

#### Persona-Specific Generation Selector

Dropdown shown only when `companyPersonas.filter(p => p.researchedAt).length > 0`.
Picks `targetPersonaId` - either "all" (per-persona loop) or a specific
researched profile (single hyper-personalized call).

#### Generate Button

Triggers `handleGenerate()` -> sets `generated = true` -> reads cached
KB questions for company -> reads cached company intel -> calls
`generateAIQuestions()`.

#### Question Database / Filters / Stats

After `generated = true`, shows the merged questions list with:

- Stage funnel (5 stages: awareness, discovery, consideration, decision, validation).
- Persona distribution bars (8 personas).
- Lifecycle distribution (pre / post / full-stack).
- Source counts (static / ai / kb / pipeline / benchmark / perception-target / persona-research / manual).
- Filter dropdowns: stage, persona, jurisdiction, lifecycle, intent type, volume tier, cluster, source.
- Question rows with: query text, persona badge, stage badge, lifecycle badge, intent badge, volume badge, MiniDonut importance score.
- Bulk select checkbox per row + select-all + select-by-filter.
- "Create Segment" button (opens segment modal, persists to `user_segments`).
- "Send to M2" / Export Markdown / Copy JSON buttons.
- Manual Question Add panel (paste-AI-output workflow).

#### MiniDonut Importance Score

For each question, `computeImportance(q)` returns
`{ score, stage, intent, volume, fit }` where:

- `stage` weight: awareness=3, discovery=5, consideration=7, decision=9, validation=10.
- `intent` weight: generic=2, category=5, vendor=8, decision=10.
- `volume` weight: high=8, medium=5, niche=3.
- `fit` = `q.personaFit` (defaults to 5).
- `raw = sw*0.35 + iw*0.30 + vw*0.20 + fw*0.15`, clamped to 1-10.

The MiniDonut SVG renders four arcs (one per dimension) with a centered
score number. Color: green >= 8, amber >= 5, red below.

#### Enrichment Animation Panel

Live progress: `Mapping intent & fit scores...` -> `Filling FIT scores
& criteria...` -> `Building decision matrix...` -> `Complete`. Streams
log lines (`Batch 3/9 - 15 questions classified`).

### 2.4 Decision Matrix Tab UI

Toggle between **Yin Matrix** and **Evaluation Scorecard**.

#### Yin Matrix

- Company selector (companies derived from `personaProfiles`).
- "Detect CLM Maturity" button (cinematic AI scan).
- Phases of detection:
  1. **init** - 1.2s pause.
  2. **scanning** - cycles through DETECT_SIGNALS at 900ms each
     (Job Postings, G2/Capterra Reviews, Tech Stack Detection,
     Employee Profiles, News & Press, Vendor Case Studies, Career Page).
  3. **evidence** - reveals each parsed signal one-by-one (350ms).
  4. **verdict** - shows the final bucket assignment + pitch angle.
- Dual-engine: fires Claude + Grok in parallel via `BUCKET_DETECTION_PROMPT`,
  then `mergeDetectionResults` if both succeed.
- Active bucket displays:
  - Bucket name + tier + Sirion fit + attack angle.
  - Tech audit (ERP / procurement / HR / CLM / other / certifications / IT partners).
  - Detected tools list.
  - Company context (parent, industry, size, digital maturity, key contracts).
  - Pitch angle (entry point, quick win, narrative).
  - Pain grid: rows = pain categories, cols = personas, cells = highest-relevance pain (click to expand).
  - "Connecting thread" = single pain category that scores highest across all personas.

#### Evaluation Scorecard

- Persona tabs (8 personas).
- Per-persona criteria list (`DECISION_CRITERIA[personaId]`) with
  weight, slider 1-10, evidence textarea.
- Scores stored in `decisionScores` keyed `<personaId>.<criterionId>`.
- Auto-grade button (`handleAutoGrade`) reads `m2_scan_results` from
  Firestore and assigns scores by 3-tier matching:
  1. Question tagged with `criterion` -> match query text to scan result -> avg positioning.
  2. All questions with this persona -> match query text -> avg.
  3. Persona-level average across all scan responses.

### 2.5 Persona Research Tab UI

#### Import Mode Toggle

Three modes: **LinkedIn Paste** | **CSV / JSON Import** | **Web Research**.

- **LinkedIn Paste** - textarea, "Import from LinkedIn paste" button.
  Calls `LINKEDIN_CLEANUP_PROMPT` via `callClaudeFast`.
- **CSV / JSON Import** - file picker. Detects columns via local pattern
  match first, falls back to `CSV_MAPPING_PROMPT`.
- **Web Research** - Name + Title + Company inputs. Runs
  `PERSONA_RESEARCH_PROMPT` via `callClaude` (web search), then
  auto-generates 5 questions from pain points.

#### Researched Personas List

For each persona profile:

- Avatar (initials) + name + title + company.
- CLM Readiness score (1-10).
- Decision style + risk tolerance + innovation affinity.
- Pain points (top 3 with severity).
- Personalized question angles.
- Web findings (clickable bullets).
- Buttons: **Research** (re-run profiler), **Find Similar**
  (`FIND_SIMILAR_PROMPT`), **Generate Questions** (pain-point flow),
  **Delete**.
- Find Similar results render as a sub-table with per-row "Import + Auto-Research" button.

---

## 3. Question Object Format

Final shape after merging across all tiers (full set of fields any
downstream consumer might see):

| Field                                 | Type        | Meaning                                                                                                                                                                           |
| ------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                                  | string      | Stable id. Format depends on source: `q-NN`, `bm-N`, `pt-<bucket><N>`, `ai-<co>-<persona>-<ts>-<i>`, `pq-<co>-<persona>-<ts>-<i>`, `manual_<ts>_<i>`, `q-pipeline-<dedupHash>`.   |
| `query`                               | string      | The actual question text. **NOT `q`, `text`, or `question`** - `query` is the canonical field name across the system.                                                             |
| `persona`                             | string      | Persona id (`gc`, `cpo`, `cio`, `vplo`, `cto`, `cm`, `pd`, `cfo`). Pipeline reads sometimes carry the label form ("General Counsel") and are normalized back to id at merge time. |
| `personaId`                           | string      | Profile id (e.g. `persona-sirion-jane-doe-...`) - present on persona-research questions; tells the filter to pull from `personaGeneratedQs[pid]` instead of the main bank.        |
| `targetPersona`                       | string      | The researched persona's name when this question was generated for them.                                                                                                          |
| `stage`                               | string      | Journey stage: `awareness`, `discovery`, `consideration`, `decision`, `validation`. Manual-add path uses uppercase `PRE-SIGN`, `POST-SIGN`, `RENEWAL`.                            |
| `cluster`                             | string      | Topic cluster (one of the 9 names in CLUSTERS_META).                                                                                                                              |
| `topic`                               | string      | Manual-add path uses this; the AI/static paths use `cluster`.                                                                                                                     |
| `lifecycle`                           | string      | `pre-signature`, `post-signature`, or `full-stack`. Defaults via `CLUSTER_LIFECYCLE_MAP[q.cluster]`.                                                                              |
| `intentType`                          | string      | `generic`, `category`, `vendor`, or `decision`. Set by enrichment classifier.                                                                                                     |
| `volumeTier`                          | string      | `high`, `medium`, `niche`. Set by enrichment.                                                                                                                                     |
| `personaFit`                          | number      | 1-10. Set by enrichment classifier.                                                                                                                                               |
| `bestPersona`                         | string      | Persona id from enrichment (may differ from `persona`).                                                                                                                           |
| `criterion`                           | string      | `<personaId>.<criterionId>` linking to a Decision Matrix cell.                                                                                                                    |
| `enrichedAt`                          | ISO string  | Set when enrichment finishes.                                                                                                                                                     |
| `searchVolume`                        | number      | Manual-add path only. Estimated monthly searches.                                                                                                                                 |
| `source`                              | string      | `static`, `ai`, `kb`, `pipeline`, `benchmark`, `perception-target`, `persona-research`, `manual`.                                                                                 |
| `classification`                      | string      | `macro` or `micro`. Verified by `verifyClassification(q, company)`.                                                                                                               |
| `company`, `companyUrl`               | string      | Target company for company-specific (`micro`) questions.                                                                                                                          |
| `industry`                            | string      | Industry context.                                                                                                                                                                 |
| `confidence`                          | number      | AI-reported confidence 0-1.                                                                                                                                                       |
| `searchContext`                       | string      | "Why this question is relevant" - AI commentary.                                                                                                                                  |
| `dedupHash`                           | string      | `questionHash(query)` - the document ID in `m1_questions_v2`.                                                                                                                     |
| `generatedAt`                         | ISO string  | Creation timestamp.                                                                                                                                                               |
| `jurisdiction`                        | string      | "Global", country/region; from pain-point flow.                                                                                                                                   |
| `painPointRef`                        | string      | The pain point text this question was derived from (persona-research source only).                                                                                                |
| `ptBucket`                            | string      | When tagged as a perception target: `fix` / `void` / `reinforce`.                                                                                                                 |
| `ptScore`                             | number      | Strategic score (20-35 typical) from PERCEPTION_TARGETS.                                                                                                                          |
| `ptProblem`                           | string      | Why it matters ("3/3 AIs say post-sig").                                                                                                                                          |
| `created_at`, `updated_at`, `savedAt` | ISO strings | Various save-time stamps.                                                                                                                                                         |

---

## 4. Static Question Bank Structure

### 4.1 Q_BANK

50+ entries (line ~171 of QuestionGenerator.jsx). Each row:
`{ q, p, s, c, l }` where:

- `q` - text (with `{company}` placeholder replaced at merge time).
- `p` - persona id.
- `s` - stage.
- `c` - cluster name.
- `l` - lifecycle.

Distribution covers all 5 stages, all 8 personas, all 9 clusters, with
explicit "PRE-SIGNATURE" and "POST-SIGNATURE" sub-sections to balance
lifecycle coverage.

### 4.2 The 8 Personas (PERSONAS array)

Full influence percentages and short labels:

| id   | label                     | short | influence | desc                          |
| ---- | ------------------------- | ----- | --------- | ----------------------------- |
| cpo  | Chief Procurement Officer | CPO   | 58        | Primary CLM buyer.            |
| gc   | General Counsel           | GC    | 32        | Senior legal authority.       |
| vplo | VP Legal Operations       | VP LO | 28        | CLM evaluator and champion.   |
| pd   | Procurement Director      | PD    | 22        | Operational procurement lead. |
| cfo  | Chief Financial Officer   | CFO   | 10        | Finance influencer.           |
| cio  | Chief Information Officer | CIO   | 8         | IT influencer.                |
| cto  | VP IT / CTO               | CTO   | 6         | Technical gatekeeper.         |
| cm   | Contract Manager          | CM    | 5         | End-user champion.            |

Each persona carries `role`, `clmAngle`, `source`
("Ron, Sirion meeting 2026-02-17" or "DJ demo request..."), and
`avatar` (Pravatar URL).

### 4.3 The 5 Stages (STAGES array)

| id            | label         | color   |
| ------------- | ------------- | ------- |
| awareness     | Awareness     | #a78bfa |
| discovery     | Discovery     | #67e8f9 |
| consideration | Consideration | #fbbf24 |
| decision      | Decision      | #4ade80 |
| validation    | Validation    | #fb923c |

### 4.4 The 9 Clusters (CLUSTERS_META array)

| name                         | weight | trend  | color   | desc                                              |
| ---------------------------- | ------ | ------ | ------- | ------------------------------------------------- |
| Contract AI / Automation     | 95     | rising | #a78bfa | AI drafting, clause extraction, risk scoring.     |
| CLM Platform Selection       | 85     | rising | #60a5fa | Vendor evaluation and feature matrices.           |
| Post-Signature / Obligations | 88     | rising | #34d399 | Obligation tracking, compliance, renewals.        |
| Procurement CLM              | 74     | rising | #fbbf24 | Procurement contract management, supplier risk.   |
| Enterprise Scale             | 65     | stable | #f472b6 | Large-scale, multi-entity, global compliance.     |
| Financial Services CLM       | 58     | stable | #38bdf8 | Banking compliance, ISDA.                         |
| Implementation & ROI         | 78     | rising | #fb923c | Deployment timelines, TCO, success metrics.       |
| Analyst Rankings             | 62     | stable | #c084fc | Gartner / Forrester / IDC.                        |
| Agentic CLM                  | 82     | rising | #4ade80 | Autonomous AI agents for negotiation/remediation. |

Each carries a `why` field with a market data citation. After
recalibration, `evidence` is also set.

### 4.5 The 3 Lifecycle Stages (CLM_LIFECYCLE)

| id             | label          | color   | icon     | desc                                          |
| -------------- | -------------- | ------- | -------- | --------------------------------------------- |
| pre-signature  | Pre-Signature  | #3b82f6 | pen      | Authoring, negotiation, redlining, approvals. |
| post-signature | Post-Signature | #10b981 | check    | Obligations, compliance, renewals, SLAs.      |
| full-stack     | Full-Stack CLM | #a78bfa | infinity | End-to-end platform, analytics, integrations. |

`CLUSTER_LIFECYCLE_MAP` maps each cluster to its primary lifecycle:

| Cluster                      | Lifecycle      |
| ---------------------------- | -------------- |
| Contract AI / Automation     | pre-signature  |
| CLM Platform Selection       | full-stack     |
| Post-Signature / Obligations | post-signature |
| Procurement CLM              | full-stack     |
| Enterprise Scale             | full-stack     |
| Financial Services CLM       | full-stack     |
| Implementation & ROI         | full-stack     |
| Analyst Rankings             | full-stack     |
| Agentic CLM                  | pre-signature  |

### 4.6 CLM_MARKET_SHARE (reference table)

Tracked vendors with `share`, `arr`, `tier`, `color`. Used for vendor
mention badges. Examples: icertis 17% / ~$350M / Leader; ironclad 10% /
$200M ARR; sirion 8% / ~$160M; conga 5% / ~$100M; agiloft 4% / NOT PUBLIC;
sap ariba 6%; contractpodai 2% / ~$47M; etc. Lookup helper
`lookupShare(name)` does exact match then substring fallback.

---

## 5. AI Prompts (Verbatim)

### 5.1 LINKEDIN_CLEANUP_PROMPT (line 273)

Purpose: extract structured profile data from raw copy-pasted LinkedIn
text. Strips navigation noise. Used by `handleLinkedinImport` and by
the Find-Similar import path. Calls `callClaudeFast` (no web search).

> You are a data extraction specialist. Your ONLY job is to take raw copy-pasted LinkedIn profile text (which contains tons of noise, navigation elements, ads, "People also viewed", etc.) and extract ONLY the meaningful profile data into a clean, structured JSON.
>
> This must be FAST. Do NOT search the web. Just parse the text.
>
> Extract ONLY these fields from the raw text. If a field is not found, use null.
>
> Respond ONLY in valid JSON (no markdown, no backticks):
> {
> "name": "Full Name",
> "headline": "Their headline/tagline",
> "current_title": "Exact current job title",
> "current_company": "Current company name",
> "location": "Location",
> "about": "Their About/summary section text (truncate to 500 chars max)",
> "experience": [
>
> > {
> > "title": "Job Title",
> > "company": "Company Name",
> > "duration": "Duration text (e.g. 'Jan 2023 - Present')",
> > "description": "Brief description if available (100 chars max per role)"
> > }
> > ],
> > "education": [
> >
> > > > { "school": "School Name", "degree": "Degree", "years": "Years" }
> > > > ],
> > > > "certifications": ["Cert 1", "Cert 2"],
> > > > "skills_top": ["Top skill 1", "Top skill 2", "Top skill 3", "Top skill 4", "Top skill 5"],
> > > > "recent_activity": [
> > > >
> > > > > > > > "Brief description of recent post or share (30 words max each)"
> > > > > > > > ],
> > > > > > > > "recommendations_summary": "Brief summary of recommendation themes if any (50 words max)",
> > > > > > > > "raw_char_count": 12345,
> > > > > > > > "cleaned_char_count": 2345
> > > > > > > > }
>
> RULES:
>
> - Strip ALL navigation text, ads, "People also viewed", "More profiles", buttons, etc.
> - Keep ONLY factual profile data
> - Limit experience to last 5 roles max
> - Limit recent_activity to last 3 items max
> - Limit skills to top 5 most relevant
> - Total output must be under 2000 characters
> - Be FAST - this is a preprocessing step

Output schema: JSON object with the fields above. Parser: `callClaudeFast`
returns parsed JSON via `parseClaudeJson`. The result is stored as
`persona.cleanedProfile` and `detectPersonaType(cleaned.current_title)`
maps it to one of the 8 persona ids.

---

### 5.2 PERSONA_RESEARCH_PROMPT (line 318)

Purpose: deep-research a decision maker, build a psyche profile + pain
points + buying triggers. Uses `callClaude` (with web search). Today's
date is interpolated at module load.

> You are a Senior Sales Psychologist and Decision Maker Profiler specializing in Enterprise CLM (Contract Lifecycle Management).
>
> Today's date: <localized current date>.
>
> YOUR MISSION: Research this decision maker deeply. Understand their psyche, decision-making DNA, pain points, and buying triggers. Make this SO detailed that anyone reading it can craft perfectly personalized outreach.
>
> RESEARCH PROCESS:
>
> 1. USE the LinkedIn profile data provided as primary source
> 2. SEARCH the web for this person's public activity, interviews, conference talks, published articles
> 3. SEARCH for their company's challenges in contract management, legal operations, procurement
> 4. ANALYZE their career trajectory for CLM buying signals
> 5. PROFILE their decision-making style based on role, experience, and activity
>
> OUTPUT - Respond ONLY with valid JSON (no markdown):
> {
> "psycheProfile": {
> "decisionStyle": "analytical|consensus|visionary|pragmatic",
> "riskTolerance": "low|medium|high",
> "innovationAffinity": "conservative|moderate|progressive",
> "buyingTriggers": ["trigger1", "trigger2", "trigger3"],
> "communicationPreference": "data-driven|narrative|peer-validated",
> "motivations": ["What drives this person professionally"],
> "concerns": ["What keeps them up at night re: contracts"]
> },
> "painPoints": [
>
> > { "pain": "Specific pain point description", "severity": "high|medium|low", "relevance": "How this relates to CLM" }
> > ],
> > "priorities": ["Top 3-5 business priorities for this person"],
> > "clmReadiness": 7.5,
> > "researchSummary": "3-4 sentence deep profile of this person's mindset, needs, and likely CLM evaluation approach",
> > "personalizedQuestionAngles": [
> >
> > > > "Specific angle for generating questions that resonate with this person"
> > > > ],
> > > > "webFindings": [
> > > >
> > > > > > > > "Key finding from web research about this person or their company"
> > > > > > > > ]
> > > > > > > > }
>
> RULES:
>
> - Be SPECIFIC, not generic. Reference actual career details, company situations, industry challenges.
> - buyingTriggers: What would make this person evaluate a CLM platform TODAY
> - painPoints: Must be role-specific (CPO cares about procurement, GC about legal risk, etc.)
> - clmReadiness: 1-10 score based on all signals
> - personalizedQuestionAngles: These will be used to generate hyper-personalized questions

Output schema: JSON object with `psycheProfile`, `painPoints`, `priorities`,
`clmReadiness`, `researchSummary`, `personalizedQuestionAngles`,
`webFindings`. Parser: standard `callClaude` -> `parseClaudeJson`.

Triggered from:

- `handleWebResearchImport` - new persona via name/title/company.
- `handleResearchPersona` - re-research an existing persona.
- `handleSimilarRowImport` - import + research a Find-Similar suggestion.

---

### 5.3 FIND_SIMILAR_PROMPT (line 364)

Purpose: given a researched decision maker, find 8-10 similar CLM-relevant
people at comparable companies. Uses `callClaude` (web search).

> You are a Senior B2B Market Intelligence Analyst specializing in CLM (Contract Lifecycle Management) buyers.
>
> YOUR MISSION: Given a researched decision maker, find 8-10 similar CLM-relevant people at comparable companies. Use web search to find real people.
>
> SIMILARITY CRITERIA:
>
> - Same or adjacent industry
> - Revenue within 0.5x-2x of source company
> - Same geographic market (same country / region)
> - Similar contract complexity: enterprise B2B, multi-department, high volume
>
> PERSONA COVERAGE: Mix buyer roles - GC, CPO, CIO, VP Legal Ops, CFO, CTO, Contract Manager, Procurement Director. Prioritize the buying committee most relevant to this industry.
>
> LINKEDIN URL RULES:
>
> - Confirmed person with known profile: use https://linkedin.com/in/firstname-lastname format
> - Otherwise: use https://www.linkedin.com/search/results/people/?keywords=FirstName+LastName+CompanyName
> - confidence 0.85+ = you found a real profile URL; 0.6 = best-guess search
>
> OUTPUT - valid JSON only, no markdown:
> {
> "sourceContext": "One sentence: why these targets match",
> "suggestions": [{
>
> > "name": "First Last",
> > "title": "Chief Procurement Officer",
> > "company": "CompanyName",
> > "companyUrl": "https://company.com",
> > "linkedinUrl": "https://linkedin.com/in/...",
> > "linkedinSearchUrl": "https://www.linkedin.com/search/results/people/?keywords=First+Last+CompanyName",
> > "location": "City, Country",
> > "companySize": "1,000-5,000",
> > "companyRevenue": "$200M-$500M",
> > "industry": "Enterprise Software",
> > "personaType": "cpo",
> > "clmSignals": "10K+ contracts/year; dedicated contract ops team hired 2024",
> > "confidence": 0.85,
> > "reason": "Same SaaS vertical, similar revenue, CPO is primary CLM buyer"
> > }]
> > }

Output schema: `{ sourceContext, suggestions: [{ name, title, company, ... }] }`.
Suggestions render in a per-persona table with paste-LinkedIn input + Import button.

---

### 5.4 QUESTION_GEN_SYSTEM (line 403)

Purpose: master system prompt for generating buyer-intent questions.
Today's date is interpolated at module load.

> You are a Senior CLM Market Intelligence Analyst specializing in buyer-intent question research for enterprise Contract Lifecycle Management (CLM) platforms.
>
> Today's date: <localized current date>.
>
> YOUR MISSION:
> Generate highly specific, research-backed buyer-intent questions that real decision makers would type into AI assistants (ChatGPT, Perplexity, Gemini, Claude) when evaluating CLM solutions.
>
> RESEARCH PROCESS:
>
> 1. SEARCH the web for the target company: recent news, funding, product launches, partnerships, customer wins, analyst mentions
> 2. SEARCH for competitive landscape: head-to-head comparisons, analyst rankings, market positioning
> 3. SEARCH for current CLM industry trends: new AI capabilities, regulatory changes, market shifts
> 4. Generate questions incorporating REAL findings
>
> QUESTION TYPES:
>
> - MACRO (industry-wide, ~40%): Apply broadly across CLM industry, no specific vendor mentioned
> - MICRO (company-specific, ~60%): Reference the specific company, competitors, recent events, unique differentiators
>
> JOURNEY STAGES:
>
> - awareness: Buyer realizes they have a contract management problem
> - discovery: Buyer actively researching CLM solutions and vendors
> - consideration: Buyer comparing specific vendors, doing deep evaluation
> - decision: Buyer making final choice, looking for validation
> - validation: Buyer post-purchase, confirming ROI and adoption
>
> CLM LIFECYCLE STAGES (CRITICAL - tag every question):
>
> - "pre-signature": Authoring, templates, redlining, negotiation, clause intelligence, approvals, collaboration
> - "post-signature": Obligation tracking, compliance, SLA monitoring, renewals, amendments, performance management
> - "full-stack": End-to-end platform, analytics, vendor selection, integrations, implementation, repository
>
> OUTPUT FORMAT - Respond ONLY with valid JSON (no markdown wrapping):
> {
> "companyIntel": {
> "keyFindings": ["finding1", "finding2", "finding3"],
> "competitors": ["comp1", "comp2"],
> "recentNews": ["news1", "news2"],
> "marketPosition": "brief summary"
> },
> "questions": [
>
> > {
> > "q": "The full question text",
> > "p": "persona_id",
> > "s": "stage_id",
> > "c": "Topic Cluster Name",
> > "l": "pre-signature|post-signature|full-stack",
> > "classification": "macro or micro",
> > "context": "Brief note on why this question is relevant",
> > "confidence": 0.85
> > }
> > ]
> > }
>
> RULES:
>
> - Generate 15-25 questions total
> - Cover at least 3 different personas from the provided list
> - Cover at least 3 different journey stages
> - Cover ALL 3 lifecycle stages (pre-signature, post-signature, full-stack) - aim for balanced coverage
> - Each question must be 10-30 words
> - MICRO questions MUST use the actual company name (not {company})
> - MACRO questions must NOT mention any specific company
> - Every question must be something a real person would type into AI search
> - Avoid generic questions - incorporate real web research findings
> - DO NOT duplicate existing questions provided below

When invoked from the **specific-person mode** the prompt is augmented with:

- "PERSONAS:" + list of `${id}: ${label}`.
- "TOPIC CLUSTERS:" + comma-joined active clusters.
- A "TARGET DECISION MAKER" block: name, title, company, decision style,
  risk tolerance, buying triggers, pain points, priorities, research summary.
- Instruction to make questions HYPER-PERSONALIZED.
- "EXISTING QUESTIONS (DO NOT DUPLICATE)" with the first 30 cached questions.

Output schema: `{ companyIntel: { keyFindings, competitors, recentNews, marketPosition }, questions: [{ q, p, s, c, l, classification, context, confidence }] }`. The `companyIntel` is saved into IndexedDB, Firebase (`m1_company_intel`), and `pipeline.m1.companyIntel`.

---

### 5.5 buildPersonaQuestionPrompt(ctx, persona, clusters, company, existing, alreadyGenerated, matchedProfile) (line 618)

Purpose: per-persona prompt builder used in PER-PERSONA MODE (one API
call per active persona, each from that persona's cognitive lens).

The prompt template (interpolated, not a static constant):

> You generate buyer-intent questions that a ${ctx.title} would type into AI assistants (ChatGPT, Perplexity, Claude, Gemini) when evaluating CLM software.
>
> PERSONA LENS - ${ctx.title.toUpperCase()}:
> ${ctx.lens}
>
> KPIs they are measured on: ${ctx.kpis.join(", ")}
> Their priorities:
> ${ctx.priorities.map(p => `- ${p}`).join("\n")}
>
> Their vocabulary: ${ctx.language.join(", ")}
> They WOULD ask about: ${ctx.wouldAsk.join(", ")}
> They would NEVER ask about: ${ctx.wouldNotAsk.join(", ")}

Optional matched-profile block:

> REAL DECISION MAKER PROFILE - make questions hyper-specific to this person:
> Name: ${matchedProfile.name} - ${matchedProfile.title} at ${matchedProfile.company}
> Decision style: ${matchedProfile.psycheProfile.decisionStyle}
> Risk tolerance: ${matchedProfile.psycheProfile.riskTolerance}
> Buying triggers: ${...}
> Pain points: ${...}
> Priorities: ${...}
> Profile: ${matchedProfile.researchSummary}

Then:

> TOPIC CLUSTERS TO COVER: ${clusters.join(", ")}
>
> QUESTION TYPES:
>
> - MACRO (~40%): Industry-wide, no specific vendor mentioned
> - MICRO (~60%): Reference ${company} or specific competitors
>
> JOURNEY STAGES: awareness, discovery, consideration, decision, validation
> CLM LIFECYCLE: pre-signature, post-signature, full-stack
>
> RULES:
>
> - Generate exactly 12 questions
> - EVERY question must authentically reflect the ${ctx.title}'s cognitive lens and vocabulary
> - Questions must sound like what THIS specific role would type - not what any generic executive asks
> - 10-30 words each, natural phrasing (as typed into a search bar, not formal language)
> - Cover at least 3 different journey stages and all 3 lifecycle stages
>
> DO NOT DUPLICATE THESE QUESTIONS:
>
> 1. <existing question 1>
> 2. <existing question 2>
>    ... (up to 30)
>
> OUTPUT - valid JSON only, no markdown:
> {"companyIntel":{"keyFindings":[],"competitors":[],"recentNews":[],"marketPosition":""},"questions":[{"q":"...","s":"stage","c":"cluster","l":"lifecycle","classification":"macro|micro","context":"why this persona would ask this","confidence":0.9}]}

Each `ctx` is a `PERSONA_CONTEXTS[personaId]` entry containing
`title`, `lens`, `kpis`, `priorities`, `language`, `wouldAsk`,
`wouldNotAsk`. See section 7 below for the complete context for each
persona.

---

### 5.6 PAIN_TO_QUESTIONS_PROMPT (line 838)

Purpose: convert a researched persona's pain points into 5 buyer-intent
questions. Uses `callClaudeFast` (no web search).

> You are a Senior CLM Market Intelligence Analyst. Convert decision maker pain points into buyer-intent questions.
>
> RULES:
>
> - Generate exactly 5 high-quality questions (1 per pain point, pick the top 5 pain points)
> - Questions must sound like what this person would TYPE into ChatGPT, Perplexity, or Google
> - Each question must be specific to the person's role, company, and jurisdiction/region
> - Include jurisdiction-aware angles (regulatory environment, local business practices, regional compliance)
> - Questions should map to buying journey stages: awareness, consideration, or discovery
> - CRITICAL: The "c" field MUST be one of these EXACT cluster names: "Contract AI / Automation", "CLM Platform Selection", "Post-Signature / Obligations", "Procurement CLM", "Enterprise Scale", "Financial Services CLM", "Implementation & ROI", "Analyst Rankings", "Agentic CLM"
> - CRITICAL: The "l" field MUST be one of: "pre-signature", "post-signature", "full-stack"
>   - pre-signature: Questions about contract authoring, templates, redlining, negotiation, approvals, clause intelligence
>   - post-signature: Questions about obligation tracking, compliance, SLA monitoring, renewals, amendments, performance
>   - full-stack: Questions about end-to-end CLM platform, analytics, integrations, vendor selection, implementation
>
> OUTPUT - Respond ONLY with valid JSON (no markdown):
> {
> "questions": [
>
> > {
> > "q": "The full question text",
> > "p": "persona_type_id (gc, cpo, cio, vplo, cto, cm, pd, cfo)",
> > "s": "awareness|consideration|discovery",
> > "c": "One of the exact cluster names listed above",
> > "l": "pre-signature|post-signature|full-stack",
> > "painRef": "Which pain point this addresses",
> > "jurisdiction": "Country or region (e.g. Bahrain, UAE, US, EU, UK, India, Global)",
> > "confidence": 0.85
> > }
> > ]
> > }

Output schema: `{ questions: [{ q, p, s, c, l, painRef, jurisdiction, confidence }] }`.

The user message includes the persona's name, title, company, location/jurisdiction,
industry, formatted pain points (with severity + relevance), and psyche
profile (decision style + risk tolerance + communication preference).

`generateQuestionsFromPainPoints(persona)` then runs cluster-name fuzzy
normalization on the response (handles AI variations like "automation" ->
"Contract AI / Automation"), assigns `lifecycle` from
`CLUSTER_LIFECYCLE_MAP` if missing, dedups against existing questions by
`dedupHash`, saves to IndexedDB + macros + Firebase, and stores per-persona
in `personaGeneratedQs[persona.id]`.

Includes retry logic: 3 attempts at delays `[0, 45000, 75000]` ms to
clear rate-limit windows.

---

### 5.7 CSV_MAPPING_PROMPT (line 869)

Purpose: AI-fallback for mapping unknown CSV column headers to the target
schema (used only when `tryLocalMapping` fails). Calls `callClaudeFast`.

> You are a data mapping specialist. Given CSV column headers, map them to our target schema.
>
> TARGET FIELDS (map each source column to one of these):
>
> - name: Person's full name
> - title: Job title / position
> - company: Company / organization name
> - linkedin_url: LinkedIn profile URL
> - company_url: Company website URL
> - location: City, country, or region
> - email: Email address (optional)
> - phone: Phone number (optional)
> - notes: Any additional notes (optional)
> - SKIP: Column should be ignored
>
> OUTPUT - Respond ONLY with valid JSON (no markdown):
> {
> "mapping": { "source_column_name": "target_field", ... },
> "confidence": 0.95,
> "unmapped": ["columns that don't match any target field"]
> }

Output schema: `{ mapping: {<src>: <target>}, confidence, unmapped }`.

---

### 5.8 Cluster Recalibration Prompt (inline in handleRecalibrate, line 1539)

Purpose: rescore the 9 clusters' market importance + trend. Uses
`callClaude` (web search). 30-day cooldown.

> You are a B2B SaaS market analyst specializing in Contract Lifecycle Management (CLM). You will receive a list of CLM topic clusters. For each cluster, use current web data to assess its MARKET IMPORTANCE (0-100) and TREND (rising/stable/declining).
>
> Base your scores on:
>
> - Search volume and buyer interest signals
> - Analyst report mentions (Gartner, Forrester, IDC)
> - Industry news and investment activity
> - Community discussions (Reddit, LinkedIn, G2)
> - Vendor marketing emphasis
>
> Return ONLY a valid JSON array, no markdown, no explanation:
> [{"name":"exact cluster name","weight":number,"trend":"rising|stable|declining","evidence":"one sentence citing specific data"}]
>
> The weight should reflect RELATIVE importance to CLM buyers right now. The highest-demand cluster should be 90-98, the lowest 45-65. Be precise - don't cluster them all around 70-80.

User message:

> Analyze the current market importance of these CLM topic clusters as of <Month Year>:
> <comma-separated cluster names>
> Use web search to find current data on each cluster's demand, growth, and buyer interest in the CLM market.

Output schema: `[{ name, weight, trend, evidence }]`. The handler validates
each entry against `CLUSTERS_META`, persists to
`localStorage["xt_cluster_cal"]` and `pipeline.m1.clusterCalibration`,
and updates `clusterWeights`/`lastCalibrated`. Requires at least 5 clusters
matched or it errors out.

---

### 5.9 Enrichment / Classification Prompt (inline in enrichQuestions, line 1666)

Purpose: classify a batch of 15 questions per call to add `personaFit`,
`bestPersona`, `intentType`, `volumeTier`, and `criterion`. Uses
`callClaudeFast`.

The criteria list interpolated comes from `Object.entries(DECISION_CRITERIA)`
flattened to `<personaId>.<criterionId>`:

> You classify CLM buyer-intent questions. Return a JSON array. Each element has:
> idx (integer), personaFit (1-10), bestPersona (gc|cpo|cio|vplo|cto|cm|pd|cfo), intentType (generic|category|vendor|decision), volumeTier (high|medium|niche), criterion (string or null).
>
> intentType: generic=no vendor/category; category=CLM topic, no specific vendor; vendor=names a vendor; decision=comparison/ROI/evaluation
> volumeTier: high=broad awareness (thousands/month); medium=category evaluation; niche=specific evaluation (dozens/month)
> criterion must be one of: <comma-joined list of all <persona>.<criterion_id> keys>
>
> Respond with ONLY a valid JSON array. No markdown, no explanation.
> Example: [{"idx":0,"personaFit":7,"bestPersona":"gc","intentType":"vendor","volumeTier":"niche","criterion":"gc.playbook_enforcement"},{"idx":1,"personaFit":4,"bestPersona":"cio","intentType":"generic","volumeTier":"high","criterion":null}]

User message: `0: [persona] question text\n1: [persona] question text...`
(15 per batch).

Output schema: `[{ idx, personaFit, bestPersona, intentType, volumeTier, criterion }]`.
Parser: validates each value against allowed enums, clamps `personaFit`
to 1-10, writes to local DB, then asyncly fans out to Firebase
(`m1_questions_v2/<dedupHash>`).

---

### 5.10 AI_PROMPT_TEMPLATE (line 2493) - Manual Question Add

Purpose: the prompt the USER copies and pastes into their own AI tool;
the user then pastes the JSON back. Not run from the app. Surfaced inside
the Manual Add panel with a Copy button.

> Generate search questions for a B2B SaaS company. Return a JSON array only - no markdown, no explanation, just the array.
>
> Each question must follow this exact format:
> {
> "query": "The question text (a real search query someone would type)",
> "persona": "Job title of the person asking (e.g. CIO, CFO, Legal Counsel, Procurement Manager)",
> "stage": "Buyer stage - must be one of: PRE-SIGN, POST-SIGN, RENEWAL",
> "topic": "Topic cluster or theme (e.g. Contract Risk, AI Automation, Vendor Management)",
> "intentType": "Must be one of: REINF (reinforcement/brand), EDUC (educational), COMP (competitive), NAVIG (navigational), TRANS (transactional)",
> "searchVolume": <estimated monthly searches as integer, 0 if unknown>,
> "personaFit": <1-10 how relevant to this persona>
> }
>
> Generate [N] questions about [TOPIC/THEME]. Focus on [PERSONA] buyers at [STAGE] stage.

Parser: `parseManualPaste(text)` strips markdown fences, parses JSON,
falls back to regex `/\[[\s\S]*\]/`. Validates each item:

- `query` must be a string with length >= 5.
- `persona` required.
- `stage` must be in `{ "PRE-SIGN", "POST-SIGN", "RENEWAL" }` (uppercased).
- `topic` required.
- `intentType` must be in `{ "REINF", "EDUC", "COMP", "NAVIG", "TRANS" }` (uppercased).

Each parsed question is given `id: "manual_<ts>_<i>"`, `source: "manual"`,
`searchVolume`/`personaFit` defaults, `dedupHash`, and timestamps. On
save: writes to `m1_questions_v2`, IndexedDB, and prepends to
`pipeline.m1.questions`.

---

### 5.11 BUCKET_DETECTION_PROMPT (from `src/data/yinMatrix.js` line 507)

Purpose: full enterprise tech audit + CLM maturity classification used by
the Yin Matrix. Run via `callClaude` AND `callGrok` in parallel; results
merged via `mergeDetectionResults`. The 8 bucket summaries (`BUCKET_SUMMARY`)
are interpolated.

> You are an elite sales intelligence analyst specializing in enterprise software. Your job is to do a COMPREHENSIVE technology audit of a company - not just CLM tools, but their ENTIRE digital infrastructure - then classify their CLM maturity.
>
> ## PHASE 1: DEEP COMPANY RESEARCH (search the web thoroughly)
>
> Research EVERY angle. Cast a wide net:
>
> 1. **Parent company / group structure** - Who owns them? Are they part of a holding group? Does the parent have an IT/tech arm?
> 2. **ERP & core systems** - SAP (which modules?), Oracle, Microsoft Dynamics, Workday, etc. Check job postings for "SAP Analyst", "Oracle Developer", etc.
> 3. **Procurement tools** - Coupa, SAP Ariba, Jaggaer, GEP, any procurement automation
> 4. **HR systems** - SuccessFactors, Workday, BambooHR, RemoteApps, etc.
> 5. **CLM / Contract tools** - Icertis, Agiloft, DocuSign CLM, Ironclad, Sirion, etc. (this may be NONE)
> 6. **Digital transformation initiatives** - AI projects, IoT sensors, paperless systems, automation partnerships
> 7. **Industry partnerships** - tech vendors they work with (Wipro, Accenture, Infosys, etc.)
> 8. **Certifications** - ISO 27001, SOC 2, GDPR compliance, industry-specific certifications
> 9. **Major contracts/deals** - big supplier agreements, government contracts, sustainability financing
> 10. **News & press releases** - recent technology announcements, digital strategy statements
>
> SEARCH QUERIES TO USE (adapt company name):
>
> - "[company] SAP implementation"
> - "[company] digital transformation"
> - "[company] technology partnership"
> - "[company] careers IT OR software OR SAP OR procurement"
> - "[company] contract management software"
> - "[company] OR [parent company] technology OR digital OR innovation"
> - "site:linkedin.com [company] SAP OR CLM OR procurement OR contract"
>
> ## PHASE 2: CLM MATURITY CLASSIFICATION
>
> Based on ALL findings, assign to one of these 8 CLM maturity buckets:
>
> <BUCKET_SUMMARY interpolated: 1. "<id>" - <name>: <description> Tools: <toolExamples>>
>
> CONFIDENCE SCORING:
>
> - 3+ signals pointing to same tool/bucket = HIGH (0.8-1.0)
> - 2 signals = MEDIUM (0.5-0.7)
> - 1 signal or inference = LOW (0.2-0.4)
>
> ## PHASE 3: PITCH INTELLIGENCE
>
> Based on the full tech audit, generate a Sirion-specific sales angle:
>
> - What existing systems can Sirion integrate with?
> - What is the "wedge" - the easiest entry point?
> - What narrative ties their existing digital investments to the CLM gap?
>
> ## RESPONSE FORMAT (JSON only, no markdown fences):
>
> {
> "bucketId": "<bucket_id>",
> "bucketName": "<bucket name>",
> "confidence": <0.0-1.0>,
> "reasoning": "<3-4 sentences explaining the classification based on evidence>",
>
> "techAudit": {
> "erp": ["<ERP systems found, e.g. SAP S/4HANA, Oracle EBS>"],
> "procurement": ["<procurement tools found>"],
> "hr": ["<HR systems found>"],
> "clm": ["<CLM/contract tools found - empty array if none>"],
> "other": ["<other enterprise software, IoT, AI tools found>"],
> "certifications": ["<ISO, SOC, compliance certifications>"],
> "itPartners": ["<implementation partners like Wipro, Accenture>"]
> },
>
> "companyContext": {
> "parentCompany": "<parent/holding company name or null>",
> "parentTechArm": "<if parent has a tech/IT subsidiary, name it>",
> "industry": "<primary industry>",
> "size": "<small/medium/large/enterprise>",
> "digitalMaturity": "<archaic/basic/growing/mature/advanced>",
> "keyContracts": "<notable large contracts, deals, or financing mentioned in news>"
> },
>
> "signals": [
>
> > {"source": "<source type>", "detail": "<specific finding>", "url": "<URL if available>"}
> > ],
>
> "pitchAngle": {
> "entryPoint": "<what existing system/pain makes Sirion an easy add>",
> "quickWin": "<first module/use case to propose>",
> "narrative": "<2-3 sentence pitch tying their digital investments to the CLM gap>"
> },
>
> "detectedTools": ["<ALL tools found across all categories>"],
> "companySize": "<small/medium/large/enterprise>",
> "industry": "<primary industry>",
> "isHybrid": false,
> "secondaryBucketId": null
> }

Parser: `parseBucketDetectionResponse(rawResponse)` (in yinMatrix.js)
strips markdown fences, validates `bucketId` against `TECH_BUCKETS` (with
fuzzy fallback by `bucketName`), normalizes `techAudit` arrays,
`companyContext`, and `pitchAngle`. Clamps `confidence` to 0-1, takes
first 15 signals, returns `{ bucketId, bucketName, confidence,
detectedTools, signals, reasoning, companySize, industry, isHybrid,
secondaryBucketId, techAudit, companyContext, pitchAngle, detectedAt }`.

`mergeDetectionResults(claudeResult, grokResult)` picks the higher-confidence
result as primary, marks `enginesAgree` if `bucketId` matches.

---

## 6. CSV Import Flow

### 6.1 detectPersonaType(title) (line 477)

Lowercases the input title and matches in this priority order:

1. `general counsel` / `chief legal` / (`legal` && `head`) -> `gc`.
2. (`procurement` && (`chief` || `vp` || `head`)) || `cpo` -> `cpo`.
3. `cio` || `chief information` || (`information` && `officer`) -> `cio`.
4. `legal operations` || `legal ops` -> `vplo`.
5. `cto` || `chief technology` || (`vp` && `it`) -> `cto`.
6. `contract manager` || `contract management` || `contracts lead` -> `cm`.
7. `procurement director` || `sourcing director` -> `pd`.
8. `cfo` || `chief financial` || (`finance` && `officer`) -> `cfo`.
9. Default -> `cm`.

Empty title -> `cm`.

### 6.2 Two-Step CSV Mapping

Step A: `tryLocalMapping(headers)` - matches lowercased headers against
known patterns:

- name: `name, full_name, person_name, contact_name, first_name, fullname, person`
- title: `title, job_title, position, role, designation, job_role`
- company: `company, company_name, organization, org, employer, firm, organisation`
- linkedin_url: `linkedin_url, linkedin, linkedin_profile, li_url, profile_url, linkedin_link`
- company_url: `company_url, website, company_website, url, web, site, domain`
- location: `location, city, country, region, geography, geo, address, jurisdiction, hq`
- email: `email, email_address, mail, e_mail`

Returns the mapping if at least `name` is matched, else null.

Step B: If local fails, `callClaudeFast(CSV_MAPPING_PROMPT, ...)` with
the headers and 3 sample rows. Uses the AI mapping result.

### 6.3 Parsing

`parseCSVLine(line)` handles quoted fields and escaped `""` quotes.

For each parsed row, builds a persona object with:

- Auto-detected `personaType` via `detectPersonaType(title)`.
- Empty `experience`, `education`, `certifications`, `skillsTop`, `recentActivity`.
- `source: "csv-import"`.
- `psycheProfile: null`, `painPoints: []`, etc. (no AI research yet).
- `id: persona-<companySlug>-<nameSlug>-<ts>-<i>`.

Saves all to IndexedDB via `savePersonas` and to Firebase via individual
`db.saveWithId("m1_personas", id, ...)` calls.

JSON file path is also supported - same parsing skips the CSV step.

---

## 7. Question Merge Logic (Pipeline -> Q_BANK -> KB -> AI)

The `questions` useMemo (line 1287) builds the displayed bank only when
`generated === true`. Uses a `seenMap` keyed by `questionHash(query)` to
dedupe.

`addQ(q, opts)` either adds a new entry or merges into an existing one:

- `mergeMetadata: true` - fill missing `persona, stage, cluster, lifecycle, classification`.
- `mergeEnrichment: true` - always overwrite `personaFit, bestPersona, intentType, volumeTier, criterion, enrichedAt`.
- `mergeOnly: true` - never add new entries (used when pipeline is the source of truth).

### Tier order

| Tier | Source                                  | Add new?            | Merge metadata?                                   | Merge enrichment? |
| ---- | --------------------------------------- | ------------------- | ------------------------------------------------- | ----------------- |
| 1    | Pipeline (`pipelineQuestions`)          | yes                 | no                                                | no                |
| 1.5  | `BENCHMARK_QUESTIONS` (10 ground-truth) | only if no pipeline | yes                                               | no                |
| 1.6  | `PERCEPTION_TARGETS` (20 strategic)     | only if no pipeline | adds `ptBucket / ptScore / ptProblem` to existing | no                |
| 2    | `Q_BANK` (50+ static)                   | only if no pipeline | yes                                               | no                |
| 3    | `kbQuestions` (IndexedDB cache)         | only if no pipeline | yes                                               | yes               |
| 4    | `aiQuestions` (current session)         | yes                 | no                                                | yes               |

Pipeline normalizes `persona`: if pipeline stored a label
("General Counsel"), `PERSONAS.find(p => p.id === q.persona || p.label === q.persona)?.id`
maps it back to `gc`.

`{company}` in Q_BANK templates is replaced with the active company name.

### Pipeline Cleanup

A separate effect (`pipelineCleanedRef`) runs once per session: dedups
`pipeline.m1.questions` by `questionHash(query)` and writes back if any
duplicates were removed (with new `generatedAt` and `generationId`).

---

## 8. exportToM2() (line 2688)

Always exports the FULL bank (`questions` array, not the filtered or
selected subset) to `pipeline.m1.questions`. Each exported question
carries id, persona (as id), stage, query, cluster, source,
classification, lifecycle, intentType, personaFit, bestPersona,
volumeTier, criterion, enrichedAt.

Also writes `personas: [...activePersonas]`, `clusters: [...activeClusters]`,
`generatedAt`, `generationId` (new ISO timestamp - downstream M2 / M3 use
this to detect staleness), `aiGenerated`, `kbLoaded`, `companyIntel`,
`decisionScores`, and a slim `personaProfiles` array (for M4 consumption).

Also copies a JSON-serialized payload to clipboard and shows
`exportCopied = true` for 2.5 seconds.

Auto-trigger: a `useEffect` runs `exportToM2()` 1.5 seconds after
`generated && questions.length > 0` changes, plus 0.5 seconds after
enrichment completes.

---

## 9. Decision Matrix and Decision Scores

### 9.1 DECISION_CRITERIA (line 671)

Per-persona criterion lists, each with `id`, `label`, `weight` (1-9):

| Persona  | Criteria                                                                                                                                                                                                                           |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **gc**   | Playbook Enforcement at Scale (9), Third-Party Paper Handling (8), Regulatory Compliance GDPR/DPA (9), Clause Risk Scoring (7), M&A Due Diligence Velocity (7), Litigation Risk Prevention (8), External Counsel Spend Control (6) |
| **cpo**  | Supplier Obligation Tracking (9), Spend Under Management Visibility (8), Rogue Spend Control (7), Auto-Renewal Management (8), Vendor Compliance Tracking (7), Supplier Risk & ESG (6)                                             |
| **cio**  | ERP/CRM Integration Depth (9), Data Security & Residency (9), API Capabilities (8), SSO & Access Management (7), AI Governance & Explainability (7), Change Management & Adoption (6)                                              |
| **vplo** | Workflow Automation (9), Cycle Time Reduction (9), Self-Service Contract Tools (8), Headcount Efficiency (8), Legal Metrics Dashboard (7), Tech Stack Rationalization (7)                                                          |
| **cto**  | AI Model Quality & Accuracy (9), Security Architecture SOC 2 (9), API-First Architecture (8), Enterprise Scalability (8), AI Training Data Quality (7), Build vs Buy Flexibility (7)                                               |
| **cm**   | Renewal & Deadline Alerts (9), Approval Workflow Speed (9), Template Management (8), Amendment & Version Control (8), Contract Search & Repository (8), Counterparty Collaboration (7)                                             |
| **pd**   | Vendor Negotiation Support (8), Auto-Renewal Trap Detection (8), Supplier Contract Compliance (8), Procurement Templates (7), Category Spend from Contracts (7), Vendor Onboarding Speed (6)                                       |
| **cfo**  | Financial Exposure Visibility (9), Revenue Recognition Compliance ASC 606 (9), Contract Value Leakage Detection (9), CLM ROI Measurement (8), Board-Level Portfolio Reporting (7), Financial Controls Integration (7)              |

### 9.2 Score Storage

`decisionScores` keyed by `<personaId>.<criterionId>` -> score 1-10.
Persisted to:

- `localStorage["xt_decision_scores"]` (legacy fallback).
- `pipeline.m1.decisionScores` (canonical, debounced 2 seconds).

Restored from pipeline when localStorage is empty (cross-domain deploy
recovery).

### 9.3 handleAutoGrade()

Reads `db.getAllPaginated("m2_scan_results")`. For each scan result, takes
the average `positioning` value across all non-error analyses.

Builds two indexes:

- `queryScore[query.toLowerCase().trim()]` -> avg.
- `personaScoreList[personaId]` -> array of scores -> averaged into `personaAvg`.

Persona label normalization map: `"general counsel" -> "gc"`, etc.

Per `(persona, criterion)` cell, three matching strategies in order:

1. Questions tagged with `criterion === key` -> match query text -> avg.
2. All questions for this persona -> match query text -> avg.
3. Persona-level average from scan.

Final score clamped to 1-10. Writes to state, localStorage, and pipeline.
Sets `autoGradeSource = { scoredAt: <time>, count: <cells filled> }`.

---

## 10. Yin Matrix Integration (`src/data/yinMatrix.js`)

### 10.1 TECH_BUCKETS (8 buckets)

Each bucket: `{ id, name, description, signals, severity, sirionFit, attackAngle, toolExamples }`.

| id               | name                                     | severity | sirionFit | Tools                                         |
| ---------------- | ---------------------------------------- | -------- | --------- | --------------------------------------------- |
| stone_age        | Stone Age (No dedicated tool)            | 10       | high      | Email, file attachments, Google Drive, paper  |
| basic_digital    | Basic Digital (Storage with structure)   | 9        | high      | SharePoint, OneDrive, Google Docs, Notion     |
| esign_only       | Point Solution - E-Signature Only        | 8        | high      | DocuSign standalone, Adobe Sign, HelloSign    |
| procurement_side | Point Solution - Procurement Side        | 7        | high      | Coupa, SAP Ariba, Jaggaer, Ivalua, GEP, Zycus |
| legal_side       | Point Solution - Legal Side              | 7        | high      | Ironclad, ContractPodAi, Juro, Linkpoint      |
| midmarket_clm    | Mid-Market CLM (Partial lifecycle)       | 5        | medium    | Conga, Agiloft, ContractWorks, DocuSign CLM   |
| enterprise_clm   | Enterprise CLM - Competitor              | 3        | medium    | Icertis, SAP CLM, Apttus/Conga Enterprise     |
| ai_native        | Modern AI-Native CLM (Where Sirion sits) | 1        | low       | Sirion, Evisort, Onit                         |

### 10.2 PAIN_CATEGORIES (7 categories)

`compliance_risk`, `cost_leakage`, `cycle_time`, `visibility_gap`,
`integration_friction`, `renewal_risk`, `scalability` - each with a label
and color.

### 10.3 PAIN_LIBRARY

Bucket-keyed lists of `{ id, category, painText, businessImpact, sirionSolution }`.
Stone Age has 8 pains, the others have similar counts.

### 10.4 Helper Functions Exported

- `detectBucketFromSignals(signals)` - rule-based bucket assignment by counting matched signal substrings.
- `getPainsForPersona(bucketId, personaType)` - returns the relevant pains for a given persona/bucket pair.
- `findConnectingThread(bucketId, personaTypes)` - returns the single pain category that scores highest across all personas, plus its `categoryInfo`.
- `buildPainGrid(bucketId, personas)` - returns the rendered grid data for the Yin Matrix UI.
- `getBucketById(bucketId)`, `getBucketOptions()` - lookup helpers.
- `BUCKET_DETECTION_PROMPT` - the AI prompt (covered above).
- `parseBucketDetectionResponse(raw)` - validates + normalizes AI output.
- `mergeDetectionResults(claude, grok)` - merges two engine outputs.

### 10.5 PERSONA_PAIN_WEIGHTS

Per-persona weight table that biases which pain categories matter most
to each role. Used by `buildPainGrid` to score cell relevance.

---

## 11. Persona Profile Structure (`personaProfiles[i]`)

| Field                                                                                             | Description                                                                                                             |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `id`                                                                                              | `persona-<companySlug>-<nameSlug>-<ts>`                                                                                 |
| `personaType`                                                                                     | One of the 8 persona ids (auto-detected via `detectPersonaType`).                                                       |
| `name`, `title`, `company`, `companyUrl`, `location`, `linkedinUrl`                               | Identity fields.                                                                                                        |
| `headline`, `about`, `experience[], education[], certifications[], skillsTop[], recentActivity[]` | LinkedIn-derived.                                                                                                       |
| `source`                                                                                          | `linkedin-paste`, `csv-import`, `web-research`, `find-similar`.                                                         |
| `rawLinkedinText`                                                                                 | Original paste before cleanup.                                                                                          |
| `cleanedProfile`                                                                                  | Output of `LINKEDIN_CLEANUP_PROMPT`.                                                                                    |
| `researchSummary`                                                                                 | 3-4 sentence profile from `PERSONA_RESEARCH_PROMPT`.                                                                    |
| `psycheProfile`                                                                                   | `{ decisionStyle, riskTolerance, innovationAffinity, buyingTriggers, communicationPreference, motivations, concerns }`. |
| `painPoints`                                                                                      | `[{ pain, severity, relevance }]`.                                                                                      |
| `priorities`                                                                                      | `[string]`.                                                                                                             |
| `clmReadiness`                                                                                    | 1-10.                                                                                                                   |
| `webFindings`                                                                                     | `[string]` of key findings from web search.                                                                             |
| `personalizedQuestionAngles`                                                                      | `[string]`.                                                                                                             |
| `m4AnalysisId, m4Stage, m4ReadinessScore, m4AnalyzedAt`                                           | Set by Buying Stage Guide module.                                                                                       |
| `createdAt, updatedAt, researchedAt`                                                              | Timestamps.                                                                                                             |

Slim version pushed to `pipeline.m1.personaProfiles` strips heavy fields
(no `experience`, no `webFindings`) so the pipeline doc stays under
Firestore's 1MB limit; full versions live in `m1_personas` collection
and IndexedDB store `personas`.

---

## 12. PERCEPTION_TARGETS Constant

A static object literal of 20 high-impact queries derived from the March
2026 baseline scan (`scan-1772486077116`). Shape:

```
PERCEPTION_TARGETS = {
  fix:       [{ q, p, s, c, l, score, problem }, ... ] // 9 items
  void:      [{ q, p, s, c, l, score, problem }, ... ] // 7 items
  reinforce: [{ q, p, s, c, l, score, problem }, ... ] // 4 items
}
```

Buckets:

- **fix** - "Sirion mentioned but framed wrong" (e.g. "3/3 AIs say post-sig").
- **void** - "Sirion not mentioned at all" (e.g. "0/3 AIs mention Sirion").
- **reinforce** - "Partial coverage - reinforce" (e.g. "Claude absent, 2/3 post-sig").

`PT_BUCKET_CONFIG` provides label/color/bg styling per bucket (FIX red,
VOID orange, REINF teal).

**Stale risk**: this constant is hardcoded based on a specific scan run.
When new scans happen the data is not auto-refreshed. Documented as a
design choice - these are the targets the team is currently writing
content against.

The merge logic in `questions` useMemo (Tier 1.6) tags any matching
existing pipeline question with `ptBucket / ptScore / ptProblem`, or
adds it as a new entry if no pipeline exists.

---

## 13. Firestore Collections Used by M1

| Collection         | docId                                 | Contents                                                                                                                                                               |
| ------------------ | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `m1_questions_v2`  | `dedupHash`                           | All questions ever generated. Each doc carries the full question shape (section 3). Updated via `db.saveWithId` in async loops with 30-50ms throttling between writes. |
| `m1_personas`      | `persona.id`                          | Full persona profiles (with cleanedProfile, painPoints, etc.).                                                                                                         |
| `m1_macros`        | `dedupHash`                           | Macro-classified questions (same shape as questions).                                                                                                                  |
| `m1_company_intel` | `companyKey` (lowercased dashed name) | `{ companyKey, companyName, url, industry, lastResearchedAt, keyFindings, competitors, recentNews, marketPosition }`.                                                  |
| `user_segments`    | `<creatorSlug>_<nameSlug>_<ts>`       | `{ id, name, creatorName, creatorEmail, questionIds, questions, questionCount, createdAt }`.                                                                           |
| `pipelines`        | shared user docId                     | The slim pipeline document carrying everything else.                                                                                                                   |

---

## 14. Pipeline Outputs (`pipeline.m1.*`)

Every field updated by M1:

| Field                | Type                                                | Source                                                             |
| -------------------- | --------------------------------------------------- | ------------------------------------------------------------------ |
| `questions`          | `Question[]`                                        | exportToM2 (debounced 1.5s after gen).                             |
| `personas`           | `string[]`                                          | `[...activePersonas]` ids.                                         |
| `clusters`           | `string[]`                                          | `[...activeClusters]` names.                                       |
| `generatedAt`        | ISO string                                          | exportToM2.                                                        |
| `generationId`       | ISO string                                          | exportToM2 / pipeline cleanup; consumed by M2/M3 staleness checks. |
| `aiGenerated`        | number                                              | `sourceCounts.ai`.                                                 |
| `kbLoaded`           | number                                              | `sourceCounts.kb`.                                                 |
| `companyIntel`       | object                                              | Latest AI-researched company intel.                                |
| `decisionScores`     | `{ [personaId.criterionId]: 1-10 }`                 | Manual + auto-grade.                                               |
| `personaProfiles`    | slim profile array                                  | Synced when personaProfiles state changes.                         |
| `clusterCalibration` | `{ weights: {[name]:{weight,trend,evidence}}, ts }` | handleRecalibrate.                                                 |
| `yinMatrix`          | (reserved)                                          | Set elsewhere if Yin state is persisted.                           |
| `scanBatch`          | `{ questions, createdAt, name, scanType }`          | createSegment - hands a curated set to M2.                         |
| `pendingSegment`     | full segment object                                 | createSegment - lets M2 know a fresh segment is queued.            |
| `segments`           | `Segment[]`                                         | List of all user segments.                                         |

---

## 15. Edge Cases and Known Gotchas

### 15.1 Field-Name Hygiene

The canonical question text field is `query`, NOT `q`, `text`, or `question`.
Multiple bugs traced to this in the past. The static Q_BANK and the AI
prompts use `q` for brevity; conversion to `query` happens at the
`addQ()` boundary inside the `questions` useMemo.

### 15.2 Persona Form

Pipeline writes sometimes carry the label form ("General Counsel") instead
of the id (`gc`). The merge logic normalizes via
`PERSONAS.find(p => p.id === x || p.label === x)?.id`.

### 15.3 Generated Flag

`questions` returns `[]` until the user explicitly clicks Generate
(`setGenerated(true)`). No auto-restore on mount. Avoids forcing the
heavy merge before the user wants to see data.

### 15.4 Pipeline Source-of-Truth

When pipeline has questions, lower tiers use `mergeOnly: true` - they
ONLY enrich existing pipeline entries, never add new ones. Otherwise the
bank would balloon every reload as Q_BANK / BENCHMARK / PERCEPTION_TARGETS
re-add their static entries.

### 15.5 Persona-Research Restoration

Persona-generated questions (`source === "persona-research"`) are
restored at boot with a 3-tier fallback: `q.personaId` field ->
`q.targetPersona` matching `loadedPersonas[i].name` -> question id prefix
match (`pq-<co>-<personaId[0:20]>-...`). The third tier exists because
older question records were written before `personaId` was added.

### 15.6 IndexedDB Singleton Reset

`questionDB.openDB()` resets `_dbPromise` on `onclose` and `onversionchange`
so another tab upgrading the DB doesn't hang the current tab.

### 15.7 Auto-Enrichment

A useEffect watches `autoEnrichPending` and triggers `enrichQuestions()`
once both `aiLoading` and `enrichmentLoading` are false and questions
exist. This is set inside `generateAIQuestions` after every successful
generation.

### 15.8 Rate-Limit Retry on Pain-Point Generation

`generateQuestionsFromPainPoints` is wrapped in 3 attempts at delays
`[0, 45000, 75000]` ms in both `handleWebResearchImport` and
`handleResearchPersona`. The 45s+75s spans cover the typical 1-minute
rate window.

### 15.9 Cluster Recalibration Cooldown

`CALIBRATION_COOLDOWN_MS = 30 days`. The button is disabled and shows
the next allowed date until that window passes.

### 15.10 Decision Score Restore on New Domain

A useEffect copies `pipeline.m1.decisionScores` into local state when
local state is empty (handles the case where the user signs in from a
different machine and localStorage starts blank).

### 15.11 Mass-Save Throttling

Every Firebase save loop (`for (const q of arr) { await
db.saveWithId(...); await sleep(50); }`) intentionally throttles to
avoid hitting the 429 circuit breaker. 30-50ms between writes is the
standard.

### 15.12 ManualParse JSON Recovery

`parseManualPaste` tolerates: outer ` ```json ` fence, leading/trailing
prose, single-object instead of array (auto-wraps), mixed casing on
`stage` and `intentType` (uppercased in validation).

### 15.13 Verifier Flips Misclassified Questions

`verifyClassification(q, company)` overrides AI's `classification` field
to `micro` when:

- The query mentions the target company (lowercased).
- The query mentions any of `CLM_COMPETITORS` (icertis, ironclad,
  agiloft, docusign, conga, juro, contractpodai, spotdraft, coupa, concord).
- The query contains a recent-time signal (`Q1-Q4 2025-2027`, `series
A-D`, `just announced`, `recently`, `new feature`).

### 15.14 Persona Profile Slim Sync

`updateModule("m1", { personaProfiles: [...] })` writes a SLIM version
to the pipeline (no `experience`, no `webFindings`, no
`personalizedQuestionAngles`). Full versions live in `m1_personas`
Firestore + IndexedDB. This keeps the pipeline doc under Firestore's 1MB
ceiling.

### 15.15 Topic vs Cluster Naming

Manual-add path uses `topic` while AI / static paths use `cluster`. They
mean the same thing but downstream code generally reads `cluster`.
Manual questions appear in M1 with the `topic` field populated and may
need normalization if M2 filters strictly by `cluster`.
