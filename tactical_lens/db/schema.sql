-- Tactical Lens 结构化比赛数据库 (SQLite)
-- Phase 0 foundation — 兼容后续迁移 PostgreSQL

PRAGMA foreign_keys = ON;

-- ========== 用户与权限 ==========
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,          -- UUID
    username        TEXT NOT NULL UNIQUE,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,             -- bcrypt
    display_name    TEXT,
    role            TEXT NOT NULL DEFAULT 'analyst',
                    -- admin | coach | analyst | viewer
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS organizations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            TEXT UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 用户所属组织（多租户轻量支持）
CREATE TABLE IF NOT EXISTS org_members (
    org_id          TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'member',
                    -- owner | admin | member
    PRIMARY KEY (org_id, user_id)
);

-- ========== 球队 / 球员 ==========
CREATE TABLE IF NOT EXISTS teams (
    id              TEXT PRIMARY KEY,
    org_id          TEXT REFERENCES organizations(id),
    name            TEXT NOT NULL,
    short_name      TEXT,
    country         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS players (
    id              TEXT PRIMARY KEY,
    team_id         TEXT REFERENCES teams(id),
    name            TEXT NOT NULL,
    jersey_number   INTEGER,
    position        TEXT,                     -- GK/DF/MF/FW 或更细
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ========== 比赛主表 ==========
CREATE TABLE IF NOT EXISTS matches (
    id              TEXT PRIMARY KEY,
    org_id          TEXT REFERENCES organizations(id),
    created_by      TEXT REFERENCES users(id),
    competition     TEXT,
    season          TEXT,
    match_date      TEXT,                     -- YYYY-MM-DD
    home_team_id    TEXT REFERENCES teams(id),
    away_team_id    TEXT REFERENCES teams(id),
    home_team_name  TEXT,                     -- 冗余，便于无 teams 时展示
    away_team_name  TEXT,
    home_score      INTEGER,
    away_score      INTEGER,
    status          TEXT NOT NULL DEFAULT 'parsed',
                    -- uploaded | parsed | analyzed | reported
    source_type     TEXT,                     -- fifa_pdf | statsbomb | excel | csv | xml | mixed | annotator
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_matches_org ON matches(org_id);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);

-- ========== 统一事件流 ==========
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    match_id        TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    period          INTEGER,                  -- 1 / 2 / 3(ET1) / 4(ET2)
    minute          INTEGER,
    second          INTEGER,
    timestamp_sec   REAL,                     -- 便于与视频对齐
    team_id         TEXT REFERENCES teams(id),
    team_name       TEXT,
    player_id       TEXT REFERENCES players(id),
    player_name     TEXT,
    event_type      TEXT NOT NULL,            -- shot | pass | tackle | pressure | ...
    subtype         TEXT,
    outcome         TEXT,                     -- success | fail | goal | saved | ...
    x               REAL,                     -- 0-100 标准化
    y               REAL,
    end_x           REAL,
    end_y           REAL,
    xg              REAL,
    xa              REAL,
    raw_payload     TEXT,                     -- JSON 字符串
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(match_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(match_id, timestamp_sec);

-- ========== 比赛球队汇总统计 ==========
CREATE TABLE IF NOT EXISTS match_team_stats (
    match_id            TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id             TEXT,
    team_name           TEXT NOT NULL,
    is_home             INTEGER,              -- 1 home / 0 away
    formation           TEXT,
    possession_pct      REAL,
    pass_accuracy       REAL,
    passes_total        INTEGER,
    passes_completed    INTEGER,
    shots_total         INTEGER,
    shots_on_target     INTEGER,
    goals               INTEGER,
    xg                  REAL,
    xga                 REAL,
    key_passes          INTEGER,
    progressive_passes  INTEGER,
    corners             INTEGER,
    fouls               INTEGER,
    yellow_cards        INTEGER,
    red_cards           INTEGER,
    ppda                REAL,
    extra_json          TEXT,                 -- 扩展指标 JSON
    PRIMARY KEY (match_id, team_name)
);

-- ========== 上传与解析记录 ==========
CREATE TABLE IF NOT EXISTS uploads (
    id                  TEXT PRIMARY KEY,
    org_id              TEXT REFERENCES organizations(id),
    user_id             TEXT REFERENCES users(id),
    original_filename   TEXT NOT NULL,
    mime_type           TEXT,
    size_bytes          INTEGER,
    storage_path        TEXT,                 -- 本地相对路径或对象存储 key
    parse_status        TEXT NOT NULL DEFAULT 'pending',
                        -- pending | parsing | success | failed
    parse_log           TEXT,
    detected_format     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS match_sources (
    match_id        TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    upload_id       TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    source_role     TEXT DEFAULT 'primary',   -- primary | supplement
    PRIMARY KEY (match_id, upload_id)
);

-- ========== 洞察与报告 ==========
CREATE TABLE IF NOT EXISTS insights (
    id              TEXT PRIMARY KEY,
    match_id        TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    category        TEXT,                     -- 进攻 | 防守 | 转换 | 定位球 | 体能 | 心态
    priority        INTEGER DEFAULT 3,        -- 1 关键 2 重要 3 观察
    title           TEXT,
    body            TEXT NOT NULL,            -- 现象 + 含义（中文激励风格）
    suggestion      TEXT,                     -- 可执行建议
    training_key    TEXT,
    evidence_json   TEXT,                     -- 证据数字/事件引用
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_insights_match ON insights(match_id);

CREATE TABLE IF NOT EXISTS reports (
    id              TEXT PRIMARY KEY,
    match_id        TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    created_by      TEXT REFERENCES users(id),
    template        TEXT DEFAULT 'emotion',   -- emotion | coach | concise | default
    format          TEXT DEFAULT 'html',      -- html | pdf | txt | md
    title           TEXT,
    summary         TEXT,
    content_path    TEXT,
    content_text    TEXT,                     -- 短报告可直接存
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ========== 会话（轻量登录，无独立 Redis） ==========
CREATE TABLE IF NOT EXISTS sessions (
    token           TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
