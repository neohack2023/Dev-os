CREATE TABLE IF NOT EXISTS evidence_roots (
    root_id TEXT PRIMARY KEY,
    root_kind TEXT NOT NULL,
    observation_question TEXT NOT NULL,
    input_identity TEXT NOT NULL DEFAULT '',
    execution_identity TEXT NOT NULL DEFAULT '',
    source_revision TEXT NOT NULL DEFAULT '',
    environment_identity TEXT NOT NULL DEFAULT '',
    provenance_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS atomic_findings (
    finding_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    branch_key TEXT NOT NULL,
    claim_key TEXT NOT NULL,
    value_text TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    root_ids_json TEXT NOT NULL,
    lineage_state TEXT NOT NULL,
    shared_input_keys_json TEXT NOT NULL,
    related_claim_keys_json TEXT NOT NULL,
    supersedes_claim_id TEXT,
    created_at TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS finding_roots (
    finding_id TEXT NOT NULL,
    root_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(finding_id, root_id),
    FOREIGN KEY(finding_id) REFERENCES atomic_findings(finding_id) ON DELETE CASCADE,
    FOREIGN KEY(root_id) REFERENCES evidence_roots(root_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS finding_assessments (
    assessment_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    cross_reference TEXT NOT NULL,
    current_claim_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES atomic_findings(finding_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS triangulation_batches (
    batch_id TEXT PRIMARY KEY,
    claim_key TEXT NOT NULL,
    state TEXT NOT NULL,
    root_summary_json TEXT NOT NULL,
    supporting_root_ids_json TEXT NOT NULL,
    contradicting_root_ids_json TEXT NOT NULL,
    notes_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_delta_packets (
    delta_id TEXT PRIMARY KEY,
    claim_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_roots_kind ON evidence_roots(root_kind);
CREATE INDEX IF NOT EXISTS idx_findings_branch_claim ON atomic_findings(branch_key, claim_key);
CREATE INDEX IF NOT EXISTS idx_findings_episode ON atomic_findings(episode_id);
CREATE INDEX IF NOT EXISTS idx_assessments_finding ON finding_assessments(finding_id);
CREATE INDEX IF NOT EXISTS idx_tri_claim ON triangulation_batches(claim_key);
CREATE INDEX IF NOT EXISTS idx_delta_claim ON evidence_delta_packets(claim_key);
