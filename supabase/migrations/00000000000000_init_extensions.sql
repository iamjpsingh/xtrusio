-- First migration: enable Postgres extensions used across the platform.
-- Supabase ships pgcrypto and citext out of the box, so this migration is
-- an explicit declaration so any environment (local, staging, prod) is
-- guaranteed to have them.
--
-- pgvector is required by the analysis toolkit (spec #3, embedding cache)
-- and may be required by future RAG / similarity features.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
