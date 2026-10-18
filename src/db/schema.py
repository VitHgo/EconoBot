"""Database schema DDL definitions and initialization."""

import sqlite3

DDL_PRODUTOS = """
CREATE TABLE IF NOT EXISTS produtos (
    url TEXT PRIMARY KEY,
    ultimo_preco REAL,
    menor_preco_semana REAL,
    menor_preco_mes REAL,
    menor_preco_ano REAL,
    data_atualizacao TEXT
);
"""

DDL_HISTORICO_PRECOS = """
CREATE TABLE IF NOT EXISTS historico_precos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_url TEXT NOT NULL,
    preco REAL NOT NULL,
    data_hora TEXT NOT NULL,
    FOREIGN KEY (produto_url) REFERENCES produtos(url) ON DELETE CASCADE
);
"""

DDL_INDEX_HISTORICO = """
CREATE INDEX IF NOT EXISTS idx_historico_produto_data
ON historico_precos (produto_url, data_hora);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Execute DDL statements to create database tables and indexes."""
    conn.execute(DDL_PRODUTOS)
    conn.execute(DDL_HISTORICO_PRECOS)
    conn.execute(DDL_INDEX_HISTORICO)
    conn.commit()
