CREATE TABLE IF NOT EXISTS github_authority_plans (
    plan_id TEXT PRIMARY KEY,
    mason_receipt_id TEXT NOT NULL,
    mason_plan_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    candidate_branch TEXT NOT NULL,
    base_revision TEXT NOT NULL,
    candidate_revision TEXT NOT NULL,
    change_digest TEXT NOT NULL,
    authorization_digest TEXT NOT NULL,
    policy_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    remote_write_authorized INTEGER NOT NULL CHECK(remote_write_authorized = 1),
    FOREIGN KEY(mason_receipt_id) REFERENCES mason_execution_receipts(receipt_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_github_authority_plans_candidate ON github_authority_plans(repository, target_branch, candidate_revision);

CREATE TABLE IF NOT EXISTS github_authority_prs (
    pr_binding_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE,
    pr_number INTEGER NOT NULL,
    head_revision TEXT NOT NULL,
    base_branch TEXT NOT NULL,
    html_url TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES github_authority_plans(plan_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_github_authority_pr_number ON github_authority_prs(plan_id, pr_number);

CREATE TABLE IF NOT EXISTS github_authority_receipts (
    receipt_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE,
    pr_number INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('MERGED','FAILED')),
    candidate_revision TEXT NOT NULL,
    authoritative_revision TEXT NOT NULL,
    policy_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    remote_authority_effect TEXT NOT NULL,
    remote_write_performed INTEGER NOT NULL CHECK(remote_write_performed IN (0,1)),
    FOREIGN KEY(plan_id) REFERENCES github_authority_plans(plan_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_github_authority_receipts_revision ON github_authority_receipts(authoritative_revision, observed_at);
