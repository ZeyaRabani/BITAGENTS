-- BIT Agents DCA - Neon PostgreSQL schema
-- Applied automatically on startup via db.init_db()

CREATE TABLE IF NOT EXISTS dca_plans (
    id                  VARCHAR(16) PRIMARY KEY,
    user_wallet         VARCHAR(64),
    name                TEXT NOT NULL,
    input_token         VARCHAR(32) NOT NULL,
    output_token        VARCHAR(32) NOT NULL,
    input_mint          VARCHAR(64) NOT NULL,
    output_mint         VARCHAR(64) NOT NULL,
    amount_per_buy      DOUBLE PRECISION NOT NULL,
    interval_label      TEXT NOT NULL,
    interval_minutes    DOUBLE PRECISION NOT NULL,
    total_budget        DOUBLE PRECISION,
    spent_so_far        DOUBLE PRECISION NOT NULL DEFAULT 0,
    max_executions      INTEGER,
    executions_count    INTEGER NOT NULL DEFAULT 0,
    slippage_bps        INTEGER NOT NULL DEFAULT 100,
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_execution_at   TIMESTAMPTZ,
    executions          JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dca_plans_user_wallet ON dca_plans (user_wallet);
CREATE INDEX IF NOT EXISTS idx_dca_plans_status ON dca_plans (status);
CREATE INDEX IF NOT EXISTS idx_dca_plans_next_execution ON dca_plans (next_execution_at)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS user_ledger (
    id              VARCHAR(16) PRIMARY KEY,
    user_wallet     VARCHAR(64) NOT NULL,
    agent_wallet    VARCHAR(64),
    signature       VARCHAR(128),
    token           VARCHAR(32) NOT NULL,
    mint            VARCHAR(64) NOT NULL,
    amount          DOUBLE PRECISION NOT NULL,
    direction       VARCHAR(10) NOT NULL DEFAULT 'deposit',
    reference_type  VARCHAR(32),
    reference_id    VARCHAR(128),
    status          VARCHAR(20) NOT NULL DEFAULT 'confirmed',
    verified_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    explorer_url    TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_ledger_user_wallet ON user_ledger (user_wallet);
CREATE INDEX IF NOT EXISTS idx_user_ledger_signature ON user_ledger (signature);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_ledger_deposit_sig
    ON user_ledger (signature, token, direction)
    WHERE direction = 'deposit' AND signature IS NOT NULL;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id              UUID PRIMARY KEY,
    user_wallet     VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_wallet ON chat_sessions (user_wallet);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL,
    content         TEXT NOT NULL,
    actions         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id, created_at);

CREATE TABLE IF NOT EXISTS wallet_auth_challenges (
    nonce           VARCHAR(64) PRIMARY KEY,
    user_wallet     VARCHAR(64) NOT NULL,
    message         TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    used            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wallet_auth_challenges_wallet ON wallet_auth_challenges (user_wallet);

CREATE TABLE IF NOT EXISTS wallet_sessions (
    token_hash      VARCHAR(64) PRIMARY KEY,
    user_wallet     VARCHAR(64) NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wallet_sessions_wallet ON wallet_sessions (user_wallet);
CREATE INDEX IF NOT EXISTS idx_wallet_sessions_expires ON wallet_sessions (expires_at);

CREATE TABLE IF NOT EXISTS user_agents (
    id              VARCHAR(36) PRIMARY KEY,
    owner_wallet    VARCHAR(64) NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    system_prompt   TEXT NOT NULL,
    model           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_agents_owner_wallet ON user_agents (owner_wallet);

CREATE TABLE IF NOT EXISTS dca_platform_metrics (
    id                  VARCHAR(32) PRIMARY KEY DEFAULT 'global',
    total_plans         INTEGER NOT NULL DEFAULT 0,
    active_plans        INTEGER NOT NULL DEFAULT 0,
    total_users         INTEGER NOT NULL DEFAULT 0,
    total_executions    INTEGER NOT NULL DEFAULT 0,
    successful_swaps    INTEGER NOT NULL DEFAULT 0,
    failed_swaps        INTEGER NOT NULL DEFAULT 0,
    total_volume_sol    DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_deposits      INTEGER NOT NULL DEFAULT 0,
    total_withdrawals   INTEGER NOT NULL DEFAULT 0,
    executions_24h      INTEGER NOT NULL DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
