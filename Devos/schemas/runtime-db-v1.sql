PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    signature TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS build_manifest (
    source_path TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    UNIQUE(path, section)
);
CREATE TABLE IF NOT EXISTS branch_state (
    branch_key TEXT PRIMARY KEY,
    scope_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    surfaces_json TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devos_tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    task_type TEXT NOT NULL,
    owner_role TEXT NOT NULL,
    assigned_agent TEXT,
    objective TEXT NOT NULL,
    transfer_canary INTEGER NOT NULL,
    tracking_json TEXT NOT NULL,
    acceptance_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_branches (
    task_id TEXT NOT NULL,
    branch_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(task_id, branch_key),
    FOREIGN KEY(task_id) REFERENCES devos_tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(branch_key) REFERENCES branch_state(branch_key) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY(task_id, depends_on_task_id),
    FOREIGN KEY(task_id) REFERENCES devos_tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(depends_on_task_id) REFERENCES devos_tasks(task_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_key TEXT PRIMARY KEY,
    repository TEXT NOT NULL DEFAULT '',
    verified_revision TEXT NOT NULL DEFAULT '',
    maturity TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    row_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_kv (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS idx_branch_status ON branch_state(status);
CREATE INDEX IF NOT EXISTS idx_tasks_ready ON devos_tasks(status, priority, task_id);
CREATE INDEX IF NOT EXISTS idx_task_branches_branch ON task_branches(branch_key, task_id);
