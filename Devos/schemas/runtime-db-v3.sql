CREATE TABLE IF NOT EXISTS reflection_candidates (
    reflection_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    branch_key TEXT NOT NULL,
    claim_key TEXT NOT NULL,
    mechanism_hypothesis TEXT NOT NULL,
    required_disconfirmation_test TEXT NOT NULL,
    authority_effect TEXT NOT NULL CHECK(authority_effect = 'NONE'),
    promotion_state TEXT NOT NULL CHECK(promotion_state = 'CANDIDATE_ONLY'),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reflection_identity
    ON reflection_candidates(source_kind, source_id, reflection_id);
CREATE INDEX IF NOT EXISTS idx_reflection_branch_claim
    ON reflection_candidates(branch_key, claim_key, created_at);
