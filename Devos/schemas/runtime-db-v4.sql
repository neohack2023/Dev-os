CREATE TABLE IF NOT EXISTS learning_procedures (
    procedure_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS procedure_reflections (
    procedure_id TEXT NOT NULL,
    reflection_id TEXT NOT NULL,
    PRIMARY KEY(procedure_id, reflection_id),
    FOREIGN KEY(procedure_id) REFERENCES learning_procedures(procedure_id) ON DELETE CASCADE,
    FOREIGN KEY(reflection_id) REFERENCES reflection_candidates(reflection_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS learning_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluation_procedures (
    evaluation_id TEXT PRIMARY KEY,
    procedure_id TEXT NOT NULL,
    FOREIGN KEY(evaluation_id) REFERENCES learning_evaluations(evaluation_id) ON DELETE CASCADE,
    FOREIGN KEY(procedure_id) REFERENCES learning_procedures(procedure_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS learning_experiences (
    memory_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experience_reflections (
    memory_id TEXT NOT NULL,
    reflection_id TEXT NOT NULL,
    PRIMARY KEY(memory_id, reflection_id),
    FOREIGN KEY(memory_id) REFERENCES learning_experiences(memory_id) ON DELETE CASCADE,
    FOREIGN KEY(reflection_id) REFERENCES reflection_candidates(reflection_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS learning_capabilities (
    capability_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS learning_capability_events (
    event_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    predecessor_event_id TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    UNIQUE(capability_id, event_sequence),
    FOREIGN KEY(capability_id) REFERENCES learning_capabilities(capability_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_learning_events_capability ON learning_capability_events(capability_id,event_sequence);
