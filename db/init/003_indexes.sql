-- Bloque base critica: indices para SQL directo sin LLM.
-- Seguro para ejecutar multiples veces sobre una base existente.

CREATE INDEX IF NOT EXISTS idx_movements_period_bank_filial
ON bank_movements(period, bank, filial);

CREATE INDEX IF NOT EXISTS idx_movements_period_account
ON bank_movements(period, account_number);

CREATE INDEX IF NOT EXISTS idx_movements_period_reconciled
ON bank_movements(period, reconciled);

CREATE INDEX IF NOT EXISTS idx_movements_account_date
ON bank_movements(account_number, movement_date DESC);

CREATE INDEX IF NOT EXISTS idx_movements_text_search
ON bank_movements USING GIN (
    to_tsvector('spanish', coalesce(description,'') || ' ' || coalesce(concept,'') || ' ' || coalesce(reference,''))
);

CREATE INDEX IF NOT EXISTS idx_incidents_period_rule_severity
ON incidents(period, rule_code, severity);

CREATE INDEX IF NOT EXISTS idx_incidents_period_bank_filial_account
ON incidents(period, bank, filial, account_number);

CREATE INDEX IF NOT EXISTS idx_statements_period_bank_filial_account
ON bank_statements(period, bank, filial, account_number);
