# M2 Report V2 — Complete Specification

This document describes `src/ReportV2.jsx` (~93 KB, ~1670 lines), the legacy M2 perception report that V6 inherits all its V2-side sections from. No code is reproduced — only behavior, data, formulas, and structural rules are described.

---

## 1. What Report V2 Is

Report V2 is the **first generation board-ready perception report** for Module 2 (Perception Monitor). It was the original "pick a single scan, render the whole report against that one scan" experience. V3, V4, V5, and V6 all evolved from this file.

V2's design tenets:

- **One scan in, one report out.** No cross-scan merging, no augment plumbing.
- **One master denominator.** Every percentage in the report traces back to `totalAnalyses = questions × LLMs × N (reps)`. The Reconciliation Pyramid visualizes this so any number on the page can be audited.
- **No accordions in the export.** All formulas + reconciliation checks are visible in the printable HTML, so a board reader can scroll and verify.
- **Self-contained HTML download.** The export bakes inline styles and inline SVGs (LLM logos), no external CSS/JS.

V2 lives next to V3/V4/V5/V6 because it is still the canonical authority on the five "section bricks" (Visibility, Share of Voice, Sentiment, Positioning, Lifecycle) — V6 imports them directly rather than reimplementing.

V2 is mounted in `PerceptionMonitor.jsx` when `nav === "reportv2"`. It still works as a standalone scan-picker-driven report.

---

## 2. Top-Level Exports

### Constants

#### `LLM_BRAND_COL`

Brand colors used wherever a model is named. Single source of truth for V2 / V6 visualisation tints.

| Key       | Color                     |
| --------- | ------------------------- |
| `claude`  | `#10b981` (emerald green) |
| `gemini`  | `#f59e0b` (amber/orange)  |
| `openai`  | `#3b82f6` (blue)          |
| `chatgpt` | `#3b82f6` (alias)         |

V6's `LLM_COL` extends this with `grok` and `perplexity`.

### `LlmLogo({ model, size = 16, color })`

React component. Renders an inline SVG brand logo for the given model. Logos are tinted via CSS `currentColor` so callers control colour through the surrounding `color` style.

- `claude` → simple-icons Claude path.
- `gemini` → simple-icons Gemini path.
- `openai` / `chatgpt` → six rotated copies of one petal path inside a 2406-unit viewBox (the OpenAI flower mark).
- `grok` → bold filled X glyph.
- `perplexity` → abstract circular/blade Q-with-tail mark.
- Returns null for unknown models.

Used by every leaderboard / citation / loss / query-summary table in both V2 and V6.

### `llmLogoHtml(model, { size, color })`

String-returning twin of `LlmLogo` for the self-contained HTML export. Expands the OpenAI petal into six explicit `<path>` elements (instead of an SVG `<use>`) so the exported file works without React.

### `canonicalVendor(name)` — vendor name normalization

The same vendor shows up under multiple variants in scan data: "Docusign", "Docusign CLM", "DocuSign". Without normalization the tally counts each variant separately, producing the "DocuSign 58 here, 64 there" mismatch the team kept seeing in early reports.

**Strategy**: Trim, then strip a fixed regex of common product/company suffixes (`CLM`, `Labs?`, `Inc.?`, `Corp.?`, `LLC`, `Ltd.?`, `Co.?`, `Software`, `Platform`, `Solutions?`, `Technologies?`), case-insensitively, only when the suffix is preceded by whitespace. Display name is the stripped variant; merge key is its lowercase form.

V6's `compute.js` and `htmlExport.js` both import `canonicalVendor` from this file — vendor canonicalization is not duplicated.

### `computeReconciliation(loaded)` — the master math function

Takes a `loadedAnalysis` object (as returned by `baselineScanner.getAnalyzedScan`) shaped like `{ scanData, verifiability, narrativeSummary, … }`. Returns the giant `recon` object that drives every V2 section, every V2 hero tile, and every V6 section that needs aggregate numbers.

#### Single-pass walk

For every `(query × model)` analysis in `scanData.results × scanData.llms`:

- Skip when missing or `_error`.
- Increment `total`.
- If `mentioned`: increment `mentioned`, bucket the rank into `r1` / `r2` / `r3` / `r4plus` / `unranked`, push the rank into `rankedVals` for the median, increment the matching `sentiment` bucket.
- For each entry of `vendors_mentioned`, parse loosely (object or JSON string), `canonicalVendor`-normalize the name, increment a `vendorTally` keyed by lowercase canonical name and the global `totalVendorOccurrences`. The first canonical-cased label wins as `vendorDisplayName`.

#### Derived statistics

- `medianRank` = median of `rankedVals` (1 decimal for even counts).
- `meanRank` = mean of `rankedVals` (2 decimals).
- `topVendors` = top 10 vendor entries by count, each with `name`, `count`, `share` (= `count / totalVendorOccurrences × 100`).

#### Output shape

The returned `recon` object has fields:

- `totalAnalyses`, `mentioned`, `notMentioned`.
- `visibility = { numerator, denominator, pct }` — `pct = mentioned / total × 100`.
- `sentiment = { denominator, positive, neutral, negative, pos_pct, neu_pct, neg_pct, reconciles }` — `reconciles` is true when `pos+neu+neg = mentioned`.
- `positioning = { denominator, r1..r4plus, unranked, *_pct, top3Count, top3Pct, medianRank, meanRank, rankedCount, reconciles }`.
- `shareOfVoice = { numerator: sirionExact, denominator: totalVendorOccurrences, pct, topVendors }`.
- `lifecycle = { mentioned, noParagraphCount, frameableCount, buckets: { pre_signature, post_signature, full_stack, unclassified }, pre_pct, post_pct, full_pct, unc_pct, reconciles }` — pulled from `loaded.narrativeSummary` (zero-filled fallback when missing).

#### Reconciliation property

The math is structured so every "section sum" should equal the parent. The boolean `reconciles` flag on each section makes that property auditable; the Reconciliation Pyramid surfaces them as ✓/✗ at the bottom.

### `ReconciliationPyramid({ recon, run, T })`

Renders a tree-like visualization of the `recon` object. The tree shows:

- **Root**: Total analyses (master denominator) — `{question_count} × {models.length} × N={reps} = {totalAnalyses}`.
- **Branch L1**: Mentioned (in blue, strong) — pct of total.
  - **L2**: Frameable (mentioned & has a prose paragraph), in teal.
    - **L3**: Full-stack (teal), Pre-signature (blue), Post-signature (orange), Unclassified (dim) — each with denom + pct vs frameable.
  - **L2**: Dropped — no prose paragraph (dim, count only).
  - **L2 (conditional)**: "Named outside prose — table or citation only" — surfaces only when there's a positive gap between Stage-2's mentioned count and `(frameableCount + noParagraphCount)`.
  - **L2**: Sentiment denom (gold) = mentioned, then **L3** Positive (green), Neutral (muted), Negative (red).
  - **L2**: Positioning denom (purple) = mentioned, then **L3** Rank 1 (green), Rank 2 (teal), Rank 3 (blue), Rank 4 or lower (orange), Mentioned but unranked (dim).
- **Branch L1**: Not mentioned (dim) — pct of total.

At the bottom four reconciliation lines display the literal arithmetic with a ✓ or ✗:

- Mentioned + Not mentioned should equal totalAnalyses.
- Lifecycle bucket sum should equal frameable count.
- Sentiment sum should equal mentioned.
- Positioning sum should equal mentioned.

V6 reuses this component verbatim inside its collapsible "Reconciliation Pyramid" panel.

### `HeroTiles({ recon, T })`

Five colored tiles in a responsive grid. Each tile shows: small uppercase label, big mono-font primary number, secondary line with sub-detail.

| Tile                    | Big number              | Sub-line                                              |
| ----------------------- | ----------------------- | ----------------------------------------------------- |
| Visibility / Citation   | `{visibility.pct}%`     | `{numerator} of {denominator}`                        |
| Share of Voice          | `{shareOfVoice.pct}%`   | `{numerator} of {denominator} vendor mentions`        |
| Sentiment               | `{sentiment.pos_pct}%`  | `positive · {neu_pct}% neutral · {neg_pct}% negative` |
| Competitive Positioning | `#{medianRank}`         | `median rank · {top3Pct}% in top 3`                   |
| Lifecycle / Narrative   | `{lifecycle.full_pct}%` | `full-stack · pre / post / unclass percents`          |

V6 imports `HeroTiles` and uses it directly.

### `ContainerSection({ T, index, title, subtitle, macro, color, formula, denominator, reconcile, children })`

Shared wrapper used by the five sub-sections (Visibility, ShareOfVoice, Sentiment, Positioning, Lifecycle). Renders:

- Header row: numbered badge + title + macro number (color-coded).
- Subtitle (one-line plain English) plus optional denominator caption.
- Hairline divider.
- Collapsible "How it's calculated" panel with the `formula` JSX (closed by default).
- Body (`children`).
- Bottom reconcile line (mono font, muted).

This is V2's "section brick" template.

### `MiniBar({ label, count, denom, pct, color, T, icon })`

Three-column horizontal bar: 42 % label column (with optional logo icon), 58 % bar track with filled colored bar (renders the `pct%` text inside the bar when `pct ≥ 14`, otherwise outside), `count/denom` mono caption on the right.

Used for every distribution chart inside the section bodies (per-model visibility, per-persona visibility, top-10 vendor SoV, sentiment distribution, rank distribution, lifecycle bucket distribution).

### `InnerCard({ T, label, hint, children, style })`

Reusable inner card wrapper with optional uppercase label + hint paragraph. Sections wrap their body content in one or more InnerCards for visual containment.

---

## 3. The Five Visualization Sections

### `VisibilitySection({ recon, segmentation, T })` — § 1

Shows how often AI mentions Sirion across CLM-related questions.

- Macro: `{visibility.pct}%`, blue.
- Denominator caption: `{visibility.denominator} analyses (queries × LLMs × N)`.
- Formula accordion: `mentioned ÷ total_analyses × 100` plus the literal numerator/denominator. Source: Stage-2 Haiku extractor's `sirion_mentioned` field, regardless of citation status.
- Body: three side-by-side InnerCards:
  - **By model**: one MiniBar per LLM, tinted by `LLM_BRAND_COL`, with the brand logo as the leading icon.
  - **By persona**: personas grouped into Procurement / Legal / Other buckets via `bucketOf` from `personaBuckets.js`. Each bucket gets a thin colored separator row labelled "{BUCKET} · weight {N}%". Personas sorted by `comparePersonas` within each bucket.
  - **By stage**: one MiniBar per stage value, sorted by total descending.
- Reconcile: `{numerator} mentioned + {N} not-mentioned = {denominator}`.

### `ShareOfVoiceSection({ recon, T })` — § 2

Shows Sirion's share of all vendor name occurrences across the scan.

- Macro: `{shareOfVoice.pct}%`, orange.
- Denominator caption: `{denominator} total vendor-name occurrences across {totalAnalyses} analyses`.
- Formula: locked symmetric formula `sirion_exact_name_in_vendors_ranked ÷ total_vendor_name_occurrences × 100`. Both numerator and denominator pull from the same field — Stage-2's `vendors_ranked[]` array — exact-name match on "Sirion" so aliases don't double-count.
- Body: single InnerCard listing the top 10 vendors as MiniBars. Sirion's bar is highlighted orange and labelled "← Sirion".
- Reconcile: numerator ÷ denominator = pct.

### `SentimentSection({ recon, T })` — § 3

Shows tone of how AI describes Sirion when it does mention it.

- Macro: `{sentiment.pos_pct}% positive`, green.
- Denominator: mentioned analyses (not total — responses without Sirion have no sentiment to measure).
- Formula: for each mentioned analysis, take Stage-2's `sentiment` field, sum by bucket, divide by mentioned.
- Body: single InnerCard with three MiniBars (Positive green, Neutral muted, Negative red).
- Reconcile: `Pos + Neu + Neg = sum` then check it equals `mentioned`.

### `PositioningSection({ recon, T })` — § 4

Shows where Sirion ranks when AI lists or compares CLM platforms.

- Macro: `Median #{medianRank}`, purple.
- Denominator: mentioned analyses. Unranked = mentioned but the LLM didn't produce an ordered list.
- Formula: bucket each mentioned analysis's `sirion_position` into 1 / 2 / 3 / 4+ / unranked. Median rank is the median over the non-null rank values. Top-3 rate is `(r1+r2+r3)/mentioned`.
- Body: InnerCard with five MiniBars (Rank 1 green, Rank 2 teal, Rank 3 blue, Rank 4+ orange, Unranked dim) plus a footer line summarising median rank, mean rank, ranked-n, top-3 rate.
- Reconcile: `R1 + R2 + R3 + R4+ + Unranked = sum` should equal `mentioned`.

### `LifecycleSection({ recon, T })` — § 5

Shows how AI distributes Sirion across the contract lifecycle (pre-signature, post-signature, full-stack).

- Macro: `{full_pct}% full-stack`, teal.
- Denominator: frameable mentions = mentioned − no-paragraph (− "named outside prose" if there's a gap).
- Formula accordion: classification precedence — END-TO-END keyword hit → full_stack; PRE and POST both hit → full_stack; PRE only → pre_signature; POST only → post_signature; no keyword hits → unclassified. Input: prose paragraph(s) in the Stage-1 response containing "Sirion". Tables, citation parentheticals, and captions are filtered out.
- Body: InnerCard with four MiniBars (Full-stack purple, Pre-signature blue, Post-signature green, Unclassified dim).
- "Excluded from framing" hint surfaces below the bars when `noParagraphCount > 0` or when `outsideProse > 0` (the gap line).
- Reconcile: `Full + Pre + Post + Unclass = sum` should equal `frameableCount`.

---

## 4. The Reconciliation / Pyramid Algorithm

The "pyramid" is the visual that proves every percentage on the page is an honest fraction with no orphan numbers.

### Layers

1. **Master denominator** = totalAnalyses = `questions × LLMs × N (reps)`.
2. Master splits into Mentioned + Not-mentioned (must sum back to totalAnalyses).
3. Mentioned hosts three independent denominators:
   - Frameable mentions (lifecycle).
   - Sentiment denom (= mentioned).
   - Positioning denom (= mentioned).
4. Frameable splits into four lifecycle buckets that must sum back to frameable.
5. Sentiment splits into Pos / Neu / Neg that must sum back to mentioned.
6. Positioning splits into Rank 1 / 2 / 3 / 4+ / Unranked that must sum back to mentioned.

### Diagnostic line

A "Named outside prose" diagnostic appears as a sibling of "Dropped — no prose paragraph" when the Stage-2 extractor counted Sirion as mentioned but the narrative classifier could find neither a prose paragraph nor a no-paragraph signal. This is usually the case where Sirion appears only inside a table cell or citation parenthetical — it is still counted in Visibility but excluded from lifecycle framing.

### Reuse audit (`ReuseAuditPanel`)

A non-exported panel that surfaces a scan's `reuseManifest` when present. Shows reused vs fresh attempts as a stacked horizontal bar, plus a list of source scans (which prior scans the reused attempts came from).

---

## 5. HTML Export — `buildReportV2Html({ recon, run, segmentation, reuseManifest, company })`

Builds a complete `<!DOCTYPE html>` document that renders the entire on-screen V2 report without any external CSS or JS. Safe to email or attach to PowerPoint via screenshot.

### Palette

A frozen light palette: bg `#fafbfc`, text `#18181b`, muted `#52525b`, dim `#a1a1aa`, border `#e4e4e7`, card `#ffffff`, accent `#0d9488`, blue `#0284c7`, orange `#ea580c`, purple `#7c3aed`, green `#059669`, red `#dc2626`, yellow `#d97706`. Uses two font stacks: a system sans default and a `ui-monospace` mono for numbers.

### Document order

1. **Header card** — "Report V2 · Board Summary" eyebrow, scan title, `scanId` mono, target company line, plus a right-aligned mono block with question count, model list, N=reps, tier label, mode, and "Generated …" timestamp.
2. **Provenance card (conditional)** — when a `reuseManifest` is supplied: stacked reused-vs-fresh bar plus the source-scan breakdown.
3. **Reconciliation pyramid** — every node from the on-screen pyramid rendered as flat HTML rows + the four reconcile-check lines at the bottom.
4. **Five hero tiles**.
5. **§ 1 Visibility** — section card with always-visible formula, three-column body (By model / By persona / By stage), reconcile line. Includes the `<!--VIS_END-->` marker comment **immediately after this section**.
6. **§ 2 Share of Voice** — top-10 vendors via shared `miniBar` HTML helper. Followed by `<!--SOV_END-->` marker.
7. **§ 3 Sentiment** — three MiniBars.
8. **§ 4 Competitive Positioning** — five MiniBars + median/mean/ranked-n/top-3 footer line.
9. **§ 5 Lifecycle / Narrative Framing** — four MiniBars + "Excluded from framing" diagnostic when applicable.
10. **Footer** — "All numbers reconcile to {N} total analyses · Generated from m2_scan_meta + m2_scan_results (Firebase)".

### Marker comments

The two HTML comments `<!--VIS_END-->` and `<!--SOV_END-->` are deliberate splice points. V6's `htmlExport.js` searches for them with literal string replace and inserts its V6-only sections (Buying-Center Mix, Persona × Stage Heatmap, Visibility Leaderboard, Citation Domain Authority) between V2's existing sections. The comment markers are part of V2's API contract.

### Helper functions used internally

- `treeRow` — one row of the pyramid (indent, color, count, label, denom, pct, strong flag).
- `miniBar` — same horizontal bar as the on-screen MiniBar but rendered as inline-styled HTML.
- `sectionBlock` — the section card wrapper (badge + title + macro + denominator + always-visible formula + body + reconcile line).
- `tiles` — the 5-tile grid.

### `safeFilename(s, fallback = "scan")`

Trims, replaces non-`[A-Za-z0-9._-]` with `_`, strips leading/trailing underscores. Returns the fallback when result is empty.

### `triggerHtmlDownload(filename, html)`

Creates a `Blob` with `text/html;charset=utf-8`, opens an object URL, programmatically clicks an anchor with that URL and the supplied filename, then revokes the URL after 1 s. The standard browser-side download trigger pattern.

---

## 6. Vendor Canonicalization in Detail

The single regex used by `canonicalVendor`:

> Match a leading whitespace-sequence followed by one of: CLM · Labs / Lab · Inc · Corp · LLC · Ltd · Co · Software · Platform · Solutions · Solution · Technologies · Technology — case-insensitive — anchored at the end of the string.

Examples of resulting canonical names (lowercase merge keys):

- "Docusign" → "Docusign" → key `docusign`
- "Docusign CLM" → "Docusign" → key `docusign`
- "Sirion Labs" → "Sirion" → key `sirion`
- "Icertis Inc." → "Icertis" → key `icertis`
- "Conga Software" → "Conga" → key `conga`

Display name in the leaderboard is whichever canonical-cased variant was seen first for a given key. Both V2's `computeReconciliation.shareOfVoice.topVendors` and V6's `computeLeaderboard` and `computeLossPatterns` rely on this single function to keep the SoV and leaderboard numbers honest.

---

## 7. Shared Infrastructure Used by V2 and V6

V6 explicitly imports the following names from `ReportV2.jsx`:

- `computeReconciliation` — used by V6's render `useMemo` over `activeDocs`.
- `ReconciliationPyramid` — V6 wraps this in a collapsible card.
- `HeroTiles` — rendered immediately after V6's pyramid.
- `VisibilitySection`, `ShareOfVoiceSection`, `SentimentSection`, `PositioningSection`, `LifecycleSection` — V6 renders each in the same order, sandwiched between V6-local sections.
- `LlmLogo` — used by V6's Leaderboard, CitationDomains, LossPatterns, QuerySummary, RawScanModal.
- `canonicalVendor` — used by V6's compute functions.
- `buildReportV2Html` — used by V6's `htmlExport.exportV6Html` to produce the V2 base document that V6 then splices into.
- `safeFilename`, `triggerHtmlDownload` — used by V6's HTML export.
- `llmLogoHtml` — used by V6's HTML builders for the Leaderboard and Citation Domains tables.

The shared imports are the entire dependency surface — V6 does not touch any private helper inside V2.

---

## 8. Theme Tokens Used

Both V2 and V6 read all visual styling from a `T` (theme) object passed in via the `T` prop. Both modules expect (at minimum) the following keys: `bg`, `text`, `muted`, `dim`, `border`, `card`, `surface`, `mono`, `teal`, `blue`, `orange`, `purple`, `green`, `red`, `gold`. V6 additionally reads `T.green` for the credibility badge and the citation owned-row tint.

The theme object is constructed in PerceptionMonitor and changes when the user toggles dark/light mode. Both modules render correctly in both themes.

---

## 9. How V2 Is Consumed by V6

V6 uses V2 in three distinct ways:

1. **As a math library** — `computeReconciliation` is called against V6's `activeDocs` to drive `recon`-shaped V2 sections.
2. **As a section library** — five V2 React components (Visibility / ShareOfVoice / Sentiment / Positioning / Lifecycle) are rendered inline in V6's section list.
3. **As an HTML-export base** — `buildReportV2Html` produces the V2 base document and V6 splices its own section HTML strings around the marker comments.

V6 never instantiates the V2 page-level component (`ReportV2` default export); it goes around the V2 page wrapper and uses only the inner pieces.

---

## 10. V2 Standalone Mounting in M2

V2 still works as its own standalone tab. In `PerceptionMonitor.jsx`:

- The valid tabs whitelist includes `"reportv2"`.
- The sidebar registers a "Report V2" item with the `FileText` icon.
- When `nav === "reportv2"`, `<ReportV2 T={T} />` renders.

### Default V2 export — `ReportV2({ T })`

The page-level component:

1. Loads every scan run from `baselineScanner.listBaselineRuns()` and renders them as `ScanCard`s in a responsive grid.
2. Each `ScanCard` shows scan name + scan_id, status badge (color-coded by status: complete green, running gold, aborted orange, else red), date, tier (Quick / Baseline / Stress / N=…), models list, mode, question count, attempts done/total with completion percent, and "ANALYSED" / "not analysed" tag. Cards with `analyzed` and a `scores` object additionally show overall + mention scores.
3. When a scan is selected, V2 calls `baselineScanner.getAnalyzedScan(selectedScanId)` and stores the `loadedAnalysis`.
4. While loading, shows "Loading analysed scan data…". On error shows the error message. When the scan exists but has not been analysed, shows a hint pointing the user to "Scan & Results → Analyze & Build Report".
5. When `loadedAnalysis` is ready and yields a `reconciliation` (via `computeReconciliation`), V2 renders, in order:
   - Selected scan header card (with an "⬇ Export HTML" button).
   - `ReuseAuditPanel` when a `reuseManifest` is present.
   - `ReconciliationPyramid`.
   - `HeroTiles`.
   - `VisibilitySection`.
   - `ShareOfVoiceSection`.
   - `SentimentSection`.
   - `PositioningSection`.
   - `LifecycleSection`.

### Differences from V6's render path

- V2 is single-scan only — no scan picker, no scope toggle, no LLM picker, no segment filter, no question table, no buying-center / heatmap / leaderboard / citation / loss / query-summary / raw-scan sections.
- V2 reads `scanData.results` and `scanData.llms` directly from the analyzed-scan blob; V6 builds `activeDocs` and `activeLlms` from filters first.
- V2's HTML export is the V2 base only; V6's export starts from the V2 base and splices the V6 sections in.

V2 remains the simpler "I just want the V3-style five-section report on one specific scan" view. V6 is what users (especially client_portal users) see for the live-data report.
