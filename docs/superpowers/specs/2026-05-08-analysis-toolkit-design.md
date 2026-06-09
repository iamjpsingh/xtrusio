# Spec #3 — Analysis Toolkit Design

**Status:** draft, awaiting user review
**Date:** 2026-05-08
**Owner:** platform team
**Depends on:** spec #1 (multi-tenant foundation), spec #2 (prompt orchestration)
**Related docs:** `docs/superpowers/ENGINEERING_PRINCIPLES.md`, `Algo.md`

---

## 1. Purpose & Scope

### 1.1 Purpose

A reusable, library-style analysis toolkit that any agentic flow (today: `company_research_run` from spec #2; tomorrow: any new flow) can call to run deterministic, audit-credible computations on text artifacts. The toolkit is **generic**, not tied to a specific product use case (e.g. perception audit). Specific product features compose these primitives; the primitives know nothing about the product.

The toolkit's value proposition is the same as `Algo.md`'s: "Use battle-tested libraries, not hand-rolled code. Pick algorithms that are explainable to a client."

### 1.2 In scope (v1)

Six algorithm primitives, chosen for the "Day-1 + similarity (medium)" tier of `Algo.md`:

| # | Algorithm | Library | Purpose |
|---|---|---|---|
| 1 | Aho-Corasick multi-pattern match | `pyahocorasick` | Find all occurrences of any pattern in text in one pass |
| 2 | Damerau-Levenshtein fuzzy match | `rapidfuzz` | Match a query against many candidates with edit-distance tolerance |
| 3 | MinHash + Jaccard | `datasketch` | Cheap lexical similarity between two texts |
| 4 | Embedding cosine similarity | `sentence-transformers` (`all-MiniLM-L6-v2`) | Semantic similarity between two texts |
| 5 | Wilson score confidence interval | `statsmodels` | Defensible CI on binomial proportions |
| 6 | SHA-256 content addressing | `hashlib` (stdlib) | Deterministic content hash for caching and dedup |

### 1.3 Out of scope (v1)

- **Pattern catalog management.** Tools accept patterns as arguments; persisting and managing per-tenant pattern lists is a follow-up spec.
- **Algorithms 6/9/10 from Algo.md** (reservoir sampling, PageRank, Myers diff). Slot in when needed.
- **TF-IDF lifecycle classifier** (algo 3 from `Algo.md`) — domain-specific feature, deferred.
- **Pgvector ANN search.** v1 uses pgvector only for exact-key cache lookups, not similarity search.
- **End-to-end flow integration tests.** Owned by spec #2's flow tests; this spec proves primitives work in isolation.
- **CI/CD setup.** Per project policy, CI lanes are added only after local development runs cleanly end-to-end.

### 1.4 Non-goals

- Replacing or wrapping the LLM provider abstraction from spec #2.
- Becoming a feature-flagged "rules engine" or DSL.
- Learning anything from data — the toolkit is deterministic; ML models it ships are pre-trained and pinned.

---

## 2. Module Layout

### 2.1 Package location

```
apps/api/src/xtrusio_api/analysis/
├── __init__.py                    # public re-exports
├── README.md                      # quickstart for callers
├── types.py                       # Pydantic input/output models  (~150 LoC)
├── errors.py                      # AnalysisError hierarchy        (~50 LoC)
│
├── matching/
│   ├── __init__.py
│   ├── aho_corasick.py            # multi_pattern_match()           (~200 LoC)
│   ├── fuzzy.py                   # fuzzy_match(), normalize_variants() (~150 LoC)
│   └── automaton_cache.py         # Valkey-backed AC automaton cache (~120 LoC)
│
├── similarity/
│   ├── __init__.py
│   ├── minhash.py                 # signature(), jaccard()          (~250 LoC)
│   ├── embedding.py               # embed(), cosine() — workers-only (~200 LoC)
│   └── embedding_cache.py         # pgvector-backed cache            (~180 LoC)
│
├── stats/
│   ├── __init__.py
│   └── wilson.py                  # wilson_interval()                (~80 LoC)
│
└── tools/
    ├── __init__.py                # register_analysis_tools(registry)
    ├── match_tool.py              # MultiPatternMatchTool(Tool)      (~120 LoC)
    ├── fuzzy_tool.py              # FuzzyMatchTool                   (~100 LoC)
    ├── similarity_tool.py         # TextSimilarityTool               (~150 LoC)
    └── stats_tool.py              # WilsonIntervalTool               (~80 LoC)
```

Every file targets ≤ 250 LoC; hard ceiling 500 LoC per `ENGINEERING_PRINCIPLES.md` section 1.

### 2.2 Cross-package shared utility

SHA-256 content addressing is a primitive used by both orchestration (LLM-call dedup, spec #2) and analysis (embedding cache key). It does not belong in `analysis/`.

```
apps/api/src/xtrusio_api/shared/cache/
└── content_hash.py                # canonicalize() + sha256_of()    (~80 LoC)
```

`canonicalize()` performs NFKC normalization, collapses whitespace, lowercases ASCII. `sha256_of()` returns a hex digest of the canonical form. Both are pure functions, fully tested in `apps/api/tests/shared/cache/`.

### 2.3 Runtime dependencies

Added to `apps/api/pyproject.toml`:

| Library | Version pin | Where installed |
|---|---|---|
| `pyahocorasick` | `^2.1.0` | base |
| `rapidfuzz` | `^3.9.0` | base |
| `datasketch` | `^1.6.5` | base |
| `statsmodels` | `^0.14.0` | base |
| `numpy` | `^2.0.0` | base (already present) |
| `sentence-transformers` | `^3.0.0` | **`ml` extra only** |

### 2.4 Install split

`sentence-transformers` ships in an optional Poetry/uv extra named `ml`. The API process installs without `ml`; worker processes (Dramatiq, Prefect) install with `ml`. This keeps the API container ≈150MB lighter and prevents the 80MB MiniLM model from ever loading in the request-serving tier.

```toml
[project.optional-dependencies]
ml = ["sentence-transformers~=3.0.0"]
```

Installed locally as:
```
uv sync                # API dev shell
uv sync --extra ml     # worker dev shell
```

---

## 3. Input/Output Types & Function Signatures

All public functions take Pydantic v2 models in and return Pydantic v2 models out. Per `ENGINEERING_PRINCIPLES.md` section 3: "Pydantic v2 models for all I/O. Never accept dicts at API boundaries." The same rule extends to library boundaries — keeps the toolkit self-documenting and gives Tool wrappers their schemas for free.

### 3.1 Shared types (`analysis/types.py`)

```python
from typing import Literal, NewType
from uuid import UUID
from pydantic import BaseModel, Field

TenantId = NewType("TenantId", UUID)

# --- Matching ---
class PatternMatch(BaseModel):
    pattern: str           # original pattern as supplied
    canonical: str         # canonicalized form (lower + nfkc)
    start: int             # char offset in haystack
    end: int               # exclusive char offset
    matched_text: str      # actual substring (may differ in case)

class MultiPatternMatchInput(BaseModel):
    text: str
    patterns: list[str] = Field(min_length=1, max_length=10_000)
    case_sensitive: bool = False

class MultiPatternMatchResult(BaseModel):
    matches: list[PatternMatch]
    pattern_hit_counts: dict[str, int]
    elapsed_ms: float

class FuzzyMatchInput(BaseModel):
    query: str
    candidates: list[str] = Field(min_length=1, max_length=50_000)
    threshold: int = Field(default=85, ge=0, le=100)
    limit: int = Field(default=5, ge=1, le=100)

class FuzzyMatch(BaseModel):
    candidate: str
    score: int        # 0-100, higher is better
    distance: int     # raw Damerau-Levenshtein

class FuzzyMatchResult(BaseModel):
    matches: list[FuzzyMatch]   # sorted desc by score
    elapsed_ms: float

# --- Similarity ---
class MinHashInput(BaseModel):
    text: str
    num_perm: int = Field(default=128, ge=16, le=512)
    shingle_size: int = Field(default=3, ge=1, le=10)

class MinHashSignature(BaseModel):
    signature: list[int]    # length == num_perm
    num_perm: int
    shingle_size: int

class JaccardInput(BaseModel):
    a: MinHashSignature
    b: MinHashSignature

class JaccardResult(BaseModel):
    similarity: float       # 0.0-1.0
    elapsed_ms: float

class EmbedInput(BaseModel):
    tenant_id: TenantId
    texts: list[str] = Field(min_length=1, max_length=256)
    use_cache: bool = True

class Embedding(BaseModel):
    text_hash: str          # SHA-256 hex of canonicalized input
    vector: list[float]     # length 384 for MiniLM-L6-v2
    model: str              # "sentence-transformers/all-MiniLM-L6-v2"
    cached: bool            # True if hit pgvector cache

class EmbedResult(BaseModel):
    embeddings: list[Embedding]   # same order as input
    elapsed_ms: float
    cache_hit_rate: float          # 0.0-1.0

class CosineInput(BaseModel):
    a: list[float]
    b: list[float]

class CosineResult(BaseModel):
    similarity: float       # -1.0 to 1.0
    elapsed_ms: float

class TextSimilarityInput(BaseModel):
    tenant_id: TenantId | None = None     # required only for embedding method
    text_a: str
    text_b: str
    method: Literal["minhash", "embedding"] = "minhash"

class TextSimilarityResult(BaseModel):
    method: Literal["minhash", "embedding"]
    similarity: float
    elapsed_ms: float

# --- Stats ---
class WilsonInput(BaseModel):
    successes: int = Field(ge=0)
    trials: int = Field(gt=0)
    confidence: float = Field(default=0.95, gt=0, lt=1)

class WilsonResult(BaseModel):
    point_estimate: float       # successes / trials
    lower: float
    upper: float
    confidence: float
    method: Literal["wilson"]
```

### 3.2 Public function signatures

```python
# matching/aho_corasick.py
async def multi_pattern_match(
    inp: MultiPatternMatchInput,
    *,
    cache: AutomatonCache | None = None,
) -> MultiPatternMatchResult: ...

# matching/fuzzy.py
async def fuzzy_match(inp: FuzzyMatchInput) -> FuzzyMatchResult: ...

async def normalize_variants(
    variants: list[str], threshold: int = 85
) -> dict[str, str]:                        # variant → canonical form

# similarity/minhash.py
def minhash_signature(inp: MinHashInput) -> MinHashSignature: ...
def jaccard(inp: JaccardInput) -> JaccardResult: ...

# similarity/embedding.py — RAISES at import time if XTRUSIO_PROCESS_ROLE != "worker"
async def embed(
    inp: EmbedInput,
    *,
    cache: EmbeddingCache,                  # DI required
    db: AsyncSession,                       # DI required
) -> EmbedResult: ...

def cosine(inp: CosineInput) -> CosineResult: ...

# stats/wilson.py
def wilson_interval(inp: WilsonInput) -> WilsonResult: ...
```

### 3.3 Three deliberate design choices

**1. `embed()` requires DI for cache and DB session, no defaults.** Forces callers to acknowledge they're hitting persistence and a worker-only path. Per `ENGINEERING_PRINCIPLES.md` section 4.

**2. `embed()` import in API process raises.** `analysis/similarity/embedding.py` runs at module-import time:

```python
import os
if os.environ.get("XTRUSIO_PROCESS_ROLE") != "worker":
    raise ImportError(
        "xtrusio_api.analysis.similarity.embedding may only be imported "
        "in worker processes. Set XTRUSIO_PROCESS_ROLE=worker."
    )
```

Workers set `XTRUSIO_PROCESS_ROLE=worker` in their entrypoint. Catches the misconfiguration that would otherwise leak the 80MB model into API memory.

**3. Async vs sync split is intentional.**

- `async def` for I/O-bound work (cache, DB, network) and CPU-batches that should yield (`multi_pattern_match` over long text).
- `def` for pure CPU functions ≤ 1ms (`jaccard`, `cosine`, `wilson_interval`).

Avoids the anti-pattern of `async def` everywhere — sync functions pretending to be async hide the real concurrency story.

---

## 4. Tool-Protocol Wrappers & Registration

These adapt the pure functions in section 3 to spec #2's `Tool` protocol so they're callable both by deterministic flow steps **and** by LLM agent steps that decide to invoke a tool.

### 4.1 Tool protocol (recap from spec #2)

```python
# orchestration/primitives/tool.py — defined in spec #2 section 5
class Tool(Protocol):
    name: str                           # globally unique
    description: str                    # shown to LLM
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    requires: frozenset[str]            # capabilities, e.g. {"db", "tenant_scope"}
    async def run(self, ctx: ToolContext, inp: BaseModel) -> BaseModel: ...
```

`ToolContext` carries: `tenant_id`, `run_id`, `db: AsyncSession`, `valkey`, `cost_meter`, `logger`. Tools never reach for globals.

### 4.1.1 Algorithm-to-tool mapping

The six algorithms in section 1.2 expose **four** Tool wrappers, not six:

| Algorithm | Tool wrapper? | Rationale |
|---|---|---|
| Aho-Corasick | `MultiPatternMatchTool` | LLMs can usefully decide to scan text for patterns. |
| rapidfuzz | `FuzzyMatchTool` | LLMs can usefully decide to fuzzy-match candidates. |
| MinHash | merged into `TextSimilarityTool` (`method="minhash"`) | Single similarity surface; method discriminator avoids cluttering the LLM's tool list. |
| Embedding cosine | merged into `TextSimilarityTool` (`method="embedding"`) | Same. |
| Wilson CI | `WilsonIntervalTool` | Useful for any scoring/audit step. |
| SHA-256 content addressing | **no Tool wrapper** | Plumbing primitive used internally by caches and runners. Lives in `shared/cache/content_hash.py` (section 2.2). Never something an LLM should call — it's deterministic, side-effect-free, and produces output the LLM cannot interpret. |

### 4.2 The four wrappers

```python
# analysis/tools/match_tool.py
class MultiPatternMatchTool(Tool):
    name = "analysis.multi_pattern_match"
    description = (
        "Find every occurrence of any pattern from a list inside a body of text. "
        "Returns char offsets and per-pattern hit counts. Use when scanning for "
        "many keywords at once (vendor names, brand mentions, etc.)."
    )
    input_schema = MultiPatternMatchInput
    output_schema = MultiPatternMatchResult
    requires = frozenset({"valkey"})

    async def run(self, ctx, inp):
        cache = AutomatonCache(ctx.valkey)
        result = await multi_pattern_match(inp, cache=cache)
        ctx.logger.info(
            "ac.match", patterns=len(inp.patterns), hits=len(result.matches)
        )
        return result

# analysis/tools/fuzzy_tool.py
class FuzzyMatchTool(Tool):
    name = "analysis.fuzzy_match"
    description = (
        "Find candidates similar to a query string with edit-distance tolerance. "
        "Returns sorted matches with scores. Use for normalizing name variants."
    )
    input_schema = FuzzyMatchInput
    output_schema = FuzzyMatchResult
    requires = frozenset()
    async def run(self, ctx, inp): return await fuzzy_match(inp)

# analysis/tools/similarity_tool.py — combines MinHash + cosine
class TextSimilarityTool(Tool):
    name = "analysis.text_similarity"
    description = (
        "Measure similarity between two texts. method='minhash' is fast and "
        "lexical; method='embedding' is slower but semantic (catches paraphrases)."
    )
    input_schema = TextSimilarityInput
    output_schema = TextSimilarityResult
    requires = frozenset({"db", "tenant_scope"})

    async def run(self, ctx, inp):
        if inp.method == "minhash":
            sig_a = minhash_signature(MinHashInput(text=inp.text_a))
            sig_b = minhash_signature(MinHashInput(text=inp.text_b))
            j = jaccard(JaccardInput(a=sig_a, b=sig_b))
            return TextSimilarityResult(
                method="minhash", similarity=j.similarity, elapsed_ms=j.elapsed_ms,
            )
        cache = EmbeddingCache(ctx.db)
        emb = await embed(
            EmbedInput(tenant_id=ctx.tenant_id, texts=[inp.text_a, inp.text_b]),
            cache=cache, db=ctx.db,
        )
        c = cosine(CosineInput(a=emb.embeddings[0].vector, b=emb.embeddings[1].vector))
        ctx.cost_meter.record_embedding(model=emb.embeddings[0].model, count=2)
        return TextSimilarityResult(
            method="embedding", similarity=c.similarity,
            elapsed_ms=emb.elapsed_ms + c.elapsed_ms,
        )

# analysis/tools/stats_tool.py
class WilsonIntervalTool(Tool):
    name = "analysis.wilson_interval"
    description = "Compute a Wilson score confidence interval for a binomial proportion."
    input_schema = WilsonInput
    output_schema = WilsonResult
    requires = frozenset()
    async def run(self, ctx, inp): return wilson_interval(inp)
```

### 4.3 Registration

```python
# analysis/tools/__init__.py
def register_analysis_tools(registry: ToolRegistry) -> None:
    """Called once at app startup, after register_orchestration_tools()."""
    registry.register(MultiPatternMatchTool())
    registry.register(FuzzyMatchTool())
    registry.register(TextSimilarityTool())
    registry.register(WilsonIntervalTool())
```

The orchestration startup hook in `apps/api/src/xtrusio_api/orchestration/bootstrap.py` calls `register_analysis_tools(registry)` after registering its own tools.

### 4.4 Two surfaces, one implementation

| Caller | How it calls |
|---|---|
| **Deterministic flow step** | Imports the pure function: `from xtrusio_api.analysis.matching import multi_pattern_match`. No tool ceremony. |
| **LLM agent step** | Receives the wrapper from the registry. `ctx.tools.call("analysis.multi_pattern_match", inp)` resolves through the registry. |

Same code path under the hood. Tests cover the pure function thoroughly; Tool wrappers get a single integration test each that proves wiring works.

### 4.5 Tool exposure is per-step

`Step.tools` from spec #2 section 5.3 controls which tools are exposed to which agent step. Analysis tools are **not** auto-injected everywhere — flows opt them in per step. Example: a comparison step adds `analysis.text_similarity` to its tool list; a research step does not.

### 4.6 Cost & observability

- The embedding path of `TextSimilarityTool` records cost via `ctx.cost_meter` (spec #2 section 10).
- Every tool emits `run_event` rows through `ctx.logger.tool_*` (spec #2 section 7) — call/result/error/duration. Already wired by spec #2's runner; analysis tools inherit the behavior automatically.
- Aho-Corasick automaton cache hit rate is logged as a structured metric for tuning.

---

## 5. Persistence — Embedding Cache

The toolkit's only persistent surface. Everything else is in-memory or Valkey TTL.

### 5.1 Table

```sql
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector, already required by spec #1

CREATE TABLE analysis_embedding_cache (
    -- identity
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     uuid        NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    text_hash     text        NOT NULL,        -- SHA-256 hex of canonicalized text
    model         text        NOT NULL,        -- e.g. "sentence-transformers/all-MiniLM-L6-v2"
    model_version text        NOT NULL,        -- pinned major.minor; cache invalidation key

    -- payload
    vector        vector(384) NOT NULL,        -- 384 dims for MiniLM-L6-v2
    text_preview  text        NOT NULL,        -- first 200 chars (debugging only)
    text_length   integer     NOT NULL,

    -- bookkeeping
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_hit_at   timestamptz NOT NULL DEFAULT now(),
    hit_count     integer     NOT NULL DEFAULT 1,

    CONSTRAINT analysis_embedding_cache_uniq
        UNIQUE (tenant_id, text_hash, model, model_version)
);

CREATE INDEX analysis_embedding_cache_tenant_idx
    ON analysis_embedding_cache (tenant_id);

CREATE INDEX analysis_embedding_cache_lru_idx
    ON analysis_embedding_cache (last_hit_at);
-- No pgvector ANN index in v1: cache is read by exact (tenant_id, text_hash, model) lookup.
```

### 5.2 Why these columns

| Column | Why |
|---|---|
| `tenant_id` | Tenant isolation per spec #1 section 6. Cross-tenant cache hits would leak content even via timing. |
| `text_hash` | SHA-256 of canonicalized text. Lookup key. |
| `model` + `model_version` | Same text under a different model = different vector. Pinning version means upgrading the model invalidates the cache automatically by missing on lookup. |
| `vector(384)` | MiniLM-L6-v2 dim. A future 768-dim model writes separate rows because `(model, model_version)` differs. |
| `text_preview` + `text_length` | Debugging only — never read by production code. Helps incident response. |
| `last_hit_at` + `hit_count` | LRU eviction signal + cache effectiveness metric. |

### 5.3 RLS policies

```sql
ALTER TABLE analysis_embedding_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY analysis_embedding_cache_tenant_read ON analysis_embedding_cache
    FOR SELECT USING (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE POLICY analysis_embedding_cache_tenant_insert ON analysis_embedding_cache
    FOR INSERT WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE POLICY analysis_embedding_cache_tenant_update ON analysis_embedding_cache
    FOR UPDATE USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Platform-user impersonation (spec #1 section 7) already sets `app.tenant_id` to the impersonated tenant's id, so impersonating users see the impersonated tenant's cache. No extra policy.

The eviction job uses a service role that bypasses RLS; every eviction run is recorded in `worker_log` (spec #1 section 9) with rows-deleted and bytes-freed counters.

### 5.4 Eviction strategy

**Write path (every cache miss → insert):**
- Insert with `created_at = now()`, `hit_count = 1`.
- On unique-constraint conflict, `ON CONFLICT DO UPDATE SET last_hit_at = EXCLUDED.created_at, hit_count = analysis_embedding_cache.hit_count + 1`.

**Read path (every cache hit):**
- `UPDATE ... SET last_hit_at = now(), hit_count = hit_count + 1 WHERE id = $1`.
- Fired via `asyncio.create_task` from the embedding tool — never awaited inside the agent step's critical path.

**Eviction job (Prefect, daily 03:00 UTC):**
- Per-tenant cap: keep most recent 100,000 rows by `last_hit_at`. Delete oldest above that.
- Global cap: ≈5GB total table size. If exceeded, halve every tenant's cap until under budget.
- Writes a `worker_log` row per tenant for observability.

### 5.5 Invalidation (no manual API)

Three implicit invalidation signals:

1. **Model version bump** — change `model_version` constant; all old rows become unreachable; eviction cleans them up.
2. **Text changes** — different `text_hash`; no hit; fresh embed.
3. **Tenant deletion** — `ON DELETE CASCADE` from `tenants`.

No explicit "invalidate cache" admin endpoint in v1. Add later if a real need appears.

### 5.6 Performance budget

| Operation | Target |
|---|---|
| Cache hit lookup | < 5ms p99 (covered by `analysis_embedding_cache_uniq`) |
| Cache miss + worker round-trip | < 800ms p99 |
| Eviction job per tenant | < 30s |

Cache hit rate is exposed as a metric in spec #1 section 13's observability hooks. Below 30% is a signal that callers' inputs are too varied to cache; revisit strategy or input normalization.

---

## 6. Compute Model

### 6.1 Process roles

| Process | Loads ML model? | Imports `analysis.similarity.embedding`? |
|---|---|---|
| API (FastAPI/Uvicorn) | no | no — import-time guard raises |
| Dramatiq worker | yes (lazy on first use) | yes |
| Prefect agent / flow runner | yes (lazy on first use) | yes |
| Local API shell (`uv run uvicorn ...`) | no | no |
| Local worker shell (`uv run dramatiq ...` / `uv run prefect ...`) | yes (with `--extra ml`) | yes |

`XTRUSIO_PROCESS_ROLE` env var tags each process. **The role is set explicitly per process — there is no global default**:

- API container and local API shell: `XTRUSIO_PROCESS_ROLE=api`. Importing `analysis.similarity.embedding` raises.
- Worker container and local worker shell: `XTRUSIO_PROCESS_ROLE=worker`. Importing the embedding module is allowed.

Local dev provides two shell aliases (defined in `Makefile` / `.envrc`): `make api` and `make worker`. Each sets the env var before invoking `uv run`. Engineers run flows interactively from `make worker`; they run the FastAPI dev server from `make api`. No one process tries to be both.

### 6.2 Model loading

`SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` is loaded once per worker process via a module-level cached function. Cold start cost: ~2s. After load, embedding throughput is CPU-bound at ~80 texts/sec on a 4-core worker (no GPU required).

### 6.3 Worker-only flow steps

When a flow step needs embeddings:

- Spec #2 section 5 `Step` objects already declare `requires: frozenset[str]`. A step that calls `TextSimilarityTool` with `method="embedding"` declares `requires={"worker"}`.
- The runner schedules `requires={"worker"}` steps onto Prefect/Dramatiq worker pool exclusively, never on the in-API path.
- API-only paths that try to call the embedding tool fail fast at registration with a clear error.

### 6.4 Latency expectations

| Path | p99 budget |
|---|---|
| Cosine on already-cached vectors | < 50ms (cache lookup + numpy math) |
| Cosine, both vectors fresh, single text-pair | < 1.5s (2× cache miss + cosine) |
| Cosine, batch of 100 pairs all fresh | < 8s (batched encode) |

---

## 7. Error Handling

### 7.1 Error hierarchy (`analysis/errors.py`)

```python
class AnalysisError(Exception):
    """Base class for all analysis toolkit errors."""

class InvalidInputError(AnalysisError, ValueError):
    """Caller-side error: input failed validation beyond Pydantic checks."""

class CacheError(AnalysisError):
    """Persistent or in-memory cache failed."""

class EmbeddingUnavailableError(AnalysisError):
    """Imported in API process, or worker model load failed."""
```

Tool wrappers catch `AnalysisError` and emit a `run_event` row with `event_type="tool_error"` (spec #2 section 7), then re-raise to let the runner decide retry/skip.

Per `ENGINEERING_PRINCIPLES.md` section 5: no bare `except`, every external call has a timeout, errors live at the boundary.

### 7.2 Specific error policies

- **Aho-Corasick build failure** (e.g., empty pattern list survived validation) → `InvalidInputError`.
- **Embedding model load timeout** (>30s) → `EmbeddingUnavailableError`. Retried once by the runner; a second failure marks the run step `failed`.
- **Pgvector cache write failure** → log + return uncached result. Never fail the user-facing operation because the cache had a hiccup.
- **Valkey cache miss/error in AC automaton path** → rebuild automaton inline, no error. Cache is best-effort.

---

## 8. Testing Strategy

### 8.1 Test layout (mirrors source)

```
apps/api/tests/analysis/
├── matching/
│   ├── test_aho_corasick.py             # pure-function tests
│   ├── test_aho_corasick_perf.py        # @pytest.mark.perf
│   ├── test_fuzzy.py
│   └── test_automaton_cache.py          # uses fakeredis
├── similarity/
│   ├── test_minhash.py
│   ├── test_embedding_unit.py           # mocked encoder
│   ├── test_embedding_integration.py    # @pytest.mark.ml
│   └── test_embedding_cache.py          # Postgres testcontainer + RLS
├── stats/
│   └── test_wilson.py
├── tools/
│   ├── test_match_tool.py
│   ├── test_fuzzy_tool.py
│   ├── test_similarity_tool.py
│   └── test_stats_tool.py
└── conftest.py
```

### 8.2 Five testing rules specific to this spec

**1. Algorithm correctness uses golden fixtures.** Each algorithm has a fixture file (`tests/analysis/fixtures/...`) with known-good `(input, expected_output)` pairs. Tests assert byte-equal outputs. Drift means a deliberate fixture update — not a silent change.

**2. RLS is tested live.** Every test that touches `analysis_embedding_cache` runs against a real Postgres testcontainer with RLS enabled and `app.tenant_id` set. Required cases (per `ENGINEERING_PRINCIPLES.md` section 9):
- Tenant A cannot SELECT tenant B's cache rows
- Tenant A cannot INSERT a row with tenant B's `tenant_id` (WITH CHECK violation)
- Service-role bypass works for the eviction job
- Impersonating platform user reads the impersonated tenant's cache

**3. Embedding tests have two tiers.**
- `test_embedding_unit.py` — every local run. Mocks `SentenceTransformer.encode` to deterministic fakes. Validates: caching logic, batch ordering, `cache_hit_rate` math, error paths.
- `test_embedding_integration.py` — `@pytest.mark.ml`. Loads the real model. Asserts: vector dim is 384; semantically similar inputs (`"GPT-4 is good"` vs `"ChatGPT-4 performs well"`) produce cosine ≥ 0.6.

**4. Tool wrappers get a single wiring test each.** ~30 LoC per Tool — proves registration, `ctx` plumbing, error propagation, and `cost_meter.record_*` invocations.

**5. Performance smoke benchmarks.** `@pytest.mark.perf` tests assert:

| Algorithm | Input size | Budget |
|---|---|---|
| Aho-Corasick | 100k chars + 1k patterns | < 50ms |
| rapidfuzz | 1 query × 10k candidates | < 200ms |
| MinHash signature | 10k chars | < 30ms |
| Wilson interval | 1 call | < 1ms |
| Cache lookup | exact hit | < 5ms p99 |

Run on demand locally via `pytest -m perf`. Non-blocking; surfaces regressions early.

### 8.3 Coverage expectations

- New code coverage: ≥ 90% (above the project default of 80% — pure library code with simpler branching).
- 100% on `stats/wilson.py` and `similarity/minhash.py` — pure math, no excuse.

### 8.4 Local verification commands

```bash
# Fast lane (default)
uv run pytest tests/analysis -m "not ml and not perf"

# ML lane (requires extra)
uv sync --extra ml
XTRUSIO_PROCESS_ROLE=worker uv run pytest tests/analysis -m "ml"

# Perf check
uv run pytest tests/analysis -m "perf"

# Static guard against ML import leak into API code
! grep -rE "^(from sentence_transformers|import sentence_transformers)" \
    apps/api/src/xtrusio_api/ \
    --include="*.py" \
  | grep -v "src/xtrusio_api/analysis/similarity/embedding.py"
```

The static grep guard is a belt-and-suspenders backup to the runtime import-time check from section 3.3.

### 8.5 What's explicitly NOT tested in this spec

- End-to-end agent flow tests that exercise tools — owned by spec #2's flow tests.
- Cross-tenant fuzz testing of RLS — owned by the spec #1 project-wide RLS test suite.
- Load-testing the embedding cache at scale — deferred to ops readiness.

---

## 9. Local Development & Tooling

### 9.1 Tooling in scope (local only)

Per project policy, **no CI/CD setup is included in this spec**. Everything below runs on the engineer's machine.

| Tool | Purpose | Invocation |
|---|---|---|
| `ruff check` | Lint analysis source | `uv run ruff check apps/api/src/xtrusio_api/analysis/` |
| `ruff format` | Format | `uv run ruff format apps/api/src/xtrusio_api/analysis/` |
| `mypy --strict` | Type check | `uv run mypy apps/api/src/xtrusio_api/analysis/` |
| `pytest` | Tests | see section 8.4 |
| Postgres testcontainer | RLS tests against real Postgres + pgvector | auto-spawned by `conftest.py` |
| `fakeredis` | Valkey mock for `automaton_cache` tests | imported in test fixtures |

All of the above must pass locally before any change to the analysis toolkit lands.

### 9.2 Migrations

A single Alembic migration creates `analysis_embedding_cache`, its indexes, and RLS policies:

```
apps/api/migrations/versions/2026_05_NN_add_analysis_embedding_cache.py
```

Migration includes a working `downgrade()` per `ENGINEERING_PRINCIPLES.md` section 5. Run locally:

```bash
uv run alembic upgrade head
uv run alembic downgrade -1   # verify reversibility
uv run alembic upgrade head
```

### 9.3 CI/CD — explicitly deferred

Per project policy ("CI/CD only after local runs cleanly"), the following are **not** part of v1:

- GitHub Actions workflow lanes (`analysis-unit`, `analysis-ml`).
- Coverage gates enforced in CI.
- Static-analysis gate for the ML-import grep guard.
- Nightly perf-benchmark scheduling.

When the platform reaches the readiness bar, a follow-up spec covers all of the above. Until then, the local commands in section 8.4 are the contract.

---

## 10. Open Questions

1. **Embedding model upgrade path.** When MiniLM-L6-v2 becomes obsolete or a domain-specific model performs noticeably better, the migration plan is "bump `model_version`, let cache repopulate, accept temporary cost spike." Is that acceptable, or should we provision a parallel-fill background job? Defer until first model swap.

2. **Cosine over numpy vs torch.** Pure-Python cosine on 384-dim vectors via numpy is ~10µs. If batches scale into the thousands, switch to torch. v1 sticks with numpy; revisit if perf benchmarks regress.

3. **Pattern catalog feature.** Out of scope for v1, but the API surface of Aho-Corasick tools is designed so a future catalog (per-tenant pattern sets) plugs in by replacing the `patterns: list[str]` argument with a `pattern_set_id` resolver. Spec lands separately when product needs it.

---

## 11. Success Criteria

The toolkit is considered "v1 done" when:

1. All six algorithms expose pure-function APIs and Tool wrappers with the signatures from section 3 and section 4.
2. `pytest tests/analysis -m "not ml and not perf"` passes locally with ≥ 90% coverage.
3. `XTRUSIO_PROCESS_ROLE=worker pytest tests/analysis -m "ml"` passes locally on a worker shell.
4. RLS tests demonstrate cross-tenant isolation on `analysis_embedding_cache`.
5. Importing `xtrusio_api.analysis.similarity.embedding` in an API process raises with a clear message.
6. The `analysis_embedding_cache` migration applies and reverses cleanly via Alembic.
7. At least one consumer flow (`company_research_run` from spec #2) calls at least one analysis tool end-to-end.

---

## 12. Cross-References

- `docs/superpowers/specs/2026-05-07-multi-tenant-foundation-design.md` — tenancy, RLS, identity, observability, audit logs.
- `docs/superpowers/specs/2026-05-07-prompt-orchestration-design.md` — `Tool` protocol, `ToolContext`, `Step`, `Runner`, `cost_meter`, `run_event`.
- `docs/superpowers/ENGINEERING_PRINCIPLES.md` — file size, typing, robustness, scalability, testing rules cited throughout.
- `Algo.md` — algorithm reference and selection rationale (the toolkit is a subset of the 10 listed there).
