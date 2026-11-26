import json
import sqlite3

DB_PATH = "jobs.db"


def _run(sql, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS jobs ("
            "id TEXT PRIMARY KEY, "
            "data TEXT NOT NULL, "
            "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        cur = conn.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        conn.commit()
        return rows
    finally:
        conn.close()


def save_job(job: dict):
    _run(
        "INSERT INTO jobs (id, data) VALUES (?, ?) "
        "ON CONFLICT(id) DO UPDATE SET data = excluded.data, "
        "updated_at = CURRENT_TIMESTAMP",
        (job["id"], json.dumps(job)),
    )


def load_job(job_id: str):
    rows = _run("SELECT data FROM jobs WHERE id = ?", (job_id,), fetch=True)
    return json.loads(rows[0][0]) if rows else None


def list_jobs():
    rows = _run(
        "SELECT data FROM jobs ORDER BY updated_at DESC LIMIT 50", fetch=True
    )
    return [json.loads(r[0]) for r in rows]


def count_jobs_on(date_str: str) -> int:
    """How many jobs were created on this UTC date (used for the daily limit)."""
    rows = _run(
        "SELECT COUNT(*) FROM jobs WHERE json_extract(data, '$.created_date') = ?",
        (date_str,),
        fetch=True,
    )
    return rows[0][0] if rows else 0