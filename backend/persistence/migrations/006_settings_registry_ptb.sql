-- Migration 006: Settings + Registry + PTB persistence for 7/24 recovery
-- Restart sonrasi coin ayarlari, event state ve PTB cache restore edilir.

CREATE TABLE IF NOT EXISTS coin_settings (
    coin TEXT PRIMARY KEY,
    coin_enabled INTEGER NOT NULL DEFAULT 0,
    side_mode TEXT NOT NULL DEFAULT 'dominant_only',
    delta_threshold REAL NOT NULL DEFAULT 50.0,
    price_min INTEGER NOT NULL DEFAULT 51,
    price_max INTEGER NOT NULL DEFAULT 85,
    spread_max REAL NOT NULL DEFAULT 3.0,
    time_min INTEGER NOT NULL DEFAULT 30,
    time_max INTEGER NOT NULL DEFAULT 270,
    event_max INTEGER NOT NULL DEFAULT 1,
    order_amount REAL NOT NULL DEFAULT 5.0,
    reactivate_on_return INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS registry_records (
    condition_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    slug TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'discovered',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status_changed_at TEXT NOT NULL,
    end_date TEXT,
    has_open_position INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_registry_status ON registry_records(status);
CREATE INDEX IF NOT EXISTS idx_registry_asset ON registry_records(asset);

CREATE TABLE IF NOT EXISTS ptb_cache (
    condition_id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    ptb_value REAL,
    status TEXT NOT NULL DEFAULT 'waiting',
    source_name TEXT NOT NULL DEFAULT '',
    acquired_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
