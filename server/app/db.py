import sqlite3
from pathlib import Path
from .config import settings

def get_conn():
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.database_path, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    return c

def init_db():
    c = get_conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS devices (
      id TEXT PRIMARY KEY,
      user_id TEXT,
      name TEXT NOT NULL,
      connector_token_hash TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'offline',
      mt5_account TEXT,
      broker TEXT,
      terminal TEXT,
      mode TEXT NOT NULL DEFAULT 'demo',
      trading_locked INTEGER NOT NULL DEFAULT 0,
      last_seen TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS pairings (
      token_hash TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      expires_at REAL NOT NULL,
      used INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS setup_tokens (
      token_hash TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      user_id TEXT,
      expires_at REAL NOT NULL,
      used INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY(device_id) REFERENCES devices(id),
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS commands (
      command_id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      device_id TEXT NOT NULL,
      payload TEXT NOT NULL,
      status TEXT NOT NULL,
      result TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT,
      device_id TEXT,
      event TEXT NOT NULL,
      detail TEXT,
      created_at TEXT NOT NULL
    );
    """)
    columns = {row[1] for row in c.execute("PRAGMA table_info(devices)").fetchall()}
    if "trading_locked" not in columns:
        c.execute(
            "ALTER TABLE devices ADD COLUMN trading_locked INTEGER NOT NULL DEFAULT 0"
        )
    c.commit()
    c.close()

def fetchone(sql, params=()):
    c = get_conn()
    row = c.execute(sql, params).fetchone()
    c.close()
    return row

def fetchall(sql, params=()):
    c = get_conn()
    rows = c.execute(sql, params).fetchall()
    c.close()
    return rows

def execute(sql, params=()):
    c = get_conn()
    cur = c.execute(sql, params)
    c.commit()
    value = cur.lastrowid
    c.close()
    return value
