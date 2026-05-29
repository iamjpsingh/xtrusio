# M4 — Buying Stage Guide

> Source files:
>
> - `src/BuyingStageGuide.jsx` (~2,255 lines)
> - `src/data/yinMatrix.js` (CLM maturity bucket database, helpers)

---

## 1. What M4 Does

M4 is **buyer-readiness intelligence on a single decision-maker at a specific company**. The user pastes a LinkedIn profile + a company website URL. M4 cleans the LinkedIn text, deeply researches the company across the web, and produces a JSON report covering: who the decision maker is, what the company looks like, their tech stack signals, hiring signals, digital footprint, competitor CLM usage, decision-maker readiness signals, primary buying stage, readiness score (1-10), confidence rating, a personalized outreach hook, recommended actions, risk factors, and a CLM maturity bucket detection.

Each analysis is saved to Firestore (`analyses` collection). The user can then verify the report (catches stale M&A info / role changes), generate an outreach script, view per-account history, and see a CLM Maturity Radar across analyzed accounts.

M4 is the only module that consumes a person's LinkedIn profile as primary input.

---

## 2. User Workflow Step-by-Step

1. **Open M4 → "Analyze" tab.**
2. **Pick a persona from M1 (optional).** If selected, the readiness analysis links back to that M1 persona via `m4AnalysisId`.
3. **Paste the company website URL** (e.g. `https://walmart.com`).
4. **Paste the raw LinkedIn profile text** for the decision maker (Ctrl+A → Ctrl+C from LinkedIn — includes a lot of navigation noise, ads, "People also viewed", etc.).
5. Click **Analyze**.
6. **Pass 0 (LinkedIn cleanup)** — `callClaudeFast(LINKEDIN_CLEANUP_PROMPT, raw)` strips the noise and returns a clean structured profile JSON. Fast — no web search.
7. **Pass 1 (Deep research)** — `callClaude(ANALYSIS_PROMPT, userMsg)` is invoked with the cleaned LinkedIn JSON + company URL + today's date. This call uses web search to fetch the company website, look up tech stack, hiring patterns, M&A activity, and competitor CLM usage. Returns the full JSON report. While this runs the UI cycles through 8 loading steps every 3.5s.
8. **Auto-display the report** in the "Report" tab.
9. **CLM Maturity bucket detection** runs locally via `detectBucketFromSignals()` against the report's tech / competitor / digital signals → assigns one of 8 buckets (`stone_age` → `ai_native`).
10. **Pipeline push** — calls `updateModule("m4", { analyses, latestStage, latestReadiness, companyBuckets, analyzedAt, generationId })`.
11. **Firebase save** — `db.save("analyses", {...})` returns a docId; the local `history` list is updated.
12. **(Optional) Verify** — user clicks "Verify" → `runVerification()` calls `VERIFICATION_PROMPT` (max 3 web searches) to catch stale claims. Corrections are merged via `mergeCorrections(analysis, verification)`.
13. **(Optional) Generate Outreach** — `generateOutreach()` interpolates `{ANALYSIS_DATA}` and `{VERIFICATION_DATA}` into `OUTREACH_PROMPT` and asks Claude for a personalized outreach report (waste-metric breakdown, lifecycle stage mapping, CTA).
14. The user can revisit any past analysis from the **History** tab or view the account intelligence summary in **Accounts**.

---

## 3. Every Prompt — Verbatim

### 3.1 `LINKEDIN_CLEANUP_PROMPT` — Pass 0 (no web search, fast)

**Purpose**: Strip the noise from a raw LinkedIn copy-paste and emit a clean structured profile JSON. Speed-optimized via `callClaudeFast()`.

**Verbatim text**:

    You are a data extraction specialist. Your ONLY job is to take raw copy-pasted LinkedIn profile text (which contains tons of noise, navigation elements, ads, "People also viewed", etc.) and extract ONLY the meaningful profile data into a clean, structured JSON.

    This must be FAST. Do NOT search the web. Just parse the text.

    Extract ONLY these fields from the raw text. If a field is not found, use null.

    Respond ONLY in valid JSON (no markdown, no backticks):
    {
      "name": "Full Name",
      "headline": "Their headline/tagline",
      "current_title": "Exact current job title",
      "current_company": "Current company name",
      "location": "Location",
      "about": "Their About/summary section text (truncate to 500 chars max)",
      "experience": [
        {
          "title": "Job Title",
          "company": "Company Name",
          "duration": "Duration text (e.g. 'Jan 2023 - Present · 2 yrs')",
          "description": "Brief description if available (100 chars max per role)"
        }
      ],
      "education": [
        { "school": "School Name", "degree": "Degree", "years": "Years" }
      ],
      "certifications": ["Cert 1", "Cert 2"],
      "skills_top": ["Top skill 1", "Top skill 2", "Top skill 3", "Top skill 4", "Top skill 5"],
      "recent_activity": [
        "Brief description of recent post or share (30 words max each)"
      ],
      "recommendations_summary": "Brief summary of recommendation themes if any (50 words max)",
      "raw_char_count": 12345,
      "cleaned_char_count": 2345
    }

    RULES:
    - Strip ALL navigation text, ads, "People also viewed", "More profiles", buttons, etc.
    - Keep ONLY factual profile data
    - Limit experience to last 5 roles max
    - Limit recent_activity to last 3 items max
    - Limit skills to top 5 most relevant
    - Total output must be under 2000 characters
    - Be FAST — this is a preprocessing step

**Output JSON schema**: as shown above. `truncate to 500 chars max` for about, max 5 experiences, max 3 recent_activity items, max 5 skills, total under 2000 chars.

**Parser behavior**: `JSON.parse()` directly inside `callClaudeFast()`. If parsing fails, the user message falls back to a truncated raw string so Pass 1 still has SOMETHING to work with.

---

### 3.2 `ANALYSIS_PROMPT` — Pass 1 (deep research)

**Purpose**: Senior Sales Intelligence Analyst persona. Combines the cleaned LinkedIn JSON, the company website (via fetch), and 5+ web searches into a comprehensive readiness analysis.

**Verbatim text**:

    You are a Senior Sales Intelligence Analyst specializing in Enterprise SaaS and CLM (Contract Lifecycle Management) for Sirion.

    CRITICAL: Today's date is {TODAY}. All information MUST reflect CURRENT status as of today.

    You will receive:
    1. A CLEANED LINKEDIN PROFILE (structured JSON) of the decision maker — this has been pre-processed to extract name, title, company, work history, skills, certifications, and activity. Use this as your primary source for the decision maker's identity and background.
    2. A COMPANY WEBSITE URL — fetch this URL to get official company information.
    3. Then do additional web searches for deeper intelligence.

    STEP-BY-STEP PROCESS:
    1. USE the cleaned LinkedIn JSON to identify:
       - Full name, exact current title, current company
       - Location
       - About/summary section (reveals priorities and pain points)
       - Complete work history (previous companies — check if any used CLM tools)
       - Skills & certifications (IACCM, legal ops = huge CLM signal)
       - Recent activity/posts (engaging with CLM, procurement tech, or vendor content?)
       - Education

    2. FETCH the company website URL to get:
       - Official company description, size, industry
       - Leadership team pages
       - News/press releases
       - Product/service information

    3. SEARCH the web for:
       - Tech Stack & Legacy Indicators (SharePoint, DocuSign, SAP Ariba, Coupa, competitor CLMs like Icertis, Ironclad, Agiloft)
       - Current hiring patterns (Legal Ops, Contract Admin, Procurement Transformation roles)
       - M&A activity, regulatory news, growth signals
       - Competitor CLM usage evidence
       - Industry-specific contract management challenges

    4. CROSS-REFERENCE the LinkedIn work history:
       - Did they previously work at a company known to use CLM? (This signals familiarity)
       - Did they come from a consulting firm? (May have seen CLM implementations)
       - How long in current role? (New = mandate to change; Long tenure = established relationships)
       - Any certifications like IACCM, PMP, Six Sigma? (Process maturity signals)

    5. ANALYZE LinkedIn activity:
       - Posts/shares about procurement, contracts, legal ops, digital transformation
       - Following/engaging with CLM vendor content
       - Conference attendance signals
       - Thought leadership on relevant topics

    For EVERY M&A deal or major event, do a SEPARATE search to confirm CURRENT status.

    Respond ONLY in valid JSON (no markdown, no backticks):
    {
      "decision_maker": {
        "name": "Full Name",
        "title": "Exact Current Title from LinkedIn",
        "company": "Current Company",
        "location": "Location",
        "tenure_current_role": "How long in current role",
        "previous_roles": [
          { "title": "Previous Title", "company": "Company", "duration": "X years", "clm_relevance": "Did this company use CLM? Any relevant experience?" }
        ],
        "certifications": ["cert1", "cert2"],
        "linkedin_activity_signals": ["Posted re: procurement transformation", "Shared vendor consolidation article"],
        "profile_summary_insights": "2-3 sentence max insights from About section"
      },
      "company_profile": {
        "industry": "Industry",
        "estimated_revenue": "Revenue",
        "employee_count": "Count",
        "headquarters": "Location",
        "global_presence": "Description",
        "recent_news": "Key developments WITH CURRENT STATUS AND DATES",
        "website_insights": "Key info gathered from fetching the company URL"
      },
      "analysis": {
        "tech_stack": { "findings": "2 sentences max. Be concise.", "signals": ["s1","s2","s3"], "score": 7 },
        "hiring_patterns": { "findings": "2 sentences max.", "signals": ["s1","s2"], "score": 5 },
        "digital_footprint": { "findings": "2 sentences max.", "signals": ["s1","s2"], "score": 6 },
        "competitor_usage": { "findings": "2 sentences max.", "signals": ["s1"], "score": 4 },
        "decision_maker_signals": {
          "findings": "2 sentences max about this person's readiness signals from LinkedIn",
          "signals": ["Previous employer used Icertis", "Shared CLM article", "IACCM certified"],
          "score": 7
        }
      },
      "stage_scores": { "awareness": 6, "consideration": 8, "discovery": 3 },
      "primary_stage": "consideration",
      "confidence": "high",
      "readiness_score": 7.2,
      "outreach_hook": "PERSONALIZED hook based on their specific LinkedIn activity, background, and company situation. Max 3 sentences.",
      "recommended_actions": ["action1","action2","action3","action4","action5"],
      "risk_factors": ["risk1","risk2","risk3","risk4"],
      "summary": "2-3 sentence executive summary",
      "personalization_notes": "Specific things to reference in outreach based on LinkedIn"
    }

    STRICT FORMATTING RULES — FOLLOW EXACTLY:
    - "signals" arrays: Each signal MUST be 3-7 words MAX. These are short TAGS, not sentences. Examples: "No CLM Platform Detected", "SAP Ariba Ecosystem", "Active M&A Integration", "Posted About Supply Chain". NEVER write full sentences like "SAP ecosystem presence creates natural pathway to SAP Ariba consideration" — that's wrong.
    - Max 4-5 signals per dimension. Pick the strongest ones only.
    - "findings": Max 2 short sentences per dimension. Be dense, not verbose.
    - "linkedin_activity_signals": Max 8 words each. Examples: "Posted re: procurement transformation", "Shared vendor consolidation article".
    - "recommended_actions": Exactly 4-5 actions. Each max 15 words. Start with verb.
    - "risk_factors": Exactly 3-4 risks. Each max 15 words.
    - "outreach_hook": Max 3 sentences.
    - "profile_summary_insights": Max 3 sentences.

`{TODAY}` is interpolated at module top via `new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })` — e.g. `"Saturday, May 9, 2026"`.

**Output JSON schema**: see above. Top-level fields: `decision_maker`, `company_profile`, `analysis` (5 dimensions each with findings + signals + 0-10 score), `stage_scores`, `primary_stage`, `confidence`, `readiness_score`, `outreach_hook`, `recommended_actions`, `risk_factors`, `summary`, `personalization_notes`.

**Parser behavior**: `callClaude()` extracts the text from Claude's response, strips any wrapping markdown fences, and `JSON.parse()`s the result. If parse fails the call surfaces an error to the UI.

**Strict word-limit rules** (enforced via the prompt itself, not code):

- `signals[]` — 3-7 words MAX each, max 4-5 per dimension, tag-style not sentences.
- `findings` — max 2 short sentences per dimension.
- `linkedin_activity_signals` — max 8 words each.
- `recommended_actions` — exactly 4-5, each max 15 words, start with verb.
- `risk_factors` — exactly 3-4, each max 15 words.
- `outreach_hook` — max 3 sentences.
- `profile_summary_insights` — max 3 sentences.

---

### 3.3 `VERIFICATION_PROMPT` — On-demand fact-check

**Purpose**: Cheap, fast verification pass. Catches what would embarrass the sales team (deal closed vs pending, person no longer holds the role, ownership change).

**Verbatim text**:

    You are a quick fact-checker. Today is {TODAY}.

    Verify a sales intelligence report. Do ONLY 2-3 targeted web searches max:
    1. "[Company] acquisition merger latest 2025 2026" — check if any deal status changed
    2. "[Person] [Company] current role" — confirm they still hold the role
    3. Only if needed: "[Company] public private status"

    DO NOT search every claim. Only catch what would cause EMBARRASSMENT (deal closed vs pending, person left, etc).

    Respond ONLY in valid JSON (no markdown, no backticks):
    {
      "verification_timestamp": "{ISO timestamp}",
      "overall_accuracy": "high|medium|low",
      "total_claims_checked": 3,
      "corrections_needed": 0,
      "corrections": [
        { "severity": "high", "original_claim": "text", "corrected_claim": "text", "field_path": "field.path", "evidence": "source" }
      ],
      "verified_claims": [
        { "claim": "text", "status": "confirmed", "source": "source" }
      ],
      "updated_summary": null,
      "updated_outreach_hook": null,
      "updated_risk_factors": null,
      "freshness_notes": "One sentence"
    }

    CRITICAL: Max 3 searches. Be fast. Only flag things that would embarrass the sales team.

**Output JSON schema**: as above. Returns corrections that include a `field_path` like `"company_profile.recent_news"`.

**Parser / merge behavior** — `mergeCorrections(analysis, verification)`:

- If `updated_summary` is set, replace `analysis.summary`.
- If `updated_outreach_hook` is set, replace `analysis.outreach_hook`.
- If `updated_risk_factors` is non-empty array, replace `analysis.risk_factors`.
- For each correction, walk `field_path.split(".")` into the analysis object. If the target field is a string and contains the original_claim text, replace it; otherwise append `" [UPDATED: {corrected_claim}]"`.

The corrected analysis is saved back to Firestore (`analysis_data: corrected`, `verification_data: result`, `verified: true`, `verified_at: now`).

---

### 3.4 `OUTREACH_PROMPT` — Personalized outreach script generator

**Purpose**: Generate a buyer-stage-specific outreach narrative grounded in verified data + LinkedIn personalization. Includes a financial-impact "waste metrics" block, a lifecycle stage mapping (Vendor Selection → Authoring → Approval → Obligations → Renewals), and a CTA.

**Verbatim text**:

    You are a Senior Sales Strategist for Sirion, the leading AI-native CLM platform.

    CRITICAL: Today is {TODAY}. Use CORRECTED/VERIFIED data only.

    ANALYSIS DATA:
    {ANALYSIS_DATA}

    VERIFICATION CORRECTIONS:
    {VERIFICATION_DATA}

    Generate a detailed, PERSONALIZED outreach report. Use the decision maker's LinkedIn background, activity, and specific situation to make this feel hand-crafted — not generic.

    Key personalization from LinkedIn:
    - Reference their specific background/previous roles where relevant
    - Use their recent activity/posts to show you understand their priorities
    - Reference certifications or expertise areas
    - Connect their career trajectory to why CLM matters NOW

    Generate as valid JSON ONLY (no markdown, no backticks):
    {
      "stage_section": {
        "headline": "Bold direct headline (max 8 words)",
        "stage_name": "awareness|consideration|discovery",
        "diagnosis": "3-4 sentence diagnosis speaking TO the prospect using VERIFIED data AND LinkedIn insights",
        "current_state_bullets": [
          {"label": "Current Reality", "detail": "1-2 sentences max based on VERIFIED signals"},
          {"label": "Industry Position", "detail": "1-2 sentences max on where they stand vs peers"},
          {"label": "Risk Exposure", "detail": "1-2 sentences max on compliance/risk implications"}
        ]
      },
      "why_section": {
        "headline": "Data headline like 'You're Losing $X.XM Every Year'",
        "summary": "1-2 sentence financial impact overview",
        "total_estimated_waste": "$24.1M",
        "waste_metrics": [
          { "category": "Revenue Leakage", "stat": "9.2%", "dollar_value": "$9.2M", "description": "lost to poor contract terms", "source": "World Commerce & Contracting 2024" },
          { "category": "Cycle Time Waste", "stat": "3.4 wks", "dollar_value": "$8.2M", "description": "avg contract cycle time", "source": "Aberdeen Group CLM Study" },
          { "category": "Compliance Risk", "stat": "$4.5M", "dollar_value": "$4.5M", "description": "penalty exposure", "source": "Deloitte Regulatory Cost Index" },
          { "category": "Resource Drain", "stat": "42 hrs/wk", "dollar_value": "$3.8M", "description": "manual admin per dept", "source": "McKinsey Operations Report" },
          { "category": "Missed Renewals", "stat": "24%", "dollar_value": "$6.1M", "description": "unfavorable auto-renewals", "source": "Gartner Procurement Research 2024" }
        ]
      },
      "how_section": {
        "headline": "Sirion: Your Partner at Every Stage",
        "intro": "1-2 sentences mapping to their lifecycle",
        "lifecycle_stages": [
          { "stage": "Vendor Selection", "icon": "🔍", "current_pain": "Max 15 words", "sirion_solution": "Max 15 words", "key_features": ["f1","f2"], "outcome": "60% faster", "score": 85 },
          { "stage": "Authoring", "icon": "✍️", "current_pain": "Max 15 words", "sirion_solution": "Max 15 words", "key_features": ["f1","f2"], "outcome": "45% shorter", "score": 70 },
          { "stage": "Approval", "icon": "✅", "current_pain": "Max 15 words", "sirion_solution": "Max 15 words", "key_features": ["f1","f2"], "outcome": "70% faster", "score": 90 },
          { "stage": "Obligations", "icon": "📋", "current_pain": "Max 15 words", "sirion_solution": "Max 15 words", "key_features": ["f1","f2"], "outcome": "95% visibility", "score": 95 },
          { "stage": "Renewals", "icon": "🔄", "current_pain": "Max 15 words", "sirion_solution": "Max 15 words", "key_features": ["f1","f2"], "outcome": "$XM saved", "score": 80 }
        ]
      },
      "closing": {
        "cta_headline": "Personalized CTA (max 6 words)",
        "cta_body": "2-3 sentence personalized closing referencing THEIR LinkedIn activity or background"
      }
    }

    STRICT FORMATTING RULES:
    - "current_pain" and "sirion_solution": Max 15 words each. Be punchy.
    - "key_features": Exactly 2 features per stage, each 2-3 words.
    - "outcome": Short metric like "60% faster" or "$6.1M saved". Max 4 words.
    - "score": Number 0-100 representing Sirion's impact for that lifecycle stage.
    - "dollar_value": Must be a dollar amount string like "$9.2M".
    - "stat": A punchy number/percentage.
    - "description": Max 8 words.

`{ANALYSIS_DATA}` and `{VERIFICATION_DATA}` are interpolated via `.replace()` with `JSON.stringify()` of the analysis and verification objects respectively.

**Output JSON schema**: top-level `stage_section`, `why_section`, `how_section`, `closing`. Five lifecycle stages always rendered (Vendor Selection / Authoring / Approval / Obligations / Renewals). The 5 waste-metrics categories reference real industry sources (WorldCC, Aberdeen, Deloitte, McKinsey, Gartner).

**Parser**: same `callClaude()` JSON-parse path. The output is rendered as a printable PDF via `DownloadPDFBtn`.

---

## 4. The 6 Analysis Dimensions

`analysis` field in the ANALYSIS_PROMPT output. Five are explicitly enumerated; the **sixth** (`decision_maker_signals`) covers the human side.

| Dimension                | What it captures                                                                                                                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tech_stack`             | What CLM-adjacent tools the company uses today (SharePoint, DocuSign, SAP Ariba, Coupa, competitor CLMs like Icertis / Ironclad / Agiloft). 2 sentences findings + 4-5 short tag signals + 0-10 score. |
| `hiring_patterns`        | Open roles signaling readiness — Legal Ops, Contract Admin, Procurement Transformation, Vendor Management, Risk Ops. 2 sentences + signals + score.                                                    |
| `digital_footprint`      | Press releases, blog posts, industry presentations, conference talks revealing maturity / digital transformation initiatives.                                                                          |
| `competitor_usage`       | Direct evidence of a competitor CLM (Icertis customer logo on their website, joint case study with Ironclad, etc.).                                                                                    |
| `decision_maker_signals` | Person-specific readiness — past employer used CLM, IACCM certified, posted about contract automation, attended CLM conferences. Pulls from the cleaned LinkedIn JSON.                                 |

The 5 dimensions each have a 0-10 score; together they feed the `readiness_score`.

---

## 5. Stage Scoring

`stage_scores` is an object with `awareness`, `consideration`, `discovery` — each 0-10. Rules expressed in the prompt rather than enforced in code:

- **awareness** — does the prospect even know they have a contract problem?
- **consideration** — are they actively evaluating CLM solutions?
- **discovery** — are they aware of vendors but still in early-fit assessment?

`primary_stage` is the AI's pick of which one dominates (string: `"awareness"` / `"consideration"` / `"discovery"`). It's surfaced as the headline stage on the report.

The local `STAGE_CONFIG` constant maps each stage to a color and label for UI rendering. There is no automated "highest score wins" — the AI picks `primary_stage` holistically given the signals.

---

## 6. `readiness_score` (1-10)

A single decimal float. Implicit weighting (per the prompt):

- Strong tech_stack signals (legacy tools = high readiness for upgrade) → +
- Active hiring of Legal Ops / Contract Admin → +
- Recent M&A or compliance pressure → +
- Decision maker has CLM-relevant background → +
- Competitor already in place (displacement opportunity) → context-dependent

The score is rendered as a `RadialScore` SVG in the report header.

---

## 7. `confidence` Rating

String `"high" | "medium" | "low"`. Reflects how much corroborating data the analysis pass found:

- `high` — multiple sources, LinkedIn rich, company website fetched cleanly, M&A confirmed.
- `medium` — partial signals.
- `low` — sparse data, rely heavily on assumptions.

The UI displays a colored confidence chip next to the readiness score.

---

## 8. `outreach_hook` Constraints

- **Max 3 sentences.**
- Must reference at least one specific LinkedIn signal (recent post, certification, previous employer).
- Must reference at least one company-specific fact (recent news, M&A, hiring).
- Must be ready-to-send — first sentence usable as a cold email opening line.

---

## 9. `recommended_actions` Constraints

- **Exactly 4-5 actions.**
- Each **max 15 words.**
- Each must **start with a verb** (e.g. "Schedule", "Reference", "Send", "Map").
- Tactical, not strategic — concrete next steps a sales rep can do this week.

---

## 10. `risk_factors` Constraints

- **Exactly 3-4 risks.**
- Each **max 15 words.**
- Each names a specific blocker (e.g. budget freeze, ongoing M&A integration, recent CIO departure).

---

## 11. `signals` Constraints (per dimension)

- **Max 4-5 signals per dimension.**
- Each signal is **3-7 words**, **tag-style** not sentences.
- Examples (good): `"No CLM Platform Detected"`, `"SAP Ariba Ecosystem"`, `"Active M&A Integration"`, `"Posted About Supply Chain"`.
- Counter-example (bad): `"SAP ecosystem presence creates natural pathway to SAP Ariba consideration"` — that's a sentence, not a tag.

The `linkedin_activity_signals` array uses **max 8 words each**.

---

## 12. Buying Maturity Radar — 5-Stage Funnel

Rendered in the Accounts view via Recharts. The 5 stages are the lifecycle stages from `OUTREACH_PROMPT` (Vendor Selection → Authoring → Approval → Obligations → Renewals), each scored 0-100.

The radar shows the average across all analyzed accounts vs the current account's specific scores — it's how the user sees where their account portfolio is concentrated and which lifecycle phase is the easiest entry point for any given prospect.

---

## 13. Stage Ownership Analysis

Inside the Accounts view, M4 cross-references the M1 personas (`pipeline.m1.personas`) with the analyses to compute which persona "owns" each stage at each company. Logic:

- Walk all analyses for a company.
- For each analysis, map `primary_stage` and the `decision_maker.title` → bucket the analysis into a `(persona, stage)` cell.
- The persona with the highest count for a stage is treated as the "owner".
- The UI renders a small badge per stage: "GC owns Awareness", "CPO owns Consideration", etc.

This helps map outreach: the M4 → M5 hand-off uses this so CLMAdvisor knows who to address per stage.

---

## 14. How M4 Reads from M1 + M2

### M1 personas

- The Analyze form has an optional "Pick a persona from M1" dropdown — populated from `pipeline.m1.personas`.
- When selected, after the analysis completes, M4 calls `updatePersona(selectedPersonaId, { m4AnalysisId, m4Stage, m4ReadinessScore, m4AnalyzedAt })` so M1 knows this persona has been fully researched.

### M2 scan results

- M4 is read-light from M2. The Accounts view can pull `pipeline.m2.scanResults` to overlay perception data per company name (does this company appear in M2 vendor lists?).
- The CLM maturity bucket detection uses M2-style competitor signals, but the bucket assignment itself runs against the analysis's own `tech_stack.signals` + `competitor_usage.signals` + `digital_footprint.signals`.

---

## 15. Outputs to `pipeline.m4`

After every analysis the module calls `updateModule("m4", {...})` with:

| Field             | Type         | Description                                                                                                               |
| ----------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `analyses`        | array        | Append-only list of `{ person, company, title, stage, readiness, bucketId, analyzedAt }`                                  |
| `latestStage`     | string\|null | The most recent `primary_stage` value                                                                                     |
| `latestReadiness` | number       | The most recent `readiness_score`                                                                                         |
| `companyBuckets`  | object       | `{ [companyName]: { bucketId, bucketName, detectedSignals[], confidence, analysisId, severity, sirionFit, detectedAt } }` |
| `analyzedAt`      | ISO string   | When this push happened                                                                                                   |
| `generationId`    | ISO string   | For staleness detection in the Dashboard                                                                                  |

`detectBucketFromSignals(techSignals)` returns `{ bucket: TECH_BUCKETS[i], confidence: 0..1, matchedSignals: [...] }`. `TECH_BUCKETS` is the 8-bucket array from `src/data/yinMatrix.js`:

| id                 | name                                     | severity | sirionFit | attackAngle                                                                         |
| ------------------ | ---------------------------------------- | -------- | --------- | ----------------------------------------------------------------------------------- |
| `stone_age`        | Stone Age (No dedicated tool)            | 10       | high      | Foundation play — they need everything. Lead with repository + obligation tracking. |
| `basic_digital`    | Basic Digital (Storage with structure)   | 9        | high      | Risk play — searchable is not manageable.                                           |
| `esign_only`       | Point Solution — E-Signature Only        | 8        | high      | Expansion play — execution solved but pre and post sig still broken.                |
| `procurement_side` | Point Solution — Procurement Side        | 7        | high      | Expansion play — procurement covered but legal and sell-side blind.                 |
| `legal_side`       | Point Solution — Legal Side              | 7        | high      | Consolidation play — legal covered but finance/procurement fragmented.              |
| `midmarket_clm`    | Mid-Market CLM (Partial lifecycle)       | 5        | medium    | Displacement play — they hit a ceiling. Lead with AI extraction.                    |
| `enterprise_clm`   | Enterprise CLM — Competitor              | 3        | medium    | Battlecard play — Sirion wins on post-sig depth, AI accuracy, time-to-value.        |
| `ai_native`        | Modern AI-Native CLM (Where Sirion sits) | 1        | low       | Expansion play — upsell modules, focus on adoption depth.                           |

---

## 16. Firestore Collections

| Collection | Purpose                                                                                                                                                                                                                                                                                                                              |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `analyses` | One doc per M4 analysis. Fields: `analysis_data`, `verification_data`, `outreach_data`, `cleaned_profile`, `company_url`, `company_name`, `person_name`, `person_title`, `primary_stage`, `readiness_score`, `clm_maturity { bucketId, bucketName, confidence, matchedSignals }`, `verified` (boolean), `verified_at`, `created_at`. |

That is the only M4-specific collection. M1 personas update goes through the M1 `m1_personas` doc via `updatePersona()`. The pipeline-level state is part of the global pipeline document.

---

## 17. Edge Cases & Gotchas

1. **LinkedIn cleanup fallback** — if `callClaudeFast(LINKEDIN_CLEANUP_PROMPT)` throws, the code falls back to `cleanedProfile = { name: "Unknown", raw_fallback: linkedinText.substring(0, 3000) }` so Pass 1 still runs.
2. **LinkedIn data staleness** — pasted LinkedIn copy can be days/weeks old. The prompt explicitly notes "today is {TODAY}" so the AI knows to weight more current company news heavier than the LinkedIn snapshot.
3. **Company website launches** — when the company URL is brand new or behind auth, the fetch returns empty and the AI relies entirely on web search for company_profile. Confidence drops to medium.
4. **False negatives on hiring** — LinkedIn job postings are heavily indexed, but companies that hire via referrals or stealth-mode roles will appear as "no hiring activity" even when readiness is high. The prompt warns the AI that absence of public hiring is not absence of need.
5. **JSON parse failures** — Claude occasionally wraps the response in markdown despite "no markdown, no backticks" instruction. `callClaude()` strips ` ```json ... ``` ` fences before parsing.
6. **Verification timeouts** — `runVerification()` sets a 90-second timeout on the call. If it times out, the UI shows "Verification timed out. You can try again." without invalidating the original analysis.
7. **Bucket detection low confidence** — when no signals match any bucket, `detectBucketFromSignals` returns `{ bucket: TECH_BUCKETS[0] /* stone_age */, confidence: 0.1, matchedSignals: [] }`. The UI shows a "<50% confidence" warning chip.
8. **Field path corrections** — `mergeCorrections` traverses `field_path.split(".")`. If any intermediate node is missing, it gracefully no-ops rather than throwing. If the original_claim text is not in the target string, it appends `[UPDATED: ...]` to preserve the audit trail.
9. **Loading-step interval** — the `setInterval(() => setLoadingStep(p => p < 7 ? p + 1 : p), 3500)` keeps stepping the progress UI even if the actual API call finishes faster, so the steps don't all flash at once.
10. **History limit** — local in-memory history is sliced to `.slice(0, 30)` for performance. Older entries still live in Firestore.
11. **Pipeline append-only** — `analyses` array is **always appended** to. There is no de-dup. Re-analyzing the same person/company creates a second entry. The `companyBuckets` object IS keyed by company name so it overwrites.
12. **Missing `useEffect` import** — same pattern as M3: the module must import `useState, useEffect, useMemo, useCallback, useRef` from React. A missing import causes a black-screen render.
13. **Outreach generation requires analysis first** — `generateOutreach()` early-returns if `analysisData` is null. Verification is optional but recommended (the prompt note literally says "Use CORRECTED/VERIFIED data only").

---

End of M4 documentation.
