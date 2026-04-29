-- Telegram bot tables — run once in Supabase SQL Editor
-- Safe to re-run: uses IF NOT EXISTS

-- ── Users ─────────────────────────────────────────────────────────────────────
-- Maps a Telegram chat_id to an app user (hillary | dennis)
CREATE TABLE IF NOT EXISTS telegram_users (
    chat_id     TEXT PRIMARY KEY,
    username    TEXT DEFAULT '',
    person_name TEXT NOT NULL,          -- 'hillary' | 'dennis'
    registered_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Sessions ──────────────────────────────────────────────────────────────────
-- Tracks multi-step conversation flows per chat_id.
-- Cleared when a flow completes or is cancelled.
CREATE TABLE IF NOT EXISTS telegram_sessions (
    chat_id     TEXT PRIMARY KEY,
    context     TEXT NOT NULL DEFAULT '',   -- e.g. 'task_create', 'payment', 'maint_create'
    record_type TEXT DEFAULT '',            -- 'task' | 'quotation' | 'maintenance' | 'receipt' | 'balancing'
    record_id   TEXT DEFAULT '',            -- DB id of the record being acted on
    step        TEXT DEFAULT '',            -- current field being collected
    data        TEXT DEFAULT '{}',          -- JSON string of accumulated form data
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);
