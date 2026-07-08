-- GeoRAG schema for tasco_jarvis_map (database: atria_map on map-db:5433).
-- Idempotent: applied by db_setup.py, safe to re-run. Data is a derived index
-- of data/pois.json + data/addresses.json (db_import.py full-syncs it).
--
-- normalized_* columns hold the dataset's precomputed q{} keys VERBATIM (built
-- with _data.fold + expand_abbrev) so query-time normalization matches the
-- index byte-for-byte. tsvector uses the 'simple' config because the text is
-- pre-folded ASCII.
--
-- Deliberately no phone/website/postal_code columns (not in the dataset; raw
-- JSONB keeps the door open) and no ivfflat/HNSW index: at ~340 rows an exact
-- sequential cosine scan is faster and always exact (revisit past ~50k rows).
--
-- Deferred (Phase 6, not v1): map_poi_edges(from_poi_id, to_poi_id,
-- relation_type, confidence) for near/same_brand/same_street/inside relations.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS map_categories (
    key       text PRIMARY KEY,
    label     text NOT NULL,
    label_vi  text NOT NULL,
    color     text,
    emoji     text
);

CREATE TABLE IF NOT EXISTS map_pois (
    poi_id              text PRIMARY KEY,
    name                text NOT NULL,
    name_en             text,
    category            text REFERENCES map_categories(key),
    brand               text,
    address             text,
    district            text,
    city                text,
    lat                 double precision NOT NULL,
    lng                 double precision NOT NULL,
    rating              real,
    opening_hours       text,
    normalized_name     text NOT NULL,   -- q.name (verbatim)
    normalized_name_en  text,            -- q.name_en (verbatim)
    normalized_address  text,            -- q.addr (verbatim)
    name_blob           text NOT NULL,   -- q.name + q.name_en + q.aliases joined
    geom                geography(Point, 4326) NOT NULL,
    raw                 jsonb NOT NULL,  -- original dataset object incl. q{} (pois-dump parity)
    source              text NOT NULL DEFAULT 'pois.json',
    updated_at          timestamptz NOT NULL DEFAULT now(),
    fts tsvector GENERATED ALWAYS AS (
        to_tsvector('simple',
            coalesce(normalized_name, '') || ' ' ||
            coalesce(normalized_name_en, '') || ' ' ||
            coalesce(normalized_address, ''))
    ) STORED
);

CREATE TABLE IF NOT EXISTS map_addresses (
    address_id       text PRIMARY KEY,
    full_address     text NOT NULL,
    house_number     text,
    street           text,
    ward             text,
    district         text,
    city             text,
    lat              double precision NOT NULL,
    lng              double precision NOT NULL,
    notes            text,
    normalized_full  text NOT NULL,      -- q.full (verbatim)
    geom             geography(Point, 4326) NOT NULL,
    raw              jsonb NOT NULL,
    source           text NOT NULL DEFAULT 'addresses.json',
    updated_at       timestamptz NOT NULL DEFAULT now(),
    fts tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', normalized_full)
    ) STORED
);

-- rank 0 = primary keys (name, name_en / full_address): no alias penalty.
-- rank 1 = dataset aliases: small penalty, preserving the legacy
-- "exact name 100 / exact alias 95" semantics.
CREATE TABLE IF NOT EXISTS map_aliases (
    id                bigserial PRIMARY KEY,
    entity_type       text NOT NULL CHECK (entity_type IN ('poi', 'address')),
    entity_id         text NOT NULL,
    alias             text NOT NULL,      -- original (accented) form
    normalized_alias  text NOT NULL,      -- folded (from q{}, verbatim)
    rank              smallint NOT NULL DEFAULT 1,
    UNIQUE (entity_type, entity_id, normalized_alias)
);

CREATE TABLE IF NOT EXISTS map_embeddings (
    entity_type     text NOT NULL CHECK (entity_type IN ('poi', 'address')),
    entity_id       text NOT NULL,
    embedding       vector(1536) NOT NULL,
    embedding_text  text NOT NULL,
    text_hash       text NOT NULL,        -- sha256(model + '\0' + embedding_text)
    model           text NOT NULL DEFAULT 'text-embedding-3-small',
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_type, entity_id)
);

-- Derived place gazetteer (see scripts/gazetteer.py): cities/districts and
-- every alias variant, DERIVED from the dataset + abbreviation dictionary at
-- import time — no place name is hardcoded in code. Rebuilt by db_import.py.
CREATE TABLE IF NOT EXISTS map_admin_areas (
    id           bigserial PRIMARY KEY,
    level        text NOT NULL CHECK (level IN ('city', 'district')),
    canonical    text NOT NULL,     -- prefix-stripped folded form (filter key)
    name         text NOT NULL,     -- original dataset value
    parent_city  text,              -- district rows only
    variant      text NOT NULL,     -- one folded alias/spelling
    source       text NOT NULL,     -- data | prefix | nospace | abbrev | seed
    UNIQUE (level, canonical, variant)
);
CREATE INDEX IF NOT EXISTS map_admin_variant_trgm
    ON map_admin_areas USING gin (variant gin_trgm_ops);

-- Query-embedding cache: repeat searches and eval reruns skip the OpenAI call.
CREATE TABLE IF NOT EXISTS map_query_embeddings (
    query_hash  text PRIMARY KEY,          -- sha256(model + '\0' + raw_query)
    query_text  text NOT NULL,
    embedding   vector(1536) NOT NULL,
    model       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS map_pois_geom_gist  ON map_pois USING gist (geom);
CREATE INDEX IF NOT EXISTS map_addr_geom_gist  ON map_addresses USING gist (geom);
CREATE INDEX IF NOT EXISTS map_pois_name_trgm  ON map_pois USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS map_pois_addr_trgm  ON map_pois USING gin (normalized_address gin_trgm_ops);
CREATE INDEX IF NOT EXISTS map_addr_full_trgm  ON map_addresses USING gin (normalized_full gin_trgm_ops);
CREATE INDEX IF NOT EXISTS map_alias_trgm      ON map_aliases USING gin (normalized_alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS map_pois_fts_gin    ON map_pois USING gin (fts);
CREATE INDEX IF NOT EXISTS map_addr_fts_gin    ON map_addresses USING gin (fts);
CREATE INDEX IF NOT EXISTS map_pois_category   ON map_pois (category);
CREATE INDEX IF NOT EXISTS map_alias_entity    ON map_aliases (entity_type, entity_id);
