-- Runs once on an empty data volume (docker-entrypoint-initdb.d), after the
-- postgis image's own 10_postgis.sh has created the postgis extension.
-- Extensions only: table DDL lives in scripts/db_schema.sql so the schema can
-- evolve without wiping the volume.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
