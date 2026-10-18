"""Database connection management for EconoBot."""

import sqlite3


def get_connection(db_path: str = "econobot.db") -> sqlite3.Connection:
    """Create and configure a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
