CREATE TABLE IF NOT EXISTS knowledge_state_transitions (
    transition_id TEXT PRIMARY KEY,
    edge_id TEXT NOT NULL UNIQUE,
    subject_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK(relation IN ('CONFIRMS','SUPERSEDES','CONFLICTS')),
    from_assertion_id TEXT NOT NULL,
    to_assertion_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    basis_refs_json TEXT NOT NULL,
    trigger_ref TEXT,
    decision_ref TEXT,
    effective_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(edge_id) REFERENCES knowledge_lineage_edges(edge_id) ON DELETE RESTRICT,
    FOREIGN KEY(subject_id) REFERENCES knowledge_subjects(subject_id) ON DELETE RESTRICT,
    FOREIGN KEY(from_assertion_id) REFERENCES knowledge_assertions(assertion_id) ON DELETE RESTRICT,
    FOREIGN KEY(to_assertion_id) REFERENCES knowledge_assertions(assertion_id) ON DELETE RESTRICT,
    CHECK(from_assertion_id <> to_assertion_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_state_transitions_subject
    ON knowledge_state_transitions(subject_id, effective_at, recorded_at, transition_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_state_transitions_assertions
    ON knowledge_state_transitions(from_assertion_id, to_assertion_id);
