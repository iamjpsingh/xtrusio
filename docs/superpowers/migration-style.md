# Migration discipline

How to write Alembic migrations that are safe to run against a **populated,
live** Postgres (managed Supabase) without taking long exclusive locks or
blocking the request path. Audit finding **M21** motivated this doc; migrations
**0010** and **0011** are the canonical worked examples.

These rules apply to any migration that touches a table which already holds
production rows. A migration that only creates brand-new empty tables is
unconstrained — the lock is instant because nothing reads the table yet.

---

## 1. Indexes on existing tables → `CREATE INDEX CONCURRENTLY`

A plain `CREATE INDEX` takes an `ACCESS EXCLUSIVE`-adjacent lock (`SHARE`) that
blocks writes for the whole build. On a populated table that can be minutes of
blocked traffic. Always build concurrently.

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block, but Alembic
wraps every migration in one. Use `op.get_context().autocommit_block()` to
commit the surrounding transaction, run the statement in autocommit, then
reopen. Always pair with `IF NOT EXISTS` so a partially-built (failed)
concurrent index is re-runnable.

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS my_table_col_idx "
            "ON my_table (col)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS my_table_col_idx")
```

**Canonical example: `0011_audit_log_indexes.py`** — three covering indexes on
the populated `rbac_audit_log` table, all built concurrently in an
`autocommit_block`.

---

## 2. Adding `NOT NULL` to an existing column → two-step (never one-shot)

`ALTER TABLE ... SET NOT NULL` performs a full table scan while holding
`ACCESS EXCLUSIVE` — every read and write blocks for the duration. On a large
table this is an outage. Split it so the expensive validation runs WITHOUT the
exclusive lock:

1. **Add a `CHECK (col IS NOT NULL) NOT VALID` constraint.** `NOT VALID` skips
   the table scan and takes only a brief lock — new/updated rows are enforced
   immediately, existing rows are not yet checked.
2. **`VALIDATE CONSTRAINT`.** This scans the table to confirm existing rows
   satisfy the check, but takes only a `SHARE UPDATE EXCLUSIVE` lock — it does
   **not** block reads or writes.
3. **`SET NOT NULL`.** Once a validated `IS NOT NULL` CHECK exists, Postgres
   uses it to prove the column and the `SET NOT NULL` is cheap (no rescan).
   Optionally drop the now-redundant CHECK afterwards.

```python
def upgrade() -> None:
    op.execute(
        "ALTER TABLE my_table "
        "ADD CONSTRAINT my_table_col_not_null CHECK (col IS NOT NULL) NOT VALID"
    )
    op.execute("ALTER TABLE my_table VALIDATE CONSTRAINT my_table_col_not_null")
    op.execute("ALTER TABLE my_table ALTER COLUMN col SET NOT NULL")
    op.execute("ALTER TABLE my_table DROP CONSTRAINT my_table_col_not_null")
```

Backfill any NULLs (see section 3) **before** step 2, or `VALIDATE` will fail.

---

## 3. Backfills over ~10k rows → batched, throttled

A single `UPDATE my_table SET ...` rewrites every row in one transaction: it
bloats the table, holds row locks for the whole run, and can blow up WAL /
replication lag. For anything above ~10k rows, batch it in ~1000-row chunks and
sleep briefly between batches so autovacuum and replicas keep up.

```python
def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            rows_updated integer;
        BEGIN
            LOOP
                UPDATE my_table
                SET col = <expr>
                WHERE id IN (
                    SELECT id FROM my_table
                    WHERE col IS NULL
                    LIMIT 1000
                );
                GET DIAGNOSTICS rows_updated = ROW_COUNT;
                EXIT WHEN rows_updated = 0;
                PERFORM pg_sleep(0.1);
            END LOOP;
        END $$;
        """
    )
```

Each batch commits independently inside the `DO` block's loop semantics; keep
the predicate (`WHERE col IS NULL`) selective so each pass makes progress and
the loop terminates.

---

## 4. General rules

- **Every migration has a working `downgrade()`** (ENGINEERING_PRINCIPLES section 5).
  Concurrent index drops also go in an `autocommit_block`.
- **Ordering guards for data-dependent migrations.** If a migration assumes a
  prior backfill ran (e.g. it retires a fallback path), assert that
  precondition at the top of `upgrade()` and `raise RuntimeError` rather than
  silently corrupting access. Canonical example: `0008_retire_enum_disjunct.py`
  refuses to run on a populated DB whose `user_roles` is still empty (M20).
- **No `CREATE EXTENSION` outside `0000_init_extensions.py`.** Extensions are
  provisioned once; CI's ephemeral Postgres pre-creates them
  (`.github/ci/ephemeral-db-bootstrap.sql`).
- **Test migrations against the real shape.** The `apps/api/tests/migrations`
  suite exercises triggers/constraints directly; add coverage for any new
  trigger or integrity constraint.

---

## Canonical examples in this repo

| Pattern | Migration |
|---|---|
| `CREATE INDEX CONCURRENTLY` via `autocommit_block` | `0011_audit_log_indexes.py` |
| Integrity hardening (CHECK pin, BEFORE-DELETE trigger, per-action RLS) | `0010_rbac_integrity.py` |
| Data-dependency ordering guard (`RuntimeError` precondition) | `0008_retire_enum_disjunct.py` |
