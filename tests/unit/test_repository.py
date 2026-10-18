"""Unit tests for SQLite repository and temporal minimum tracking."""

from datetime import datetime
import os
import sqlite3
import tempfile
import unittest

from src.db.repository import ProdutoRepository


class TestProdutoRepository(unittest.TestCase):
    def setUp(self):
        """Create a temporary directory and fresh database instance for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_econobot.db")
        self.repo = ProdutoRepository(db_path=self.db_path)
        self.repo.init_db()

    def tearDown(self):
        """Clean up temporary database directory."""
        self.repo.close()
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Schema & Table Creation
    # -------------------------------------------------------------------------
    def test_init_db_creates_required_tables_and_columns(self):
        """Verify that produtos and historico_precos tables exist with all required columns."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check produtos table columns
            cursor.execute("PRAGMA table_info(produtos)")
            cols_produtos = {row[1] for row in cursor.fetchall()}
            expected_produtos = {
                "url",
                "ultimo_preco",
                "menor_preco_semana",
                "menor_preco_mes",
                "menor_preco_ano",
                "data_atualizacao",
            }
            self.assertTrue(
                expected_produtos.issubset(cols_produtos),
                f"Missing columns in produtos: {expected_produtos - cols_produtos}",
            )

            # Check historico_precos table columns
            cursor.execute("PRAGMA table_info(historico_precos)")
            cols_historico = {row[1] for row in cursor.fetchall()}
            expected_historico = {"id", "produto_url", "preco", "data_hora"}
            self.assertTrue(
                expected_historico.issubset(cols_historico),
                f"Missing columns in historico_precos: {expected_historico - cols_historico}",
            )

    def test_in_memory_db_preserves_schema_and_data(self):
        """Verify that :memory: databases persist across repository calls."""
        memory_repo = ProdutoRepository(db_path=":memory:")
        memory_repo.init_db()
        try:
            url = "https://aliexpress.com/item/mem.html"
            memory_repo.inserir_produto(url, preco_inicial=50.0)
            produtos = memory_repo.listar_produtos()
            self.assertEqual(len(produtos), 1)
            self.assertEqual(produtos[0]["ultimo_preco"], 50.0)
        finally:
            memory_repo.close()

    # -------------------------------------------------------------------------
    # 2. CRUD Operations
    # -------------------------------------------------------------------------
    def test_listar_produtos_vazio(self):
        """listar_produtos returns an empty list when no products are registered."""
        produtos = self.repo.listar_produtos()
        self.assertEqual(produtos, [])
        self.assertIsInstance(produtos, list)

    def test_inserir_produto_sem_preco_inicial(self):
        """Inserting a product without initial price creates a record with null prices."""
        url = "https://aliexpress.com/item/1001.html"
        self.repo.inserir_produto(url)

        produtos = self.repo.listar_produtos()
        self.assertEqual(len(produtos), 1)
        p = produtos[0]
        self.assertEqual(p["url"], url)
        self.assertIsNone(p["ultimo_preco"])
        self.assertIsNone(p["menor_preco_semana"])
        self.assertIsNone(p["menor_preco_mes"])
        self.assertIsNone(p["menor_preco_ano"])
        self.assertIsNone(p["data_atualizacao"])

        historico = self.repo.listar_historico(url)
        self.assertEqual(len(historico), 0)

    def test_inserir_produto_com_preco_inicial(self):
        """Inserting a product with initial price initializes all period metrics and history."""
        url = "https://aliexpress.com/item/1002.html"
        preco = 199.90
        self.repo.inserir_produto(url, preco_inicial=preco)

        produtos = self.repo.listar_produtos()
        self.assertEqual(len(produtos), 1)
        p = produtos[0]
        self.assertEqual(p["url"], url)
        self.assertEqual(p["ultimo_preco"], preco)
        self.assertEqual(p["menor_preco_semana"], preco)
        self.assertEqual(p["menor_preco_mes"], preco)
        self.assertEqual(p["menor_preco_ano"], preco)
        self.assertIsNotNone(p["data_atualizacao"])

        historico = self.repo.listar_historico(url)
        self.assertEqual(len(historico), 1)
        self.assertEqual(historico[0]["preco"], preco)

    def test_inserir_produto_duplicado(self):
        """Inserting a duplicate URL must enforce unique constraint."""
        url = "https://aliexpress.com/item/1003.html"
        self.repo.inserir_produto(url, preco_inicial=100.0)

        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.inserir_produto(url, preco_inicial=150.0)

        produtos = self.repo.listar_produtos()
        self.assertEqual(len(produtos), 1)
        self.assertEqual(produtos[0]["ultimo_preco"], 100.0)

    def test_listar_produtos_formato(self):
        """listar_produtos returns a list of dictionaries with all required keys."""
        url1 = "https://aliexpress.com/item/item1.html"
        url2 = "https://aliexpress.com/item/item2.html"
        self.repo.inserir_produto(url1, preco_inicial=50.0)
        self.repo.inserir_produto(url2, preco_inicial=None)

        produtos = self.repo.listar_produtos()
        self.assertEqual(len(produtos), 2)
        expected_keys = {
            "url",
            "ultimo_preco",
            "menor_preco_semana",
            "menor_preco_mes",
            "menor_preco_ano",
            "data_atualizacao",
        }
        for item in produtos:
            self.assertIsInstance(item, dict)
            self.assertEqual(set(item.keys()), expected_keys)

    def test_obter_produto(self):
        """obter_produto returns product dictionary or None if not found."""
        url = "https://aliexpress.com/item/obter.html"
        self.assertIsNone(self.repo.obter_produto(url))

        self.repo.inserir_produto(url, preco_inicial=75.0)
        prod = self.repo.obter_produto(url)
        self.assertIsNotNone(prod)
        self.assertEqual(prod["url"], url)
        self.assertEqual(prod["ultimo_preco"], 75.0)

    def test_atualizar_preco_inicial_apos_cadastro_nulo(self):
        """Updating price for a product with null initial prices initializes all metrics."""
        url = "https://aliexpress.com/item/nulo.html"
        self.repo.inserir_produto(url, preco_inicial=None)

        ts = datetime(2026, 10, 12, 10, 0, 0)
        self.repo.atualizar_preco(url, 150.0, timestamp=ts)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["ultimo_preco"], 150.0)
        self.assertEqual(p["menor_preco_semana"], 150.0)
        self.assertEqual(p["menor_preco_mes"], 150.0)
        self.assertEqual(p["menor_preco_ano"], 150.0)
        self.assertEqual(p["data_atualizacao"], ts.isoformat())

    # -------------------------------------------------------------------------
    # 3. Temporal Boundary & Rollover Conditions
    # -------------------------------------------------------------------------
    def test_atualizar_preco_queda(self):
        """Price drop updates ultimo_preco and all period minimums."""
        url = "https://aliexpress.com/item/queda.html"
        t1 = datetime(2026, 10, 12, 10, 0, 0)
        t2 = datetime(2026, 10, 13, 10, 0, 0)

        self.repo.atualizar_preco(url, 150.0, timestamp=t1)
        self.repo.atualizar_preco(url, 120.0, timestamp=t2)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["ultimo_preco"], 120.0)
        self.assertEqual(p["menor_preco_semana"], 120.0)
        self.assertEqual(p["menor_preco_mes"], 120.0)
        self.assertEqual(p["menor_preco_ano"], 120.0)

    def test_atualizar_preco_aumento_mantem_minimos(self):
        """Price increase updates ultimo_preco while preserving lowest period prices."""
        url = "https://aliexpress.com/item/aumento.html"
        t1 = datetime(2026, 10, 12, 10, 0, 0)
        t2 = datetime(2026, 10, 14, 10, 0, 0)

        self.repo.atualizar_preco(url, 100.0, timestamp=t1)
        self.repo.atualizar_preco(url, 140.0, timestamp=t2)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["ultimo_preco"], 140.0)
        self.assertEqual(p["menor_preco_semana"], 100.0)
        self.assertEqual(p["menor_preco_mes"], 100.0)
        self.assertEqual(p["menor_preco_ano"], 100.0)

    def test_virada_semana_reseta_menor_preco_semana(self):
        """Calendar week rollover resets menor_preco_semana without affecting month/year."""
        url = "https://aliexpress.com/item/semana.html"

        # Sunday Oct 11, 2026 (ISO Week 40, Month 10, Year 2026): price 50.0
        t_week40 = datetime(2026, 10, 11, 20, 0, 0)
        self.repo.atualizar_preco(url, 50.0, timestamp=t_week40)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["menor_preco_semana"], 50.0)
        self.assertEqual(p["menor_preco_mes"], 50.0)
        self.assertEqual(p["menor_preco_ano"], 50.0)

        # Monday Oct 12, 2026 (ISO Week 41, Month 10, Year 2026): price rises to 80.0
        t_week41 = datetime(2026, 10, 12, 8, 0, 0)
        self.repo.atualizar_preco(url, 80.0, timestamp=t_week41)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["ultimo_preco"], 80.0)
        self.assertEqual(p["menor_preco_semana"], 80.0)  # Reset in new week
        self.assertEqual(p["menor_preco_mes"], 50.0)     # Preserved for month
        self.assertEqual(p["menor_preco_ano"], 50.0)     # Preserved for year

    def test_virada_mes_reseta_menor_preco_mes(self):
        """Calendar month rollover resets menor_preco_mes without affecting year."""
        url = "https://aliexpress.com/item/mes.html"

        # Saturday Oct 31, 2026 (Month 10, Year 2026, Week 43): price 40.0
        t_oct = datetime(2026, 10, 31, 15, 0, 0)
        self.repo.atualizar_preco(url, 40.0, timestamp=t_oct)

        # Sunday Nov 01, 2026 (Month 11, Year 2026, Week 43): price rises to 95.0
        t_nov = datetime(2026, 11, 1, 15, 0, 0)
        self.repo.atualizar_preco(url, 95.0, timestamp=t_nov)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["ultimo_preco"], 95.0)
        self.assertEqual(p["menor_preco_semana"], 40.0)  # Same week (43)
        self.assertEqual(p["menor_preco_mes"], 95.0)     # Reset in new month
        self.assertEqual(p["menor_preco_ano"], 40.0)     # Preserved for year 2026

    def test_virada_ano_reseta_menor_preco_ano(self):
        """Calendar year rollover resets menor_preco_ano."""
        url = "https://aliexpress.com/item/ano.html"

        # Thursday Dec 31, 2026 (Year 2026): price 30.0
        t_2026 = datetime(2026, 12, 31, 18, 0, 0)
        self.repo.atualizar_preco(url, 30.0, timestamp=t_2026)

        # Friday Jan 01, 2027 (Year 2027): price rises to 70.0
        t_2027 = datetime(2027, 1, 1, 10, 0, 0)
        self.repo.atualizar_preco(url, 70.0, timestamp=t_2027)

        p = self.repo.obter_produto(url)
        self.assertEqual(p["ultimo_preco"], 70.0)
        self.assertEqual(p["menor_preco_ano"], 70.0)     # Reset in new year 2027
        self.assertEqual(p["menor_preco_mes"], 70.0)     # Reset in new month
        self.assertEqual(p["menor_preco_semana"], 70.0)  # Reset in new week

    def test_multiplos_produtos_isolamento(self):
        """Price updates on product A must not affect product B."""
        url_a = "https://aliexpress.com/item/prod_a.html"
        url_b = "https://aliexpress.com/item/prod_b.html"

        t1 = datetime(2026, 10, 5, 10, 0, 0)
        t2 = datetime(2026, 10, 5, 12, 0, 0)

        self.repo.inserir_produto(url_a, preco_inicial=100.0)
        self.repo.inserir_produto(url_b, preco_inicial=200.0)

        self.repo.atualizar_preco(url_a, 50.0, timestamp=t2)

        produtos = {p["url"]: p for p in self.repo.listar_produtos()}
        self.assertEqual(produtos[url_a]["ultimo_preco"], 50.0)
        self.assertEqual(produtos[url_a]["menor_preco_semana"], 50.0)
        self.assertEqual(produtos[url_b]["ultimo_preco"], 200.0)
        self.assertEqual(produtos[url_b]["menor_preco_semana"], 200.0)


if __name__ == "__main__":
    unittest.main()
