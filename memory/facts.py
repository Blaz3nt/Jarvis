"""Long-term fact memory — things Jarvis knows about the user.

Stores persistent facts in SQLite:
  "User's name is Tony"
  "User takes coffee at 8am"
  "Home Assistant is at 192.168.1.50"
  "User prefers Celsius"

Facts are extracted by Claude after conversations and stored permanently.
They're injected into every new conversation so Jarvis always "remembers."

Stored at /data/memory.db (Docker volume — persists across restarts).
"""

import sqlite3
import os
from datetime import datetime
import config

DB_PATH = os.path.join(os.path.dirname(config.REMINDERS_DB), "memory.db")


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            content TEXT NOT NULL UNIQUE,
            source TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def add_fact(content, category="general", source=""):
    """Store a fact. Ignores duplicates."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO facts (category, content, source) VALUES (?, ?, ?)",
            (category, content, source),
        )
        conn.commit()
    finally:
        conn.close()


def add_facts(facts_list):
    """Store multiple facts at once. Each item is a dict with 'content' and optional 'category'."""
    conn = _connect()
    try:
        for fact in facts_list:
            content = fact if isinstance(fact, str) else fact.get("content", "")
            category = "general" if isinstance(fact, str) else fact.get("category", "general")
            if content:
                conn.execute(
                    "INSERT OR IGNORE INTO facts (category, content) VALUES (?, ?)",
                    (category, content),
                )
        conn.commit()
    finally:
        conn.close()


def get_all_facts():
    """Get all stored facts, grouped by category."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT category, content FROM facts ORDER BY category, created_at"
        ).fetchall()
        if not rows:
            return ""
        result = {}
        for category, content in rows:
            result.setdefault(category, []).append(content)
        lines = []
        for category, facts in result.items():
            lines.append(f"[{category}]")
            for f in facts:
                lines.append(f"- {f}")
        return "\n".join(lines)
    finally:
        conn.close()


def search_facts(query):
    """Search facts by keyword."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT category, content FROM facts WHERE content LIKE ? ORDER BY category",
            (f"%{query}%",),
        ).fetchall()
        return [{"category": r[0], "content": r[1]} for r in rows]
    finally:
        conn.close()


def delete_fact(content):
    """Delete a fact by its content."""
    conn = _connect()
    try:
        cursor = conn.execute("DELETE FROM facts WHERE content = ?", (content,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def update_fact(old_content, new_content):
    """Update a fact's content."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE facts SET content = ?, updated_at = ? WHERE content = ?",
            (new_content, datetime.now().isoformat(), old_content),
        )
        conn.commit()
    finally:
        conn.close()


def count():
    """Return total number of stored facts."""
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    finally:
        conn.close()


def prune(max_facts):
    """If facts exceed max_facts, delete the oldest ones.

    This keeps the facts table from growing unbounded over years.
    The most recent facts (most likely still relevant) are kept.
    """
    current = count()
    if current <= max_facts:
        return 0

    to_delete = current - max_facts
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM facts WHERE id IN (SELECT id FROM facts ORDER BY updated_at ASC, created_at ASC LIMIT ?)",
            (to_delete,),
        )
        conn.commit()
        return to_delete
    finally:
        conn.close()
