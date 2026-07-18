"""Databasehjelper for Flask.

Støtter to backends med samme grensesnitt:
  - SQLite (standard, lokal bruk – ingenting å sette opp)
  - PostgreSQL (brukes ved hosting når DATABASE_URL er satt, f.eks. en gratis
    Neon-database, slik at dataene overlever selv om web-appen startes på nytt)

Appen skriver spørringer med «?» som plassholder (SQLite-stil). For Postgres
oversettes «?» til «%s» automatisk, så resten av koden er lik uansett backend.
"""
import os
import sqlite3
from pathlib import Path

from flask import g

DATABASE_URL = os.environ.get("DATABASE_URL", "")
BRUK_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

# Sti til SQLite-fila (kun relevant lokalt).
SQLITE_PATH = Path(os.environ.get("DATABASE_PATH",
                                  Path(__file__).parent / "hold_kontakten.db"))
SCHEMA_SQLITE = Path(__file__).parent / "schema.sql"
SCHEMA_POSTGRES = Path(__file__).parent / "schema_postgres.sql"


# ---------------------------------------------------------------------------
# Postgres-adapter som etterligner den lille biten av sqlite3-grensesnittet
# appen bruker: conn.execute(sql, params) -> resultat med fetchone/fetchall,
# samt conn.commit() og conn.close().
# ---------------------------------------------------------------------------
class _PgResultat:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PgTilkobling:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        from psycopg2.extras import RealDictCursor
        cur = self._raw.cursor(cursor_factory=RealDictCursor)
        # Oversett SQLite-plassholder «?» til Postgres «%s».
        cur.execute(sql.replace("?", "%s"), params)
        return _PgResultat(cur)

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()


def _koble_postgres():
    import psycopg2
    return _PgTilkobling(psycopg2.connect(DATABASE_URL))


def _koble_sqlite():
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Hent (eller opprett) databasetilkobling for gjeldende request."""
    if "db" not in g:
        g.db = _koble_postgres() if BRUK_POSTGRES else _koble_sqlite()
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Opprett tabeller hvis de ikke finnes."""
    if BRUK_POSTGRES:
        import psycopg2
        raw = psycopg2.connect(DATABASE_URL)
        with open(SCHEMA_POSTGRES, "r", encoding="utf-8") as f:
            cur = raw.cursor()
            cur.execute(f.read())
        raw.commit()
        raw.close()
    else:
        SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        with open(SCHEMA_SQLITE, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
