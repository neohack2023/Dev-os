CREATE TABLE IF NOT EXISTS github_policy_audits (
    audit_id TEXT PRIMARY KEY,
    repository TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    capability TEXT NOT NULL CHECK(capability IN ('RULESET','BRANCH_PROTECTION','UNPROTECTED','UNKNOWN')),
    compliance_state TEXT NOT NULL CHECK(compliance_state IN ('COMPLIANT','NONCOMPLIANT','UNVERIFIABLE')),
    policy_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_github_policy_audits_target ON github_policy_audits(repository,target_branch,observed_at);

CREATE TABLE IF NOT EXISTS github_policy_receipts (
    receipt_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('AUDIT_ONLY','APPLY_AND_VERIFY')),
    outcome TEXT NOT NULL CHECK(outcome IN ('COMPLIANT','APPLIED','BLOCKED','FAILED')),
    repository TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    before_digest TEXT NOT NULL,
    after_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    administrative_write_performed INTEGER NOT NULL CHECK(administrative_write_performed IN (0,1)),
    FOREIGN KEY(audit_id) REFERENCES github_policy_audits(audit_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_github_policy_receipts_target ON github_policy_receipts(repository,target_branch,observed_at);
