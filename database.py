"""
Per-user PostgreSQL database via Supabase.
Set DATABASE_URL in environment to your Supabase connection string.
"""

import os
import json
import psycopg2
import psycopg2.extras
from datetime import datetime


def get_db():
    """Return a new psycopg2 connection with dict-like row access."""
    url = os.getenv("DATABASE_URL", "")
    # Supabase/Heroku sometimes emit postgres:// — psycopg2 needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id          TEXT PRIMARY KEY,
                    email       TEXT UNIQUE NOT NULL,
                    name        TEXT DEFAULT '',
                    picture     TEXT DEFAULT '',
                    plan        TEXT DEFAULT 'free',
                    plan_status TEXT DEFAULT 'inactive',
                    razorpay_subscription_id TEXT,
                    razorpay_customer_id     TEXT,
                    created_at  TIMESTAMP DEFAULT NOW(),
                    last_login  TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_configs (
                    user_id     TEXT PRIMARY KEY,
                    config_json TEXT DEFAULT '{}',
                    updated_at  TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
        conn.commit()
    finally:
        conn.close()


# ── User CRUD ─────────────────────────────────────────────────────────────────

def upsert_user(info: dict):
    """Insert or update a user from Auth0 userinfo dict."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (id, email, name, picture, last_login)
                VALUES (%(id)s, %(email)s, %(name)s, %(picture)s, %(now)s)
                ON CONFLICT (id) DO UPDATE SET
                    email      = EXCLUDED.email,
                    name       = EXCLUDED.name,
                    picture    = EXCLUDED.picture,
                    last_login = EXCLUDED.last_login
            """, {
                "id":      info["id"],
                "email":   info["email"],
                "name":    info.get("name", ""),
                "picture": info.get("picture", ""),
                "now":     datetime.now(),
            })
        conn.commit()
    finally:
        conn.close()


def get_user(user_id: str) -> dict | None:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def activate_plan(user_id: str, plan: str, subscription_id: str = ""):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET plan = %s, plan_status = 'active', razorpay_subscription_id = %s
                WHERE id = %s
            """, (plan, subscription_id, user_id))
        conn.commit()
    finally:
        conn.close()


def cancel_plan(user_id: str):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET plan_status = 'cancelled' WHERE id = %s",
                (user_id,)
            )
        conn.commit()
    finally:
        conn.close()


def get_all_users() -> list[dict]:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ── Per-user config ───────────────────────────────────────────────────────────

def get_user_config(user_id: str) -> dict:
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT config_json FROM user_configs WHERE user_id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            return json.loads(row["config_json"]) if row else {}
    finally:
        conn.close()


def save_user_config(user_id: str, config: dict):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_configs (user_id, config_json, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    config_json = EXCLUDED.config_json,
                    updated_at  = EXCLUDED.updated_at
            """, (user_id, json.dumps(config), datetime.now()))
        conn.commit()
    finally:
        conn.close()
