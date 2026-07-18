"""Enkel SQLite-hjelper for Flask."""
import os
import sqlite3
from pathlib import Path

from flask import g

# Hvor databasefila ligger. Ved hosting bør DATABASE_PATH peke på en varig disk
# (et «volume»), ellers forsvinner dataene ved hver omstart/ny utrulling.
DB_PATH = Path(os.environ.get("DATABASE_PATH",
                              Path(__file__).parent / "hold_kontakten.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db():
    """Hent (eller opprett) databasetilkobling for gjeldende request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Opprett tabeller hvis de ikke finnes."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
