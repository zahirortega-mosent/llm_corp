CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS bank_statements (
    statement_pk BIGSERIAL PRIMARY KEY,
    source_statement_id BIGINT,
    statement_uid TEXT NOT NULL UNIQUE,
    source_hash TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    account_number TEXT,
    clabe TEXT,
    entity_name TEXT,
    filial TEXT,
    bank TEXT NOT NULL,
    currency TEXT,
    period DATE,
    period_start DATE,
    period_end DATE,
    opening_balance NUMERIC(18,2),
    closing_balance NUMERIC(18,2),
    total_deposits NUMERIC(18,2),
    total_withdrawals NUMERIC(18,2),
    reconciled_deposit_balance NUMERIC(18,2),
    reconciled_withdrawal_balance NUMERIC(18,2),
    statement_balance_ok BOOLEAN,
    header_only BOOLEAN DEFAULT FALSE,
    created_at_source TIMESTAMP NULL,
    updated_at_source TIMESTAMP NULL,
    ingested_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_statements_period ON bank_statements(period);
CREATE INDEX IF NOT EXISTS idx_bank_statements_bank ON bank_statements(bank);
CREATE INDEX IF NOT EXISTS idx_bank_statements_filial ON bank_statements(filial);
CREATE INDEX IF NOT EXISTS idx_bank_statements_account ON bank_statements(account_number);

CREATE TABLE IF NOT EXISTS bank_movements (
    movement_pk BIGSERIAL PRIMARY KEY,
    movement_uid TEXT NOT NULL UNIQUE,
    source_movement_id BIGINT NULL,
    source_statement_id BIGINT NULL,
    statement_uid TEXT REFERENCES bank_statements(statement_uid) ON DELETE CASCADE,
    bank_transaction_id BIGINT NULL,
    bank TEXT NOT NULL,
    filial TEXT,
    account_number TEXT,
    clabe TEXT,
    entity_name TEXT,
    period DATE,
    movement_date DATE,
    settlement_date DATE,
    reference TEXT,
    folio TEXT,
    description TEXT,
    concept TEXT,
    movement_type TEXT,
    amount NUMERIC(18,2),
    deposit NUMERIC(18,2),
    withdrawal NUMERIC(18,2),
    balance NUMERIC(18,2),
    liquidation_balance NUMERIC(18,2),
    currency TEXT,
    reconciled BOOLEAN,
    source_filename TEXT,
    source_hash TEXT,
    source_group TEXT,
    raw_payload JSONB,
    created_at_source TIMESTAMP NULL,
    updated_at_source TIMESTAMP NULL,
    ingested_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bank_movements_period ON bank_movements(period);
CREATE INDEX IF NOT EXISTS idx_bank_movements_bank ON bank_movements(bank);
CREATE INDEX IF NOT EXISTS idx_bank_movements_filial ON bank_movements(filial);
CREATE INDEX IF NOT EXISTS idx_bank_movements_account ON bank_movements(account_number);
CREATE INDEX IF NOT EXISTS idx_bank_movements_date ON bank_movements(movement_date);
CREATE INDEX IF NOT EXISTS idx_bank_movements_amount ON bank_movements(amount);
CREATE INDEX IF NOT EXISTS idx_bank_movements_statement_uid ON bank_movements(statement_uid);
CREATE INDEX IF NOT EXISTS idx_bank_movements_filename ON bank_movements(source_filename);
CREATE INDEX IF NOT EXISTS idx_bank_movements_desc_trgm ON bank_movements USING gin (description gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bank_movements_ref_trgm ON bank_movements USING gin (reference gin_trgm_ops);

CREATE TABLE IF NOT EXISTS assignments (
    assignment_pk BIGSERIAL PRIMARY KEY,
    filial TEXT NOT NULL,
    bank TEXT NOT NULL,
    account_number TEXT NOT NULL,
    owner_name TEXT,
    area TEXT,
    email TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(filial, bank, account_number)
);

CREATE INDEX IF NOT EXISTS idx_assignments_account ON assignments(account_number);
CREATE INDEX IF NOT EXISTS idx_assignments_filial ON assignments(filial);

CREATE TABLE IF NOT EXISTS business_rules (
    rule_code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    origin TEXT NOT NULL,
    severity TEXT NOT NULL,
    applies_to TEXT NOT NULL,
    auto_detectable BOOLEAN NOT NULL DEFAULT FALSE,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    normative_basis TEXT,
    recommendation TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_pk BIGSERIAL PRIMARY KEY,
    incident_uid TEXT NOT NULL UNIQUE,
    rule_code TEXT NOT NULL REFERENCES business_rules(rule_code),
    period DATE,
    bank TEXT,
    filial TEXT,
    account_number TEXT,
    statement_uid TEXT,
    movement_uid TEXT,
    source_filename TEXT,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'abierta',
    suggested_owner TEXT,
    evidence JSONB,
    detected_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_period ON incidents(period);
CREATE INDEX IF NOT EXISTS idx_incidents_bank ON incidents(bank);
CREATE INDEX IF NOT EXISTS idx_incidents_filial ON incidents(filial);
CREATE INDEX IF NOT EXISTS idx_incidents_account ON incidents(account_number);
CREATE INDEX IF NOT EXISTS idx_incidents_rule ON incidents(rule_code);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);

CREATE TABLE IF NOT EXISTS knowledge_snippets (
    snippet_pk BIGSERIAL PRIMARY KEY,
    snippet_uid TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_path TEXT,
    page_number INTEGER,
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    content_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED,
    ingested_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_type ON knowledge_snippets(source_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_path ON knowledge_snippets(source_path);
CREATE INDEX IF NOT EXISTS idx_knowledge_tags ON knowledge_snippets USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_knowledge_tsv ON knowledge_snippets USING gin(content_tsv);

CREATE TABLE IF NOT EXISTS prompt_audit (
    audit_pk BIGSERIAL PRIMARY KEY,
    asked_at TIMESTAMP NOT NULL DEFAULT NOW(),
    question TEXT NOT NULL,
    parsed_filters JSONB,
    used_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    response TEXT
);

-- Índices compuestos para preguntas rápidas desde el chat.
CREATE INDEX IF NOT EXISTS idx_bank_movements_scope ON bank_movements(period, bank, filial, account_number);
CREATE INDEX IF NOT EXISTS idx_bank_movements_scope_amount ON bank_movements(period, bank, filial, account_number, amount DESC);
CREATE INDEX IF NOT EXISTS idx_bank_movements_unreconciled ON bank_movements(period, bank, filial, account_number) WHERE reconciled IS FALSE OR reconciled IS NULL;
CREATE INDEX IF NOT EXISTS idx_bank_statements_scope ON bank_statements(period, bank, filial, account_number);
CREATE INDEX IF NOT EXISTS idx_bank_statements_mismatch ON bank_statements(period, bank, filial, account_number) WHERE statement_balance_ok IS FALSE;
CREATE INDEX IF NOT EXISTS idx_incidents_scope ON incidents(period, bank, filial, account_number);
CREATE INDEX IF NOT EXISTS idx_incidents_scope_severity ON incidents(period, bank, filial, account_number, severity);
CREATE INDEX IF NOT EXISTS idx_incidents_rule_severity ON incidents(rule_code, severity);
CREATE INDEX IF NOT EXISTS idx_bank_movements_concept_trgm ON bank_movements USING gin (concept gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bank_movements_folio_trgm ON bank_movements USING gin (folio gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bank_movements_entity_trgm ON bank_movements USING gin (entity_name gin_trgm_ops);
