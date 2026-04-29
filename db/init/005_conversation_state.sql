-- Bloque 3 - estado conversacional persistente para follow-ups.
-- Ejecuta tambien db/migrations/005_conversation_state.sql en bases ya creadas.

CREATE TABLE IF NOT EXISTS conversation_state (
    conversation_id TEXT NOT NULL,
    username TEXT NOT NULL,
    last_question TEXT,
    last_intent TEXT,
    last_filters JSONB DEFAULT '{}'::jsonb,
    last_entities JSONB DEFAULT '{}'::jsonb,
    last_route JSONB DEFAULT '{}'::jsonb,
    last_result_refs JSONB DEFAULT '[]'::jsonb,
    last_answer_summary TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, username)
);

CREATE INDEX IF NOT EXISTS idx_conversation_state_username_updated
ON conversation_state(username, updated_at DESC);
