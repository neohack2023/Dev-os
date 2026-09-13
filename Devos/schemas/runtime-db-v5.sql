CREATE TABLE IF NOT EXISTS promotion_envelopes (
    envelope_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL,
    branch_scope TEXT NOT NULL,
    candidate_revision TEXT NOT NULL,
    change_digest TEXT NOT NULL,
    stone_state TEXT NOT NULL,
    mason_state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    authority_effect TEXT NOT NULL DEFAULT 'NONE',
    write_authorized INTEGER NOT NULL DEFAULT 0 CHECK(write_authorized = 0),
    FOREIGN KEY(capability_id) REFERENCES learning_capabilities(capability_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_promotion_envelopes_branch ON promotion_envelopes(branch_scope, observed_at);
CREATE INDEX IF NOT EXISTS idx_promotion_envelopes_revision ON promotion_envelopes(candidate_revision);

CREATE TABLE IF NOT EXISTS promotion_decisions (
    decision_id TEXT PRIMARY KEY,
    envelope_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('PROMOTE','REVISE','ROLLBACK','NO_OP')),
    candidate_revision TEXT NOT NULL,
    verifier_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    authority_effect TEXT NOT NULL DEFAULT 'NONE',
    write_authorized INTEGER NOT NULL DEFAULT 0 CHECK(write_authorized = 0),
    FOREIGN KEY(envelope_id) REFERENCES promotion_envelopes(envelope_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_promotion_decisions_envelope ON promotion_decisions(envelope_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_promotion_decisions_outcome ON promotion_decisions(outcome, observed_at);
