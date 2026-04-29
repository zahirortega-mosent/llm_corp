-- Bloque 4 - Memoria institucional formal e hibrida
-- Seguro para imagenes PostgreSQL sin pgvector: intenta crear extension vector,
-- pero no falla si la extension no esta instalada. La columna vectorial se agrega
-- solo cuando el tipo vector existe.

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
    WHEN undefined_file OR insufficient_privilege THEN
        RAISE NOTICE 'pgvector no disponible en esta imagen/permisos. La memoria institucional arrancara solo con busqueda lexical/full-text.';
END $$;

CREATE TABLE IF NOT EXISTS institutional_documents (
    document_id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('pdf','docx','markdown','txt','html','csv','manual','policy','process','person_directory','other')),
    source_path TEXT,
    owner_area TEXT,
    confidentiality_level TEXT NOT NULL DEFAULT 'internal',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','archived')),
    version TEXT,
    checksum TEXT,
    tags TEXT[] DEFAULT '{}',
    allowed_groups TEXT[] DEFAULT '{}',
    created_by TEXT,
    approved_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS institutional_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES institutional_documents(document_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED,
    -- JSONB mantiene la migracion segura cuando pgvector no esta instalado.
    -- Si pgvector existe, el bloque DO de abajo agrega embedding_vector vector(1024).
    embedding JSONB,
    embedding_model TEXT,
    embedding_dim INT,
    tags TEXT[] DEFAULT '{}',
    area TEXT,
    allowed_groups TEXT[] DEFAULT '{}',
    allowed_roles TEXT[] DEFAULT '{}',
    valid_from DATE,
    valid_to DATE,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS institutional_entities (
    entity_id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('person','area','process','system','bank','filial','account','rule','policy','document')),
    canonical_name TEXT NOT NULL,
    aliases TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT true,
    UNIQUE(entity_type, canonical_name)
);

CREATE TABLE IF NOT EXISTS institutional_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    subject_entity_id BIGINT REFERENCES institutional_entities(entity_id),
    subject_text TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_text TEXT NOT NULL,
    source_document_id BIGINT REFERENCES institutional_documents(document_id),
    source_chunk_id BIGINT REFERENCES institutional_chunks(chunk_id),
    confidence NUMERIC(4,3) NOT NULL DEFAULT 0.800,
    area TEXT,
    allowed_groups TEXT[] DEFAULT '{}',
    valid_from DATE,
    valid_to DATE,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_institutional_documents_status_active
ON institutional_documents(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_institutional_documents_checksum
ON institutional_documents(checksum);

CREATE INDEX IF NOT EXISTS idx_institutional_documents_tags
ON institutional_documents USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_institutional_documents_allowed_groups
ON institutional_documents USING GIN(allowed_groups);

CREATE INDEX IF NOT EXISTS idx_institutional_chunks_tsv
ON institutional_chunks USING GIN(content_tsv);

CREATE INDEX IF NOT EXISTS idx_institutional_chunks_tags
ON institutional_chunks USING GIN(tags);

CREATE INDEX IF NOT EXISTS idx_institutional_chunks_allowed_groups
ON institutional_chunks USING GIN(allowed_groups);

CREATE INDEX IF NOT EXISTS idx_institutional_chunks_active_validity
ON institutional_chunks(active, valid_from, valid_to);

CREATE INDEX IF NOT EXISTS idx_institutional_entities_type_name
ON institutional_entities(entity_type, canonical_name);

CREATE INDEX IF NOT EXISTS idx_institutional_facts_subject
ON institutional_facts(subject_text);

CREATE INDEX IF NOT EXISTS idx_institutional_facts_predicate
ON institutional_facts(predicate);

CREATE INDEX IF NOT EXISTS idx_institutional_facts_active_validity
ON institutional_facts(active, valid_from, valid_to);

DO $$
BEGIN
    IF to_regtype('vector') IS NOT NULL THEN
        ALTER TABLE institutional_chunks
        ADD COLUMN IF NOT EXISTS embedding_vector vector(1024);

        -- ivfflat requiere datos suficientes para ser util; este indice es opcional
        -- y no rompe si ya existe. Ajustar dimensiones/modelo antes de produccion.
        CREATE INDEX IF NOT EXISTS idx_institutional_chunks_embedding_vector
        ON institutional_chunks USING ivfflat (embedding_vector vector_cosine_ops)
        WITH (lists = 100);
    ELSE
        RAISE NOTICE 'Tipo vector no disponible. Se omite columna/indice embedding_vector.';
    END IF;
EXCEPTION
    WHEN undefined_object OR feature_not_supported OR insufficient_privilege THEN
        RAISE NOTICE 'No se pudo crear columna/indice pgvector. Continuara busqueda full-text.';
END $$;
