-- PAR-F F.1: bootstrap an ephemeral CI Postgres so this project's Alembic
-- migrations can run WITHOUT a managed Supabase instance.
--
-- Supabase provides the GoTrue-owned `auth` schema and `auth.users` table that
-- several FKs target (tenants.created_by, platform_users.id, user_roles.*,
-- *_invites.*). A plain Postgres has neither, so migration 0001 would fail at
-- `REFERENCES auth.users(id)`. We create a MINIMAL stub here — only the columns
-- the FKs and the Supabase-free tests reference. This is CI scaffolding only;
-- production/dev use real managed Supabase.
--
-- Extensions: `pgcrypto` + `citext` ship in the postgres image; `vector` is
-- provided by the `pgvector/pgvector:pg16` CI image (see ci.yml). All three are
-- created idempotently here so migration 0000's `CREATE EXTENSION IF NOT EXISTS`
-- statements are no-ops against an already-prepared DB.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS auth;

-- Minimal stand-in for Supabase's auth.users. Only the columns our migrations
-- and tests touch are modelled; everything else GoTrue adds is irrelevant to
-- the Supabase-free test subset.
CREATE TABLE IF NOT EXISTS auth.users (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id         uuid,
    aud                 varchar(255),
    role                varchar(255),
    email               citext UNIQUE,
    encrypted_password  varchar(255),
    email_confirmed_at  timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
