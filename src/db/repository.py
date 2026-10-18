"""Repository for managing products and price history in SQLite."""

from datetime import datetime
import sqlite3
from typing import Optional, Union

from src.db.connection import get_connection
from src.db.schema import create_tables


class ProdutoRepository:
    """Manages persistence of products and price history with temporal tracking."""

    def __init__(
        self,
        db_path: str = "econobot.db",
        connection: Optional[sqlite3.Connection] = None,
    ):
        self.db_path = db_path
        if connection is not None:
            self._conn: Optional[sqlite3.Connection] = connection
        elif db_path == ":memory:":
            # Preserve a persistent connection for in-memory database instances
            self._conn = get_connection(db_path)
        else:
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = get_connection(self.db_path)
        return self._conn

    def init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        create_tables(self.conn)

    def listar_produtos(self) -> list[dict]:
        """List all registered products."""
        cursor = self.conn.execute(
            """
            SELECT url, ultimo_preco, menor_preco_semana, menor_preco_mes, menor_preco_ano, data_atualizacao
            FROM produtos
            ORDER BY rowid ASC
            """
        )
        return [dict(row) for row in cursor.fetchall()]

    def obter_produto(self, url: str) -> Optional[dict]:
        """Retrieve a single product by URL."""
        cursor = self.conn.execute(
            """
            SELECT url, ultimo_preco, menor_preco_semana, menor_preco_mes, menor_preco_ano, data_atualizacao
            FROM produtos
            WHERE url = ?
            """,
            (url,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def inserir_produto(
        self,
        url: str,
        preco_inicial: Optional[float] = None,
        timestamp: Optional[Union[datetime, str]] = None,
    ) -> None:
        """Insert a new product URL with optional initial price."""
        if preco_inicial is not None:
            preco = float(preco_inicial)
            if timestamp is None:
                now_iso = datetime.now().isoformat()
            elif isinstance(timestamp, datetime):
                now_iso = timestamp.isoformat()
            else:
                now_iso = str(timestamp)

            self.conn.execute(
                """
                INSERT INTO produtos (url, ultimo_preco, menor_preco_semana, menor_preco_mes, menor_preco_ano, data_atualizacao)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (url, preco, preco, preco, preco, now_iso),
            )
            self.conn.execute(
                """
                INSERT INTO historico_precos (produto_url, preco, data_hora)
                VALUES (?, ?, ?)
                """,
                (url, preco, now_iso),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO produtos (url, ultimo_preco, menor_preco_semana, menor_preco_mes, menor_preco_ano, data_atualizacao)
                VALUES (?, NULL, NULL, NULL, NULL, NULL)
                """,
                (url,),
            )
        self.conn.commit()

    def atualizar_preco(
        self,
        url: str,
        novo_preco: float,
        timestamp: Optional[Union[datetime, str]] = None,
    ) -> None:
        """
        Update product price and recalculate lowest price for week (%Y-%W),
        month (%Y-%m), and year (%Y) based on temporal history.
        """
        preco = float(novo_preco)

        if timestamp is None:
            ts_dt = datetime.now()
        elif isinstance(timestamp, str):
            ts_dt = datetime.fromisoformat(timestamp)
        elif isinstance(timestamp, datetime):
            ts_dt = timestamp
        else:
            raise TypeError(f"Invalid timestamp type: {type(timestamp)}")

        ts_iso = ts_dt.isoformat()
        week_key = ts_dt.strftime("%Y-%W")
        month_key = ts_dt.strftime("%Y-%m")
        year_key = ts_dt.strftime("%Y")

        # Ensure product exists in produtos table
        self.conn.execute(
            "INSERT OR IGNORE INTO produtos (url) VALUES (?)",
            (url,),
        )

        # Record new price point in historical records
        self.conn.execute(
            """
            INSERT INTO historico_precos (produto_url, preco, data_hora)
            VALUES (?, ?, ?)
            """,
            (url, preco, ts_iso),
        )

        # Recalculate minimums for week, month, and year
        cursor = self.conn.execute(
            """
            SELECT
                MIN(CASE WHEN strftime('%Y-%W', data_hora) = ? THEN preco END) AS menor_semana,
                MIN(CASE WHEN strftime('%Y-%m', data_hora) = ? THEN preco END) AS menor_mes,
                MIN(CASE WHEN strftime('%Y', data_hora) = ? THEN preco END) AS menor_ano
            FROM historico_precos
            WHERE produto_url = ?
            """,
            (week_key, month_key, year_key, url),
        )
        row = cursor.fetchone()
        menor_semana = float(row["menor_semana"]) if row and row["menor_semana"] is not None else preco
        menor_mes = float(row["menor_mes"]) if row and row["menor_mes"] is not None else preco
        menor_ano = float(row["menor_ano"]) if row and row["menor_ano"] is not None else preco

        # Persist updated metrics
        self.conn.execute(
            """
            UPDATE produtos
            SET ultimo_preco = ?,
                menor_preco_semana = ?,
                menor_preco_mes = ?,
                menor_preco_ano = ?,
                data_atualizacao = ?
            WHERE url = ?
            """,
            (preco, menor_semana, menor_mes, menor_ano, ts_iso, url),
        )
        self.conn.commit()

    def listar_historico(self, url: str) -> list[dict]:
        """Retrieve complete historical readings for a product."""
        cursor = self.conn.execute(
            """
            SELECT id, produto_url, preco, data_hora
            FROM historico_precos
            WHERE produto_url = ?
            ORDER BY data_hora ASC, id ASC
            """,
            (url,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close connection if opened."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
