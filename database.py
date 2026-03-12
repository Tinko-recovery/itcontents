"""
Per-user SQLite database.
Each ContentAI customer has one row in `users` and one row in `user_configs`.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "content_ai.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe for concurrent Flask workers
    return conn


def init_db():
    """Create all tables. Safe to call on every startup."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,          -- Auth0 'sub' e.g. google-oauth2|12345
                email       TEXT UNIQUE NOT NULL,
                name        TEXT DEFAULT '',
                picture     TEXT DEFAULT '',
                plan        TEXT DEFAULT 'free',       -- free | starter | pro
                plan_status TEXT DEFAULT 'inactive',   -- inactive | active | cancelled
                razorpay_subscription_id TEXT,
                razorpay_customer_id     TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                last_login  TEXT
            );

            CREATE TABLE IF NOT EXISTS user_configs (
                user_id     TEXT PRIMARY KEY,
                config_json TEXT DEFAULT '{}',
                updated_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


# ── User CRUD ─────────────────────────────────────────────────────────────────

def upsert_user(info: dict):
    """Insert or update a user from Auth0 userinfo dict."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (id, email, name, picture, last_login)
            VALUES (:id, :email, :name, :picture, :now)
            ON CONFLICT(id) DO UPDATE SET
                email      = excluded.email,
                name       = excluded.name,
                picture    = excluded.picture,
                last_login = excluded.last_login
        """, {
            "id":      info["id"],
            "email":   info["email"],
            "name":    info.get("name", ""),
            "picture": info.get("picture", ""),
            "now":     datetime.now().isoformat(),
        })


def get_user(user_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def activate_plan(user_id: str, plan: str, subscription_id: str = ""):
    with get_db() as conn:
        conn.execute("""
            UPDATE users
            SET plan = ?, plan_status = 'active', razorpay_subscription_id = ?
            WHERE id = ?
        """, (plan, subscription_id, user_id))


def cancel_plan(user_id: str):
    with get_db() as conn:
        conn.execute("""
            UPDATE users SET plan_status = 'cancelled' WHERE id = ?
        """, (user_id,))


def get_all_users() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── Per-user config ───────────────────────────────────────────────────────────

def get_user_config(user_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT config_json FROM user_configs WHERE user_id = ?", (user_id,)
        ).fetchone()
        return json.loads(row["config_json"]) if row else {}


def save_user_config(user_id: str, config: dict):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_configs (user_id, config_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at  = excluded.updated_at
        """, (user_id, json.dumps(config), datetime.now().isoformat()))
