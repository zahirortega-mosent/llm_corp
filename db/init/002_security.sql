CREATE TABLE IF NOT EXISTS app_users (
    user_pk BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT,
    email TEXT,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    web_access_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    role_pk BIGSERIAL PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE,
    description TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_pk BIGSERIAL PRIMARY KEY,
    permission_code TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_pk BIGINT NOT NULL REFERENCES app_users(user_pk) ON DELETE CASCADE,
    role_pk BIGINT NOT NULL REFERENCES roles(role_pk) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_pk, role_pk)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_pk BIGINT NOT NULL REFERENCES roles(role_pk) ON DELETE CASCADE,
    permission_pk BIGINT NOT NULL REFERENCES permissions(permission_pk) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role_pk, permission_pk)
);

CREATE TABLE IF NOT EXISTS role_table_access (
    role_pk BIGINT NOT NULL REFERENCES roles(role_pk) ON DELETE CASCADE,
    table_name TEXT NOT NULL,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role_pk, table_name)
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value JSONB NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS policy_audit (
    policy_audit_pk BIGSERIAL PRIMARY KEY,
    policy_type TEXT NOT NULL,
    action TEXT NOT NULL,
    payload JSONB,
    requested_by TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS host_command_queue (
    command_pk BIGSERIAL PRIMARY KEY,
    command_type TEXT NOT NULL,
    command_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_by TEXT,
    result_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMP NULL,
    executor_host TEXT NULL
);

CREATE TABLE IF NOT EXISTS web_search_audit (
    web_search_audit_pk BIGSERIAL PRIMARY KEY,
    username TEXT,
    original_question TEXT NOT NULL,
    sanitized_query TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO permissions(permission_code, description)
VALUES
    ('view_summary', 'Puede consultar resumen ejecutivo'),
    ('view_movements', 'Puede consultar movimientos'),
    ('view_incidents', 'Puede consultar incidencias'),
    ('view_knowledge', 'Puede consultar conocimiento indexado'),
    ('view_rules', 'Puede consultar reglas de negocio'),
    ('ask_internal', 'Puede preguntar solo sobre datos internos'),
    ('ask_hybrid', 'Puede usar comparacion controlada con conceptos externos'),
    ('manage_users', 'Puede crear y administrar usuarios'),
    ('manage_roles', 'Puede crear y administrar roles'),
    ('manage_policies', 'Puede cambiar politicas globales'),
    ('host_network_control', 'Puede enviar comandos de red al host')
ON CONFLICT (permission_code) DO NOTHING;

INSERT INTO roles(role_name, description, is_system)
VALUES
    ('admin', 'Administracion total del stack seguro', TRUE),
    ('analyst', 'Analista con acceso operativo y chat protegido', TRUE),
    ('auditor', 'Acceso de consulta y comparacion controlada', TRUE),
    ('viewer', 'Solo lectura resumida', TRUE)
ON CONFLICT (role_name) DO NOTHING;
