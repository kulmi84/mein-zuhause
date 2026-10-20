CREATE TABLE IF NOT EXISTS snapshot (
  id INTEGER PRIMARY KEY CHECK(id = 1),
  entities_json TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','claimed','done','failed')),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS commands_status ON commands(status, expires_at);
