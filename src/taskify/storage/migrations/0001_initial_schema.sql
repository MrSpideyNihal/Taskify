-- Initial database schema for Taskify

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    start_time REAL NOT NULL,
    end_time REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    text TEXT NOT NULL,
    confidence REAL NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    processed INTEGER DEFAULT 0 CHECK (processed IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT DEFAULT '',
    due_date TEXT DEFAULT '',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS matrix_entries (
    task_id INTEGER PRIMARY KEY,
    quadrant TEXT NOT NULL CHECK (quadrant IN ('urgent_important', 'important_not_urgent', 'urgent_not_important', 'neither')),
    user_override INTEGER DEFAULT 0 CHECK (user_override IN (0, 1)),
    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
