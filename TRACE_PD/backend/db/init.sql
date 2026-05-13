-- ============================================================
--  TRACE_PD – PostgreSQL Initialisation
--  Runs once on first `docker compose up`
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Users ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT UNIQUE NOT NULL,
    username    TEXT NOT NULL,
    hashed_pw   TEXT NOT NULL,
    timezone    TEXT DEFAULT 'UTC',
    consent     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Activity Logs ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activity_type   TEXT NOT NULL,
    duration        INT NOT NULL,
    mood            INT CHECK (mood BETWEEN 1 AND 10),
    focus_score     INT CHECK (focus_score BETWEEN 0 AND 100),
    notes           TEXT,
    details         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trcpd_logs_user_time ON logs(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trcpd_logs_type      ON logs(user_id, activity_type);

-- ── Behavior Loops ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS loops (
    id              SERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    trigger_desc    TEXT NOT NULL,
    trigger_time    TEXT,
    action_desc     TEXT NOT NULL,
    outcome_desc    TEXT NOT NULL,
    confidence      FLOAT NOT NULL DEFAULT 0.0,
    occurrences     INT  NOT NULL DEFAULT 1,
    status          TEXT DEFAULT 'active',
    causal_estimate TEXT,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trcpd_loops_user ON loops(user_id);

-- ── Fix Suggestions ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS fixes (
    id          SERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    loop_id     INT  REFERENCES loops(id) ON DELETE CASCADE,
    suggestion  TEXT NOT NULL,
    effort      TEXT DEFAULT 'Medium',
    impact      TEXT DEFAULT 'Medium',
    applied     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Breakpoints ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS breakpoints (
    id              SERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    condition_type  TEXT NOT NULL,
    threshold       FLOAT NOT NULL,
    action_msg      TEXT,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Chat History ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    tokens_used INT  DEFAULT 0,
    model_used  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Vector Embeddings (pgvector) ─────────────────────────
CREATE TABLE IF NOT EXISTS vectors (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id   BIGINT,
    embedding   vector(1536),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ════════════════════════════════════════════════════════
--  Seed demo data
-- ════════════════════════════════════════════════════════

-- Demo user  (password: demo1234)
INSERT INTO users (id, email, username, hashed_pw, timezone, consent)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'demo@trace.dev',
    'demo',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'UTC',
    TRUE
) ON CONFLICT DO NOTHING;

-- Activity logs (last 7 days)
INSERT INTO logs (user_id, timestamp, activity_type, duration, mood, focus_score, notes) VALUES
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '6 days 14 hours', 'deep_work', 90,  8, 88, 'ML model training'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '6 days 12 hours', 'phone',     35,  5, NULL,'Instagram, news'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '5 days 14 hours', 'deep_work', 120, 9, 92, 'FastAPI endpoint design'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '5 days 15 hours', 'break',     15,  7, NULL,'Coffee walk'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '4 days 8 hours',  'exercise',  30,  9, NULL,'Running 5k'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '4 days 21 hours', 'sleep',     480, 7, NULL,'8 hrs, 2 wake events'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '3 days 15 hours', 'phone',     65,  4, NULL,'Post-lunch YouTube'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '3 days 9 hours',  'deep_work', 60,  7, 74, 'LangGraph agent design'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '2 days 15 hours', 'phone',     40,  5, NULL,'3PM energy dip scroll'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '1 day  9 hours',  'deep_work', 90,  8, 85, 'React dashboard build'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '1 day  21 hours', 'sleep',     450, 6, NULL,'7.5 hrs'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '6 hours',         'deep_work', 60,  8, 72, 'Docker config'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '2 hours',         'break',     10,  8, NULL,'10-min walk'),
('a0000000-0000-0000-0000-000000000001', NOW() - INTERVAL '1 hour',          'phone',     30,  5, NULL,'3PM dip scroll')
ON CONFLICT DO NOTHING;

-- Behavior loops
INSERT INTO loops (user_id, trigger_desc, trigger_time, action_desc, outcome_desc, confidence, occurrences, status, causal_estimate)
VALUES
('a0000000-0000-0000-0000-000000000001',
 'Energy dip detected', '3:00 PM', 'Phone usage (30+ mins)', 'Low focus score (<50)',
 0.87, 12, 'active',
 'DoWhy back-door adjustment: phone usage mediates 73% of focus drop (p=0.002). IsolationForest flagged 12 anomalous sessions.'),
('a0000000-0000-0000-0000-000000000001',
 'Heavy meal + no movement', 'Post-lunch', 'Unplanned YouTube (45+ mins)', 'Missed deep work block',
 0.71, 8, 'active',
 'IsolationForest anomaly on 8 days. CATE estimate: removing phone post-lunch recovers 1.4 hrs productive time (EconML, 74% CI).'),
('a0000000-0000-0000-0000-000000000001',
 'Screen exposure after 10 PM', '11:00 PM', 'Late-night scrolling (1+ hr)', 'Poor sleep quality',
 0.94, 21, 'resolved',
 'DoWhy IV: screen exposure explains 81% of sleep variance (p<0.001). Resolved via app-blocker fix.')
ON CONFLICT DO NOTHING;

-- Fixes for loop 1
INSERT INTO fixes (user_id, loop_id, suggestion, effort, impact)
SELECT 'a0000000-0000-0000-0000-000000000001', id, 'Replace phone with 10-min walk at 2:50 PM', 'Low', 'High'
FROM loops WHERE trigger_time = '3:00 PM' AND user_id = 'a0000000-0000-0000-0000-000000000001' LIMIT 1;

INSERT INTO fixes (user_id, loop_id, suggestion, effort, impact)
SELECT 'a0000000-0000-0000-0000-000000000001', id, 'Schedule protein-rich snack at 2:45 PM', 'Low', 'Medium'
FROM loops WHERE trigger_time = '3:00 PM' AND user_id = 'a0000000-0000-0000-0000-000000000001' LIMIT 1;

-- Fixes for loop 2
INSERT INTO fixes (user_id, loop_id, suggestion, effort, impact)
SELECT 'a0000000-0000-0000-0000-000000000001', id, '5-min walk after every lunch', 'Low', 'High'
FROM loops WHERE trigger_time = 'Post-lunch' AND user_id = 'a0000000-0000-0000-0000-000000000001' LIMIT 1;

-- Breakpoint
INSERT INTO breakpoints (user_id, name, condition_type, threshold, action_msg)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'Focus Drop Alert', 'focus_drop', 60,
    'Your focus score dropped below 60. Take a 10-min walk!'
) ON CONFLICT DO NOTHING;
