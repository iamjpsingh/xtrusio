# The Task-Queue Blueprint

### A language-agnostic design for a production-grade background job system

Implementable in **Python** (Celery / arq / Dramatiq), **TypeScript** (BullMQ),
**PHP** (Laravel Queues / Symfony Messenger), **Go** (Asynq / River), **Ruby**
(Sidekiq). The principles are the same everywhere — only the library names change.

> **Naming note.** The process that runs jobs is correctly called a **worker**
> (BullMQ `Worker`, Celery "workers", Sidekiq "workers"). This is unrelated to
> "Cloudflare Workers" — that product reused the word for edge functions; it is a
> name clash, not the same concept. The *whole system* described here is a
> **Background Job System** / **Task Queue** — an implementation of the
> **Producer–Consumer (Queue–Worker) pattern**, also known as **Queue-Based
> Load Leveling**.

---

## 0. The mental model

```
PRODUCER ──enqueue(job)──▶ BROKER(queue) ──pull──▶ WORKER ──run──▶ result
   ▲                          │                       │
   │                          │ schedule              │ on permanent failure
SCHEDULER ──────recurring─────┘                       ▼
                                                  DEAD-LETTER QUEUE
   CLIENT ──poll(jobId)──▶ RESULT BACKEND ◀──write status── WORKER
```

**The named parts:**

| Part                    | Proper name                     |
| ----------------------- | ------------------------------- |
| Thing that adds jobs    | **Producer** / **Enqueuer**     |
| Where jobs wait         | **Broker** / **Queue**          |
| Process that runs jobs  | **Worker** / **Consumer**       |
| Recurring trigger       | **Scheduler** / **Beat**        |
| Failed-job store        | **Dead-Letter Queue (DLQ)**     |
| Status/result store     | **Result Backend**              |

**Two invariants the whole design protects:**

1. **At-least-once delivery** — a job may run more than once (crash mid-run,
   retry). Therefore **every handler must be idempotent or deduplicated.**
2. **Never run slow/failing work on the request path** — the web request only
   *enqueues*; the worker *executes*.

Everything below serves those two invariants plus operability.

---

## Part A — The core loop (minimum viable queue)

```
# PRODUCER
function enqueue(jobType, payload, options):
    job = { id: options.id or random(), type: jobType,
            payload: payload, attempts: 0, enqueued_at: now() }
    BROKER.push(queue, job)
    return job.id

# WORKER (long-running process)
function worker_loop():
    while not shutting_down:
        job = BROKER.pull(queue, block=true, lock_for=LOCK_DURATION)  # claim atomically
        if job == none: continue
        run_job(job)

function run_job(job):
    handler = HANDLERS.get(job.type)
    if handler == none:                       # ㉓ fail-closed (see below)
        DLQ.push(job, "unknown_job_type"); return BROKER.ack(job)
    try:
        result = run_with_timeout(handler, job.payload, TIMEOUTS[job.type])  # ④
        BROKER.ack(job)
        RESULTS.set(job.id, "completed", result, ttl=RESULT_TTL)
    except err:
        on_failure(job, err)
```

> **Why `pull` must claim atomically (`lock_for`):** two workers must never grab
> the same job. In Redis this is `BRPOPLPUSH` / a visibility timeout; in Postgres
> it is `SELECT … FOR UPDATE SKIP LOCKED`. This is the foundation of everything.

---

## Part B — The hardening principles

Each principle = one production lesson. ⭐ marks the two highest-value ideas.

### ① Deterministic-ID deduplication ⭐

A resource can only have **one** in-flight job. Mashing "Sync now" + the nightly
scheduler must collapse into one — never N concurrent runs hammering one API.

```
function enqueue_dedup(jobType, payload, resourceId):
    jobId = jobType + ":" + resourceId          # DETERMINISTIC, not random
    existing = BROKER.get(jobId)
    if existing and existing.state in {WAITING, ACTIVE, DELAYED}:
        return jobId                             # already in flight → no-op
    if existing: BROKER.remove(jobId)            # finished/failed → replace
    BROKER.push(queue, {id: jobId, ...})         # broker enforces id-uniqueness ATOMICALLY
    return jobId
```

The broker's atomic id-uniqueness is what makes this race-free (O(1), no scan, no
TOCTOU). Never emulate it with "read all jobs, then decide."

### ② Bounded retries with exponential backoff

```
MAX_ATTEMPTS = 3
function handle_failure(job, err):
    job.attempts += 1
    if job.attempts < MAX_ATTEMPTS:
        delay = BASE_DELAY * (2 ^ job.attempts)   # 30s → 60s → 120s
        BROKER.requeue(job, after=delay)
    else:
        finalize_failure(job, err)                # → DLQ + alert (⑦, ⑪)
```

### ③ Retention / auto-trim

```
on_complete: keep COMPLETED_TTL (e.g. 1h) or last N
on_fail:     keep FAILED_TTL    (e.g. 24h) or last N
DLQ:         NEVER auto-delete                     # forensics
```

### ④ Per-job-type timeout (anti-hang)

```
TIMEOUTS = { "sync": 5min, "fan-out": 1min, "rate-check": 30s }

function run_with_timeout(handler, payload, limit):
    try:    return race(handler(payload), timeout_after(limit))
    finally: cancel_timer()                        # never leak the timer
```

### ⑤ Concurrency cap

```
worker.concurrency = N      # at most N jobs at once
```

### ⑥ Start-rate limiter (partner of fan-out ⑩)

When a fan-out enqueues 30 children at 2 AM, don't open 30 external connections
in the same second → instant rate-limit / ban.

```
limiter = { max: 2, per: 5s }                      # ≤ 2 job STARTS per 5s
before run_job: limiter.acquire()                  # token bucket in the broker
```

### ⑦ Dead-Letter Queue (DLQ)

A permanently-failed job must be preserved for a human, not vanish.

```
function finalize_failure(job, err):
    isolated_post_failure(job, err)                # ⑦+⑪ isolation, see below
```

### ⑧ Stall / lock recovery

A worker that crashes mid-job must release the job for another worker to retry.

```
lock_duration = longest_job_timeout                # lock must outlive the job
stalled_check = every 60s                          # scan for expired locks
max_stalls    = 2                                  # recover once; fail on 2nd stall
```

### ⑨ Guarded status state-machine

Mark progress optimistically, but never leave a resource stuck — and don't
clobber a status the handler already set.

```
function handle(resourceId):
    DB.set(resourceId, status="syncing")
    try:
        do_work(resourceId,
                on_progress = (p) => RESULTS.progress(job.id, p))   # see ⑨-progress
    except err:
        DB.update(resourceId, status="error")
           .WHERE(status == "syncing")             # GUARD: only rescue stuck rows
           .ignore_secondary_errors()              # don't mask the real error
        raise err
```

**⑨-progress — progress carries a human stage, not just a percent:**

```
progress(jobId, { percent: 45,
                  stage:   "refreshing_token",     # machine key
                  message: "Upserting 240 rows" }) # human label for the UI
```

### ⑩ Fan-out / parent-child

Isolate failures — one bad child must not take down the nightly run.

```
function fan_out():
    children = DB.query(eligible_resources)
    for r in children:
        try: enqueue_dedup("sync", r)              # each child = own retryable job
        except: failed += 1                        # one bad enqueue ≠ abort all
        progress("enqueued i/total")
    return { enqueued, failed }                    # parent stays THIN (short timeout)
```

### ⑪ Failure observability + in-product alert

Failures must surface where humans look — not only in logs.

```
on_failure(job, err):
    LOG.error(structured{ jobId, type, attempt, final: attempt>=MAX, err, payload })
    if final:
        DB.insert(admin_notifications, { role:"admin", type:"job_failed", ... })
```

### ⑫ Health endpoint

```
GET /health → { status: running ? 200 : 503,
                uptime, jobs:{processed, failed}, last_job_at }
```

### ⑬ Idempotent scheduler (cron)

Restarting the worker must not create duplicate schedules.

```
scheduler.upsert("nightly-sync",  cron="0 2 * * *", tz=TZ, job="fan-out")
scheduler.upsert("rate-check",    cron="0 3 * * *", tz=TZ)
scheduler.upsert("audit-cleanup", cron="0 4 * * 0", tz=TZ)
# upsert = create-or-replace by name → idempotent across restarts
```

### ⑭ Missed-window catch-up ⭐ (self-healing scheduler)

If the worker was down at 2 AM, a naive cron silently skips. This guarantees data
is at most `STALE_WINDOW` old. **No library ships this — it is always your code.**

```
on_startup (after worker ready, +5s):
    cutoff  = now() - STALE_WINDOW                 # e.g. 24h
    overdue = DB.query(resources WHERE (last_run is null OR last_run < cutoff)
                                  AND status NOT IN TERMINAL)          # ㉑
    for r in overdue: enqueue_dedup("sync", r)     # ① makes re-enqueue safe
```

> **⑭ + ① together** = idempotent **and** self-healing: spam the trigger, restart
> the worker, survive an outage — the system always converges to "exactly one
> correct run per resource." This is the hallmark of production queue experience.

### ⑮ Graceful shutdown

```
on SIGTERM/SIGINT:
    stop_accepting_new_jobs()
    wait_for_inflight(or release their locks for retry)
    flush_logs()
    exit(0)
```

### ⑯ Broker-connection hardening (HA-aware) + boot-time config visibility

```
broker_options:
    block_command_retries = unlimited              # don't abort during blocking pull
    reconnect_backoff(attempt) = min(attempt*500ms, 10s)
    reconnect_on_error(err) = err contains "READONLY"   # replica promoted → reconnect
    log_dsn = mask_password(dsn)                    # never log the secret

on_startup:                                         # answer "what config am I running?"
    LOG.info("worker_boot", {
        broker: mask_password(BROKER_URL),
        concurrency: N, timeouts: TIMEOUTS,
        feature_flags: { ... },                     # e.g. TIKTOK_RELAY: on
        schedules: scheduler.list_names() })
```

---

## Part C — Improvements (close the gaps a first version usually has)

### ⑰ Circuit breaker

If a platform API is fully down, don't let every job burn all its retries — trip
open and fail fast.

```
breaker[provider] = { state: CLOSED, failures: 0 }
before external_call(provider):
    if breaker.state == OPEN and now() < breaker.open_until: raise CircuitOpen
on success: breaker.failures = 0; breaker.state = CLOSED
on failure:
    breaker.failures += 1
    if breaker.failures >= THRESHOLD:
        breaker.state = OPEN; breaker.open_until = now() + COOLDOWN
# after cooldown → HALF_OPEN: allow one trial call before fully closing
```

### ⑱ Pre-run token refresh

Long-lived OAuth tokens expire → refresh before work, don't surface as a "sync
error."

```
before do_work(connection):
    if connection.token_expires_at < now() + SKEW:
        connection.token = refresh_oauth(connection.provider, connection.refresh_token)
        DB.save(connection.token)
```

### ⑲ Typed DLQ payload

The DLQ record is what a human reads at 3 AM — schema-validate it, no escape
hatch (no `any`).

```
schema DeadLetter { original_job: Job, error: string, stack: string,
                    provider: string, failed_at: timestamp }
# validate on write; reject malformed → the type system protects forensics
```

### ⑳ Tests on the high-value logic

Dedup (①) and catch-up (⑭) are the highest-value, least-obvious logic — protect
them.

```
test "double enqueue → one job"        : enqueue_dedup x2 ⇒ queue.size == 1
test "catch-up re-enqueues only stale" : seed stale+fresh ⇒ only stale enqueued
test "catch-up is dedup-safe"          : pre-queue one ⇒ catch-up adds no dup
test "terminal state skips retry"      : fail with expired ⇒ no requeue, alert sent
test "permanent failure → DLQ + alert" : fail MAX times ⇒ DLQ has 1, alert sent
test "timeout frees the slot"          : hang a job ⇒ fails, worker continues
test "unknown job type → DLQ"          : enqueue bad type ⇒ quarantined, no fallback
```

---

## Part D — UX hardening (additions from real operation)

### ㉑ Terminal (non-retryable) states ⭐

Not every failure should retry. `expired` / `revoked` / `needs-reauth` means
**stop — a human must act.** Retrying just burns attempts and spams alerts. This
also tells retry (②) and catch-up (⑭) what to skip.

```
RETRYABLE = { error, rate_limited, timeout }       # ② retries these
TERMINAL  = { expired, revoked, deleted }          # STOP — no retry, no catch-up

on_failure(job, err):
    state = classify(err)                          # map error → resource state
    DB.set(job.resource, status=state)
    if state in TERMINAL:
        alert_once("needs_human", job.resource, job)   # ㉒ surface, don't retry
        return BROKER.ack(job)                     # remove; do NOT requeue
    else:
        handle_failure(job, err)                   # normal ②/⑦ retry+DLQ path

# ⑭ catch-up & ② retry both filter:  WHERE status NOT IN TERMINAL
```

### ㉒ Alert-dedup guard

An alerting job must not spam — one open notification per condition until
resolved.

```
function alert_once(type, condition_key, payload):
    existing = DB.find(notifications WHERE type==type AND key==condition_key
                                     AND is_read==false AND dismissed==null)
    if existing: return skipped                     # already open → no spam
    DB.insert(notifications, {type, key: condition_key, payload})
```

### ⑦+⑪ Isolated post-failure handler

The alert failing must not stop the DLQ write, and vice-versa.

```
function isolated_post_failure(job, err):
    run_all_isolated([ () => alert_admin(job, err),
                       () => DLQ.push(typed_dead_letter(job, err)) ])   # ⑲
    # each step in its own try/catch; one failing never blocks the other,
    # and neither masks the original error that gets re-raised
```

### ㉓ Fail-closed dispatch

An unknown job type is a bug or a poisoned message — never silently coerce it.

```
handler = HANDLERS.get(job.type)
if handler == none:
    LOG.error("unknown_job_type", job.type)
    DLQ.push(job, "unknown_job_type")              # quarantine for inspection
    return BROKER.ack(job)                         # do NOT run a fallback handler

# ANTI-PATTERN (never copy):  default → HANDLERS["sync-connection"]
```

### ㉔ Client-side polling that distinguishes "dead" from "slow"

Avoid false "it failed" on a big dataset.

```
function poll(jobId):
    not_found = 0
    loop every INTERVAL until DEADLINE:
        s = RESULTS.get(jobId)
        if s == none:
            if ++not_found > 5: return error("job not found — worker may be down")
            continue
        if s.state == completed: return s.result
        if s.state == failed:    return error(s.reason)
        # else: show s.progress.message  (⑨-progress) while waiting
    if RESULTS.get(jobId).state == active:
        return info("still running — large dataset, check back shortly")   # NOT error
    return error("timed out")
```

---

## Part E — Implementation cheat-sheet

Which library gives you each principle natively (✅) vs. you build it (manual):

| Principle          | BullMQ (TS) | Celery (Py)    | arq (Py)  | Asynq (Go)  | Laravel (PHP)        |
| ------------------ | ----------- | -------------- | --------- | ----------- | -------------------- |
| ① dedup-by-id      | `jobId`     | `celery-once`  | `_job_id` ✅ | unique opt | `WithoutOverlapping` |
| ② retry+backoff    | ✅          | `autoretry_for`| ✅        | `MaxRetry`  | `backoff()`          |
| ④ timeout          | per-job     | `time_limit`   | `timeout` | `Timeout`   | `timeout`            |
| ⑥ rate limiter     | `limiter`   | `rate_limit`   | semaphore | `RateLimit` | `throttle`           |
| ⑦ DLQ              | manual      | manual         | manual    | `Archived`  | `failed_jobs`        |
| ⑬ cron             | scheduler   | `beat`         | `cron()` ✅ | `Scheduler` | `schedule()`         |
| ⑭ catch-up         | app code    | app code       | app code  | app code    | app code             |
| ㉑ terminal states | app code    | app code       | app code  | app code    | app code             |

> ⑭ catch-up and ㉑ terminal states are always **your** code — no library ships
> them. They are what separate a queue that "usually runs" from one that is
> correct under downtime and dead tokens.

---

## Part F — Maturity ladder (build in this order)

```
MVP         : ①enqueue ②worker-loop ③atomic-claim ④handler           # works
Reliable    : +②retry +④timeout +⑧stall +⑮graceful-shutdown          # survives failures
Operable    : +⑦DLQ +⑪alerts +⑫health +⑯conn-hardening               # survives production
Correct     : +①dedup +⑨guarded-status +⑩fan-out +⑥rate-limit +㉓fail-closed
Self-healing: +⑬cron +⑭catch-up +㉑terminal-states                    # survives downtime ⭐
Hardened    : +⑰breaker +⑱token-refresh +⑲typed-DLQ +⑳tests +㉒alert-dedup +㉔smart-poll
```

---

## Appendix — Example maintenance jobs (illustrative, NOT core)

These are *bodies*, not principles — they are product logic and intentionally
live outside the core blueprint. They illustrate ⑬ (cron) + ㉒ (alert-dedup).
Replace with your own domain logic.

**FX-drift check** — illustrates ㉒:

```
RATE_THRESHOLD_PERCENT = 0.5
for ccy in tracked_currencies:
    live   = 1 / fetch_rate(ccy)                   # API quotes "1 USD = X"; invert
    stored = DB.rate(ccy)
    drift  = abs((live - stored) / stored) * 100
    if drift > RATE_THRESHOLD_PERCENT:
        alert_once("rate_change", ccy, {live, stored, drift})   # ㉒ no spam
```

**Audit cleanup** — illustrates ⑬ + bounded retention:

```
cutoff = now() - RETENTION_DAYS * 1_day            # e.g. 90 days
DB.delete(audit_log WHERE actor_type=="user" AND created_at < cutoff)
# only trims user rows; keeps compliance/admin records
```

---

*Provenance: distilled from a production BullMQ metric-sync subsystem
(Meta / Google Ads / TikTok / GA4 sync), generalized to be language- and
product-agnostic.*
