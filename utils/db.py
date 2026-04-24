"""Database connection helpers — pooled, one connection per request."""
import os
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from flask import g

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(
            1, 5, DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


def get_db():
    """Return the per-request connection, creating it from the pool if needed."""
    if "_db" not in g:
        g._db = _get_pool().getconn()
    return g._db


def close_db(error=False):
    """Commit (or rollback on error) and return connection to pool.
    Called automatically by app.teardown_appcontext."""
    conn = g.pop("_db", None)
    if conn is None:
        return
    try:
        if error:
            conn.rollback()
        else:
            conn.commit()
    finally:
        _get_pool().putconn(conn)


def query(sql, params=None):
    cur = get_db().cursor()
    cur.execute(sql, params or ())
    return cur.fetchall()


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    cur = get_db().cursor()
    cur.execute(sql, params or ())


def next_quotation_number():
    from datetime import date
    year = date.today().year
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='qt_year'")
    row  = cur.fetchone()
    saved_year = int(row["value"]) if row else year
    cur.execute("SELECT value FROM settings WHERE key='qt_counter'")
    row2    = cur.fetchone()
    counter = int(row2["value"]) if row2 else 0
    if saved_year != year:
        counter = 0
    counter += 1
    cur.execute("UPDATE settings SET value=%s WHERE key='qt_year'",    (str(year),))
    cur.execute("UPDATE settings SET value=%s WHERE key='qt_counter'", (str(counter),))
    # Commit immediately so the counter is safe even if the request later errors
    conn.commit()
    return f"QT-{year}-{counter:03d}"
