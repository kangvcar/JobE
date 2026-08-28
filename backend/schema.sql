-- PostgreSQL 承载原始快照、职位、证据、变更流水与用户数据。
-- 图谱本身在 Neo4j（见 ADR 0002），这里只存图谱之外的东西。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sources (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    license              TEXT NOT NULL,
    requires_login       BOOLEAN NOT NULL DEFAULT FALSE,
    is_leading_indicator BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS snapshots (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources (id),
    fetched_at   TIMESTAMPTZ NOT NULL,
    url          TEXT,
    content_hash TEXT NOT NULL,
    payload      JSONB NOT NULL,
    UNIQUE (source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS snapshots_source_fetched_idx ON snapshots (source_id, fetched_at);

CREATE TABLE IF NOT EXISTS postings (
    id               TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL REFERENCES sources (id),
    snapshot_id      TEXT NOT NULL REFERENCES snapshots (id),
    title            TEXT NOT NULL,
    title_normalized TEXT,
    company          TEXT,
    city             TEXT,
    published_at     DATE,
    updated_at       DATE,
    period           TEXT,
    description      TEXT,
    occupation_code  TEXT,
    salary_min       INTEGER,
    salary_max       INTEGER,
    duplicate_of     TEXT REFERENCES postings (id),
    simhash          BIGINT,
    boilerplate_spans JSONB NOT NULL DEFAULT '[]'
);

-- 近重复判定走 归一化标题 + 公司 + 城市 + 滚动时间窗
CREATE INDEX IF NOT EXISTS postings_dedup_idx ON postings (title_normalized, company, city, published_at);
CREATE INDEX IF NOT EXISTS postings_period_idx ON postings (period) WHERE duplicate_of IS NULL;

CREATE TABLE IF NOT EXISTS documents (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    canonical_text TEXT NOT NULL,
    char_index     JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES sources (id),
    posting_id  TEXT REFERENCES postings (id),
    doc_id      TEXT,
    span_start  INTEGER NOT NULL,
    span_end    INTEGER NOT NULL,
    page_index  INTEGER,
    bbox        JSONB,
    quote       TEXT NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    extractor   TEXT NOT NULL,
    confidence  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS evidence_posting_idx ON evidence (posting_id);

-- 变更流水。所有自动发布都进这里，可回滚。
CREATE TABLE IF NOT EXISTS change_log (
    id            TEXT PRIMARY KEY,
    entity_kind   TEXT NOT NULL,
    entity_id     TEXT NOT NULL,
    kind          TEXT NOT NULL,
    before        JSONB,
    after         JSONB,
    reason        TEXT NOT NULL,
    evidence_ids  JSONB NOT NULL DEFAULT '[]',
    occurred_on   DATE NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    state         TEXT NOT NULL,
    reviewed_by   TEXT,
    rolled_back   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS change_log_entity_idx ON change_log (entity_kind, entity_id, occurred_on);
CREATE INDEX IF NOT EXISTS change_log_state_idx ON change_log (state);

-- role_id 空串表示"跨岗位的全局观测"。主键不允许 NULL，所以用空串而非 NULL 作哨兵；
-- 领域模型里它是 role_id: str | None，两侧的转换只在 storage/observations.py 里发生。
CREATE TABLE IF NOT EXISTS skill_observations (
    skill_id         TEXT NOT NULL,
    role_id          TEXT NOT NULL DEFAULT '',
    period           TEXT NOT NULL,
    weight           REAL NOT NULL,
    posting_count    INTEGER NOT NULL,
    total_postings   INTEGER NOT NULL,
    ontology_version TEXT NOT NULL,
    PRIMARY KEY (skill_id, role_id, period, ontology_version)
);

-- 技能点向量用于别名归一的召回，不用独立向量库（规模不需要）
CREATE TABLE IF NOT EXISTS skill_vectors (
    skill_id         TEXT PRIMARY KEY,
    ontology_version TEXT NOT NULL,
    embedding        vector(1024)
);

-- 别名裁决结果持久化，同一别名对只裁决一次
CREATE TABLE IF NOT EXISTS alias_decisions (
    surface_form TEXT PRIMARY KEY,
    skill_id     TEXT,
    decided_by   TEXT NOT NULL,
    confidence   REAL NOT NULL,
    decided_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 学习资源。URL 必须来自真实检索结果，大模型只能从候选里挑，不能发明链接。
-- checked_at 为空或过期的资源要重新探活，探活失败即下线。
CREATE TABLE IF NOT EXISTS learning_resources (
    skill_id   TEXT NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    kind       TEXT NOT NULL,
    source     TEXT NOT NULL,
    checked_at TIMESTAMPTZ,
    PRIMARY KEY (skill_id, url)
);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE,
    password_hash TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS skill_profiles (
    id            TEXT PRIMARY KEY,
    user_id       TEXT REFERENCES users (id),
    resume_doc_id TEXT REFERENCES documents (id),
    skills        JSONB NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
