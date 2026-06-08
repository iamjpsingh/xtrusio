-- Auth-event capture webhook (PR #77) — wires GoTrue login/logout/etc into the
-- activity feed's `auth` category by POSTing each new auth.audit_log_entries row
-- to the API's ingest endpoint.
--
-- PREFER the Supabase Dashboard path (Database → Webhooks) — it provisions the
-- trigger with the right privileges. Use this SQL only for IaC / repeatable
-- setup; it requires TRIGGER privilege on auth.audit_log_entries (owned by
-- supabase_auth_admin), so run it as a sufficiently-privileged role (the
-- Dashboard's SQL editor runs as `postgres`; grant TRIGGER first if it errors).
--
-- Replace the two placeholders before running, then execute against the project:
--   __API_BASE_URL__         e.g. https://api.xtrusio.org   (NO trailing slash)
--   __AUTH_WEBHOOK_SECRET__  the exact value of AUTH_WEBHOOK_SECRET in the API env
--
-- The trigger payload supabase_functions.http_request sends is
--   {"type":"INSERT","table":"audit_log_entries","schema":"auth","record":{…}}
-- which is exactly what POST /api/internal/auth-events expects.

drop trigger if exists xtrusio_auth_event_ingest on auth.audit_log_entries;

create trigger xtrusio_auth_event_ingest
after insert on auth.audit_log_entries
for each row execute function supabase_functions.http_request(
  '__API_BASE_URL__/api/internal/auth-events',
  'POST',
  '{"Content-Type":"application/json","X-Webhook-Secret":"__AUTH_WEBHOOK_SECRET__"}',
  '{}',
  '5000'
);

-- Rollback:
--   drop trigger if exists xtrusio_auth_event_ingest on auth.audit_log_entries;
