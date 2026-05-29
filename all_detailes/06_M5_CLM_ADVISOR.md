# Module 5 — CLM Advisor

File: `src/CLMAdvisor.jsx` (~1240 lines).

This is a **front-end-only** vendor selection assistant. There is no LLM call from this module today — every "recommendation" is computed by a deterministic JavaScript scoring engine driven by a hand-curated vendor knowledge base baked into the file. It is best understood as a self-service "which CLM should I buy?" wizard that doubles as a CMO-grade lead capture surface for Sirion's advisory team.

---

## 1. What M5 Does (CMO-Level Strategic Advice Synthesizer)

- Asks the visitor for their **role, industry, company size, current pains, CLM maturity, and ranked priorities**.
- Scores **15 well-known CLM vendors** against that profile using a weighted-base + capped-context-adjustment formula.
- Renders a 3-step wizard with: profile capture → assessment + live preview → ranked results.
- Offers a downloadable HTML one-pager summarizing the analysis and pushing the visitor toward `mailto:hello@sirion.ai` for human follow-up.
- Persists the top 5 recommendations to `pipeline.m5.recommendations` so a future report can reuse them.

The page is positioned in the UI as "CLM Advisor by Sirion Intelligence — Analyst-Backed · 15 vendors". The vendor dataset is described in the source as "ESTIMATED from public analyst data and reviews — Forrester Wave Q1 2025, Gartner Peer Insights, G2 Winter 2026, MGI 360 Ratings."

---

## 2. User Workflow

The component holds a `step` state with three values:

| Step | Name       | What happens                                                                                                                                                                                                                                                                                                    |
| ---- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0    | Profile    | Pick persona, industry, company size. When persona is chosen, default pain points + priority ranking are auto-seeded from the persona's `typicalPains` and `priorities` lists.                                                                                                                                  |
| 1    | Assessment | Multi-select pain points, pick CLM maturity (0–4 scale), then drag/arrow-reorder eight priority dimensions. A live preview of the top 6 vendors with score bars updates on every priority swap.                                                                                                                 |
| 2    | Results    | Hero card for the #1 recommendation, a ranked list of all 15 vendors with tier badges and bars, a clickable vendor detail card with strengths/concerns, a top-3 capability radar chart, two CTAs (download HTML report, contact Sirion advisory), a recommended-next-steps block, and a methodology disclaimer. |

A sticky header at the top renders a 3-dot stepper showing progress.

When the user advances from Step 1 to Step 2, the code calls `updateModule("m5", { recommendations: scores.slice(0, 5).map(s => ({ vendorId: s.id, score: s.score })), generatedAt: ... })`.

---

## 3. LLM Prompts

**There are no LLM calls in M5.** No prompt strings, no calls to `claudeApi.js`, no Gemini/Perplexity/Grok/Claude integration. Every score is computed in `calcScores()` from constants in the same file.

The only AI-adjacent connection is that:

- M4 buyer data may eventually be auto-mapped to a persona (a `useEffect` exists with the comment "If M4 has analysis data, we could pre-select persona based on the buyer's title — For now just mark as loaded — future: auto-map title to persona"). This auto-map is **not implemented** yet.
- The pipeline writes `pipeline.m5.recommendations` for downstream consumers but no other M5 field is populated.

**No prompts to quote.**

---

## 4. UI Sections

The wizard delivers strategic advice through these Result-step blocks. None of them are powered by an LLM — they are templated around the scoring output and the static `VENDORS` table.

### Hero Recommendation Card

Top-of-page tile showing the #1 vendor's name, tagline, "best for" tags, analyst badge, and the fit score (e.g. "92% fit score"). Background gradient is built from the vendor's brand color.

### All 15 Vendors Ranked

A scrollable, click-to-select list. Each row shows: rank, color dot, name, tier badge ("Leader" / "Strong Performer" / "Notable"), pricing range, implementation time, ±% adjustment vs base, final score, and a colored bar. Clicking a row swaps the radar chart and renders a vendor detail panel.

### Vendor Detail Panel (when one is clicked)

- Header: vendor name, tagline, analyst badge, final score with `base: X · adj: ±Y%` breakdown.
- 4-tile strip: pricing, implementation, scale range, tier.
- Two-column block: bulleted **Strengths** (green check icons) and bulleted **Concerns** (gold minus-circle icons).

### Capability Comparison — Top 3 (Radar)

A `recharts` `RadarChart` plotting the top vendor (or the user-selected one) plus the next two on the six lifecycle dimensions: Pre-Signature, Negotiation, Execution, Post-Signature, Analytics, Repository. The first vendor is filled at higher opacity to dominate visually.

### CTA Block ("Need Help Deciding?")

Two buttons — "Download Full Report" (triggers the HTML download) and "Contact Sirion Intelligence" (`mailto:hello@sirion.ai?subject=CLM%20Advisory%20Request`).

### Recommended Next Steps Card

Three numbered bullets, hardcoded:

1. "Schedule a personalized demo based on your profile"
2. "See how Sirion addresses your top 3 priorities"
3. "Get a custom ROI projection for your organization"

### Disclaimer Block

Quotes the methodology source list (Forrester Wave Q1 2025, Gartner Peer Insights, G2 Winter 2026, MGI 360 Ratings) and notes that scores are estimates.

### Stage-Based Messaging / Authority Roadmap / Battlecards / Sales Enablement

**Not implemented as separate sections.** The doc-task brief asks about "stage-based messaging, authority roadmap, competitor battlecards, sales enablement." None of these exist as discrete UI in `CLMAdvisor.jsx`. The vendor strengths/concerns lists serve a battlecard-like purpose, but there is no dedicated battlecard tab, no per-stage message rotation, and no authority-domain roadmap. Treat these as **future hooks** (see §13).

---

## 5. How M5 Reads Other Modules

Despite the doc-task brief's reference to M2/M3/M4 wiring, **M5 reads almost nothing from upstream modules today**.

| Source                           | Field          | Usage in M5                                                                                                                                                    |
| -------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pipeline.m4.latestStage`        | Buyer stage    | Watched in a `useEffect` for the express purpose of pre-filling the persona — but the actual auto-map is a TODO. The hook only sets `pipelineM4Loaded = true`. |
| `pipeline.m2.scanResults`        | Scan results   | **Not read.**                                                                                                                                                  |
| `pipeline.m2.contentGaps`        | Content gaps   | **Not read.**                                                                                                                                                  |
| `pipeline.m3.prioritizedDomains` | Authority gaps | **Not read.**                                                                                                                                                  |
| `pipeline.m4.analyses`           | Buyer analyses | **Not read.**                                                                                                                                                  |

In other words, the M5 scoring engine ignores live perception data and works purely from the static vendor table and the user's wizard inputs.

---

## 6. Outputs to `pipeline.m5`

Only one write happens, when the user clicks "See My Results" on Step 1:

```
pipeline.m5 = {
  recommendations: [
    { vendorId: "sirion", score: 92 },
    { vendorId: "icertis", score: 88 },
    ... up to 5 ...
  ],
  generatedAt: "2026-05-09T12:34:56.789Z"
}
```

Fields the brief asks about that **do not exist**:

- `pipeline.m5.leadData` — never written.
- Per-recommendation `recommendation.fields` like rationale, score breakdown, sales talking points, target persona — none of these are persisted; only `vendorId` + `score`.

---

## 7. Competitor List (Vendors Known to M5)

The `VENDORS` constant is grouped by Forrester tier. Each entry carries a tagline, six dimension scores (preSig / negotiation / execution / postSig / analytics / repository), pricing range in $K/yr, implementation weeks, contract scale range, strengths, concerns, "best for" tags, and an analyst attribution string.

### Forrester Leaders

| Vendor       | Tier   | Tagline (verbatim)                        |
| ------------ | ------ | ----------------------------------------- |
| **Sirion**   | Leader | AI-Native Contract Intelligence Platform  |
| **Icertis**  | Leader | Enterprise Contract Intelligence at Scale |
| **Ironclad** | Leader | Digital Contracting for Modern Teams      |
| **Agiloft**  | Leader | Data-First No-Code Agreement Platform     |

### Forrester Strong Performers

| Vendor                | Tier             | Tagline                                          |
| --------------------- | ---------------- | ------------------------------------------------ |
| **LinkSquares**       | Strong Performer | AI-Powered Contract Intelligence                 |
| **DocuSign CLM**      | Strong Performer | eSignature + Full Lifecycle Management           |
| **Conga**             | Strong Performer | Revenue Lifecycle + Contract Management          |
| **ContractPodAi**     | Strong Performer | AI-First Contract Management                     |
| **Evisort (Workday)** | Strong Performer | AI-First Contract Analysis — Now Part of Workday |

### Notable Players

| Vendor          | Tier    | Tagline                                              |
| --------------- | ------- | ---------------------------------------------------- |
| **Juro**        | Notable | Browser-Native Contracts for Fast Teams              |
| **SpotDraft**   | Notable | Modern CLM for Growing Legal Teams                   |
| **CobbleStone** | Notable | Enterprise Contract Management with Compliance Focus |
| **PandaDoc**    | Notable | Document Automation for Sales Teams                  |
| **Onit**        | Notable | Legal Operations + Contract Management               |
| **Malbek**      | Notable | AI-Powered CLM for Enterprise Legal Teams            |

15 vendors total. Sirion's row is intentionally written to score the highest "post-signature" mark in the dataset (96), with the analyst badge "Forrester Leader · Gartner Customers Choice".

---

## 8. Recommendation / Scoring Object Structure

Each scored vendor returned by `calcScores(profile)` carries:

| Field   | Type   | Source                                                              |
| ------- | ------ | ------------------------------------------------------------------- |
| `id`    | string | Vendor key in `VENDORS`                                             |
| `score` | int    | Final fit score, clamped 15–97                                      |
| `base`  | int    | Weighted base score (priority-weighted average of dimension scores) |
| `adj`   | int    | Net context adjustment, clamped to ±25%                             |

The richer per-vendor data the UI uses (strengths, concerns, pricing, scale, tier, color, analyst badge) is read from the `VENDORS` constant rather than passed along inside the scoring object.

The 6 lifecycle dimensions used in scoring + radar:

| Dimension key | Label          |
| ------------- | -------------- |
| `preSig`      | Pre-Signature  |
| `negotiation` | Negotiation    |
| `execution`   | Execution      |
| `postSig`     | Post-Signature |
| `analytics`   | Analytics      |
| `repository`  | Repository     |

---

## 9. Scoring Logic (Lead-Like Scoring)

There is **no marketing-style "lead score" in the conventional sense** (no MQL/SQL gradations, no enrichment lookups, no email capture). The vendor fit score is what stands in for a lead score and is computed as follows.

### Step 1 — Weighted Base Score

The user has dragged 8 priority dimensions into rank order. Priority `i` (0-indexed) gets weight `max(0.2, 3.0 - i × 0.4)`. So #1 = 3.0, #2 = 2.6, #3 = 2.2, …, #7 = 0.2, #8 = 0.2 (floor).

For each vendor:

- Sum `(vendorScore[dim] / 100) × weight` across the 8 ranked priorities.
- Add an extra `(vendorScore[impliedDim] / 100) × 0.2` for every dimension implied by every selected pain point (each pain implies 1–2 dimensions; see `PAIN_POINTS[].implies`).
- Divide by the total weight; multiply by 100. That's `base`.

### Step 2 — Context Adjustments (Additive)

Five adjustment blocks add or subtract integer percentage points from `adj`:

1. **Size fit** — penalises enterprise-only vendors when `size = startup/smb`, rewards small vendors with low scale floors and low pricing.
2. **Industry compliance burden** — for industries with weight ≥ 1.15 (Pharma, Financial, Healthcare, Government) bonuses vendors whose `(postSig + compliance)/2` is above 75. Government adds named exceptions (`docusign +6 FedRAMP`, `agiloft +8 on-prem`, `cobblestone +5`).
3. **Maturity** — at maturity 0–1 (chaos / reactive) rewards short implementations; at maturity 3–4 (optimised / intelligent) rewards vendors with high postSig + analytics + repository averages.
4. **Speed priority** — if `execution` is in the user's top 3 priorities, rewards short implementation cycles, penalises long ones.
5. **Cost priority** — if `cost` is in the top 3, rewards low pricing caps, penalises premium pricing.

### Step 3 — Cap and Clamp

- `adj` is clamped to ±25% to ensure base capabilities still drive ranking.
- Final score = `base × (1 + cappedAdj/100)`, then clamped to `[15, 97]` and rounded.

The disclaimer block in the UI quotes this logic explicitly: "Step 1 — Weighted Base Score: Priority #1 gets 3.0x weight, #8 gets 0.2x. Step 2 — Context Modifiers: Size fit, industry compliance burden, maturity, speed, and cost adjustments are summed additively. Step 3 — Cap at ±25%: No vendor can be boosted or penalized beyond ±25%, ensuring product capabilities always drive rankings."

---

## 10. UI Patterns and UX Notes

- **Theme tokens** — `C_DARK` / `C_LIGHT` constants; the active palette is mutated via `Object.assign(C, ...)` at the top of the component on every render based on `useTheme().mode`.
- **Animations** — CSS keyframes `fadeUp`, `pulse`, `barGrow` injected via a `<style>` tag in the header.
- **Drag-and-drop priority list** — native HTML5 drag, with up/down arrow buttons as a fallback for users who prefer arrows.
- **Live preview** — Step 1 renders a side panel of the top 6 scored vendors that re-orders on each priority swap, animated by the `fadeUp` class with a `scoreKey` ratchet to retrigger.
- **Recharts radar** — Top-3 capability comparison; the leading vendor uses 0.15 fill opacity, others 0.04, so the eye is drawn to it.
- **HTML report download** — `downloadReport()` builds a 3K+ character HTML string in JS, blob-wraps it, triggers an `<a download>` click. The HTML is fully self-styled with embedded Inter / JetBrains Mono fonts and a meta description targeted at SEO ("CLM Vendor Analysis: {persona} in {industry} | CLM Advisor"). It includes hero, full rankings, why-it-leads, methodology, pricing, and an outbound mailto.
- **Sticky stepper** — Top header is `position: sticky` with a translucent background + blur, showing 1/2/3 dots that turn green when complete and accent-blue when active.
- **Personas** — 8 personas (`CPO`, `GC`, `CLO`, `Legal Ops`, `Procurement Director`, `CFO`, `COO`, `Sales Ops`) each with `typicalPains` and a default `priorities` ordering used to prefill Step 1 → Step 2.
- **Industries** — 12 industries each with a compliance-tag list and a numeric weight (`w`) used in Step 2 of scoring.
- **Sizes** — 5 buckets (Startup / Small-Mid / Mid-Market / Enterprise / Large Enterprise) each with a contract volume hint.
- **Maturity** — 5 levels (Chaos / Reactive / Controlled / Optimized / Intelligent) with color coding.

---

## 11. Firestore Collections

**M5 does not write to Firestore.** All persistence routes through `updateModule("m5", ...)` and lands in `pipeline.m5` (which the global `persistenceManager` then mirrors to localStorage + Firebase as part of the pipeline document). No M5-specific collection exists.

---

## 12. Limitations

- **Static vendor data** — All 15 vendor scoring vectors are hand-encoded. There is no live ingest from analyst feeds; the file's own comment notes "Will be replaced with verified evidence-backed data."
- **No live perception integration** — Despite the brief implying M5 reads M2/M3 data, the implementation ignores those modules. The fit score is purely profile-driven.
- **No M4 auto-fill** — The `useEffect` watching `pipeline.m4.latestStage` exists but only flips a boolean; the comment in the source explicitly says "For now just mark as loaded — future: auto-map title to persona."
- **No discrete battlecards / authority roadmap / sales enablement views** — The brief's request to document "competitor battlecards, sales enablement" cannot be honored from the code; those surfaces do not exist. The closest thing is the per-vendor strengths/concerns list in the detail panel.
- **No lead capture mechanics** — There is no email field, no scoring of the human user, no CRM webhook. The only conversion path is the hardcoded `mailto:hello@sirion.ai` link.
- **Methodology disclaimer baked into UI** — The user is repeatedly told scores are "estimated from publicly available data including Forrester Wave Q1 2025, Gartner Peer Insights, G2 Winter 2026, and MGI 360 Ratings". Treat the scoring as marketing-grade analysis, not formal procurement evidence.
- **Single recommendation persisted** — Only the top 5 vendor IDs + scores are written. No persistence of the user's profile, their pain points, or their priority ranking, so a re-open of the module starts from scratch.
- **No A/B variants** — Hero copy, CTA copy, and "next steps" are hardcoded strings.

---

## 13. Future Work Hooks (Code Comments + Obvious Gaps)

- **Auto-map M4 buyer title → persona** — placeholder `useEffect` in the component.
- **Evidence-backed scores** — comment says "Full evidence-backed scores with source URLs available in the Premium report." A "Premium report" tier is implied but not built.
- **Lead capture API** — The mailto CTA could be replaced with a form posting to a CRM / Sirion Intelligence inbox.
- **Stage-based messaging** — A future panel could pull `pipeline.m4.analyses` per buyer stage and render stage-specific talking points.
- **Authority roadmap** — A future panel could pull `pipeline.m3.prioritizedDomains` to suggest which publications to target alongside vendor selection.
- **Competitor battlecards** — The vendor strengths/concerns lists are battlecard-shaped; a dedicated battlecard view (per persona, per industry) is a natural extension.
- **Live competitor intelligence** — The vendor table could be hydrated from `pipeline.m2.scanResults.results` (competitor mentions across LLMs) so rankings reflect real perception, not analyst snapshots.
- **Dimension-level evidence** — Each cell in the 6-dimension matrix could carry a citation URL.
- **Lead scoring** — A real lead scoring layer (engagement events, completed steps, downloads, follow-on chat) is missing entirely; today the score is the vendor fit, not the visitor.
- **Persistence of profile** — Saving the user's profile/maturity/priorities would let M5 reopen at the result step on return visits.

Relevant file path: `/home/user/sirion-perception-shift/src/CLMAdvisor.jsx`
