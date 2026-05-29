# Xtrusio — Full Infrastructure & Architecture Brief

A multi-tenant AI-perception SaaS. Helps companies measure and improve how AI assistants (Claude, ChatGPT, Gemini, Grok, Perplexity) perceive them when their buyers ask category questions, then closes the gap through targeted content + link placement + targeted outreach.

This document is the complete architectural picture. Any engineer joining the project should be able to read this cold and understand what we're building, why, and how the pieces fit.

---

## 1. Product summary

**What it does end-to-end.** A tenant signs in, pastes their company URL, and the system scrapes their site + a few authoritative external sources, extracts structured facts, and bootstraps a per-tenant template (personas, competitors, lifecycle stages, pain library, buyer-intent questions). The tenant then runs scans against all major AI assistants to measure visibility, narrative framing, share of voice, sentiment, and competitive position. The system surfaces content gaps, white-space opportunities, weekly action plays, and a predictive signals graph (Domino-style). The tenant produces journalist-grade articles, places them on third-party blogs within a monthly budget, tracks live URLs, and re-scans to measure the perception shift.

**Who uses it.**

- Platform owner / super admin (us)
- Tenant admin (the client's marketing lead)
- Tenant editor (content / SEO contributor)
- Tenant client-portal viewer (read-only reports)

**Multi-tenancy.** Shared database + `tenant_id` column on every domain table + Postgres Row-Level Security policies. One Supabase project, many tenants.

---

## 2. Stack at a glance

| Layer            | Tech                                                                | Notes                                                                                                                                                         |
| ---------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Frontend         | Vite + React 18 + TypeScript (strict, no `.js`/`.jsx`)              | TanStack Router (file-based, autoCodeSplitting), TanStack Query, Tailwind v4 (CSS-first), shadcn-ui (in-tree at `apps/web/src/components/ui/`), Framer Motion |
| Backend          | Python 3.12 + FastAPI + SQLAlchemy 2.0 async + Alembic              | Async-first, asyncpg driver, Pydantic v2                                                                                                                      |
| Database         | PostgreSQL 17 (managed Supabase, supabase.com)                      | Extensions: `pgvector`, `pg_trgm`, `pg_cron` — all enabled in the managed product                                                                             |
| Auth             | Managed Supabase Auth (GoTrue, JWT, HS256, 30-day sessions)         | Email/password day 1; OAuth later. FastAPI validates JWT directly; not proxied through PostgREST.                                                             |
| Object storage   | Managed Supabase Storage (S3-compatible)                            | Uploaded sample articles, DOCX exports, PDF imports, scan archives                                                                                            |
| Realtime         | Managed Supabase Realtime                                           | Live scan progress, run-log streaming                                                                                                                         |
| Async work queue | arq (Redis-backed)                                                  | Embedding jobs, scrape jobs, scan workers, recurring recrawl                                                                                                  |
| Cache            | Redis                                                               | TTL-bounded lens caches, run-output dedup, rate-limit counters                                                                                                |
| LLM providers    | Anthropic / Google Gemini / OpenAI / xAI Grok / Perplexity          | Routed via in-house orchestration layer (FastAPI), not Cloudflare Worker                                                                                      |
| Scraping         | Firecrawl API                                                       | `onlyMainContent: true`, sequential per host, errors per source not fatal                                                                                     |
| Embeddings       | Gemini `text-embedding-004` (default; 768-dim)                      | Provider-pluggable; pgvector index                                                                                                                            |
| Deploy — web     | Cloudflare Pages                                                    | Standard build pipeline, no committed `dist/`                                                                                                                 |
| Deploy — api     | VPS (Docker Compose) behind a reverse proxy (Caddy or nginx)        | TLS via Let's Encrypt                                                                                                                                         |
| Deploy — db      | Managed Supabase project (Pro tier initially)                       | PITR + daily backups + log retention handled by Supabase                                                                                                      |
| Observability    | OpenTelemetry → Grafana Cloud (or self-hosted Loki + Tempo + Mimir) | Structured logs from FastAPI, run-level traces                                                                                                                |
| CI/CD            | GitHub Actions                                                      | Lint + typecheck + tests + build; deploy on tag                                                                                                               |

**Why not Cloudflare Workers for the API.** The orchestration backbone needs long-running scan workers (multi-minute LLM calls, parallel fan-out, retry budgets), structured observability across many calls, and access to Postgres without a connection-pool hop. FastAPI + asyncpg on a VPS is the simpler, cheaper, more debuggable choice. Cloudflare Pages is still the web host because static asset edge serving is genuinely cheaper and faster there.

**Why managed Supabase (not self-hosted, no local stack).** Zero ops burden on Postgres / GoTrue / Realtime / Storage — upgrades, security patches, daily backups, point-in-time recovery, log retention, and the Studio dashboard all belong to Supabase. RLS, `pgvector`, `pg_cron`, `pg_trgm` are all available in the managed product. Cost is predictable on Pro / Team tier at our target customer count. **Local dev connects directly to a managed Supabase dev project** (separate Supabase project from prod, same product) — no `supabase start`, no local Postgres / GoTrue / Realtime / Storage / Studio containers. Migrations are written in `supabase/migrations/*.sql` and applied via `supabase db push --db-url <project-url>` against whichever environment is being deployed.

---

## 3. Architecture overview

```
┌───────────────────────────────────────────────────────────────┐
│                        Cloudflare Pages                       │
│         apps/web (Vite + React + TS, shadcn, TanStack)        │
└───────────────────────────────┬───────────────────────────────┘
                                │   HTTPS, Bearer JWT
                                ▼
        ┌───────────────────────────────────────────────────────┐
        │                Reverse Proxy (Caddy)                  │
        └───────────────────────────────┬───────────────────────┘
                                        ▼
        ┌───────────────────────────────────────────────────────┐
        │                   FastAPI (apps/api)                  │
        │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
        │  │   routes    │→ │  services   │→ │ repositories│    │
        │  └─────────────┘  └─────────────┘  └─────────────┘    │
        │                          │                            │
        │                          ▼                            │
        │  ┌───────────────────────────────────────────────┐    │
        │  │             orchestration layer               │    │
        │  │  router · prompts · runs · cost · cache       │    │
        │  └──────────┬───────────────────────────┬────────┘    │
        └─────────────┼───────────────────────────┼─────────────┘
                      │                           │
                      ▼                           ▼
           ┌────────────────────┐    ┌───────────────────────────┐
           │  Managed Supabase  │    │  LLM Providers + Firecrawl│
           │  (supabase.com)    │    │  · Anthropic Claude       │
           │  · Postgres 17     │    │  · Google Gemini          │
           │    + pgvector      │    │  · OpenAI                 │
           │    + pg_cron       │    │  · xAI Grok               │
           │  · Auth (GoTrue)   │    │  · Perplexity             │
           │  · Storage         │    │  · Firecrawl              │
           │  · Realtime        │    └───────────────────────────┘
           └────────┬───────────┘
                    │
                    ▼
            ┌────────────────────┐
            │  arq workers       │
            │  (Redis-backed)    │
            │  · ingest          │
            │  · embed           │
            │  · extract facts   │
            │  · scan execution  │
            │  · scheduled       │
            └────────────────────┘
```

**Write path.** Client request → FastAPI route → service → repository (SQLAlchemy async) → Postgres with RLS. For LLM-touching operations the service enqueues an arq job; the worker pulls inputs, invokes the orchestration router, writes the result back, and publishes a Realtime event for the UI.

**Read path.** Client → FastAPI route → service → repository, with optional retrieval-augmentation via `knowledge.retriever` (pgvector cosine-similarity query) when the request is LLM-bound.

---

## 4. Bounded contexts (the twelve domains)

We do not name modules M1–M7. Bounded contexts map to business concerns and double as Python package boundaries and frontend route groups.

| Context           | Owns                                                                                                                                            |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **tenants**       | Tenant identity, members, roles, plan tier, API budget enforcement                                                                              |
| **profile**       | Per-tenant facts: company info, personas, journey/lifecycle stages, competitors, pain library, decision criteria, maturity buckets, voice/style |
| **knowledge**     | RAG layer: ingested documents, chunks, embeddings, structured facts, retrieval API                                                              |
| **research**      | Buyer-intent question generation, persona research, segments                                                                                    |
| **perception**    | Scan engine (all four modes), per-question per-LLM results, 5 metrics, gaps, trajectory                                                         |
| **reports**       | Read-only visualization layer over perception data, exports, client-portal views                                                                |
| **authority**     | Third-party domain catalog, outreach plan, citation tracking                                                                                    |
| **readiness**     | Per-prospect dossiers (LinkedIn + company), buying-stage scoring, outreach script generation                                                    |
| **advisor**       | Deterministic vendor scoring wizard, downloadable report                                                                                        |
| **content**       | Campaigns, tracks, topics, journalist packs, articles, style rules, client review                                                               |
| **placement**     | Blog catalog, article-to-blog matcher, monthly calendar with budget enforcement                                                                 |
| **intel**         | Five lenses: position, competitors, market pulse, opportunities, actions                                                                        |
| **signals**       | Predictive correlation engine: industries × companies × signals, force graph, heatmap, predictions                                              |
| **orchestration** | Cross-cutting: LLM router, prompt registry, run logs, cost meter, retries, circuit breakers                                                     |

Each context owns its tables (RLS-scoped to `tenant_id`), its prompts (rows in `prompt_registry`), its routes (`/contexts/{name}` URL group), and its services. Cross-context calls go through service-level functions, never direct table access into a neighbor's namespace.

---

## 5. Knowledge Base / RAG layer

The differentiator vs the legacy. Replaces "hardcoded company JSON stuffed into every prompt" with retrieval-augmented prompts.

### 5.1 What lives in the KB

| Source                                             | Ingested by                   | Refresh cadence    | Used by                                                   |
| -------------------------------------------------- | ----------------------------- | ------------------ | --------------------------------------------------------- |
| Tenant's own website                               | Firecrawl sitemap walk        | Weekly + manual    | Profile bootstrap, content de-dup, citation lineage       |
| Tenant case studies, white papers, product pages   | Firecrawl + manual upload     | On-demand          | Content pipeline backlink suggestions, Advisor, Readiness |
| Tenant published articles                          | Hook on `content.publish`     | Immediate          | Style mining, dedup, citation lineage                     |
| Uploaded style samples (DOCX, PDF, plain text)     | Direct upload                 | On-demand          | `extractRules` → Style Rules library                      |
| Past LLM scan responses                            | Hook after each scan          | Immediate          | Trajectory analytics, drift detection                     |
| Competitor case-study pages                        | `signals.harvest` (Firecrawl) | Weekly             | Signals lens, multi-vendor customer maps                  |
| Authority domain pages (verifying "poison quotes") | `authority.verify`            | Manual + scheduled | Outreach action queue                                     |
| Industry analyst reports referenced in Intel       | Manual upload + Firecrawl     | On-demand          | Vendor share, market pulse validation                     |
| Third-party news items archived                    | Hook from intel news pipeline | Daily              | News dedup across refreshes, drift                        |

### 5.2 Pipeline shape

```
URL or upload
    │
    ▼ ① fetch (Firecrawl or direct)
    │
    ▼ ② normalize → write to documents
    │
    ▼ ③ chunk (semantic boundaries, ~600 tokens, 80 overlap)
    │
    ▼ ④ embed (batch, Gemini text-embedding-004 default)
    │
    ▼ ⑤ extract structured facts (LLM call per doc type)
    │
    ▼ ⑥ index (pgvector HNSW)
    │
    ▼ ⑦ verify / dedup
```

Every stage runs in an arq worker. Failures are isolated per document; partial successes are kept. Cost is metered per stage and written to `cost_ledger`.

### 5.3 Retrieval API

```python
from xtrusio.knowledge.retriever import retrieve

chunks = await retrieve(
    tenant_id=tenant.id,
    query="Sirion's strongest pre-signature feature",
    k=8,
    filters={
        "source_type": ["tenant_site", "case_study"],
        "after": "2024-01-01",
    },
)
```

Every prompt builder accepts optional `context_chunks`. The orchestration layer does retrieval and passes results in. Prompt code stays clean and provider-agnostic. The retrieved chunk IDs are logged in `retrieval_log` so we can audit "which chunks influenced this answer."

### 5.4 Structured facts (the second output of ingestion)

The same document yields both retrievable chunks AND typed facts. Facts are extracted by a small dedicated prompt per document type:

```
fact_type ∈ {
  company_overview, product, competitor, persona_signal,
  case_study_outcome, metric_claim, regulatory_reference,
  award, analyst_position, partnership, executive_move, ...
}
```

Facts flow into `profile.*` tables during onboarding. They are also retrievable independently so prompts can request "give me every metric claim from the tenant's site" without scanning chunks.

---

## 6. Multi-tenancy model

| Layer                      | Mechanism                                                                                                                                            |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Database                   | Every domain table has a non-null `tenant_id uuid` column with FK to `tenants(id)`                                                                   |
| Row-Level Security         | RLS enabled on every tenant-owned table. Single policy: `tenant_id = current_setting('app.tenant_id', true)::uuid`                                   |
| Tenant context propagation | FastAPI middleware extracts `tenant_id` from the JWT claim, opens a Postgres session, executes `SET LOCAL app.tenant_id = $1` before any query       |
| Service guard              | Every service-layer function takes `tenant_id` as a non-defaultable argument. Lint rule + test suite enforce                                         |
| Cross-tenant queries       | Only super-admin endpoints; they switch to a service-role connection and explicitly bypass RLS with `SET role = service_role` after permission check |
| Tenant invites             | Email-based invite → user creates Supabase Auth account → row written to `tenant_members`                                                            |

### Roles within a tenant

| Role     | Can                                                                         |
| -------- | --------------------------------------------------------------------------- |
| `owner`  | Everything within the tenant including billing, member management, deletion |
| `admin`  | Everything except billing + member deletion + tenant deletion               |
| `editor` | Create/edit research, perception scans, content articles; cannot delete     |
| `viewer` | Read all reports                                                            |
| `client` | Read approved articles + perception reports only (client-portal mode)       |

Platform-level roles (cross-tenant): `super_admin` (us), `support` (us, read-only).

---

## 7. Authentication and authorization

**Identity provider.** Managed Supabase Auth (GoTrue). The project's JWT secret is shared with FastAPI via `SUPABASE_JWT_SECRET` env var (read from the Supabase project settings). Tokens HS256, 30-day sessions, refresh token rotation enabled. Custom SMTP relay (Resend by default) configured in the Supabase dashboard for transactional email.

**Frontend flow.** Direct use of `@supabase/supabase-js`. The auth provider hydrates session on mount, listens for `onAuthStateChange`, and stores the access token in memory (not localStorage). The API client attaches `Authorization: Bearer <jwt>` to every FastAPI call.

**FastAPI validation.** A `Depends(get_current_user)` dependency validates the JWT against `SUPABASE_JWT_SECRET`, returns a `User` Pydantic model with `id, email, role, tenant_id`. A second `Depends(require_super_admin)` checks `platform_users.role`.

**Why not PostgREST.** PostgREST is fine for table-level CRUD but the system is heavily verb-driven (scan, generate-topics, run-advisor, harvest-companies). FastAPI gives us cleaner verb endpoints, typed Pydantic contracts, dependency injection for auth, and async LLM call composition.

---

## 8. Orchestration backbone

Single ingress for every AI/scrape call. Every prompt invocation goes through `orchestration.router.run_task(slug, inputs, tenant_id)`.

### 8.1 Provider chains

Carried over from the legacy with the same semantics:

| Chain                     | Order                                                              | Use case                                                           |
| ------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| `RESEARCH_PREMIUM`        | Perplexity Sonar Pro → Gemini Pro grounded → Perplexity Sonar      | Live-web, world-class. News, opportunities (verification searches) |
| `RESEARCH_FAST`           | Perplexity Sonar → Gemini Flash grounded                           | Cost-sensitive trends                                              |
| `RESEARCH_VERIFIED`       | Gemini Pro grounded → Perplexity Sonar Pro → Gemini Flash grounded | Vendor share, analyst rankings (diverse domain returns)            |
| `RESEARCH_CURRENT_EVENTS` | Perplexity Sonar Pro → Gemini Pro grounded → Perplexity Sonar      | Capital flow, product launches                                     |
| `SYNTHESIS_PREMIUM`       | Gemini 2.5 Pro → Claude Sonnet 4 → OpenAI GPT-4o                   | Pure synthesis, no web needed                                      |
| `SYNTHESIS`               | Gemini Flash → OpenAI                                              | Lower-cost synthesis                                               |

**Retries.** Exponential backoff 1s/2s/4s on `503/502/504/500/429/rate limit/timeout/overload`. After 3 attempts the next provider in the chain is tried. After all providers exhaust, the run is marked failed and the error is classified.

**Circuit breaker.** Per-provider rolling 429 counter; if >5 in 60s, the provider is taken out of rotation for 5 minutes.

### 8.2 Prompt registry

Prompts are not source code constants. They are rows in `prompt_registry`:

```
prompt_registry (
  id uuid, slug text, version int, system_text text, user_template text,
  input_schema jsonb, output_schema jsonb, model_default text, tools jsonb,
  created_at, deprecated_at
)
```

Editing a prompt is `INSERT` of a new version, never `UPDATE`. Every `runs` row pins `prompt_slug + prompt_version`, so a re-render of a report can use exact-version reproduction. Supports A/B by running version N+1 on a sample of traffic.

### 8.3 Cost meter

Every successful call writes to `cost_ledger`:

```
cost_ledger (
  id, tenant_id, run_id, kind {llm|embed|scrape},
  provider, units (input_tokens|output_tokens|chars|pages),
  cost_usd numeric(12,6), ts
)
```

Provider adapters normalize token shapes (Anthropic / Gemini / OpenAI / Grok / Perplexity all differ). Per-model rate cards are kept in code (`orchestration.cost.rates`), versioned, and applied at write time. `tenant_api_budget` enforces a hard cap per period; the router refuses new runs when the cap is hit.

### 8.4 JSON parsing

Carried over from the legacy:

| Provider                   | Strategy                                                                                                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Anthropic                  | Concatenate text blocks → strip ` ``` ` fences → JSON.parse → fall back to first `{...}` regex                                                                    |
| Gemini                     | 4 strategies: fence strip → first `{` last `}` slice → balanced-block walk largest-first → up-to-12 truncation-repair iterations counting unmatched quotes/braces |
| OpenAI / Grok / Perplexity | Strip fences → JSON.parse → throw with `rawText` attached                                                                                                         |

All parsing happens inside the router, callers receive parsed dicts.

---

## 9. Database schema

Multi-tenant Postgres. Every domain table carries `tenant_id uuid not null` + RLS policy. Surrogate `id uuid` PK using `gen_random_uuid()`. Audit columns `created_at`, `updated_at`, `created_by`, `updated_by` on every table. Soft delete via `deleted_at`.

### 9.1 Platform tables (no tenant_id)

```
platform_users          — id, email, name, role (super_admin|support), created_at
tenants                 — id, slug, name, primary_url, industry_template_id, byline,
                          status (active|suspended|deleted), plan_tier, created_at
tenant_members          — id, tenant_id, user_id, role, invited_at, accepted_at
tenant_settings         — tenant_id, key, value jsonb
tenant_api_budget       — tenant_id, period_start, llm_tokens_used, scrape_calls_used,
                          embedding_tokens_used, cost_usd, hard_cap_usd
```

### 9.2 profile

```
profile                 — tenant_id PK, name, url, industry, sub_industry,
                          target_market jsonb, products jsonb, brand_voice jsonb,
                          match_aliases text[]
profile_personas        — id, tenant_id, name, role, influence_weight,
                          kpis text[], priorities text[], language text[],
                          would_ask text[], would_not_ask text[], lens text,
                          source (template|onboarding|manual)
profile_journey_stages  — id, tenant_id, slug, label, color, weight
profile_lifecycle_stages — id, tenant_id, slug, label, lexicon_id
profile_lifecycle_lexicons — id, tenant_id, name, pre_terms text[], post_terms text[],
                          end_to_end_terms text[]
profile_pain_library    — id, tenant_id, category, pain_text, business_impact, our_solution
profile_buying_centers  — id, tenant_id, name, weight, persona_match_terms text[]
profile_clusters        — id, tenant_id, name, description, weight, trend, color,
                          lifecycle_id
profile_competitors     — id, tenant_id, name, aliases text[], color, tier,
                          market_share_pct, arr_estimate, analyst_badge, case_study_url
profile_competitor_capabilities — competitor_id, dimension, score
profile_decision_criteria — id, tenant_id, persona_id, slug, label, weight
profile_maturity_buckets — id, tenant_id, slug, name, severity, fit_level,
                          attack_angle, tool_examples text[]
profile_industry_universe — id, tenant_id, industry_id, tier,
                          regulatory_drivers jsonb, procurement_complexity,
                          signal_priorities text[]
```

### 9.3 knowledge

```
documents               — id, tenant_id, source_type, source_url, title,
                          fetched_at, content_hash, status (active|superseded),
                          metadata jsonb
document_chunks         — id, document_id, chunk_index, text, token_count,
                          span_start, span_end
document_embeddings     — chunk_id PK, embedding vector(768), model_id, created_at
document_facts          — id, tenant_id, document_id, fact_type, fact_json,
                          confidence, extracted_by, verified_at
document_links          — id, document_id, anchor_text, target_url, link_type
embedding_jobs          — id, tenant_id, document_id, status, attempt, error,
                          created_at, completed_at
retrieval_log           — id, run_id, tenant_id, query, retrieved_chunk_ids uuid[],
                          scores numeric[], k, model, ts
```

Indexes: HNSW on `document_embeddings(embedding vector_cosine_ops)`, `tenant_id` on every table, `content_hash` UNIQUE per tenant on `documents`.

### 9.4 research

```
research_questions      — id, tenant_id, query, query_hash UNIQUE per tenant,
                          persona_id, journey_stage_id, cluster_id, lifecycle_id,
                          intent_type, volume_tier, persona_fit,
                          classification, source, generated_at, enriched_at,
                          generation_id
research_personas       — id, tenant_id, name, title, company, linkedin_url,
                          cleaned_profile jsonb, psyche jsonb, pain_points jsonb,
                          priorities jsonb, readiness_score numeric(3,1),
                          summary, web_findings jsonb,
                          readiness_analysis_id (FK)
research_segments       — id, tenant_id, name, scope, question_ids uuid[],
                          created_by, created_at
research_macros         — id, tenant_id, query_hash, times_seen,
                          first_seen_at, last_seen_at
```

### 9.5 perception

```
perception_scans        — id, tenant_id, mode (api|paste|batch|excel),
                          status (queued|running|paused|complete|failed),
                          llms text[], scan_type, segment_id, section_id,
                          totals_expected, totals_completed,
                          started_at, completed_at, cost_usd, errors jsonb
perception_results      — id, scan_id, qid, query, persona_id, stage_id,
                          lifecycle_id, difficulty jsonb
perception_analyses     — id, result_id, llm, mentioned, rank, sentiment,
                          narrative_label, response_snippet, full_response,
                          vendors_mentioned jsonb, sources_cited jsonb,
                          content_gaps jsonb, mention_corrected boolean,
                          attempts_pooled int, raw_attempt_id
perception_attempts     — id, scan_id, qid, model, attempt, status,
                          raw_response, retry_count, http_status,
                          latency_ms, tokens jsonb, cost_usd, error
perception_metrics      — scan_id PK, visibility numeric, narrative jsonb,
                          share_of_voice numeric, sentiment jsonb,
                          competitive_position jsonb, overall numeric
perception_gaps         — id, tenant_id, scan_id, qid, gap_type, severity,
                          priority_score, frequency, lifecycle_id,
                          persona_ids uuid[], stage_ids uuid[],
                          status (open|in_progress|resolved|dismissed)
perception_sections     — id, tenant_id, name, question_ids uuid[]
perception_segments     — id, tenant_id, name, scope, scan_ids uuid[],
                          qids text[], picked_llms text[],
                          is_manual_pick boolean, source (manual|filter)
```

Atomic concurrent writes via composite UNIQUE constraint `(scan_id, qid, llm, attempt)` on `perception_attempts`. Partition `perception_analyses` by month if volume warrants.

### 9.6 authority

```
authority_domains       — id, tenant_id, slug, domain, da, ai_citation_weight,
                          category, tier, status, our_presence text,
                          our_content_type, narrative_gap, approach, method,
                          difficulty, est_cost_low, est_cost_high,
                          timeline_weeks, contact_type, persona_ids uuid[],
                          stage_ids uuid[], priority_score, urls jsonb,
                          search_queries text[], verified_at
authority_competitor_presence — id, domain_id, competitor_id, present boolean,
                          content_type, notes, verified_at
authority_outreach_methods — id, tenant_id, slug, label, cost_low, cost_high,
                          timeline, quality, when_to_use
authority_outreach_tracker — id, tenant_id, domain_id, status, owner,
                          started_at, notes
```

### 9.7 readiness

```
readiness_analyses      — id, tenant_id, person_name, person_title,
                          person_company, company_url, cleaned_profile jsonb,
                          primary_stage, stage_scores jsonb, readiness_score,
                          confidence, analysis_data jsonb,
                          verification_data jsonb, outreach_data jsonb,
                          maturity_bucket_id, severity, fit_level,
                          verified_at, created_at
```

### 9.8 advisor

```
advisor_assessments     — id, tenant_id, persona_id, industry, size,
                          maturity_level, pain_ids uuid[], priorities text[],
                          recommendations jsonb, generated_at
```

### 9.9 content

```
content_campaigns       — id, tenant_id, slug, name, subtitle, status, byline,
                          source_scan_ids uuid[], segment_ids uuid[],
                          description, monthly_placement_budget jsonb,
                          show_tracks boolean, created_at
content_tracks          — id, campaign_id, name, tagline, lifecycle_id,
                          direction (increase|decrease|track-only),
                          write_articles boolean
content_topics          — id, tenant_id, campaign_id, track_id, title,
                          content_format (faq|narrative),
                          addresses_gap_ids uuid[], persona_id, lifecycle_id,
                          angle_hook, word_count_target, rationale, status,
                          proposed_at, article_id
content_articles        — id, tenant_id, campaign_id, track_id, title, body,
                          status (imported-pending|imported-rejected|
                                  needs-revision|revising|ready-for-client|
                                  in-review|approved|published),
                          source, byline, tags text[], word_count, read_time,
                          meta_description, url_slug, keywords,
                          import_notes, import_comments, import_verdict,
                          last_citations jsonb, last_sirion_backlinks jsonb,
                          source_topic_id, content_format,
                          created_at, updated_at
content_revisions       — id, article_id, body, title, prompt, source,
                          trigger_comment, created_at
content_client_comments — id, article_id, text, by_client_id, status, added_at
content_style_rules     — id, tenant_id, rule, scope (client|campaign|track),
                          campaign_id, track_id, source, source_comment_id,
                          status, category, added_at
content_gap_descriptions — id, tenant_id, gap_id, description, placement,
                          placement_reason, manual_placement, last_enriched_at
content_gap_market_demand — id, tenant_id, gap_id, search_volume_monthly,
                          scan_frequency, last_estimated_at, source
content_gap_dismissals  — id, tenant_id, campaign_id, gap_id
```

### 9.10 placement

```
placement_blogs         — id, tenant_id, domain, url, dr, da, traffic, country,
                          price_usd, niche, audience_fit, ai_citation_strength,
                          est_time_to_index, est_time_to_ai_cite,
                          fit_verdict (good|okay|not), fit_reason,
                          quality_notes, enriched_at, enrichment_source,
                          status (active|removed),
                          notes, tags text[], added_by_admin
placement_assignments   — id, tenant_id, article_id, target_month text,
                          tier (high-da|mid-da), status, candidates jsonb,
                          out_of_budget jsonb, warning, selected_blog_id,
                          last_touch_at, provider_used, fallback boolean
placement_month_plans   — id, tenant_id, year_month text, budget_cap_usd,
                          slots jsonb
```

### 9.11 intel

```
intel_news              — id, tenant_id, title, summary, source_url,
                          source_name, published_date, category, affects,
                          impact_score, impact_rationale, sources text[],
                          corroboration int, first_seen_at, last_seen_at,
                          fetch_count int, url_hash UNIQUE per tenant
intel_market_data       — id, tenant_id, kind (vendor_share|analyst_rankings|
                          capital_flow|launches|trends), payload jsonb,
                          computed_at, ttl_until, provider, status
intel_subscriptions     — tenant_id PK, competitors text[], industry_terms text[],
                          custom_topics text[], updated_at, updated_by
intel_opportunities     — id, tenant_id, session_id, title, type,
                          description, evidence jsonb, scores jsonb,
                          recommended_play, effort, channel, persona_id,
                          stage_id, already_exists boolean, existing_url,
                          verification_evidence, content_hash UNIQUE per tenant,
                          first_seen_at, last_seen_at, occurrence_count,
                          latest_score
intel_actions           — id, tenant_id, session_id, tier, title, rationale,
                          recommended_play, evidence jsonb, owner_suggestion,
                          effort, scores jsonb, channel, channel_rationale,
                          generated_at
intel_snapshots         — tenant_id, snapshot_date PK composite,
                          vendor_share jsonb, share_of_voice jsonb,
                          stage_scores jsonb, overall_score numeric,
                          news_counts jsonb, capital_flow_count int,
                          provider, captured_at
intel_cache             — id, tenant_id, key, payload jsonb, ttl_until,
                          computed_at
```

### 9.12 signals

```
signals_industries      — id, tenant_id, slug, name, tier, size_global_usd,
                          size_year, maturity, regulatory_drivers jsonb,
                          procurement_complexity, signal_priorities text[],
                          primary_buyer_persona text[],
                          notable_wins jsonb, source_urls text[],
                          last_refreshed_at
signals_companies       — id, tenant_id, name, industry_id, current_vendor,
                          vendor_relation_type, evidence_snippet,
                          confidence, vendor_references jsonb,
                          source_urls text[], heat numeric,
                          last_seen_signal_at
signals_signal_types    — id, tenant_id, slug, label, description
signals_hits            — id, tenant_id, company_id, industry_id,
                          signal_type_id, headline, summary, source_url,
                          source_name, source_date, disruption_score,
                          score_rationale, our_relevance,
                          relevance_rationale, captured_at,
                          dedup_key UNIQUE per tenant
signals_correlations    — id, tenant_id, leading_industry_id,
                          trailing_industry_id, signal_type_id,
                          correlation numeric, lag_weeks int, sample_size int
signals_predictions     — id, tenant_id, leading_industry_id,
                          leading_signal_id, leading_week,
                          spike_magnitude_sigma numeric,
                          trailing_industry_id, expected_intensity_change,
                          expected_arrival_week, confidence numeric,
                          narrative text, content_angle text,
                          suggested_persona_id, suggested_assets jsonb,
                          verified boolean, materialized boolean
```

### 9.13 orchestration

```
prompt_registry         — id, slug, version, system_text, user_template,
                          input_schema jsonb, output_schema jsonb,
                          model_default, tools jsonb,
                          created_at, deprecated_at,
                          UNIQUE (slug, version)
runs                    — id, tenant_id, prompt_slug, prompt_version,
                          task_kind, status, context, inputs_hash,
                          started_at, completed_at, latency_ms,
                          provider_chain text[], provider_used,
                          retries int, tokens_in int, tokens_out int,
                          cost_usd, error_class, error_msg
run_attempts            — id, run_id, attempt_number, provider, status,
                          latency_ms, http_status, retry_after,
                          error, tokens_in, tokens_out
run_outputs             — run_id PK, output_json jsonb, raw_text,
                          repaired boolean
cost_ledger             — id, tenant_id, run_id, kind (llm|embed|scrape),
                          provider, units bigint, cost_usd numeric(12,6), ts
provider_health         — provider PK, last_success_at, last_failure_at,
                          rolling_429_count, circuit_open_until
```

---

## 10. Backend service layout

```
apps/api/src/xtrusio/
├── core/
│   ├── config.py            # pydantic-settings
│   ├── db.py                # async engine, SessionLocal, Base
│   ├── auth.py              # JWT validate, get_current_user, role guards
│   ├── multi_tenant.py      # tenant context, RLS GUC setter
│   ├── logging.py           # structured logging
│   └── errors.py            # typed exceptions
├── orchestration/
│   ├── router.py
│   ├── providers/
│   │   ├── anthropic.py
│   │   ├── google.py        # Gemini + grounding
│   │   ├── openai.py
│   │   ├── grok.py
│   │   ├── perplexity.py
│   │   └── firecrawl.py
│   ├── prompts.py           # registry CRUD, versioning
│   ├── runs.py
│   ├── cost.py
│   ├── parser.py            # 4-strategy JSON repair
│   └── cache.py
├── knowledge/
│   ├── ingest/
│   │   ├── website.py
│   │   ├── pdf.py
│   │   ├── docx.py
│   │   └── direct_text.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── facts.py
│   ├── retriever.py
│   ├── jobs.py
│   └── routes.py
├── tenants/
│   ├── service.py
│   ├── invites.py
│   └── routes.py
├── profile/
│   ├── bootstrap.py
│   ├── service.py
│   └── routes.py
├── research/
│   ├── generator.py
│   ├── personas.py
│   ├── enrichment.py
│   └── routes.py
├── perception/
│   ├── scanner.py           # 4 modes
│   ├── parser.py            # 6-level fallback
│   ├── narrative.py         # deterministic classifier
│   ├── verifier.py          # mention cross-verify
│   ├── metrics.py           # 5 metrics
│   ├── segmentation.py
│   └── routes.py
├── reports/
│   ├── compose.py           # V6-style read-only views
│   ├── exports.py           # HTML, CSV
│   └── routes.py
├── authority/
│   ├── catalog.py
│   ├── verify.py
│   ├── outreach.py
│   └── routes.py
├── readiness/
│   ├── analyzer.py          # 3-pass: cleanup → analyze → verify
│   ├── outreach.py
│   └── routes.py
├── advisor/
│   ├── scoring.py           # deterministic
│   ├── report.py
│   └── routes.py
├── content/
│   ├── topics.py
│   ├── articles.py
│   ├── revision.py
│   ├── style_rules.py
│   ├── exports.py           # DOCX, plain-text-with-footnotes
│   └── routes.py
├── placement/
│   ├── enrich.py
│   ├── matcher.py
│   ├── calendar.py
│   ├── budget.py
│   └── routes.py
├── intel/
│   ├── lenses/
│   │   ├── position.py
│   │   ├── competitors.py
│   │   ├── market_pulse.py
│   │   ├── opportunities.py
│   │   └── actions.py
│   ├── news/
│   │   ├── aggregator.py
│   │   ├── dedup.py
│   │   ├── archive.py
│   │   └── subscriptions.py
│   ├── validators.py        # hallucination guards
│   ├── snapshots.py
│   └── routes.py
├── signals/
│   ├── industries.py
│   ├── harvest.py           # Firecrawl across vendor case-study URLs
│   ├── sweep.py             # signal sweep
│   ├── dataset.py           # live vs mock builder
│   ├── insights.py
│   └── routes.py
├── workers/
│   ├── ingest.py
│   ├── embed.py
│   ├── facts.py
│   ├── perception_scan.py
│   ├── intel_news.py
│   ├── signals_harvest.py
│   └── scheduler.py
└── main.py
```

`pyproject.toml` declares `uv` workspace. Tests in `apps/api/tests/` using `pytest-asyncio` with `asyncio_default_fixture_loop_scope = "session"`.

---

## 11. Frontend information architecture

URL groups map 1:1 to bounded contexts.

```
/onboarding              first-run wizard
/profile                 read/edit company facts, personas, competitors, voice
/knowledge               uploads, recrawl, document browser, retrieval-debug
/research                questions + segments + maturity buckets
/perception              scans, results, segments, drift
/reports                 read-only, client-portal-friendly
/authority               domain catalog, outreach board
/readiness               per-prospect dossiers
/advisor                 vendor wizard + report
/content                 campaigns, kanban, editor, style rules
/placement               blog catalog, calendar, candidates
/intel                   5 lenses
/signals                 force graph, heatmap, predictions
/runs                    orchestration log, cost ledger, prompt versions
/settings                tenants/members/billing/api budget
/sign-in                 forced-dark, no aurora, centred card
```

Three-group sidebar:

| Group            | Contexts                                 |
| ---------------- | ---------------------------------------- |
| **Foundation**   | profile, knowledge                       |
| **Research**     | research, perception, reports, authority |
| **Production**   | content, placement, advisor, readiness   |
| **Intelligence** | intel, signals                           |
| **Admin**        | runs, settings                           |

**Frontend stack details.**

- TanStack Router with autoCodeSplitting and per-route loaders.
- TanStack Query for server state. Mutations go through service-layer hooks (`useScanMutation`, etc.).
- Tailwind v4 CSS-first config in `globals.css`. Black-and-white palette + semantic status colors (`destructive / warning / success / info`).
- shadcn-ui owned in-tree at `apps/web/src/components/ui/`.
- Framer Motion for mount-in animations.
- Charts: Recharts (radar, sankey, scatter, treemap).
- Force graph: `react-force-graph-2d` (signals).
- Realtime: Supabase Realtime channels for live scan progress + run logs.
- shadcn dark/light theme with per-route theme override (sign-in forced dark).

---

## 12. External integrations

| Provider                     | Use                                                                                            | Quirks                                                            |
| ---------------------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Anthropic Claude             | Generation, JSON synthesis, web search (`web_search_20250305`)                                 | Wraps headers in `**bold**` — parser strips before regex          |
| Google Gemini                | Generation, grounding via `google_search`, embeddings, JSON mode (only when no grounding tool) | `responseMimeType: application/json` incompatible with grounding  |
| OpenAI                       | Pure synthesis (no live web)                                                                   | Never put in research chains                                      |
| xAI Grok                     | Real-time search via `live_search`, `max_search_results: 10`                                   |                                                                   |
| Perplexity Sonar / Sonar Pro | Built-in search, citation-heavy answers                                                        | Best for current-events queries                                   |
| Firecrawl                    | Scrape with `onlyMainContent: true`                                                            | Some sites block; <200 char markdown ≡ skip; never blocks the run |
| Supabase                     | Auth, Storage, Realtime                                                                        | Self-hosted                                                       |

Provider keys live in FastAPI env (Vault / Doppler / .env-with-direnv). The orchestration router is the only consumer.

---

## 13. Dev environment

There is no local Supabase stack. Dev connects directly to a **managed Supabase dev project** on supabase.com (separate from prod). Two Supabase projects total to start with: `xtrusio-dev` and `xtrusio-prod`.

### 13.1 First-time setup

1. Create the `xtrusio-dev` Supabase project (Pro tier or Free tier for now; Pro before any real testing).
2. In the project's API settings, copy: `Project URL`, `anon key`, `service_role key`, `JWT secret`, pooled connection string, direct connection string.
3. Copy `.env.example` to `.env` and fill from those values:

```
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@<region>.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
SUPABASE_JWT_SECRET=<jwt secret>
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
REDIS_URL=redis://localhost:6379/0
# Provider keys
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
OPENAI_API_KEY=...
XAI_API_KEY=...
PERPLEXITY_API_KEY=...
FIRECRAWL_API_KEY=...
```

4. Apply schema: `supabase db push --db-url $DATABASE_URL` (the Supabase CLI is still used as a _migration tool_, never as a _local stack runner_).
5. Bootstrap a platform owner: `make create-platform-owner email=... password=...`.

### 13.2 Daily commands

```
make api             # uvicorn apps/api with reload, connects to managed dev project
make web             # vite dev, connects to managed dev project
make dev             # api + web in parallel
make worker          # arq worker (needs Redis running)
make redis-up        # docker run a local Redis (optional — can use remote)
make migrate-new name=add_some_table   # generate a new migration file
make migrate         # supabase db push --db-url $DATABASE_URL
make create-platform-owner email=... password=...
```

Apps run natively on the host via `uv` (Python) and `pnpm` (web). The only Docker dependency in dev is Redis, and even that is optional — a remote Redis or Upstash works the same.

### 13.3 What's NOT in dev anymore

- `supabase start` / `supabase stop` — not used.
- Local containers for Postgres, GoTrue, PostgREST, Realtime, Storage, Studio, Inbucket, Kong — not used.
- `make db-up` / `make db-down` — removed.
- `scripts/generate-env.sh` writing `localhost:54322` connection strings — removed; replaced by `.env.example` template filled manually from the Supabase dashboard.

### 13.4 Conventions

**Pre-commit hooks**: `no-js-in-frontend` (rejects `.js/.jsx/.mjs/.cjs` under `apps/web`), `no-hardcoded-colors` (rejects raw `#hex` outside Tailwind tokens), ruff, mypy strict (with provider-stub overrides), eslint, prettier.

**Testing**.

- API: pytest + pytest-asyncio + httpx, fixtures for `db_session`, `make_jwt`, `super_admin_user`, `http_client`. Asyncio session-scoped loop. Tests run against a dedicated `xtrusio-test` Supabase project (or a schema inside `xtrusio-dev` that's wiped between runs).
- Web: Vitest + React Testing Library + Playwright for critical flows.
- Per-tenant data isolation tests in CI; isolation suite seeds two tenants and asserts zero cross-tenant leakage on every endpoint.

---

## 14. Production deployment

### 14.1 Topology

| Component                            | Where                                                  | Notes                                                                   |
| ------------------------------------ | ------------------------------------------------------ | ----------------------------------------------------------------------- |
| Web                                  | Cloudflare Pages                                       | Connected to GitHub `main`, standard Vite build                         |
| API + Workers                        | VPS (4 vCPU / 8 GB / NVMe, Hetzner or DO)              | Docker Compose: `api`, `worker`, `caddy`, `redis`                       |
| Database + Auth + Storage + Realtime | Managed Supabase project (Pro tier, $25/mo)            | Backups, PITR, log retention, monitoring all included                   |
| DNS / TLS                            | Cloudflare proxied                                     | API origin protected by Cloudflare; Caddy gets Let's Encrypt via DNS-01 |
| Secrets                              | Doppler (or `sops` + age in repo)                      | Provider keys, Supabase service-role key, JWT secret                    |
| Transactional email                  | Resend (custom SMTP relay configured in Supabase Auth) | Cheap, good deliverability                                              |

### 14.2 Compose snippets (illustrative — exact files in repo)

**API tier `compose.yaml`**:

```yaml
services:
  api:
    image: ghcr.io/<org>/xtrusio-api:${TAG}
    env_file: .env.production
    depends_on: [redis]
    restart: unless-stopped
  worker:
    image: ghcr.io/<org>/xtrusio-api:${TAG}
    command: arq xtrusio.workers.main.WorkerSettings
    env_file: .env.production
    depends_on: [redis]
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    volumes: ["redis:/data"]
    restart: unless-stopped
  caddy:
    image: caddy:2
    ports: ["443:443", "80:80"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
volumes: { redis: {}, caddy_data: {}, caddy_config: {} }
```

**DB tier**: managed by Supabase — no compose file in dev or prod. Two Supabase projects (`xtrusio-dev`, `xtrusio-prod`); connection strings (pooled + direct), `anon` key, `service_role` key, and JWT secret come from each project's API settings page and are loaded into FastAPI via env vars (Doppler in prod).

### 14.3 CI/CD

GitHub Actions on push to `main`:

1. Lint (ruff, mypy, eslint, tsc) + tests.
2. Build API image, tag `:sha`, push to GHCR.
3. Build web bundle, deploy to Cloudflare Pages preview.
4. Migrations: run `supabase db push --db-url $PROD_DB_URL` against the managed Supabase project (gated on tag for prod).
5. On tag `v*`: deploy API to VPS via SSH `docker compose pull && docker compose up -d`, run `alembic upgrade head` against the managed Postgres connection, promote web Pages deployment.

### 14.4 Migrations

Alembic + async env.py. Forward-compatible rules:

- New columns always `NULL` or with default.
- Backfills are async, never blocking the deploy.
- Renames done as add-column → dual-write → backfill → swap reads → drop old.
- Schema version recorded in a `schema_versions` table for safety.

### 14.5 Backups + DR

- Postgres backups + point-in-time recovery: handled by managed Supabase. Pro tier ships daily backups with 7-day retention; Team tier extends to 28 days + PITR.
- Storage bucket backup: enabled in the Supabase dashboard; for extra safety, weekly cross-region replication to an off-Supabase S3 bucket via a worker job.
- Restore drill quarterly: restore a Supabase backup into a staging project, point the API at it, run the test suite.

---

## 15. Observability and cost

### 15.1 Logs

Structured JSON via `structlog`. Every request logs `tenant_id`, `user_id`, `route`, `status`, `latency_ms`, `request_id`. Workers log per-job. Logs shipped to Loki (self-hosted) or Grafana Cloud.

### 15.2 Traces

OpenTelemetry SDK in FastAPI; one trace per request. Per-run spans for every provider attempt with `provider`, `tokens_in`, `tokens_out`, `cost_usd`. Tempo or Grafana Cloud Tempo.

### 15.3 Metrics

Prometheus client exposes:

- HTTP latency / status histogram.
- Run latency by `provider` + `prompt_slug`.
- Worker queue depth.
- Postgres connection pool usage.
- Cost ledger sums (per tenant per day).

### 15.4 Cost surfaces

- `/runs` UI page (super admin + tenant admin): every run, click for details, filter by status / context / cost.
- Per-tenant budget bar in tenant settings.
- Alert at 80% / 95% / 100% of monthly cap.
- Daily email digest to platform owner: cost by tenant, top failing prompts, retry rate by provider.

### 15.5 Scheduled-work policy

**Bright line**: if a job would still need to run with the API down, it belongs in `pg_cron`. Otherwise it belongs in `arq`.

**`pg_cron` is for database-internal hygiene only:**

| Job                                                                                                     | Cadence      | Why it's here                           |
| ------------------------------------------------------------------------------------------------------- | ------------ | --------------------------------------- |
| `VACUUM (ANALYZE)` on hot tables (`perception_analyses`, `runs`, `cost_ledger`)                         | Nightly      | Storage hygiene, zero app context       |
| Partition rotation on `perception_analyses` (create next month's partition)                             | Monthly      | Pure DDL                                |
| Cold-archive cutoff: copy >90d `perception_analyses` rows to `perception_analyses_archive`, then delete | Nightly      | One SQL statement against indexed range |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY` for reporting views                                            | Hourly       | View lives in SQL                       |
| TTL sweep of `intel_cache` where `ttl_until < now()`                                                    | Every 15 min | One DELETE, no app logic                |
| `runs` cleanup: archive succeeded rows older than 30 days, drop after 180                               | Nightly      | Same shape                              |
| Provider health rolling-window decay (decrement `rolling_429_count` past window)                        | Every minute | Bounded counter math                    |

That is the entire `pg_cron` surface.

**`arq` owns every product-level scheduled job and every async pipeline.** Queues:

| Queue         | Job kinds                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------- |
| `ingest`      | Firecrawl scrape, PDF parse, DOCX parse, raw-text intake, content-hash dedup                |
| `embed`       | Chunk + embed batches, provider retry + cost ledger writes                                  |
| `facts`       | Structured fact extraction per document type                                                |
| `perception`  | API-mode scan workers — one job per `(scan_id, qid, model, attempt)`, with resume semantics |
| `intel`       | Multi-source news aggregation, dedup, validators, archive write, digest synthesis           |
| `signals`     | Vendor case-study harvest, per-industry signal sweeps, per-company batch sweeps             |
| `authority`   | Live URL re-verification, Boolean Google query refresh                                      |
| `content`     | Article revision, topic generation, suggested-topics-from-gaps, style-rules extraction      |
| `placement`   | Blog enrichment, article-to-blog matcher, free-text CSV parse                               |
| `recrawl`     | Per-tenant scheduled tenant-site recrawl                                                    |
| `cost_alerts` | Per-tenant budget threshold emails                                                          |

Recurring `arq` work is declared in `workers/scheduler.py` (cron-style decorators) — same codebase as the workers themselves. We never wire `pg_cron` to call back into the API.

Why this split:

- arq jobs make outbound HTTP calls with multi-minute timeouts, walk provider chains, mutate `runs / run_attempts / cost_ledger` rows mid-flight, and need backoff + circuit-breaker awareness + dead-lettering. None of that fits inside a Postgres transaction.
- arq jobs spawn child jobs (a scan job enqueues per-question jobs). `pg_cron` can't enqueue.
- arq has per-tenant rate limits, retry policies, and visible queue depth in observability. `pg_cron` has none of that.

---

## 16. Build sequencing

Six phases. Each phase yields a usable system before the next.

| Phase                                  | Weeks | Deliverable                                                                                                                                                                     |
| -------------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **0. Foundation**                      | done  | Multi-tenant skeleton, auth, app shell, sign-in route                                                                                                                           |
| **1. Profile + Knowledge MVP**         | 2–3   | URL onboarding wizard; Firecrawl ingest of tenant site → chunk → embed → extract competitors / products / target market → fill `profile.*`; `/knowledge` browser; retrieval API |
| **2. Research + Perception**           | 4–6   | Question generator with RAG-augmented prompts; persona research; scan engine (paste mode first); 5 metrics; segments; reports                                                   |
| **3. Content + Placement**             | 3–4   | Campaign + kanban with topic/article/review/approved; style rules; blog catalog; matcher; monthly calendar                                                                      |
| **4. Authority + Readiness + Advisor** | 2–3   | Domain catalog (seeded from KB facts + manual edit); outreach tracker; per-prospect analysis; vendor wizard                                                                     |
| **5. Intel + Signals**                 | 4–6   | 5 lenses; multi-source news with hallucination guards; snapshots; signals industry/company/signal pipelines; force graph; heatmap                                               |
| **6. API mode + billing**              | 2     | Live API scan mode with realtime progress; cost ledger UI; budget enforcement; optional BYO keys                                                                                |

Total: 17–24 weeks single senior engineer. 10–14 weeks with a partner.

---

## 17. Architectural decisions still open

These are the choices that need to be locked before kickoff. Defaults in **bold**.

| #   | Decision                            | Options                                                                               | Default                                                                 |
| --- | ----------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1   | Embedding provider                  | **Gemini text-embedding-004 (768d)** / OpenAI text-embedding-3-small (1536d) / Cohere | Gemini for cost + speed                                                 |
| 2   | Vector store                        | **pgvector (HNSW)** / Qdrant / Weaviate                                               | pgvector — keep an abstraction layer for swap                           |
| 3   | Async job runner                    | **arq (Redis)** / Celery (Redis + Beat)                                               | arq for simplicity                                                      |
| 4   | Onboarding bootstrap depth          | L1 minimal / **L2 opinionated review-and-confirm** / L3 full clone                    | L2 — best UX, manageable cost                                           |
| 5   | Industry templates shipped on day 1 | One generic B2B SaaS / **B2B SaaS + e-commerce + fintech** / library of 10+           | Three covers most early customers                                       |
| 6   | Cost model                          | Flat per-tier budget / Usage-based billing / **BYO keys**                             | BYO keys first (simplest, customers pay direct), add metered tier later |
| 7   | LLM proxy host                      | **Same FastAPI** / Cloudflare Worker (legacy pattern)                                 | Same FastAPI — observability and DB access wins                         |
| 8   | Realtime scan progress              | **Supabase Realtime channels** / SSE from FastAPI / WebSocket                         | Realtime — already in stack                                             |
| 9   | Cross-tenant analytics surface      | Build now (anonymized aggregates) / **Defer to phase 7+**                             | Defer — privacy review needed                                           |
| 10  | Trajectory archive                  | **Hot in Postgres, cold to S3 Parquet after 90d** / All Postgres / All S3             | Hybrid is the standard pattern                                          |

---

## 18. Known patterns lifted from the legacy

Carried forward exactly because they're load-bearing:

- Atomic composite IDs for parallel writers (`{scanId}__{qid}__{model}__{attempt}`) → enforced via UNIQUE constraint.
- Mention cross-verification: if the LLM claims it mentioned the company but the company name isn't in `full_response` or `vendors_mentioned`, auto-flip to absent. Always log the override.
- Parser fallback (6 levels) for messy paste-mode responses.
- Deterministic narrative classifier with pre/post/end-to-end lexicons (pluggable per tenant via `profile_lifecycle_lexicons`).
- Provider chains with retry budgets and circuit breakers.
- Hallucination guards: tenant-specific host allowlists / rejectlists, source-diversity validators, "leave it out if unsure" prompt instructions, mandatory verification searches before recommending opportunities.
- Daily idempotent snapshots (`YYYY-MM-DD` doc IDs).
- TTL-bounded lens caches with Refresh-only invalidation.
- Style rules library that auto-prepends to every content-generation prompt.
- DOCX export with inline `[N]` citation markers + side-by-side anchor text and URL so publishers can copy URLs into real hyperlinks.

---

## 19. Known anti-patterns removed

- Hardcoded `Sirion`, `CLM`, vendor lists, persona arrays, lifecycle stages — all become per-tenant data.
- Browser localStorage as primary persistence — replaced by FastAPI as source of truth + TanStack Query cache.
- SHA-256 + static salt auth + URL hash session token — replaced by Supabase Auth.
- Firestore REST + value-flatten-to-depth-3 + 200KB string cap — replaced by Postgres + JSONB.
- Committed `dist/` folder as deploy artifact — replaced by normal CF Pages build.
- Hash routing + 13-entry MODULES table + `VITE_PORTAL_MODE` tree-shake — replaced by TanStack Router + RLS-based gating.
- Cloudflare Worker AI proxy as the single auth gate — replaced by FastAPI orchestration (we own the prompts and the cost meter).
- M2 V6 reading `m2_scans` as a fallback — drop the legacy aggregate blob; ship only the granular per-query store.
- React without TypeScript — TypeScript-only across the frontend.

---

## 20. Repository layout

```
xtrusio/
├── apps/
│   ├── api/                FastAPI service + workers
│   ├── web/                Vite + React frontend
│   └── infra/              compose files, Caddyfile, deploy scripts
├── packages/
│   └── shared-types/       OpenAPI-derived TS types (optional, generated)
├── supabase/               supabase/config.toml, migrations/seeds
├── scripts/                bootstrap, smoke tests, ops helpers
├── docs/
│   ├── architecture/       this document + ADRs
│   ├── specs/              per-feature design specs
│   └── runbooks/           on-call procedures
├── Makefile
├── .pre-commit-config.yaml
├── pyproject.toml          uv workspace
└── README.md
```

ADRs (Architectural Decision Records) live in `docs/architecture/adr/NNN-title.md` so the why behind every choice is captured at the time of the choice. The decisions in §17 each become an ADR once locked.

---

---

## 21. Build philosophy (non-negotiable)

These rules govern _how_ we build, not just what.

### 21.1 `all_detailes/` is reference, not template

The `all_detailes/` folder documents the legacy single-tenant Sirion engine. It is read to understand _what_ a feature does — its workflows, prompts, edge cases, data shapes. It is **not** ported verbatim. Every feature in the rebuild is designed from scratch against:

- The bounded-context layout (§4)
- The KB/RAG layer (§5)
- The multi-tenant + RLS model (§6)
- The orchestration backbone (§8)
- The managed Supabase substrate (§14)

Patterns that are load-bearing get lifted (atomic composite IDs, mention cross-verification, deterministic narrative classifier, provider chains, hallucination guards, TTL caches, DOCX export with inline citations). UI, code style, schema, and prompts are all written fresh.

### 21.2 Enterprise register, not demo-ware

Every screen must read as real enterprise SaaS. Visual reference: Anthropic console, Linear, Vercel dashboard.

- Hairline borders, not heavy shadows. `border-foreground/10` is the default surface edge.
- Black/white palette + semantic status tokens (`destructive / warning / success / info`). No decorative color.
- Geist + Geist Mono only.
- Framer Motion mount-ins on first paint, never on data changes.
- Every screen ships its empty state, loading state, error state, and densest-data state on day one.
- Keyboard navigation is a requirement, not a stretch goal. ⌘K palette, ⌘/ shortcuts, tab order verified per route.
- No aurora, no mesh gradients, no glow rings, no marketing chrome. Sign-in is forced dark with a centred card; that is the maximum decoration anywhere in the product.

### 21.3 One feature, end-to-end, before the next

We do not scaffold all 12 bounded contexts at once. Build order is sequential per §16:

```
tenants → profile → knowledge → research → perception → reports →
content → placement → authority → readiness → advisor → intel → signals
```

Each context ships complete: schema migration → RLS policies → repository → service → routes → workers if any → frontend routes → empty/loading/error/data states → tests (unit + per-tenant isolation) → polish pass. Nothing lands in a "demo" or "TODO" or "placeholder" state. The legacy mess we're rebuilding away from came from half-finished modules left for later.

### 21.4 Definition of done (per feature)

A feature is done when:

1. Migration is checked in, applies cleanly forward + back.
2. RLS policy is enabled + `FORCE ROW LEVEL SECURITY`.
3. Per-tenant isolation test covers list / get / create / update / delete for the new tables.
4. All UI states (empty / loading / error / dense data) are implemented and screenshot-tested.
5. Keyboard navigation works without mouse.
6. Frontend types are generated from the OpenAPI schema, not handwritten.
7. Observability: every new prompt slug has a row in `prompt_registry`; every new endpoint logs `tenant_id`, `user_id`, `latency_ms`, `status`.
8. Documentation: ADR for any decision that wasn't covered in this brief; per-feature spec in `docs/specs/`.

If any of the above is missing, the feature is not done. There is no "ship it and clean up later" track.

---

**End of brief.** This is enough to bring a new engineer or contractor up to speed in one read. Outstanding items in §17 should be locked before code is written. Build philosophy in §21 is non-negotiable.
