CREATE TABLE IF NOT EXISTS knowledge_subjects (
    subject_id TEXT PRIMARY KEY,
    scope_key TEXT NOT NULL,
    knowledge_key TEXT NOT NULL,
    knowledge_kind TEXT NOT NULL CHECK(knowledge_kind IN ('episodic','semantic','procedural','negative')),
    created_at TEXT NOT NULL,
    UNIQUE(scope_key, knowledge_key)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_subjects_scope ON knowledge_subjects(scope_key, knowledge_key);

CREATE TABLE IF NOT EXISTS knowledge_assertions (
    assertion_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    claim_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    effective_at TEXT,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(subject_id) REFERENCES knowledge_subjects(subject_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_knowledge_assertions_subject ON knowledge_assertions(subject_id, recorded_at, assertion_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_assertions_claim ON knowledge_assertions(subject_id, claim_hash);

CREATE TABLE IF NOT EXISTS knowledge_lineage_edges (
    edge_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK(relation IN ('CONFIRMS','SUPERSEDES','CONFLICTS')),
    from_assertion_id TEXT NOT NULL,
    to_assertion_id TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(subject_id) REFERENCES knowledge_subjects(subject_id) ON DELETE RESTRICT,
    FOREIGN KEY(from_assertion_id) REFERENCES knowledge_assertions(assertion_id) ON DELETE RESTRICT,
    FOREIGN KEY(to_assertion_id) REFERENCES knowledge_assertions(assertion_id) ON DELETE RESTRICT,
    CHECK(from_assertion_id <> to_assertion_id),
    UNIQUE(relation, from_assertion_id, to_assertion_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_lineage_subject ON knowledge_lineage_edges(subject_id, relation, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_lineage_to ON knowledge_lineage_edges(to_assertion_id, relation);
