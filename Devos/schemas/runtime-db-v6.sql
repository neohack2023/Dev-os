CREATE TABLE IF NOT EXISTS mason_execution_plans (
    plan_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    envelope_id TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    base_revision TEXT NOT NULL,
    candidate_revision TEXT NOT NULL,
    change_digest TEXT NOT NULL,
    authorization_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    local_execution_authorized INTEGER NOT NULL CHECK(local_execution_authorized = 1),
    remote_write_authorized INTEGER NOT NULL DEFAULT 0 CHECK(remote_write_authorized = 0),
    FOREIGN KEY(decision_id) REFERENCES promotion_decisions(decision_id) ON DELETE RESTRICT,
    FOREIGN KEY(envelope_id) REFERENCES promotion_envelopes(envelope_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_mason_plans_decision ON mason_execution_plans(decision_id, prepared_at);
CREATE INDEX IF NOT EXISTS idx_mason_plans_candidate ON mason_execution_plans(candidate_revision);

CREATE TABLE IF NOT EXISTS mason_execution_receipts (
    receipt_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE,
    outcome TEXT NOT NULL CHECK(outcome IN ('APPLIED','FAILED')),
    base_revision TEXT NOT NULL,
    post_revision TEXT NOT NULL,
    change_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    local_authority_effect TEXT NOT NULL,
    remote_authority_effect TEXT NOT NULL DEFAULT 'NONE' CHECK(remote_authority_effect = 'NONE'),
    remote_write_performed INTEGER NOT NULL DEFAULT 0 CHECK(remote_write_performed = 0),
    FOREIGN KEY(plan_id) REFERENCES mason_execution_plans(plan_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_mason_receipts_outcome ON mason_execution_receipts(outcome, observed_at);
