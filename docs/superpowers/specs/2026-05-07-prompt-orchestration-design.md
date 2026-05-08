# Prompt Orchestration Engine — Design Spec

**Project:** Xtrusio AI SaaS Platform
**Spec ID:** 2026-05-07-prompt-orchestration
**Status:** Draft (pending user review)
**Depends on:** spec #1 (multi-tenant foundation) — must ship first
**Scope:** Subsystem #2 — the AI orchestration layer that runs agentic research workflows on tenant-provided inputs using per-tenant prompts and multiple LLM providers.

---

## 1. Overview

This spec defines the **agentic prompt orchestration engine**: how single-shot, variable-duration AI workflows execute against multiple LLM providers, what tools they have, how their state is persisted, how progress streams to the UI, and how prompts are managed per tenant.

The first concrete workflow is **company research**: a tenant submits a company URL → the agent researches the company, generates research questions, scans the web, synthesizes findings into a structured report → the tenant gets a finished artifact. The architecture is built so adding new agentic workflows later is additive (new flow file, new prompts, optional new tools), not a refactor.

### 1.1 Goals

- A tenant can submit a research input (a URL), trigger a run, navigate away, and come back to a finished artifact.
- The agent uses multiple LLM providers in the same run — picking the right model for each step (Claude for reasoning, Gemini Flash for cheap classification, Perplexity for web-grounded synthesis).
- Live progress (which step is running, results so far, errors) streams to the UI without polling.
- Per-tenant prompts are versioned, edited platform-side only, and tied to specific steps.
- Every run is fully observable: who triggered it, what each step did, what the LLM saw and returned, what tokens it cost.
- Failed runs are inspectable and resumable from the failing step.
- Adding a new LLM provider is a single ~250-line file.
- Adding a new tool is a single ~250-line file.
- Adding a new flow kind is a single file plus its prompts.

### 1.2 Non-goals (deferred)

- Mid-run user interaction / steerable agents (requires session-management; defer to spec #2.5 if/when needed).
- Multi-flow concurrency limits, queues per tenant tier (defer to billing spec).
- Semantic response caching beyond pgvector dedup of inputs (defer).
- OCR for scanned PDFs (defer).
- Playwright fallback for JS-heavy sites (defer; optional in v1.5 if Tavily/trafilatura miss too much).
- Custom user-authored prompts / prompt marketplaces (prompts remain platform-controlled).
- Fine-tuning, embeddings training, model hosting (we use API providers only).

---

## 2. Architecture overview

### 2.1 Layered design

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (apps/web)                                        │
│  Run kickoff form  ─►  Run progress page (Realtime)         │
│  Run history       ─►  Artifact viewer                      │
└──────────────────────────────┬──────────────────────────────┘
                               │  REST + Supabase Realtime
┌──────────────────────────────▼──────────────────────────────┐
│  FastAPI (apps/api)                                         │
│  /runs (create, get, list)  ─►  enqueue Prefect flow run    │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Prefect worker (same Docker image, separate process)       │
│  Loads flow ─► executes Steps in order ─► persists state    │
└──┬─────────────┬────────────┬──────────────┬────────────────┘
   │             │            │              │
   ▼             ▼            ▼              ▼
LLMProvider   Tool        run_steps       run_events
adapters    registry      table           table (CDC)
   │
   ├─► AnthropicAdapter
   ├─► OpenAIAdapter (GPT, Grok, Perplexity)
   ├─► GeminiAdapter
   └─► PerplexityAdapter (online citations)
```

### 2.2 Module layout (`apps/api/src/xtrusio_api/orchestration/`)

```
orchestration/
├── __init__.py
├── providers/
│   ├── __init__.py            # registry, get_provider(name)
│   ├── base.py                # LLMProvider protocol, types (~200 LoC)
│   ├── anthropic_adapter.py   # ~250 LoC
│   ├── openai_adapter.py      # ~250 LoC (also serves Grok via base_url override)
│   ├── gemini_adapter.py      # ~250 LoC
│   └── perplexity_adapter.py  # ~200 LoC (extends openai_adapter for online mode)
├── tools/
│   ├── __init__.py            # Tool registry
│   ├── base.py                # Tool protocol, ToolCall, ToolResult (~150 LoC)
│   ├── web_search.py          # Tavily + Brave fallback (~250 LoC)
│   ├── web_fetch.py           # httpx + trafilatura (~200 LoC)
│   ├── vector_search.py       # pgvector lookup (~150 LoC)
│   └── extract_pdf.py         # pypdf (~150 LoC, deferred unless needed in MVP)
├── primitives/
│   ├── step.py                # Step protocol, StepContext, StepResult (~200 LoC)
│   ├── runner.py              # Runner: walks step DAG, persists state (~300 LoC)
│   └── events.py              # Event publishing helpers (~100 LoC)
├── flows/
│   └── company_research/
│       ├── flow.py            # Prefect flow + step composition (~300 LoC)
│       ├── steps/
│       │   ├── validate_input.py        # ~100 LoC
│       │   ├── fetch_homepage.py        # ~150 LoC
│       │   ├── extract_company_profile.py  # LLM step (~200 LoC)
│       │   ├── generate_questions.py    # LLM step (~150 LoC)
│       │   ├── research_question.py     # parallel sub-flow (~250 LoC)
│       │   └── synthesize_report.py     # LLM step (~250 LoC)
│       └── schemas.py         # Pydantic input/output models (~200 LoC)
├── prompts/
│   ├── service.py             # CRUD, versioning, current-version resolution (~300 LoC)
│   └── routes.py              # /platform/prompts API (~200 LoC)
├── runs/
│   ├── service.py             # create, get, list, cancel runs (~250 LoC)
│   ├── routes.py              # /runs API (~200 LoC)
│   └── models.py              # SQLAlchemy models for runs/run_steps/run_events
└── cost/
    ├── pricing.py             # model_pricing lookup (~150 LoC)
    └── meter.py               # cost calculation per call (~150 LoC)
```

Every file targets 200-300 LoC per `ENGINEERING_PRINCIPLES.md` §1. Splits are pre-planned.

### 2.3 Request flow (kicking off a run)

1. Tenant user submits the run kickoff form on `/clients/<slug>/research/new`.
2. POST `/api/runs` with `{ kind: "company_research", input: { url, ... } }`.
3. FastAPI handler (with permission check): inserts `runs` row with `status=queued`, `started_by_user_id`, `tenant_id`.
4. Handler enqueues a Prefect flow run for `company_research_run` with `run_id` parameter.
5. Returns `{ run_id }` to the frontend. Frontend redirects to `/clients/<slug>/runs/:id`.
6. Frontend subscribes to Supabase Realtime channel `run_events:run_id=<id>` for live progress.

### 2.4 Run flow (Prefect worker side)

1. Prefect worker picks up the flow run.
2. Flow loads `runs` row, sets `status=running`, emits `run_started` event.
3. Walks each `Step` in order (or DAG):
   - Resolve required `prompts` (current published version) for the step.
   - Build the `StepContext` (run_id, tenant_id, prior step outputs, prompt body, tool registry).
   - Execute step's `run()`.
   - Persist `run_steps` row with input/output/tokens/cost.
   - Emit `step_completed` event to `run_events`.
   - On error: persist with `status=failed`, emit `step_failed`, retry per step retry policy, fail the flow if exhausted.
4. On completion: write final artifact, set `runs.status=succeeded`, set `runs.result`, emit `run_completed`.
5. On unrecoverable failure: set `runs.status=failed`, set `runs.error`, emit `run_failed`. Notification fires (email + in-app inbox once spec #3 lands).

---

## 3. Provider abstraction layer

### 3.1 The `LLMProvider` protocol

```python
class LLMProvider(Protocol):
    name: str                         # "anthropic", "openai", "gemini", "perplexity"
    capabilities: ProviderCapabilities  # supports_tools, supports_caching, supports_vision, ...

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        system: str | None = None,
        tools: Sequence[ToolSchema] | None = None,
        response_model: type[BaseModel] | None = None,
        max_tokens: int,
        temperature: float = 0.7,
        extra: dict[str, Any] | None = None,  # provider-specific (cache_control, online, etc.)
    ) -> LLMResponse: ...

    async def stream(
        self,
        *,
        model: str,
        messages: Sequence[Message],
        ...
    ) -> AsyncIterator[LLMChunk]: ...

    def estimate_cost(self, *, model: str, tokens_in: int, tokens_out: int) -> Decimal: ...
```

### 3.2 Common types

`Message`, `LLMResponse`, `LLMChunk`, `ToolSchema`, `ToolCall`, `ToolResult` are all Pydantic models. They are the **lingua franca** — every provider adapter converts to/from them. Steps only ever see these types, never raw SDK objects.

### 3.3 Adapter responsibilities

Each adapter (~250 LoC):

1. Translate our `Message`/`ToolSchema` types → provider's native format.
2. Call the native SDK (anthropic/openai/google-genai).
3. Translate response back → our `LLMResponse` (including normalized tool calls).
4. Compute cost from token counts using `cost.pricing` lookup.
5. Surface provider-specific features via the `extra` parameter:
   - Anthropic: `extra={"cache_control": "ephemeral"}` enables prompt caching.
   - Gemini: `extra={"grounding": True}` enables Google Search grounding.
   - Perplexity: `extra={"online": True}` returns citations.
   - OpenAI: `extra={"reasoning_effort": "high"}` for reasoning models.
6. Map provider errors → standard exceptions (`RateLimitError`, `ContextLengthError`, `ContentPolicyError`, `ProviderError`).

### 3.4 Provider registry

`providers/__init__.py` exposes:

```python
def get_provider(name: ProviderName) -> LLMProvider: ...
def list_providers() -> list[LLMProvider]: ...
```

Registry initialized at app startup from config. Each provider's API key comes from environment variables; the platform admin UI does not store provider keys (single set of keys for all tenants in MVP — per-tenant keys deferred).

### 3.5 Structured outputs via `instructor`

`response_model: type[BaseModel]` parameter means "give me back this Pydantic shape". Implemented via `instructor` library inside each adapter:

```python
async def chat(self, *, response_model=None, ...):
    if response_model is not None:
        client = instructor.from_anthropic(self._client)
        return await client.messages.create(response_model=response_model, ...)
    ...
```

`instructor` handles retries on schema validation failure across all providers — it's the right tool, already in the stack.

---

## 4. Tool layer

### 4.1 The `Tool` protocol

```python
class Tool(Protocol):
    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    requires: ToolRequirements   # network, llm, db, etc. — for permission gating

    async def execute(self, ctx: ToolContext, args: BaseModel) -> BaseModel: ...

    def to_provider_schema(self, provider: ProviderName) -> ToolSchema: ...
```

`ToolContext` carries `tenant_id`, `run_id`, `step_id`, the DB session, and a budget tracker (kills the call if it would exceed the per-step token/cost limit).

### 4.2 MVP tools

| Tool | Purpose | Underlying |
|---|---|---|
| `web_search` | Search the web, get clean ranked results | Tavily (primary), Brave (fallback) |
| `web_fetch` | Fetch a URL, return main content as Markdown | `httpx` + `trafilatura` |
| `vector_search` | Search prior tenant artifacts for cached research | `pgvector` over `artifacts` table |

### 4.3 `web_search` details

- Provider: Tavily (`api.tavily.com`) — purpose-built for AI agents, returns ranked results with snippets + extracted content.
- Cost: ~$0.005 per search, billed against the run.
- Fallback: Brave Search API on Tavily errors.
- Caching: identical query within the same run reuses the prior result (in-memory per run).
- Per-tenant override: if tenant config specifies a preferred search provider, use that.
- Returns: `WebSearchResult { query, results: list[SearchHit{ url, title, snippet, content_preview, published_at }] }`.

### 4.4 `web_fetch` details

- Default: `httpx.AsyncClient` with 15s timeout, 5MB max response, redirects followed (max 5).
- Content extraction: `trafilatura.extract(html, output_format="markdown", with_metadata=True)`.
- Content guards: reject if content < 200 chars (likely JS-heavy or blocked); reject if content > 200KB (truncate to first 200KB).
- Robots.txt: respected — `web_fetch` checks robots.txt cached for 1 hour per host before fetching.
- User-Agent: `Xtrusio-Research/1.0 (+https://xtrusio.com/bot)` — identifiable, polite.
- Returns: `WebFetchResult { url, status, title, content_md, fetched_at, word_count }`.

### 4.5 `vector_search` details

- Searches the tenant's `artifacts` table (created by past runs).
- Embeddings: `text-embedding-3-small` (cheap, fast) — costs metered per query.
- Top-K configurable per call (default 5, max 20).
- RLS-scoped (tenant_id filter is automatic).

### 4.6 Tool exposure to LLM

`Tool.to_provider_schema(provider)` produces the right format:
- Anthropic: `{ "name": ..., "description": ..., "input_schema": <JSON Schema> }`
- OpenAI: `{ "type": "function", "function": { "name": ..., "parameters": <JSON Schema> } }`
- Gemini: `{ "function_declarations": [...] }`
- Perplexity: same as OpenAI (compatible).

When the LLM calls a tool, the adapter normalizes to `ToolCall { name, args }`. The Step orchestrates the call: validates args → executes → records `run_steps` sub-row → returns `ToolResult` to the model in the format the provider expects.

---

## 5. Agent primitives

### 5.1 `Step`

```python
class Step(Protocol):
    name: str                                      # unique within a flow
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    retries: int = 2
    retry_delay: timedelta = timedelta(seconds=5)

    async def execute(self, ctx: StepContext, input: BaseModel) -> BaseModel: ...
```

A `Step` is a single unit of work — usually one LLM call, sometimes a tool call sequence. Examples:
- `ExtractCompanyProfileStep` — calls Claude with the homepage HTML + the `company_profile_extraction` prompt → returns structured `CompanyProfile`.
- `GenerateQuestionsStep` — calls GPT-4.1 with the `CompanyProfile` + `research_question_generation` prompt → returns `list[Question]`.
- `ResearchQuestionStep` — for one question, runs a small loop: web_search → top-N fetch → synthesize answer with Perplexity.

### 5.2 `StepContext`

Provides the step everything it needs:
- `run_id`, `tenant_id`, `step_id`
- `prompts: dict[str, ResolvedPrompt]` — prompts the step declared it needs, pre-resolved to current version
- `providers: ProviderRegistry`
- `tools: ToolRegistry`
- `prior_outputs: dict[str, Any]` — outputs of previous steps in the run
- `event_emitter`
- `cost_tracker`

### 5.3 `Runner`

Lives inside the Prefect flow. Given a list of steps and a run row:

1. For each step in order (or per the DAG):
   - Build context.
   - Validate input against step's schema.
   - Call `step.execute(ctx, input)`.
   - Persist `run_steps` row (input, output, tokens_in, tokens_out, cost_usd, provider, model, prompt_version_id, started_at, finished_at).
   - Emit progress event.
2. Compose final result.
3. On step failure: retry per step config; if exhausted, fail the run with rich error context (which step, which prompt version, what input, what error).

### 5.4 Why not LangGraph

Prefect provides flow control, retries, persistence, observability. Adding LangGraph means duplicating that machinery. Custom primitives are ~600 LoC total and give us full control over tenant scoping, cost tracking, and event emission — none of which LangGraph integrates with cleanly.

---

## 6. Concrete flow: `company_research_run`

### 6.1 Input

```python
class CompanyResearchInput(BaseModel):
    url: HttpUrl
    research_depth: Literal["quick", "standard", "deep"] = "standard"
    focus_areas: list[Literal["overview", "products", "competitors", "pricing", "news", "leadership"]] = ["overview", "products"]
```

### 6.2 Step sequence

```
1. ValidateInputStep       (no LLM)
2. FetchHomepageStep       (no LLM, uses web_fetch tool)
3. ExtractCompanyProfileStep   (LLM, prompt: company_profile_extraction)
4. GenerateQuestionsStep   (LLM, prompt: research_question_generation,
                            output: list[Question] with focus area attached)
5. For each Question (parallel, max concurrency 5):
    5a. SearchQuestionStep     (no LLM, uses web_search tool)
    5b. FetchTopResultsStep    (no LLM, uses web_fetch tool, top 3)
    5c. SynthesizeAnswerStep   (LLM, prompt: question_answer_synthesis,
                                provider: Perplexity online OR Claude with sources)
6. SynthesizeReportStep    (LLM, prompt: report_synthesis,
                            input: CompanyProfile + answered_questions,
                            output: structured ResearchReport)
7. PersistArtifactStep     (no LLM, writes to artifacts + R2 if exporting PDF)
```

`research_depth` controls:
- `quick`: skip step 5 sub-fetches (synthesize from search snippets only); 5 questions.
- `standard`: full pipeline; 8 questions.
- `deep`: full pipeline; 15 questions; double-pass synthesis.

### 6.3 Per-step model routing (default)

| Step | Default model | Rationale |
|---|---|---|
| 3 (ExtractProfile) | Claude Sonnet | High accuracy on extraction; structured output via instructor |
| 4 (GenerateQuestions) | GPT-4.1 | Good at creative question diversity |
| 5c (Synthesize answer) | Perplexity Sonar Online | Web-grounded answers with citations native |
| 6 (Synthesize report) | Claude Opus | Best long-context synthesis |

These are *defaults*. Per-tenant config (in `prompts.params`) can override the model + provider for any step. This is how a tenant can opt into a cheaper model tier or a specialized one.

### 6.4 Output: `ResearchReport`

Structured Pydantic model with sections (overview, products, competitors, etc.), each with answers + citations. Stored as `artifacts.body jsonb`. Frontend renders with a typed schema → consistent UI across runs.

---

## 7. Run state persistence

### 7.1 Tables

```
runs(
  id uuid pk,
  tenant_id uuid fk → tenants,
  kind text,                          -- "company_research"
  input jsonb,
  status text,                        -- queued|running|succeeded|failed|cancelled
  started_by_user_id uuid fk → users,
  prefect_flow_run_id text,
  started_at timestamptz,
  finished_at timestamptz,
  result jsonb,                       -- final artifact reference / inline result
  error jsonb,                        -- error class, message, step_id where it failed
  total_tokens_in int,
  total_tokens_out int,
  total_cost_usd numeric(10,6),
  total_steps int,
  steps_completed int,
  created_at, updated_at
)

run_steps(
  id uuid pk,
  run_id uuid fk → runs,
  step_name text,
  step_index int,
  parent_step_id uuid,                -- for parallel sub-steps under step 5
  attempt int,
  status text,                        -- queued|running|succeeded|failed|skipped
  input jsonb,
  output jsonb,
  provider text,                      -- nullable (no-LLM steps)
  model text,                         -- nullable
  prompt_id uuid,                     -- nullable
  prompt_version_id uuid,             -- nullable, frozen for run reproducibility
  tools_called jsonb,                 -- list of {tool_name, args, result_summary}
  tokens_in int,
  tokens_out int,
  cost_usd numeric(10,6),
  started_at, finished_at,
  error jsonb
)

run_events(
  id uuid pk,
  run_id uuid fk → runs,
  kind text,                          -- run_started|step_started|step_progress|step_completed|step_failed|run_completed|run_failed
  step_id uuid,                       -- nullable
  payload jsonb,
  created_at timestamptz
)

artifacts(
  id uuid pk,
  tenant_id uuid fk,
  run_id uuid fk,
  kind text,                          -- "research_report"
  body jsonb,
  embedding vector(1536),             -- for vector_search reuse
  r2_key text,                        -- if exported to PDF
  created_at
)
```

### 7.2 RLS

All four tables are tenant-scoped (RLS enforces `tenant_id = current_tenant_id`). Platform users with non-impersonation context can read across tenants per the `platform_bypass` policy from spec #1.

`run_events` retention: 30 days after `runs.finished_at` (high volume, low value after run completes).
`run_steps` retention: 90 days after `runs.finished_at`.
`runs`: indefinite (with archival to R2 after 1 year if needed).

### 7.3 Indexes

- `runs(tenant_id, status, started_at DESC)` — for run history listings
- `runs(prefect_flow_run_id)` UNIQUE — for Prefect callback lookup
- `run_steps(run_id, step_index)` — for ordered display
- `run_events(run_id, created_at DESC)` — for event feed
- `artifacts USING ivfflat (embedding vector_cosine_ops)` — vector search

---

## 8. Live progress: Supabase Realtime

The frontend subscribes to changes on the `run_events` table filtered by `run_id`. Postgres CDC streams INSERTs to the WebSocket, the frontend updates its progress UI directly.

```ts
const channel = supabase
  .channel(`run:${runId}`)
  .on("postgres_changes",
      { event: "INSERT", schema: "public", table: "run_events",
        filter: `run_id=eq.${runId}` },
      handleEvent)
  .subscribe();
```

Why this beats SSE/custom WebSocket:
- No new endpoint, no protocol design.
- Supabase Realtime auth uses the same JWT — RLS is enforced (tenant A can't subscribe to tenant B's run).
- Reconnect handling and backfill (events on reconnect) are managed by the Realtime client.

---

## 9. Per-tenant prompts

### 9.1 Data model

```
prompts(
  id uuid pk,
  tenant_id uuid fk → tenants,        -- NULLABLE: NULL means "system default", inherited by tenants without an override
  key text,                           -- "company_profile_extraction", "research_question_generation"
  name text,                          -- display name
  description text,
  kind text,                          -- "system", "extraction", "generation", "synthesis"
  current_version_id uuid,
  created_at, updated_at,
  UNIQUE(tenant_id, key)              -- composite key: (NULL, "company_profile_extraction") is the system default;
                                      -- (acme_id, "company_profile_extraction") is Acme's override
)

prompt_versions(
  id uuid pk,
  prompt_id uuid fk,
  version int,                        -- monotonic, starts at 1
  body text,                          -- the prompt template (uses Jinja2 syntax for {{var}} interpolation)
  model text,                         -- which model this prompt is tuned for
  provider text,                      -- which provider
  params jsonb,                       -- temperature, max_tokens, response_model_name, tools_enabled
  created_by_user_id uuid fk,
  created_at,
  published_at,                       -- nullable, set when promoted to current
  archived_at,                        -- nullable, set when superseded
  UNIQUE(prompt_id, version)
)
```

### 9.2 RLS

- **No tenant role can read or write `prompts` or `prompt_versions`.** Even `tenant_owner`. This is core to the product: prompts are platform IP; tenants get features driven by them but never see them.
- **Platform users with `prompts.write` permission** (super_admin, admin, editor) can CRUD tenant-specific prompts (rows where `tenant_id IS NOT NULL`).
- **System default prompts** (`tenant_id IS NULL`) can only be edited by `super_admin`. Editing a default affects every tenant that hasn't customized that key — high blast radius, requires the highest role.
- The orchestration runtime (a service role) reads prompts via a security-definer function, so RLS doesn't block the runner.

### 9.3 Prompt resolution at runtime

When a step declares `requires_prompt = "company_profile_extraction"`, the runner does a single CTE-style lookup that prefers the tenant-specific row over the system default:

```sql
SELECT pv.*
FROM prompts p
JOIN prompt_versions pv ON pv.id = p.current_version_id
WHERE p.key = $key
  AND (p.tenant_id = $tenant_id OR p.tenant_id IS NULL)
ORDER BY p.tenant_id NULLS LAST   -- tenant-specific first, system default as fallback
LIMIT 1
```

The resolved `prompt_version_id` is **frozen onto the `run_steps` row** — runs are reproducible against the prompt version they actually used, even after the prompt is later edited or the tenant adds an override.

If no system default exists either (programming error: a step references a key with no seed), the runner fails the step with a `PromptNotFoundError`. CI catches this via a static check that every `Step.requires_prompt` value has a matching seeded default.

### 9.4 Editing & publishing

- Platform admin opens `/platform/clients/<slug>/prompts` → list of prompts for that tenant.
- Click a prompt → see all versions, current version highlighted.
- "Edit" creates a new draft version (incremented version number, `published_at = NULL`).
- "Test" runs the draft against a sample input (small, cheap model) showing the output side-by-side with the current version.
- "Publish" sets `prompt_versions.published_at = now()` and `prompts.current_version_id = <new_id>`. Old version is kept (now `archived_at = now()`).
- All actions logged to `platform_audit_log`.

### 9.5 Default prompt catalog

System-default prompts ship in `apps/api/src/xtrusio_api/orchestration/flows/company_research/default_prompts/*.j2`. Migrations seed them as `prompts` rows with `tenant_id = NULL` (special "system" tenant). Tenants inherit until customized.

---

## 10. Cost & token metering

### 10.1 `model_pricing` table

```
model_pricing(
  provider text,
  model text,
  input_per_1k numeric(10,6),
  output_per_1k numeric(10,6),
  effective_from timestamptz,
  effective_to timestamptz,           -- nullable for current
  UNIQUE(provider, model, effective_from)
)
```

Maintained by platform team. Migrations seed initial rows for current Claude/GPT/Gemini/Perplexity pricing as of the implementation date. New rows added when providers change pricing — historical runs retain their original cost (we look up by `effective_from <= run_started_at < effective_to`).

### 10.2 Cost computation

Every `LLMProvider.chat()` returns `tokens_in`, `tokens_out`. Adapter computes `cost_usd = pricing.input_per_1k * tokens_in / 1000 + pricing.output_per_1k * tokens_out / 1000`. Stored on `run_steps.cost_usd`. Aggregated into `runs.total_cost_usd` on flow completion.

### 10.3 Budget enforcement

Per-run hard ceiling configurable via tenant config (`runs_max_cost_usd`, default 5.00). `cost_tracker` in `StepContext` tracks running total; if a step would exceed budget, it raises `BudgetExceeded` and the run aborts with a clear error. Tenant admin sees this in their UI.

### 10.4 Tenant-facing cost views

- Per-run cost (in run history listing)
- Per-run breakdown (in run detail page: cost per step, cost per provider)
- Tenant-level monthly aggregate (in `/clients/<slug>/usage`, deferred to billing spec but the data is there from day one)

---

## 11. Frontend

### 11.1 New routes (under `/clients/:slug/`)

- `/research` — list of runs (TanStack Table, paginated, filter by status/date)
- `/research/new` — kickoff form (URL input, depth selector, focus areas multi-select)
- `/research/:runId` — run detail page (live progress + final artifact)

Plus platform-side:
- `/platform/clients/:slug/prompts` — prompt management
- `/platform/clients/:slug/prompts/:promptId` — versions + editor + test runner

### 11.2 Run detail page

Three regions:
1. **Header** — status badge, started_at, total cost, elapsed, kickoff input recap.
2. **Steps timeline** — vertical list of steps with status icons, expand each to see input/output preview, tools called, tokens, cost, duration. Live-updated via Realtime.
3. **Artifact** — once `runs.status=succeeded`, renders the `ResearchReport` with structured sections, citations, "Export PDF" / "Copy to Clipboard" actions.

Failed runs show the failing step expanded by default with the error, and a "Retry from this step" button (platform users only in MVP; tenant retry deferred).

### 11.3 Prompt editor (platform-only)

Monaco editor for the prompt body (Jinja2 syntax highlighting). Side panel: `model`, `provider`, `temperature`, `max_tokens`, `response_model_name`, `tools_enabled` toggles. Right pane: "Test against sample input" — picks a saved sample, runs the prompt, shows output + cost. "Compare with current" diff view.

---

## 12. Permissions added by spec #2

New permission keys (added to `permissions` table per spec #1 conventions):

| Key | Granted to roles |
|---|---|
| `runs.create` | tenant: owner, admin, editor — platform: super_admin, admin |
| `runs.read` | tenant: all roles (RLS scopes them) — platform: super_admin, admin |
| `runs.cancel` | tenant: owner, admin — platform: super_admin, admin |
| `prompts.read` | platform: super_admin, admin, editor (NEVER tenant) |
| `prompts.write` | platform: super_admin, admin, editor |
| `prompts.publish` | platform: super_admin, admin |
| `pricing.write` | platform: super_admin |

---

## 13. Testing strategy

### 13.1 Adapter tests

For each provider adapter: integration tests against real APIs (gated behind `RUN_LIVE_LLM_TESTS=1` env var — not in regular CI; runs nightly with budget cap). Unit tests against recorded fixtures (saved real responses) for normal CI runs.

### 13.2 Tool tests

`web_search` / `web_fetch` mocked with `respx` for unit tests. Integration tests against real endpoints in nightly job with allowlisted target URLs.

### 13.3 Step tests

Each step has unit tests with mocked providers and tools. Tests assert: input validation, prompt resolution, output schema conformance, token/cost recording.

### 13.4 Flow tests

`company_research_run` end-to-end test against a fixture URL (e.g., `https://example.com`) with all providers/tools mocked. Asserts: every step ran, artifact has expected shape, cost is computed, all `run_events` were emitted in order.

### 13.5 RLS tests

Per spec #1 §6.4: every new table (`runs`, `run_steps`, `run_events`, `artifacts`, `prompts`, `prompt_versions`, `model_pricing`) has RLS isolation tests.

### 13.6 Live LLM smoke (deferred)

Run on demand locally during development: `make smoke-live` invokes the full `company_research_run` flow against a fixed canary URL with a $0.50 budget cap. Catches provider API breakage, prompt regression, tool reliability. Scheduling this nightly via CI/CD is part of the deferred CI work (see §14).

---

## 14. CI additions on top of spec #1 (deferred — see project policy)

**Deferred until local development runs cleanly end-to-end** (project policy 2026-05-08, identical to spec #1 §14). The lint rules and integrity checks below are still implemented as **local commands** (runnable via `make lint` / `make check-prompts` / etc.), they are simply not wired into CI runners until the readiness bar is met.

Local checks to implement:
- Static check: every `Step` subclass must define `input_schema`, `output_schema`, `name`. Fail-fast at app startup; lint script wraps it.
- Static check: every step that calls an LLM must declare `requires_prompt = "..."`.
- Pricing-table integrity check: every model used in any step's default config has a current pricing row.
- Live-LLM smoke as a manual `make smoke-live` target.

When the local-stable bar is met, these become CI lanes alongside spec #1's deferred CI lanes.

---

## 15. Local development additions

- `docker-compose.yml` adds a Prefect Server container.
- `make dev` starts a Prefect worker process.
- Provider API keys loaded from `.env.local` (gitignored; `.env.example` lists required keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `PERPLEXITY_API_KEY`, `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`).
- Without LLM keys: `make dev-mock` starts with a `MockLLMProvider` that returns canned responses for fast local iteration without burning real tokens.

---

## 16. Open questions for follow-up specs

1. **Per-tenant LLM API keys.** MVP uses platform-wide keys. Spec #N should add per-tenant key storage (encrypted at rest, decrypted at provider-init time only) for tenants who want to BYOK.
2. **Mid-run clarifying questions.** Spec #2.5 — agent pauses, asks user, resumes (Q2=C upgrade).
3. **Multi-flow concurrency limits** per tenant tier.
4. **Semantic response cache** (beyond pgvector dedup).
5. **Prompt A/B testing** (route X% of runs to draft prompt, compare outcomes).
6. **Custom user-authored tools** (tenant-defined webhooks the agent can call).
7. **Eval harness** — gold-standard inputs with scored outputs for prompt regression detection.

---

## 17. Success criteria (acceptance)

Spec #2 is complete when:

1. A platform admin can create a tenant, configure the `company_research` feature flag, edit & publish all six prompts for that tenant, and see them in the prompt management UI.
2. A tenant editor logs in, navigates to `/clients/<slug>/research/new`, submits a URL, gets redirected to the run detail page.
3. The run detail page shows live progress: `validate_input → fetch_homepage → extract_profile → generate_questions → research_question (×8 parallel) → synthesize_report → persist_artifact`. Each step's status updates within 1s of completion via Realtime.
4. Final artifact renders with structured sections, citations, and metadata (tokens, cost, duration).
5. Provider routing is observable: each step's `run_steps` row records which provider+model was used.
6. Per-run cost is computed and visible. Budget exceeded aborts the run with a clear error.
7. Tenant users cannot access `/platform/...prompts` (RLS + route guard).
8. Failed runs are inspectable; the failing step is highlighted with full error context.
9. RLS test suite covers all new tables.
10. Nightly live-LLM smoke is green.
11. All files are under 500 LoC per `ENGINEERING_PRINCIPLES.md` §1.

---

## 18. Estimated scope

5-7 weeks for one or two engineers, assuming spec #1 has shipped. Risks:
- Provider API drift during build (mitigated by adapter isolation — each adapter is its own file).
- Prompt quality (the prompts in the default catalog need real evaluation against sample companies; allocate explicit time for prompt iteration with real outputs).
- Tavily/Brave reliability and cost — need a budget alarm in week 1.
- Prefect operational complexity (new infra component; 2-3 days to get smooth deploys).
