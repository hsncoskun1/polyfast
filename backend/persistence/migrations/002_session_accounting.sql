-- Migration 002: Session accounting table
-- Stores session accounting snapshots for startup bootstrap and recovery.

CREATE TABLE IF NOT EXISTS session_accounting (
    session_id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
