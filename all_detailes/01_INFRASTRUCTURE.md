# 01 - INFRASTRUCTURE

This document covers the foundational infrastructure of the Xtrusio Growth Engine
(folder `sirion-perception-shift`). It describes the global state container, the
persistence engine, the Firestore wrapper, the AI proxy client, the application
shell + routing, theming, authentication, the IndexedDB knowledge base, and a
small specialized scan loader.

---

## 1. Architecture Overview

```
+-----------------------------------------------------------------------+
|                         BROWSER (React SPA)                           |
|                                                                       |
|   +------------------+      +------------------+                      |
|   |  LoginScreen     | ---> |   AuthContext    |                      |
|   +------------------+      +------------------+                      |
|                                      |                                 |
|                                      v                                 |
|   +------------------+      +------------------+    +-------------+   |
|   |  ThemeContext    | ---> |    AppShell      | -> |  Sidebar    |   |
|   +------------------+      |  (hash router)   |    +-------------+   |
|                              +------------------+                      |
|                                      |                                 |
|                                      v                                 |
|              +-----------------------------------------+               |
|              |             PipelineProvider            |               |
|              |   (single source of truth, useReducer)  |               |
|              +-----------------------------------------+               |
|                  |                |                |                   |
|                  v                v                v                   |
|         +----------------+  +-----------+  +----------------+          |
|         | Module Screens |  | persistMgr|  | claudeApi      |          |
|         | (M1..M7, Intel)|  | (batch    |  | (proxy client) |          |
|         +----------------+  | 1.5s)     |  +----------------+          |
|                  |          +-----------+          |                   |
|                  |              |                  |                   |
|                  v              v                  v                   |
|        +-------------+   +-------------+   +-----------------------+   |
|        | IndexedDB   |   | localStorage|   | Cloudflare Worker     |   |
|        | (xtrusio-m1)|   | (snapshot)  |   | xtrusio-ai...workers  |   |
|        | questions,  |   |             |   | (holds provider keys) |   |
|        | personas... |   |             |   +-----------+-----------+   |
|        +-------------+   +-----+-------+               |               |
|                                |                       v               |
|                                v               +---------------+       |
|                          +-----------+         | Anthropic /   |       |
|                          | Firestore |         | OpenAI / Grok |       |
|                          | REST API  |         | Gemini / Pplx |       |
|                          +-----------+         +---------------+       |
+-----------------------------------------------------------------------+
```

### Write Path

`module updates state` -> `updateModule("mX", data)` -> `dispatch UPDATE_MODULE` ->
`queueMicrotask` -> `pmRef.current.enqueueSave()` -> writes localStorage immediately,
debounces 1.5s -> writes Firebase via read-merge-write reconciliation.

### Read Path

`PipelineProvider mounts` -> `db.getAll("pipelines")` (Firebase primary) ->
falls back to `localStorage["xt_pipeline_snapshot"]` -> falls back to
`INITIAL_STATE`.

### Cross-tab Sync

`focus event` on the window -> pull `pipelines` again -> `MERGE_REMOTE` action
that uses per-item Last-Write-Wins helpers in `pipelineMergeHelpers.js`.

---

## 2. PipelineContext (`src/PipelineContext.jsx`)

This is the single React Context that owns the entire application's persistent
state. It uses `useReducer` for predictable mutation, a `stateRef` for
synchronous reads inside callbacks, and a `pmRef` that holds the
PersistenceManager instance.

### 2.1 Constants

| Constant       | Value             | Purpose                                                                                                                                                                 |
| -------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `COLLECTION`   | `"pipelines"`     | Firestore collection that stores the consolidated pipeline document(s).                                                                                                 |
| `DATA_VERSION` | `"2026-04-16-v6"` | Schema version. Bumping this clears `xt_pipeline_snapshot`, `m2_scanHistory`, and the `xtrusio-m1` IndexedDB on next load. Set under `localStorage["xt_data_version"]`. |

A self-executing IIFE at module load reads `xt_data_version`; if it doesn't
match `DATA_VERSION`, all stale caches are wiped and the new version is written.

### 2.2 INITIAL_STATE Shape

The reducer's initial state has the following top-level keys. Anything not
listed here is silently dropped during Firebase hydration (this is a real
historical bug source - missing keys = lost data).

| Key       | Description                                                                                        |
| --------- | -------------------------------------------------------------------------------------------------- |
| `_docId`  | Firestore document ID for this user's pipeline. Null until first save.                             |
| `_loaded` | False until initial Firebase/localStorage load completes.                                          |
| `_saving` | True while a Firebase save is in flight.                                                           |
| `meta`    | `{ company, url, industry }` - always overwritten to "Sirion" / "https://sirion.ai" on every load. |
| `m1`      | Question Generator slice (see below).                                                              |
| `m2`      | Perception Monitor slice (see below).                                                              |
| `m3`      | Authority Ring slice.                                                                              |
| `m4`      | Buying Stage Guide slice.                                                                          |
| `m5`      | CLM Advisor slice.                                                                                 |
| `m6`      | Original Content Strategy slice.                                                                   |
| `m6v2`    | Content Strategy V2 (campaign + tracks + AI revisions + style rules).                              |
| `m7v2`    | Link Strategy V2 (assignments + monthPlans + catalog overrides).                                   |
| `intel`   | Company Intelligence slice.                                                                        |

#### m1 fields

`questions`, `personas`, `clusters`, `generatedAt`, `personaProfiles`,
`decisionScores`, `yinMatrix`, `generationId`, `scanBatch`, `pendingSegment`,
`segments`, `clusterCalibration`.

#### m2 fields

`scanResults`, `scores`, `contentGaps`, `personaBreakdown`, `stageBreakdown`,
`recommendations`, `scannedAt`, `scanProgress`, `generationId`,
`m1GenerationId`, `calibration`, `contentPipeline`.

#### m3 fields

`prioritizedDomains`, `gapMatrix`, `outreachPlan`, `personaDomainMap`,
`gapCount`, `strongCount`, `analyzedAt`, `generationId`, `m2GenerationId`.

#### m4 fields

`analyses`, `latestStage`, `latestReadiness`, `companyBuckets`, `analyzedAt`,
`generationId`.

#### m5 fields

`recommendations`, `leadData`, `generatedAt`, `generationId`.

#### m6 fields

`topics`, `journalistPacks`, `articles`, `transfers`, `tags`, `articleBriefs`,
`generatedAt`, `generationId`.

#### m6v2 fields

- `articles` - keyed by article id, each carries its own `updatedAt` for LWW.
- `styleRules` - global writing rules (per campaign).
- `dismissedGapIds` - per-campaign list of gap IDs the user snoozed.
- `gapMarketDemand` - cached `{ searchVolumeMonthly, lastEstimatedAt, source }` per gapId.
- `gapDescriptions` - AI-generated rich context per gap, with placement hint and manual override.
- `topics` - keyed by topicId, each storing `{ title, addressesGapIds, persona, lifecycle, angleHook, ... }`.
- `lastGapRefresh` - per-campaign ISO timestamp of last M2 gap pull.
- `generationId` - rev marker.

#### m7v2 fields

- `assignments` - `{ [articleId]: AssignmentRecord }` - LWW by `lastTouchAt`, tie-break to non-empty candidates.
- `monthPlans` - `{ [yearMonth]: MonthPlan }`.
- `samples` - pre-seeded sample articles.
- `samplesSeeded` - boolean flag, OR-merged across sessions so once set it stays set.
- `catalogEnrichment` - `{ [domain]: EnrichmentRecord }` - LWW by `enrichedAt`.
- `catalogOverrides` - `{ addedBlogs, notes, tags, removedDomains }` - additive merging, set-union for added/removed, local-wins-then-remote for notes/tags.

#### intel fields

`companyName`, `companyUrl`, `industry`, `overview`, `productsServices`,
`targetMarket`, `competitors`, `decisionMakers`, `buyerPersonas`, `recentNews`,
`marketPosition`, `keyFindings`, `demandMap`, `questions`, `researchedAt`,
`generationId`, `researchPhase`, `error`, `scanResults`, `scanScores`,
`narrativeBreakdown`, `scannedAt`, `marketPulse`, `marketPulseAt`, `marketData`,
`marketDataAt`.

### 2.3 Reducer Actions

| Action type     | Effect                                                                                                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `LOAD`          | Merges payload into state, sets `_loaded = true`, force-overwrites meta to Sirion.                                                                      |
| `MERGE_REMOTE`  | Used by focus-refresh. Reconciles fresh Firestore payload via `mergePipelineSlices` from `pipelineMergeHelpers.js`. Preserves `_docId` and pinned meta. |
| `UPDATE_MODULE` | Shallow-merges `data` into `state[moduleId]`.                                                                                                           |
| `UPDATE_META`   | Shallow-merges `data` into `state.meta`.                                                                                                                |
| `SET_DOC_ID`    | Stores the Firestore docId returned after first save.                                                                                                   |
| `SET_SAVING`    | Toggles the saving indicator.                                                                                                                           |
| `SET_LOADED`    | Marks the pipeline as loaded (used when both Firebase and localStorage are empty).                                                                      |

### 2.4 Hydration Order

On first mount the provider runs an async loader effect:

1. Calls `loadApiKeys()` (no-op shim that scrubs legacy localStorage entries).
2. `db.getAll("pipelines")` - read all pipeline documents from Firestore.
3. If at least one doc exists, take the latest, peel out `_id`, then for every
   key in `INITIAL_STATE` copy the field over (preserving defaults for nested
   objects).
4. Compare the localStorage snapshot's `updated_at` against Firebase's. If
   localStorage is newer, merge for `m1, m2, m3, m4, m5, m6, m6v2, m7v2,
intel, meta`. The `m6v2` / `m7v2` slices use the dedicated `mergeM6V2` /
   `mergeM7V2` helpers; everything else uses INITIAL_STATE -> local -> remote
   layered shallow merge.
5. Dispatch `LOAD`.
6. If Firebase returned zero docs, fall back to `localStorage["xt_pipeline_snapshot"]`.
7. If both fail, fall back to defaults via `SET_LOADED`.

### 2.5 Focus-Refresh Behavior

A second effect attaches a `focus` listener to the window. When the tab gains
focus and `_loaded` is true, it pulls `db.getAll("pipelines")` again and
dispatches `MERGE_REMOTE`. An `inFlight` boolean prevents overlapping
refreshes. This avoids running a real-time Firestore listener (cost) while
still letting two browser tabs (admin + client portal) converge within a
second of switching.

### 2.6 PersistenceManager Lifecycle

`pmRef.current` is created lazily on first render. The cleanup effect runs
`destroy()` on unmount and nulls out `pmRef.current` so React StrictMode's
intentional mount-unmount-mount cycle creates a fresh PM instance the second
time. Forgetting to null this ref previously broke persistence under
StrictMode (Known Pitfall #8 in CLAUDE.md).

### 2.7 Public API

The provider exposes via `usePipeline()`:

- `pipeline` - the full state object.
- `updateModule(moduleId, data)` - dispatch `UPDATE_MODULE`, also patch
  `stateRef.current` synchronously, then enqueue a save in a microtask.
- `updateMeta(data)` - same shape for `meta`.
- `getStatus()` - returns `{ m1, m2, m3, m4, m5, intel }` each with
  `{ hasData, count, at }`. Used by the Dashboard.
- `getStaleness()` - returns `{ m2, m3 }` booleans indicating whether each
  module's stored `mXGenerationId` lags the upstream `generationId`.
- `getSaveStatus()` - proxies `pmRef.current.getStatus()`.
- `getDiagnostics()` - returns boot-time diagnostics + current docId,
  question count, AI access flags. Logged to console at boot.
- `persistApiKeys()` - no-op shim returning `false`. Provider keys live on
  the Worker.

---

## 3. PersistenceManager (`src/persistenceManager.js`)

A factory function `createPersistenceManager(getState, getDocId, setDocId)`
returns `{ enqueueSave, flush, getStatus, destroy }`.

### 3.1 Constants

| Constant       | Value                  | Meaning                                            |
| -------------- | ---------------------- | -------------------------------------------------- |
| `COLLECTION`   | `"pipelines"`          | Same Firestore collection.                         |
| `BATCH_DELAY`  | `1500`                 | Milliseconds of quiet before flushing to Firebase. |
| `RETRY_DELAYS` | `[5000, 15000, 30000]` | Backoff schedule for failed Firebase saves.        |

### 3.2 Snapshot Builder

`_buildSnapshot(state)` copies all non-underscore keys, then strips heavy
data that lives in dedicated collections so the pipeline document stays
small:

- `m1.questions` removed (lives in `m1_questions_v2`).
- `m1.personaProfiles` removed (lives in `m1_personas`).
- `intel.scanResults.results` removed (kept metadata only).
- `m2.scanResults.results` removed (kept metadata only).

Stamps `updated_at = new Date().toISOString()`.

### 3.3 Save Pipeline

`enqueueSave()` does:

1. Synchronous `_writeLocalStorage()` for crash safety.
2. Clears any pending timer, then schedules `flush()` after `BATCH_DELAY`.

`flush()` does:

1. Skip if `_destroyed` or `_saving`. Skip if state not loaded.
2. Build snapshot, write to localStorage.
3. Compute a quick string hash. If unchanged from `_lastHash`, skip Firebase
   altogether (write amplification reduction).
4. Try `_writeFirebase(snap)`. On success, set `_lastSavedAt` and clear the
   retry counter. On failure, schedule the next retry per `RETRY_DELAYS`. If
   all 3 retries are exhausted, log "Data is in localStorage only" and stop.

### 3.4 Per-item LWW Merge (read-merge-write)

`_writeFirebase` does NOT just PATCH. Before writing, it reads the current
Firebase doc via `db.getById` and merges these slices per-item:

#### m6v2

- `articles`: `mergeByIdLwW(local, remote)` - newer `updatedAt` wins.
- `topics`: same `mergeByIdLwW`.

#### m7v2

- `assignments`: `mergeAssignmentsByLastTouch` - newer `lastTouchAt` wins, tie-break to whichever side has non-empty `candidates` (prevents stale empty admin RAM from erasing client's matched state).
- `catalogEnrichment`: `mergeEnrichmentByEnrichedAt` - per-domain LWW.
- `catalogOverrides.addedBlogs`: union by lowercase domain, later `addedAt` wins.
- `catalogOverrides.removedDomains`: case-insensitive set union.
- `catalogOverrides.notes` / `tags`: local wins, remote fills gaps.
- `samplesSeeded`: OR semantics (sticky once set).

The merged result is then written back to localStorage too so the next
reload sees the same merged truth that Firebase received.

### 3.5 Degraded Mode

If the pre-write read fails (network, rate limit), the manager falls through
to a plain `db.saveWithId` without merging. Persistence still works locally
even if Firebase is unreachable; the warning is logged but the user can
continue working.

### 3.6 Lifecycle Hooks

- `beforeunload` - synchronous localStorage write only (`fetch` may not
  complete during unload).
- `visibilitychange` (hidden) - localStorage write + best-effort
  `db.saveWithId(...)` (may not finish).
- `destroy()` - sets `_destroyed = true`, clears the pending timer, removes
  both event listeners.

### 3.7 Status

`getStatus()` returns `{ saving, lastSavedAt, error }` for UI indicators.

### 3.8 Limitation: Deletes

There is no tombstone mechanism. An item present in the remote doc but
absent from the local snapshot is preserved by the merge. In practice the
session that did the delete re-saves shortly after - its RAM also doesn't
have the item, so future merges drop it - but cross-session deletes can
linger.

---

## 4. firebase.js (`src/firebase.js`)

### 4.1 Configuration

`FIREBASE_CONFIG = { apiKey: VITE_FIREBASE_API_KEY, projectId: VITE_FIREBASE_PROJECT_ID }`.

`FS_BASE` is the REST URL `https://firestore.googleapis.com/v1/projects/<projectId>/databases/(default)/documents`,
or empty string if `projectId` is missing.

`FIREBASE_ENABLED = !!FS_BASE`. If false, the app warns in the console and
all Firebase calls fail through to localStorage-only operation.

### 4.2 Value Conversion Helpers

- `toFsVal(val, depth=0)` - converts a JS value to a Firestore value.
  - null/undefined -> `nullValue`.
  - boolean -> `booleanValue`.
  - integer / float -> `integerValue` / `doubleValue`.
  - string - capped at 200,000 characters (~35K-word article body).
  - At depth >= 3, objects/arrays are serialized to JSON strings (avoids
    Firestore's 20-level depth limit).
  - Arrays larger than 500 elements are serialized to a JSON string instead
    of `arrayValue`.
- `fromFsVal(val)` - inverse. Tries `JSON.parse` on strings that look like
  objects/arrays, falling back to the raw string.
- `fromFsDoc(doc)` - converts a Firestore document into a plain object,
  attaches `_id` from the document name path.

### 4.3 Local Cache Layer

A localStorage cache keyed by `xt_<collection>_<docId>` mirrors writes for
fallback. The cache:

- Skips storing data for collections in `LARGE_COLLECTIONS` (`m2_scan_results`,
  `m2_scans`) when serialized size > 500KB.
- On `QuotaExceededError`, evicts the oldest 25% of entries (keyed by
  `_cachedAt`), but never evicts `xt_pipeline_snapshot` or `xt_data_version`.

### 4.4 Circuit Breaker

A single 429 from Firebase trips a 5-minute circuit (`CIRCUIT_COOLDOWN_MS`).
While open, all Firebase calls return the cached value (or null) immediately
without hitting the network.

### 4.5 The `db` Object

| Function                                      | Purpose                                                                                                        |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `db.getLastError()`                           | Returns the last error string for diagnostics UI.                                                              |
| `db.save(collection, data)`                   | POST a new document. Returns the new docId, or null on failure (and writes a `local_<timestamp>` cache entry). |
| `db.update(collection, docId, data)`          | PATCH with `updateMask` field paths. Always writes to local cache first.                                       |
| `db.getAll(collection)`                       | GET with `pageSize=50`. Sorted by `updated_at` desc. Falls back to local cache.                                |
| `db.getById(collection, docId)`               | GET single doc by ID. Returns null on 404, falls back to cache on other errors.                                |
| `db.delete(collection, docId)`                | DELETE + local cache eviction.                                                                                 |
| `db.saveWithId(collection, docId, data)`      | PATCH at known ID (creates if missing). Always writes to local cache first.                                    |
| `db.getAllPaginated(collection, maxPages=20)` | GET with `pageSize=100`, follows `nextPageToken` up to `maxPages` (default 20 = 2,000 docs).                   |
| `db.test()`                                   | Pings the `analyses` collection with `pageSize=1`. Returns `{ ok, error? }`.                                   |

### 4.6 Firestore Collections Used

| Collection            | Purpose / docId convention                                                           |
| --------------------- | ------------------------------------------------------------------------------------ |
| `pipelines`           | The merged pipeline document. One per user, autogen ID.                              |
| `m1_questions_v2`     | All M1 questions. docId = `questionHash(query)` (dedupHash).                         |
| `m1_personas`         | Persona profiles. docId = persona.id.                                                |
| `m1_macros`           | Industry-wide macro questions. docId = dedupHash.                                    |
| `m1_company_intel`    | AI-researched company intel snapshots. docId = `companyKey` (lowercased dashed).     |
| `m2_scan_meta`        | One doc per M2 scan run.                                                             |
| `m2_scans`            | Raw paste scans.                                                                     |
| `m2_scan_results`     | Per-question scan analyses. Filtered by `scanId`.                                    |
| `m2_scanHistory`      | Legacy localStorage-only fallback.                                                   |
| `user_segments`       | User-defined question segments. docId = `<creator>_<name>_<ts>`.                     |
| `app_config_accounts` | User accounts (admin-managed). docId = email with non-alphanumerics replaced by `_`. |
| `analyses`            | Generic analysis store (used by `db.test()`).                                        |

### 4.7 API Key Shims

`loadApiKeys()` and `saveApiKeys()` are kept for back-compat; both run
`scrubLegacyKeys()` which removes the legacy entries
`xt_anthropic_key, xt_gemini_key, xt_openai_key, xt_perplexity_key,
xt_grok_key`. Provider keys now live on the Cloudflare Worker.

---

## 5. claudeApi.js - AI Proxy Client (`src/claudeApi.js`)

All provider calls route through a Cloudflare Worker at
`https://xtrusio-ai.thedevimapro.workers.dev` (overridable with
`VITE_AI_PROXY_URL` env var). The browser holds only a per-client signed
bearer token in `sessionStorage["xt_token"]`, set by the bootstrap in
`main.jsx` from URL hash params (`?c=<clientId>&t=<token>`).

### 5.1 Wire Format

Single endpoint: `POST /api/ai/chat`. Request body:

```
{ provider: "anthropic"|"openai"|"grok"|"gemini"|"perplexity",
  body:    <exact upstream body>,
  model?:  <gemini model name (used in URL)> }
```

Response: `{ provider, model, content, raw }` where `raw` is the verbatim
upstream JSON. Callers receive `raw` from `proxyChat`.

### 5.2 Token Helpers

- `getProxyToken()` - reads `xt_token` from sessionStorage.
- `ensureToken()` - throws "Access link required..." if absent.
- `getAnthropicKey()` - returns `"(proxy)"` when token present, `""` otherwise (back-compat truthy gate).
- `getGrokKey()` - returns the token directly.
- `getAnthropicHeaders()` - returns `{ "Content-Type": ..., Authorization: "Bearer ..." }` for legacy fetch sites.
- `hasAccessToken()`, `getAccessClient()`, `clearAccessToken()` - diagnostics helpers.

### 5.3 proxyChat(provider, body, opts)

Generic dispatcher. For Gemini, callers pass `{ model, payload }` and the
function rewraps it as `{ provider: "gemini", model, body: payload }`. For
all other providers it sends `{ provider, body }`.

Behaviour:

- AbortController with `opts.timeoutMs` (default 120,000ms).
- Forwards `opts.signal` for external cancellation.
- 401: clears `xt_token` + `xt_client`, throws "expired" error.
- 403: throws "Access revoked".
- 429: throws "Rate limit hit - wait a moment and try again".
- 504: "Upstream timed out".
- 502: "AI provider failed".
- Any other non-OK: "AI request failed".
- Returns `wrappedRes.raw || wrappedRes` so callers see verbatim provider JSON.

### 5.4 Public Functions

| Function                                                     | Provider / Model                       | Default Timeout | Default Tokens | Web Search?                    | JSON Parse?   |
| ------------------------------------------------------------ | -------------------------------------- | --------------- | -------------- | ------------------------------ | ------------- |
| `callClaudeFast(system, user, maxTokens=1500)`               | Anthropic / `claude-sonnet-4-20250514` | 60,000          | 1500           | No                             | Yes           |
| `callClaude(system, user, timeoutMs=120000, maxTokens=4096)` | Anthropic / `claude-sonnet-4-20250514` | 120,000         | 4096           | Yes (`web_search_20250305`)    | Yes           |
| `callClaudeChat(system, messages, maxTokens=2048)`           | Anthropic / `claude-sonnet-4-20250514` | 60,000          | 2048           | No                             | No (raw text) |
| `callGrok(system, user, opts)`                               | xAI / `grok-4-latest`                  | 120,000         | 4096           | Yes (`max_search_results: 10`) | Yes (or raw)  |
| `callOpenAI(system, user, opts)`                             | OpenAI / `gpt-4o`                      | 120,000         | 4096           | No                             | Yes (or raw)  |
| `callGemini(system, user, opts)`                             | Google / `gemini-2.5-flash`            | 120,000         | 4096           | Tools opt-in                   | Yes (or raw)  |
| `callPerplexity(system, user, opts)`                         | Perplexity / `sonar`                   | 120,000         | 4096           | Built-in                       | Yes (or raw)  |

`opts` for the chat-completions-shaped providers (Grok, OpenAI, Gemini,
Perplexity): `{ model, maxTokens, temperature, timeoutMs, raw, ... }`. Grok
also accepts `maxSearchResults`. Gemini accepts `tools` and `forceJson`.

### 5.5 Anthropic JSON Parsing

`parseClaudeJson(data, label)`:

1. Concatenate all `text`-typed content blocks.
2. Strip ` ```json ` and ` ``` ` fences.
3. `JSON.parse(cleaned)`.
4. On failure, regex out the first `{...}` span and try again.
5. On second failure, throw "<label> returned a malformed response".

### 5.6 Gemini JSON Parsing - parseGeminiJson()

Highly defensive, runs four strategies in sequence:

1. Strip markdown fences and `JSON.parse` the whole thing.
2. Slice between the first `{` and the last `}`, retry.
3. Walk all balanced `{...}` blocks, sort largest first, try each.
4. Aggressive truncation repair: walk back through trailing characters trimming to each comma / `}` / `]`, count unmatched quotes/braces/brackets, append closers as needed, retry up to 12 times.

If everything fails, throws an error containing the first 280 chars of the
response so the UI can show context. The original raw text is attached as
`err.rawText`.

For Gemini specifically:

- When `forceJson` is true and `raw` is false and no Google search grounding
  tool is present, sets `responseMimeType: "application/json"`.
- Grounding tools (`google_search`, `google_search_retrieval`) disable JSON
  mode (Gemini doesn't support both at once).

### 5.7 callFirecrawl(targetUrl, opts)

Routes through `POST /api/scrape` on the same Worker. Body:

```
{ url, formats: ["markdown"], onlyMainContent: true, timeout: 30000, waitFor: 0 }
```

Returns `{ markdown, html, metadata, sourceUrl }`. Raises the usual 401/404/429/timeout errors.

### 5.8 proxyFetch (Back-Compat Shim)

Old call sites used path-style providers like `anthropic-search` or
`anthropic-chat`. `proxyFetch(legacyPath, body, opts)` rewrites the path to
the canonical provider name and wraps the result in a `Response` so old
code expecting `.json()` still works.

---

## 6. App.jsx - Application Shell (`src/App.jsx`)

### 6.1 Route Table (MODULES)

The `MODULES` constant holds 13 entries; each is the source of truth for
sidebar entry, route hash, allowed roles, and module rendering.

| id            | Sidebar # | Label                  | Hash path       | Component                                               | Notes                                                      |
| ------------- | --------- | ---------------------- | --------------- | ------------------------------------------------------- | ---------------------------------------------------------- |
| `home`        | 0         | Dashboard              | `/`             | `Dashboard` (defined in App.jsx)                        | Sirion overview tiles.                                     |
| `intel`       | R         | Company Intel          | `/intel`        | `CompanyIntelligence`                                   | Tree-shaken in portal builds.                              |
| `intel2`      | R2        | Company Intel V2       | `/intel-v2`     | `CompanyIntelligenceV2`                                 | Tree-shaken in portal builds.                              |
| `m1`          | 1         | Question Generator     | `/questions`    | `QuestionGenerator`                                     | Tree-shaken in portal.                                     |
| `m2`          | 2         | Perception Monitor     | `/perception`   | `PerceptionMonitor`                                     | Always loaded; portal sees only Report V6 + Trajectory V2. |
| `m3`          | 3         | Authority Ring         | `/authority`    | `AuthorityRing`                                         | Tree-shaken in portal.                                     |
| `m4`          | 4         | Buying Stage Guide     | `/buying-stage` | `BuyingStageGuide`                                      | Tree-shaken in portal.                                     |
| `m5`          | 5         | CLM Advisor            | `/advisor`      | `CLMAdvisor`                                            | Tree-shaken in portal.                                     |
| `m6`          | 6         | Content Strategy       | `/content`      | `ContentStrategy`                                       | Tree-shaken in portal.                                     |
| `m6v2`        | 6+        | Content Strategy v2    | `/content-v2`   | `ContentStrategyV2`                                     | Loaded in BOTH builds; portal uses for client review.      |
| `links`       | L         | Link Strategy          | `/links`        | `LinkStrategyV2` (`./modules/linkStrategyV2/index.jsx`) | New version.                                               |
| `linksLegacy` | L-        | Link Strategy (legacy) | `/links-legacy` | `LinkStrategy`                                          | Legacy.                                                    |
| `settings`    | S         | Settings               | `/settings`     | `SettingsPage`                                          | section: "system" - separator before this entry.           |

### 6.2 Build-Flag Tree-Shaking

`__PORTAL = import.meta.env.VITE_PORTAL_MODE === "client"`. When true, every
internal module is replaced with `null` at build time so Rollup tree-shakes
the chunks out of the client-portal bundle entirely.

### 6.3 Hash Routing

- `pathToId` / `idToPath` are `Object.fromEntries(MODULES.map(...))`.
- `getModuleFromHash()` parses `window.location.hash`, looks up the path,
  supports sub-routes (e.g. `#/perception/scan` -> `m2`).
- `getSubTabFromHash()` returns the second path segment as the active tab
  inside a module.
- `useHashRouter()` returns `[active, setActive(id, sub), subTab]`. Listens
  for `hashchange` and updates state accordingly.
- `setActive(id, sub)` writes `window.location.hash = path[+ "/" + sub]`.

### 6.4 AppShell Behavior

- Reads `useAuth()`. If not logged in, renders `<LoginScreen onLogin=auth.login />`.
- If the active module is forbidden for the role, falls back to the role's
  `defaultModuleFor()` (Dashboard for admin/client, `m2` for client_portal).
- `client_portal` users see ONLY their permitted modules in the sidebar
  (filter: `auth.role === "client_portal" ? auth.canModule(mod.id) : true`).
  Other roles see everything with a lock icon on forbidden entries.
- Sidebar collapses on mobile (`window.innerWidth < 900`).
- Top bar shows the active module label, theme toggle (sun/moon), and a
  pulsing green dot labelled "LIVE".
- Renders the active module via the `renderContent()` switch statement.

### 6.5 Dashboard (defined inline in App.jsx)

The Dashboard reads the entire pipeline via `usePipeline()` and renders:

- **Intel banner** (clickable) - shows when `intel.researchPhase === "complete"`,
  displays company name, competitors / personas / queries counts, demand map
  dimensions, and last researched timestamp.
- **Row 1 - Score gauges** (4 cards, GaugeArc component):
  - AI Visibility (overall score, M2).
  - Mention Rate (% of LLMs that mention Sirion, M2).
  - Authority Gaps (zero-presence count, M3).
  - Share of Voice (% vs competitors, M2).
- **Row 2 - Strategic Focus** (3 cards): TOP OPPORTUNITY, BIGGEST RISK,
  QUICK WIN derived from current scores.
- **Scan progress + staleness banners** when M2/M3 are stale or a scan is running.
- **This Week's Priorities** (top 3 ranked actions).
- **Row 3** - LLM radial bar chart (Claude / Gemini / ChatGPT / Grok / Perplexity)
  - competitor leaderboard bar chart.
- **Row 4** - CLM Lifecycle donut (pre / post / full-stack) + Authority Ring
  horizontal bar chart with top-3 priority gaps.
- **Row 4.5 - Narrative Classification** donut (when present) showing
  post-sig %, full-stack %, pre-sig % with a single-sentence insight.
- **Row 5 - Persona Coverage rings** (PersonaRing component) - first 6
  persona profiles, green ring = researched, amber dashed = not.

`scoreColor(val, low, mid)` colours by threshold (green / amber / red).
`emptyState(msg, mod, color)` shows a "Go to MOD" CTA when there's no data yet.

### 6.6 ErrorBoundary + ModuleArea + Suspense

`ModuleArea` wraps the rendered module in an `ErrorBoundary` (top-level
class component, defined in App.jsx) and a `Suspense` fallback for the
`React.lazy` chunks.

---

## 7. ThemeContext (`src/ThemeContext.jsx`)

Exports `themes = { dark, light }` and a `ThemeContext` (default `themes.light`),
plus the `useTheme()` hook.

### Common Keys (both themes)

`mode`, `bg`, `bgAlt`, `bgCard`, `sidebar`, `sidebarBorder`, `border`,
`borderMid`, `text`, `textSec`, `textDim`, `textGhost`, `brand`, `brandDim`,
`client`, `green`, `red`, `yellow`, `orange`, `heatGreen`, `heatYellow`,
`heatRed`, `heatZero`, `tooltipBg`, `inputBg`, `inputBorder`, `btnBg`,
`btnText`, `barBg`, `sectionNum`, `scrollThumb`, `badgeTxt`.

Both themes have the same key set - this is enforced by convention
(violations cause invisible text in the other mode; documented as a
recurring gotcha for M2 / M3).

### Mode Toggle

Toggled in `AppShell` via `setIsDark(!isDark)`. The selected theme object is
passed down through `ThemeContext.Provider`.

---

## 8. AuthContext (`src/AuthContext.jsx`) and `auth.js`

### 8.1 AuthContext

`AuthProvider` initializes session from `localStorage["xt_auth_session"]`
via `getSession()` (in `auth.js`). Exposes:

- `session`, `user` (alias), `role`, `isLoggedIn`.
- `login(email, password)` - calls `loginUser`, sets session on success.
- `logout()` - calls `logoutUser`, clears session.
- `canModule(moduleId)` - delegates to `canAccessModule(role, moduleId)`.
- `canTab(moduleId, tabId)` - delegates to `canAccessTab(role, moduleId, tabId)`.

### 8.2 Roles (ROLE_PERMISSIONS)

| Role            | Modules allowed                                                                 | Tab restrictions                                                                                                                                                       |
| --------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `admin`         | home, intel, intel2, m1, m2, m3, m4, m5, m6, m6v2, links, linksLegacy, settings | m1: questions/matrix/research; m2: scan/summary/report/reportv2..v6/trajectoryv2/trajectory/settings; intel: position/pulse/alerts/reference; m6: topics/pack/articles |
| `client`        | intel, m1, m2                                                                   | m1: questions only (Decision Matrix + Persona Research locked); m2: full scan/report set; intel: full set                                                              |
| `client_portal` | m2, m6v2, links                                                                 | m2: only `reportv6` and `trajectoryv2`. m6v2 has no tab allowlist (uses its own track tabs; Style Rules gated by IS_CLIENT_PORTAL inside the component).               |

### 8.3 Helper Functions

- `canAccessModule(role, moduleId)` - simple includes check on
  `ROLE_PERMISSIONS[role].modules`.
- `canAccessTab(role, moduleId, tabId)` - if the module has no tab list,
  allow; otherwise check tab is included.
- `defaultModuleFor(role)` - `client_portal` -> `m2`, others -> `home`.
- `defaultTabFor(role, moduleId)` - first allowed tab for that module, or null.
- `IS_CLIENT_PORTAL = import.meta.env.VITE_PORTAL_MODE === "client"` - build flag.

### 8.4 Authentication Flow

`loginUser(email, password)`:

1. SHA-256 hash the password with the static salt `"_xt_salt_2026"`. Hashing
   requires HTTPS (or localhost) - throws a friendly error otherwise.
2. Check the `BUILTIN_ACCOUNTS` array first (in-bundle):
   - `gaurav@xtrusio.com` -> role `admin`.
   - `client@sirion.ai` -> role `client_portal` (rotation instructions inline).
3. If not built-in, try Firebase: `db.getAll("app_config_accounts")` and match.
4. Fallback: scan localStorage cache for `xt_app_config_accounts_*`.
5. On success, also call `exchangeForProxyToken(email, password)` which
   POSTs to `${PROXY_BASE}/api/auth/login` and stores the returned
   `xt_token` + `xt_client` in sessionStorage. This token is required for
   any AI call.

Sessions persist 30 days (`Date.now() - session.loginAt > 30 * 24 * 60 *
60 * 1000` triggers expiry and removal).

### 8.5 createAccount(email, password, role, name)

Admin tool that hashes the password and PUTs to `app_config_accounts` with
docId = email with non-alphanumerics replaced by `_`.

---

## 9. m2ScanLoader.js (`src/m2ScanLoader.js`)

Specialized loader that builds the canonical V5 scan dataset (154 questions
across 5 LLMs) by:

### 9.1 Constants

- `SCAN_35Q  = "baseline_20260423_1718"` - the locked 35-question V3 baseline.
- `SCAN_119Q = "baseline_20260423_2229"` - the 119-question V3 baseline.
- `AUGMENT_LLMS = ["grok", "perplexity"]` - LLMs whose results are spliced
  in from later scans.

### 9.2 Functions

- `loadScanDocs(scanId)` - posts a Firestore `:runQuery` against
  `m2_scan_results` filtered by `scanId == scanId`. Returns up to 500 docs.
- `loadAugmentingScans()` - reads `m2_scan_meta`, filters out the two
  baseline IDs, runs `loadScanDocs` on each remaining scan, flattens.
- `mergeAugmentingAnalyses(baselineDocs, augmentDocs)` - sorts augment docs
  by completion time, builds a `qid -> { grok, perplexity }` map (latest
  non-error wins), then for each baseline doc adds the augment LLMs into
  `analyses` if present.
- `loadCombinedScanDocs()` - public entry point. Returns a merged array of
  doc objects of shape:
  ```
  { qid, query, persona, stage, analyses: { [llm]: { mentioned, ... } }, ... }
  ```
  Returns `[]` if Firebase is unreachable or all loads fail.
- `llmsInDocs(docs)` - scans all `analyses` keys across docs, returns the
  distinct list of LLM IDs that have at least one non-error analysis.

### 9.3 Consumers

Used by `ReportV2.jsx` and other report views that need a stable
ground-truth dataset matching what `ReportV5.jsx` displays. Ensures the
numbers in V2 stay consistent with V5.

---

## 10. questionDB.js - IndexedDB Knowledge Base (`src/questionDB.js`)

### 10.1 Schema

`DB_NAME = "xtrusio-m1"`, `DB_VERSION = 2`. The `openDB()` singleton lazily
opens the database; on `onclose` or `onversionchange` (another tab upgraded)
it nulls the singleton so the next call reopens.

### Object Stores

| Store          | Key          | Indexes                                                        | Purpose                                                                                                                  |
| -------------- | ------------ | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `questions`    | `id`         | `company`, `persona`, `stage`, `classification`, `generatedAt` | All questions ever generated for any company.                                                                            |
| `companyIntel` | `companyKey` | (none)                                                         | Cached AI research about target companies.                                                                               |
| `macroBank`    | `dedupHash`  | `timesGenerated`                                               | Industry-wide questions seen across companies. Tracks `seenForCompanies`, `firstSeenAt`, `lastSeenAt`, `timesGenerated`. |
| `personas`     | `id`         | `company`, `personaType`, `name`, `createdAt`                  | Researched persona profiles (decision makers).                                                                           |

### 10.2 Hash Function

`questionHash(text)` lowercases, strips non-word chars, collapses
whitespace, then runs djb2 (`5381` seed, `((h << 5) + h) + charCode`),
ending with `(h >>> 0).toString(36)`. Used as the dedupHash everywhere -
identical text always produces the same key, allowing cross-collection
deduping.

### 10.3 Exposed Functions

| Function                                                                     | Purpose                                                                                                  |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `saveQuestions(questions)`                                                   | Batch put into `questions`.                                                                              |
| `replaceAllQuestions(keptQuestions)`                                         | Clear store + re-save.                                                                                   |
| `deleteQuestions(ids)`                                                       | Batch delete by id.                                                                                      |
| `getQuestionsForCompany(company)`                                            | Index lookup by company.                                                                                 |
| `getAllQuestions()`                                                          | All stored questions across companies.                                                                   |
| `saveMacro(question)`                                                        | Upsert into `macroBank` - increments `timesGenerated`, unions `seenForCompanies`.                        |
| `getAllMacros()`                                                             | All macroBank entries.                                                                                   |
| `saveCompanyIntel(intel)` / `getCompanyIntel(company)`                       | Cache per company (key = lowercased dashed company name).                                                |
| `getAllCompanyIntel()`                                                       | All.                                                                                                     |
| `getKnowledgeBaseStats()`                                                    | Counts: `{ totalQuestions, totalMacros, companiesResearched, totalPersonas }`.                           |
| `hydrateQuestions(fbQuestions)`                                              | Merge cloud questions in - newer `generatedAt` wins.                                                     |
| `hydrateMacros(fbMacros)`                                                    | Merge cloud macros - max `timesGenerated`, union companies, earliest `firstSeenAt`, latest `lastSeenAt`. |
| `hydrateCompanyIntel(fbIntel)`                                               | Merge cloud intel - newer `lastResearchedAt` wins.                                                       |
| `savePersona(p)` / `savePersonas(arr)`                                       | Single + batch upsert.                                                                                   |
| `getPersonasForCompany(company)` / `getAllPersonas()` / `getPersonaById(id)` | Read variants.                                                                                           |
| `updatePersona(id, updates)`                                                 | Read existing, shallow-merge updates, set `updatedAt`, write back.                                       |
| `deletePersona(id)`                                                          | Delete by id.                                                                                            |

### 10.4 Reset Behavior

When `DATA_VERSION` in PipelineContext is bumped, the IIFE at module load
calls `indexedDB.deleteDatabase("xtrusio-m1")` so this entire DB is wiped
along with the localStorage snapshot. Bump only when the schema truly
changes.

---

## Cross-cutting Notes

- Every persistent collection has a localStorage cache fallback (`xt_<col>_<id>`)
  except m2_scan_results / m2_scans for entries > 500KB.
- The provider-key system has been intentionally removed from the browser;
  legacy keys are scrubbed on every boot. AI access depends entirely on
  `xt_token` from the Worker handshake.
- Production guard: if `FIREBASE_ENABLED` is false in `import.meta.env.PROD`,
  the boot logs `[INVARIANT] Firebase is DISABLED in production`.
