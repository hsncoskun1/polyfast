-- Migration 003: Discovery checkpoints table
-- Stores discovery scan results for tracking and recovery.

CREATE TABLE IF NOT EXISTS discovery_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_data_json TEXT NOT NULL,
    total_scanned INTEGER NOT NULL DEFAULT 0,
    total_matched INTEGER NOT NULL DEFAULT 0,
    parse_failures INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    scanned_at TEXT NOT NULL DEFAULT (datetime('now'))
);
