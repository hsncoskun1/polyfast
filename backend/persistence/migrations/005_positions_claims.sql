-- Migration 005: Position + Claim persistence for 7/24 recovery
-- Restart sonrasi acik pozisyonlar ve pending claim/redeem restore edilir.

CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    side TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending_open',
    created_at TEXT NOT NULL,

    -- Entry authoritative
    requested_amount_usd REAL NOT NULL DEFAULT 0.0,
    fill_price REAL NOT NULL DEFAULT 0.0,
    gross_fill_shares REAL NOT NULL DEFAULT 0.0,
    entry_fee_shares REAL NOT NULL DEFAULT 0.0,
    net_position_shares REAL NOT NULL DEFAULT 0.0,
    fee_rate REAL NOT NULL DEFAULT 0.0,
    opened_at TEXT,

    -- Close authoritative
    exit_fill_price REAL NOT NULL DEFAULT 0.0,
    exit_gross_usdc REAL NOT NULL DEFAULT 0.0,
    actual_exit_fee_usdc REAL NOT NULL DEFAULT 0.0,
    net_exit_usdc REAL NOT NULL DEFAULT 0.0,
    net_realized_pnl REAL NOT NULL DEFAULT 0.0,
    close_reason TEXT,
    close_trigger_set TEXT NOT NULL DEFAULT '[]',
    close_triggered_at TEXT,
    close_requested_price REAL NOT NULL DEFAULT 0.0,
    closed_at TEXT,

    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_positions_state ON positions(state);
CREATE INDEX IF NOT EXISTS idx_positions_condition ON positions(condition_id);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    condition_id TEXT NOT NULL,
    position_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT '',
    claim_status TEXT NOT NULL DEFAULT 'pending',
    outcome TEXT NOT NULL DEFAULT 'pending',
    claimed_amount_usdc REAL NOT NULL DEFAULT 0.0,
    claimed_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,

    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(claim_status);
CREATE INDEX IF NOT EXISTS idx_claims_position ON claims(position_id);
