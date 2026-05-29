# Xtrusio Growth Engine — Complete Rebuild Documentation

This folder contains everything needed to rebuild the Xtrusio Growth Engine (Sirion Perception Shift) from scratch. Every module, every prompt, every Firestore collection, every cross-module data flow, every edge case is documented in plain English.

**No code is reproduced** — only behavior, schemas, prompts (quoted verbatim), and connections. Use these docs alongside the source bundles (`V6_BUNDLE_FOR_CLONE.txt`, `MARKET_PULSE_BUNDLE_FOR_CLONE.txt`, `INTELV2_BUNDLE_FOR_CLONE.txt`) at the repo root if you also need the actual code.

---

## What The System Is

The Xtrusio Growth Engine is a 7-module + Company-Intelligence platform built for Sirion (a CLM software vendor). Its purpose is to measure how AI assistants (Claude, ChatGPT, Gemini, Grok, Perplexity) perceive Sirion versus competitors when answering buyer questions, then close the gap through targeted content, link placements, and outreach.

**Tech stack:** React + Vite (no TypeScript), Firebase Firestore for persistence, Cloudflare Pages for deployment, a Cloudflare Worker (`xtrusio-ai.thedevimapro.workers.dev`) as the AI proxy for Claude / OpenAI / Gemini / Grok / Perplexity / Firecrawl.

---

## How To Use These Docs

| Goal                           | Read in this order                     |
| ------------------------------ | -------------------------------------- |
| Understand the whole system    | 00 → 15 → 17                           |
| Rebuild from scratch           | 17 → 01 → 14 → 16 → individual modules |
| Just understand one module     | Jump to that module's file             |
| Find a specific prompt         | 16 (master prompts index)              |
| Add a new Firestore collection | 14                                     |
| Wire a new cross-module flow   | 15                                     |

---

## File Index

### Synthesis (start here)

| #   | File                          | What's in it                                                        |
| --- | ----------------------------- | ------------------------------------------------------------------- |
| 00  | `00_README.md`                | This file — master index                                            |
| 14  | `14_FIRESTORE_COLLECTIONS.md` | Every Firestore collection across the system with full schema       |
| 15  | `15_DATA_FLOW_MAP.md`         | Cross-module data flow — who reads what, who writes what            |
| 16  | `16_PROMPTS_MASTER_INDEX.md`  | Every LLM prompt in the system — name, file, purpose, output format |
| 17  | `17_REPLICATION_GUIDE.md`     | Step-by-step rebuild instructions for a cloned project              |

### Infrastructure

| #   | File                   | Covers                                                                                                                               |
| --- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 01  | `01_INFRASTRUCTURE.md` | PipelineContext, persistenceManager, firebase.js, claudeApi.js, App.jsx routing, ThemeContext, AuthContext, m2ScanLoader, questionDB |

### The 7 Modules

| #   | File                          | Module                                                          |
| --- | ----------------------------- | --------------------------------------------------------------- |
| 02  | `02_M1_QUESTION_GENERATOR.md` | M1 — Question Generator (questions, personas, decision matrix)  |
| 03  | `03_M2_PERCEPTION_MONITOR.md` | M2 — Perception Monitor (the heart of the system)               |
| 04  | `04_M3_AUTHORITY_RING.md`     | M3 — Authority Ring (40+ high-DA domain database)               |
| 05  | `05_M4_BUYING_STAGE_GUIDE.md` | M4 — Buying Stage Guide (per-decision-maker sales intelligence) |
| 06  | `06_M5_CLM_ADVISOR.md`        | M5 — CLM Advisor (15-vendor scoring engine, no LLM)             |
| 07  | `07_M6_CONTENT_STRATEGY.md`   | M6 + M6v2 — Content Strategy (topics → packs → articles)        |
| 08  | `08_M7_LINK_STRATEGY.md`      | M7 + M7v2 — Link Strategy (blog catalog, placements, calendar)  |

### Company Intelligence

| #   | File                            | Covers                                                                                           |
| --- | ------------------------------- | ------------------------------------------------------------------------------------------------ |
| 09  | `09_COMPANY_INTELLIGENCE_V1.md` | V1 — 4-tab dashboard with manual Gemini paste prompts                                            |
| 10  | `10_COMPANY_INTELLIGENCE_V2.md` | V2 — 5 lenses (Position, Competitors, Market Pulse, Opportunities, Actions) + all intelV2/ files |
| 11  | `11_DOMINO_SUBMODULE.md`        | Domino — company-customer mapping via Firecrawl                                                  |

### M2 Sub-Modules

| #   | File                 | Covers                                                                   |
| --- | -------------------- | ------------------------------------------------------------------------ |
| 12  | `12_M2_REPORT_V6.md` | V6 Report — read-only visualization layer (24 files in src/m2/reportV6/) |
| 13  | `13_REPORT_V2.md`    | Legacy V2 Report — base sections that V6 inherits from                   |

---

## The 7 Modules At A Glance

| Module                    | One-line purpose                                                                                           | Has LLM prompts?  |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- | ----------------- |
| **M1 Question Generator** | Generate buyer-intent questions tagged by persona/stage/cluster/lifecycle; research personas from LinkedIn | YES (11 prompts)  |
| **M2 Perception Monitor** | Scan how AI systems perceive your company across all questions; produce 5 metrics                          | YES (6 prompts)   |
| **M3 Authority Ring**     | Reference database of 40+ high-DA domains where you should have presence                                   | NO                |
| **M4 Buying Stage Guide** | Per-decision-maker readiness scoring + outreach hooks                                                      | YES (4 prompts)   |
| **M5 CLM Advisor**        | Deterministic 3-step wizard scoring 15 hard-coded vendors against buyer profile                            | NO                |
| **M6 Content Strategy**   | 3-stage content pipeline: Topics → Journalist Pack → Full Article                                          | YES (10+ prompts) |
| **M7 Link Strategy**      | Blog catalog + article-to-blog assignment + 3-month placement calendar                                     | YES (3 prompts)   |
| **Company Intel V1**      | 4-tab competitive dashboard with manual paste workflow                                                     | YES (2 prompts)   |
| **Company Intel V2**      | 5 strategic lenses synthesizing perception, competitors, news, opportunities, actions                      | YES (10+ prompts) |
| **Domino**                | Customer-vendor mapping via Firecrawl scraping of competitor case studies                                  | YES (5+ prompts)  |

---

## Total Documentation Stats

- **13 module docs** + **5 synthesis docs** = **18 markdown files**
- ~500 KB of plain-English explanations
- Every prompt quoted verbatim
- Every Firestore document shape detailed
- Every UI tab and section described
- Every edge case and known gotcha logged

---

## Companion Source Bundles

For quick replication, these bundle files at the repo root contain the actual source code:

| Bundle                                       | Contents                                         |
| -------------------------------------------- | ------------------------------------------------ |
| `V6_BUNDLE_FOR_CLONE.txt` (412 KB)           | All 24 V6 Report files + 6 external deps         |
| `MARKET_PULSE_BUNDLE_FOR_CLONE.txt` (252 KB) | Market Pulse lens + 11 supporting files          |
| `INTELV2_BUNDLE_FOR_CLONE.txt` (476 KB)      | Full Company Intelligence V2 + Domino + 36 files |

Each bundle has `===== FILE: <path> =====` separators between files for easy extraction.

---

## Project Identity (Important)

- **Folder:** `sirion-perception-shift/` (NOT sirion-v2 or sirion-v3)
- **Repo:** `https://github.com/wemoni-beep/sirion-perception-shift.git`
- **Deploy:** push to `main` branch → Cloudflare auto-deploys committed `dist/` folder
- **DO NOT** deploy via `wrangler deploy` directly
- **DO NOT** make changes in `sirion-v2/` or `sirion-v3/` folders

See `CLAUDE.md` at the repo root for the full project rules and known pitfalls.
