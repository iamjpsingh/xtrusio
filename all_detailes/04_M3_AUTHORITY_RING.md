# M3 — Authority Ring

> Source file: `src/AuthorityRing.jsx` (~2,346 lines).

---

## 1. What M3 Does

M3 is a **pure-reference, no-LLM-prompts** module. Its job: tell the user **WHERE** to build third-party presence so AI assistants pick up Sirion in their answers. M1 tells us **what questions matter**, M2 tells us **whether AIs mention us**, and M3 tells us **which domains we need to plant content on** — ranked by AI citation weight, buyer persona, buying stage, narrative gap, and outreach cost.

The module renders:

- A **gap map** of high-DA domains where Sirion has zero or wrong presence.
- A **filter UI** to slice by status, approach, cost band, persona, stage.
- An **expandable per-domain card** with verified Google Boolean searches, narrative-gap notes, contacts, costs, timeline.
- An **outreach planner** with cost roll-ups and quick-win prioritization.
- A **content action queue** that scans live URLs to verify whether "poison" quotes (text reinforcing the post-sig narrative) still exist.
- A live link to perception data from M2: gaps drive priority, M2 citations boost domain priority.

M3 writes its outputs back to `pipeline.m3` so the Dashboard and other modules can read it.

---

## 2. Hardcoded Domain Database — Sample Entries

The full database is the constant `DOMAINS` (an array literal at the top of the file). All domains were verified manually using Google Boolean searches (e.g. `"sirion" site:hbr.org`).

A representative sample:

| ID             | Domain              | DA  | AI Citation Weight | Category               | Sirion Status    | Tier | Approach                                  |
| -------------- | ------------------- | --- | ------------------ | ---------------------- | ---------------- | ---- | ----------------------------------------- |
| hbr            | hbr.org             | 93  | 95                 | Tier-1 Media           | verified_zero    | 1    | Research Partnership                      |
| zdnet          | zdnet.com           | 92  | 88                 | Enterprise Tech Media  | verified_zero    | 1    | Product Review / Vendor Spotlight         |
| venturebeat    | venturebeat.com     | 92  | 89                 | Enterprise Tech Media  | verified_zero    | 1    | AI Product Announcement                   |
| techrepublic   | techrepublic.com    | 92  | 85                 | Enterprise Tech Media  | verified_zero    | 1    | Contributed Article / Buyer Guide         |
| techtarget     | techtarget.com      | 92  | 87                 | Enterprise Tech Media  | verified_zero    | 1    | Vendor Profile + Sponsored Content        |
| cfo            | cfo.com             | 78  | 80                 | Finance Media          | verified_zero    | 1    | Executive Byline                          |
| computerweekly | computerweekly.com  | 90  | 82                 | Enterprise Tech Media  | verified_zero    | 1    | UK/EU Vendor Spotlight                    |
| theregister    | theregister.com     | 88  | 79                 | Enterprise Tech Media  | verified_zero    | 1    | Editorial Pitch                           |
| spiceworks     | spiceworks.com      | 84  | 74                 | IT Community           | verified_zero    | 1    | Community Content                         |
| atl            | abovethelaw.com     | 82  | 76                 | Legal Media            | verified_zero    | 1    | Legal Tech Coverage                       |
| cloc           | cloc.org            | 55  | 72                 | Legal Ops              | verified_present | 1    | Sponsorship + Event + Amplify White Paper |
| supplychain    | supplychaindive.com | 70  | 68                 | Procurement Media      | verified_zero    | 1    | Guest Article                             |
| isaca          | isaca.org           | 70  | 70                 | Compliance / Risk      | verified_zero    | 1    | Webinar / White Paper                     |
| compweek       | complianceweek.com  | 65  | 68                 | Compliance Media       | verified_zero    | 1    | Contributed Article                       |
| forbes         | forbes.com          | 95  | 93                 | Tier-1 Media           | verified_present | 2    | Reactivate Forbes Council                 |
| techcrunch     | techcrunch.com      | 94  | 91                 | Tier-1 Media           | verified_present | 2    | Product Announcement Coverage             |
| diginomica     | diginomica.com      | 75  | 74                 | Enterprise IT Analysis | verified_present | 2    | Updated Customer Case Study               |
| bizinsider     | businessinsider.com | 95  | 86                 | Tier-1 Media           | verified_present | 2    | Enterprise AI Product Story               |
| softrev        | softwarereviews.com | 65  | 73                 | Review Platform        | verified_strong  | 2    | Drive New Reviews                         |
| kpmg           | kpmg.com            | 93  | 84                 | Big 4 Consulting       | verified_strong  | 3    | Deepen Joint Content                      |
| deloitte       | deloitte.com        | 93  | 83                 | Big 4 Consulting       | verified_present | 3    | Joint Thought Leadership                  |
| worldcc        | worldcc.com         | 60  | 75                 | Industry Association   | verified_strong  | 3    | Maintain & Leverage                       |
| microsoft      | microsoft.com       | 96  | 94                 | Technology Partner     | verified_strong  | 3    | Amplify AI First Movers                   |
| sap            | sap.com             | 96  | 90                 | Technology Partner     | verified_strong  | 3    | Joint Blog + Customer Case Study          |
| medium         | medium.com          | 96  | 65                 | Blog Platform          | verified_present | 4    | Revive Dormant Account                    |
| fastco         | fastcompany.com     | 93  | 82                 | Tier-1 Media           | verified_present | 4    | Apply for 2026 MIC List                   |
| bloomberg      | bloomberg.com       | 97  | 92                 | Tier-1 Financial Media | verified_present | 4    | Leverage TPG/Warburg Story                |

---

## 3. Domain Object Shape — Every Field

| Field                | Type              | Description                                                                                                           |
| -------------------- | ----------------- | --------------------------------------------------------------------------------------------------------------------- |
| `id`                 | string            | Stable short id (e.g. `"hbr"`, `"forbes"`)                                                                            |
| `domain`             | string            | The domain (e.g. `"hbr.org"`)                                                                                         |
| `da`                 | number            | Moz Domain Authority                                                                                                  |
| `aiCitationWeight`   | number            | How much weight LLMs give this domain when answering CLM questions (manually scored)                                  |
| `category`           | string            | Bucket label (e.g. `"Tier-1 Media"`, `"Big 4 Consulting"`, `"Review Platform"`)                                       |
| `sirionStatus`       | string            | One of: `verified_zero`, `verified_present`, `verified_strong`, `needs_verification`                                  |
| `sirionPresence`     | string\|null      | Plain-language description of what Sirion content exists today (or null for verified_zero)                            |
| `sirionContentType`  | string\|null      | Coded label like `white_paper`, `funding_coverage`, `awards_listing`, `partner_case_study_pre_sig`                    |
| `icertisPresent`     | boolean           | Does competitor Icertis have presence here?                                                                           |
| `icertisContentType` | string\|null      | Description of what Icertis has there                                                                                 |
| `searchQueries`      | array of strings  | Boolean Google searches used for verification (e.g. `'"sirion" site:hbr.org'`)                                        |
| `verifiedDate`       | string            | YYYY-MM-DD when the manual search was last run                                                                        |
| `approach`           | string            | High-level outreach strategy label                                                                                    |
| `method`             | string            | One-sentence concrete tactic                                                                                          |
| `difficulty`         | string            | `easy` / `medium` / `hard` / `very_hard`                                                                              |
| `estCostLow`         | number            | USD lower bound                                                                                                       |
| `estCostHigh`        | number            | USD upper bound                                                                                                       |
| `timelineWeeks`      | string            | e.g. `"3-6"`, `"12-16"`, `"ongoing"`, `"application-based"`                                                           |
| `fiverr`             | boolean           | Whether the tactic can be cheaply executed via Fiverr                                                                 |
| `contactType`        | string            | Who to reach (e.g. `"Editor / Academic Co-Author"`, `"Forbes Council (existing)"`)                                    |
| `topicsFit`          | array             | Topics the domain's audience cares about                                                                              |
| `priorityScore`      | number            | Manual 0-100 priority — higher = act first                                                                            |
| `narrativeGap`       | string\|undefined | Optional — explains why the existing presence is wrong (e.g. softwarereviews.com's "best for post-signature" reviews) |
| `buyerPersonas`      | array             | Personas this domain influences                                                                                       |
| `buyingStages`       | array             | Stages this domain influences (`awareness` / `discovery` / `consideration` / `decision`)                              |
| `urls`               | array             | Direct URLs (the actual article / page references)                                                                    |

A few examples have these extra fields stamped at runtime by `enhancedDomains` memo:

- `enhancedPriority` — `priorityScore` adjusted by AI citation count (M2-derived)
- `aiCitations` — number of times this domain appeared in M2 `sources_cited` arrays

---

## 4. The 4 Tiers

Tiers are **comments / section headers** in the `DOMAINS` array, not a stored field. The runtime infers tier purely from `sirionStatus + narrativeGap`.

### Tier 1 — Pure Gaps (`verified_zero`)

Domains where Sirion has **zero indexed content**. These are the highest-leverage opportunities because every piece of content planted there is net-new visibility. Examples: hbr.org, zdnet.com, venturebeat.com, techrepublic.com, techtarget.com, cfo.com, computerweekly.com, theregister.com, spiceworks.com, abovethelaw.com, supplychaindive.com, isaca.org, complianceweek.com.

### Tier 2 — Wrong Narrative (`verified_present` with `narrativeGap`)

Domains where Sirion content exists but reinforces the wrong story (post-sig only, or just funding coverage, or 2017 case studies). Examples:

- **forbes.com** — 5 articles incl. 3 Forbes Tech Council pieces by Claude Marais (2020) framed around old "CLM++" concept; needs current agentic CLM positioning.
- **techcrunch.com** — only funding coverage ($1B valuation 2024, $85M 2022, $44M 2020); needs product story.
- **diginomica.com** — one Vestas case study from 2017 (post-sig focused); needs updated full-lifecycle agentic CLM coverage.
- **businessinsider.com** — funding/deal coverage; needs product analysis.
- **softwarereviews.com** — **active harm**: reviews say "best suited for post-signature contract management" which directly reinforces the perception problem.

### Tier 3 — Strong Partnerships (`verified_strong`, leverage existing)

Existing deep alliances that just need amplification. Examples:

- **kpmg.com** — joint white paper "Turning Contracts Into Strategic Assets", press release, Digital Strategy hub listing, dedicated US+UK pages.
- **deloitte.com** — formal Africa partnership (Jun 2024), actively hiring Sirion-certified consultants.
- **worldcc.com** — CEO keynote at Benchmark 2025, Innovation Awards case study (Norlys), co-published "From Control to Connection" report.
- **microsoft.com** — 7+ listings incl. AI First Movers page (Redline Agent case study: 60% faster redlining, 40% faster negotiations, 3x more issues identified). DA 96 with the CEO quote _"Sirion has emerged as the definitive leader of leaders in the CLM space."_
- **sap.com** — Ariba partner page, CPQ + S/4HANA integration with full config guides.

### Tier 4 — Easy Wins (cheap, fast)

Low-cost / no-cost, fast execution. Examples:

- **medium.com** — official `@SirionLabs` account, dormant since ~2017, just needs revival.
- **fastcompany.com** — Most Innovative Companies recognition in 2017 + 2021 (Top 10 Enterprise); apply for 2026 list.
- **bloomberg.com** — company profiles, TPG/Warburg $500M stake article, $85M funding press release.

---

## 5. Filtering UI

The filter bar lets the user slice the domain grid by:

- **Status** — `verified_zero` / `verified_present` / `verified_strong` / `all`.
- **Approach** — Research Partnership, Product Review, Council Membership, Sponsored Content, Webinar, Customer Case Study, etc.
- **Cost band** — `< $1k`, `$1k-5k`, `$5k-15k`, `> $15k`.
- **Persona** — CPO, GC, CFO, CIO, VPLegalOps, VPProcurement.
- **Buying stage** — awareness / discovery / consideration / decision.

Filters are local state. They drive the `enhancedDomains` filter memo and reflow the bar charts and treemap.

---

## 6. Microsoft AI First Movers Page — Special Treatment

The `microsoft` domain entry has a unique role. The verified `sirionPresence` field reads:

> 7+ listings: Marketplace, Word add-in, Dynamics 365 integration, AI First Movers dedicated page (Redline Agent case study — 60% faster redlining, 40% faster negotiations, 3x more issues identified), Cloud Blog mention. CEO quote on AI First Movers: 'Sirion has emerged as the definitive leader of leaders in the CLM space.' Mission framed as 'from drafting and negotiation to managing performance and risks' — explicitly full lifecycle. Key URL: microsoft.com/en-in/aifirstmovers/sirion

The `narrativeGap` field calls this out as a **counternarrative asset**:

> COUNTERNARRATIVE ASSET: AI First Movers page is the single strongest pre-signature signal on the internet for Sirion — DA 96, Microsoft endorsement, product metrics all pre-sig focused. But it's ONE page vs Icertis's 47+ links. Needs massive amplification: backlinks, social shares, PR references, internal linking from sirion.ai.

Strategy spelled out in `method`:

> CRITICAL: The AI First Movers page positions Sirion as PRE-SIGNATURE (Redline Agent = contract review, negotiation, redlining powered by Azure OpenAI). This is DA 96 counternarrative gold. Strategy: (1) Backlink to this page from every possible source, (2) Co-author a follow-up blog on Microsoft Tech Community about agentic CLM, (3) Push for a joint webinar or case study video that AI crawlers can index.

Three URLs are pinned: the AI First Movers page, the Microsoft Marketplace listing, and the AppSource listing.

The UI flags this domain with a special "Counternarrative Asset" badge so users see it's a leverage point, not a gap.

---

## 7. Forbes Council & HBR Access Notes

### Forbes

The Forbes entry's `contactType` field reads `"Forbes Council (existing)"` — meaning Claude Marais (a Sirion exec) **already has Forbes Tech Council membership**. The recommended approach is "Reactivate Forbes Council" — `difficulty: easy`, `estCostLow: 500`, `estCostHigh: 2000`, `timelineWeeks: "1-2"`. The notes explain the old 2020 articles focused on the "CLM++" concept and need a refresh framed around agentic contract governance. Pinned URL: `https://www.forbes.com/councils/forbestechcouncil/people/claudemarais/`.

### HBR

HBR has the highest priority score (98) and the highest difficulty (`very_hard`). `approach` is `"Research Partnership"` — co-author with an academic on a contract AI ROI study. Cost band `$15,000-$25,000`. Timeline `12-16 weeks`. Contact type `"Editor / Academic Co-Author"`. Cannot be done via Fiverr. The narrative reasoning: HBR is the strongest authority signal for C-level buyers (CFO, CPO, GC) but requires real research data and a credentialed academic co-author, not a marketing pitch.

---

## 8. Per-Domain Expansion

Clicking a domain card expands it inline to show:

- Full `sirionPresence` write-up (or "Not present — gap" if `verified_zero`).
- The list of `searchQueries` used for verification (so the user can re-verify via Google).
- Verified date (so the user knows whether the data is stale).
- Competitor presence (`icertisPresent` + `icertisContentType`).
- The `narrativeGap` callout (when set) in a red/orange highlighted card.
- Outreach plan: `approach`, `method`, `contactType`, cost band, timeline.
- Pinned URLs (clickable).
- `topicsFit` chips.
- `buyerPersonas` and `buyingStages` chips.
- Action buttons: "Add to Outreach Plan", "Mark In Progress", "Mark Done".
- Live URL scanner button (when the domain has a `narrativeGap` URL) — calls `scanContentUrl()` → uses Claude API + web search tool to verify whether the "poison quote" still exists on the page.

---

## 9. Outreach Methods

Defined in the `OUTREACH_METHODS` constant.

| Method id            | Label                         | Cost range      | Timeline    | Quality     | When to use                                                                                                           |
| -------------------- | ----------------------------- | --------------- | ----------- | ----------- | --------------------------------------------------------------------------------------------------------------------- |
| `fiverr_guest_post`  | Fiverr Guest Post             | $150–$500       | 1-2 weeks   | low-medium  | Tier 1 Tech Media that accept contributed posts (zdnet, venturebeat, techrepublic, techtarget, compweek, supplychain) |
| `pr_agency`          | PR Agency Pitch               | $3,000–$8,000   | 4-8 weeks   | high        | Editorial-first outlets (techcrunch, bizinsider, bloomberg, theregister)                                              |
| `council_membership` | Council/Contributor Access    | $500–$2,500/yr  | 1-2 weeks   | high        | Forbes (already have access)                                                                                          |
| `partner_co_create`  | Partner Co-Creation           | $2,000–$12,000  | 4-10 weeks  | very high   | Microsoft, SAP, KPMG, Deloitte — leverage existing alliances                                                          |
| `sponsored_content`  | Sponsored Content             | $2,500–$15,000  | 2-6 weeks   | medium-high | TechTarget, CLOC, ISACA — paid placement with editorial standards                                                     |
| `self_publish`       | Self-Publish                  | $0–$500         | < 1 week    | varies      | Medium (revive @SirionLabs), Fast Company applications                                                                |
| `academic_research`  | Academic Research Partnership | $15,000–$25,000 | 12-16 weeks | very high   | HBR — only path to Tier-1 academic media                                                                              |
| `event_sponsorship`  | Event Sponsorship             | $5,000–$25,000  | 4-12 weeks  | high        | CLOC Institute, WorldCC Benchmark, ISACA conferences                                                                  |
| `review_campaign`    | Customer Review Drive         | $2,000–$4,000   | 4-8 weeks   | high        | softwarereviews.com — drive new full-lifecycle reviews to displace post-sig framing                                   |

---

## 10. Verification Mechanism — Boolean Google Searches

Every domain has a `searchQueries` array containing the exact Google Boolean strings used to verify presence. Examples:

- `'"sirion" site:hbr.org'`
- `'"sirion" site:zdnet.com'` and `'"sirionlabs" site:zdnet.com'`
- `'"sirion" site:venturebeat.com'`
- `'"sirion" site:cfo.com'`
- `'sirionlabs forbes'`, `'"claude marais" Forbes CLM'`, `'site:forbes.com "claude marais"'`, `'site:forbes.com sirion'`
- `'sirion site:techcrunch.com'`
- `'sirion site:microsoft.com'`, `'sirion redline agent microsoft'`
- `'"sirion" site:cloc.org'`
- `'"sirion" site:softwarereviews.com'`

These are stored verbatim so any user can re-run them in Google to confirm the verification. `verifiedDate` tells them how stale the check is.

For live URL verification (the action queue), `scanContentUrl(url, poisonQuote)` calls Claude with the `web_search_20250305` tool (max 5 uses) to check whether the "poison quote" still appears on the page. The full prompt is documented in the M2 file (Section 3.6) since the same helper is shared. Returns `{found, currentText, status: still_harmful|partially_fixed|fully_fixed|page_not_found, summary}`.

---

## 11. Outputs to `pipeline.m3`

Whenever `perceptionData` (from M2) or `aiCitedDomains` change, M3 fires a `useEffect` that calls `updateModule("m3", m3Data)` with:

| Field                | Type         | Description                                                                                                          |
| -------------------- | ------------ | -------------------------------------------------------------------------------------------------------------------- |
| `prioritizedDomains` | array        | All `verified_zero` (gap) domains, mapped to `{ domain, da, priority, personas, stages, narrativeGap, aiCitations }` |
| `personaDomainMap`   | object       | `{ [persona]: [domain1, domain2, ...] }` — every domain a persona cares about                                        |
| `aiCitedDomains`     | array        | Up to 50 domains M2 actually saw cited in scan responses                                                             |
| `gapCount`           | number       | Count of `verified_zero` domains                                                                                     |
| `strongCount`        | number       | Count of `verified_strong` domains                                                                                   |
| `presentCount`       | number       | Count of `verified_present` domains                                                                                  |
| `totalDomains`       | number       | Total in DB                                                                                                          |
| `analyzedAt`         | ISO string   | When this rollup ran                                                                                                 |
| `generationId`       | ISO string   | Stamp so Dashboard can detect M3 freshness                                                                           |
| `m2GenerationId`     | string\|null | The M2 generation this M3 output was built from — used to detect "M2 ran, M3 stale"                                  |

The module also persists `outreachTracker` (which domains the user has marked in-progress / done) and `caq` (content action queue state) to the same pipeline slot via `updateModule("m3", { outreachTracker, caq })`. PipelineContext then handles the actual Firebase save through `persistenceManager` — M3 itself never writes directly to its own dedicated collection (per the architecture note "Removed separate db.saveWithId('m3_authority_ring')").

---

## 12. NO LLM PROMPTS — M3 Is Pure Reference Data

M3 itself **does not call any LLM for analysis or scoring**. The entire domain database is hand-curated by the Sirion team via Google Boolean searches. The only LLM calls touched from M3 are:

1. `scanContentUrl(url, poisonQuote)` — verifies whether a "poison quote" still exists on a target URL via Claude + web search (helper documented under M2 Section 3.6 because the same Claude proxy is shared).

That's it. No prompt to score domains, no prompt to generate gap matrices, no prompt to suggest outreach. All ranking, all priority, all method selection is deterministic JavaScript on the static `DOMAINS` array, modulated by M2 perception data and user-toggled outreach state.

This is intentional: the team wanted the domain reference set to be auditable, not LLM-generated.

---

## 13. Edge Cases & Gotchas

1. **Verification staleness** — `verifiedDate` is the only signal that the manual Google checks are old. The UI surfaces it so users know to re-verify. There is no automated re-verification.
2. **Budget tiers** — cost ranges are stored as `estCostLow` / `estCostHigh` (numbers). The filter uses `< $1k`, `$1k-5k`, `$5k-15k`, `> $15k` bands; cost roll-ups in the planner use the midpoint.
3. **Firebase array shape** — Firebase stores arrays as objects with numeric keys. M3 normalizes via the `asArray()` helper on every read so loops never break. Always feed perception arrays through `asArray()` before iterating.
4. **`useEffect` dependency** — the import block must include `useEffect`. There was a regression where M3 went black-screen because `useEffect` was missing from the React import (documented as Pitfall #6 in CLAUDE.md).
5. **Outreach tracker persistence** — `outreachTracker` writes through `updateModule("m3", ...)` and survives a refresh. Marking "Done" is local-first then persisted by the next `persistenceManager` flush window.
6. **Active harm detection** — softwarereviews.com is the only domain currently flagged as actively reinforcing the wrong narrative. The UI gives it a red badge and prioritizes it ahead of pure gaps because every new buyer reading the page reinforces the post-sig framing.
7. **Personas hardcoded** — the `PERSONAS` array (CPO, GC, CFO, CIO, VPLegalOps, VPProcurement) and `STAGES` array (awareness, discovery, consideration, decision) are hardcoded at module top. Adding a new persona requires editing the source.
8. **Microsoft AI First Movers** is treated as a leverage point, not a gap — its `priorityScore: 98` matches HBR's despite being `verified_strong`, because the page is high-DA pre-sig signal that needs amplification, not creation.
9. **Counts in filters** — when M2 has not run, `aiCitations` is 0 for every domain and `enhancedPriority` falls back to `priorityScore`. Filtering still works but the "lift from M2 citations" column is empty.
10. **Cost roll-ups** in the planner use the **low end** of cost ranges by default; the user can toggle to "high end" or "midpoint" in the settings.

---

End of M3 documentation.
