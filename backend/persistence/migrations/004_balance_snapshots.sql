-- Migration 004: Balance snapshots table
-- Stores balance fetch history for session accounting and recovery.

CREATE TABLE IF NOT EXISTS balance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_balance REAL NOT NULL,
    available_balance REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
