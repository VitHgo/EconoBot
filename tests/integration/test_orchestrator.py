"""Integration tests for the One-off Cron Orchestrator and Business Logic.

Tests the full orchestration workflow:
- 100% Offline Testing Strategy (mocked Telegram HTTP and mocked extractors).
- Test Case 1: First run (ultimo_preco is None) initializes DB price and minimums, no Telegram alert sent.
- Test Case 2: Price drop (novo_preco < ultimo_preco) dispatches Telegram alert with old and new price, updates DB.
- Test Case 3: Price increase or equal (novo_preco >= ultimo_preco) updates DB without sending Telegram alert.
- Test Case 4: Multiple products in DB processed sequentially in a single pass.
- Test Case 5: Single extractor error does not abort entire batch run.
- Test Case 6: Script terminates cleanly without looping (asserts one-off execution).
- Edge Cases: Empty DB, environment seeding, Telegram service failures, and unsupported product domains.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from main import executar_orquestrador, main
from src.db.repository import ProdutoRepository
from src.extractors.base import (
    DominioNaoSuportadoError,
    ExtratorBase,
    FalhaAcessoPaginaError,
    PrecoNaoEncontradoError,
)
from src.services.telegram import TelegramService


class BaseOrchestratorTest(unittest.TestCase):
    """Base fixture providing an isolated in-memory SQLite database and mocked TelegramService."""

    def setUp(self):
        # 100% in-memory SQLite instance
        self.repo = ProdutoRepository(db_path=":memory:")
        self.repo.init_db()

        # Mocked Telegram notification service
        self.mock_telegram = MagicMock(spec=TelegramService)
        self.mock_telegram.enviar_alerta.return_value = True

    def tearDown(self):
        self.repo.close()


class TestOrchestratorIntegration(BaseOrchestratorTest):
    """Integration test suite exercising end-to-end orchestration workflows."""

    # -------------------------------------------------------------------------
    # Test Case 1: First Run (ultimo_preco is None)
    # -------------------------------------------------------------------------
    @patch("main.obter_extrator")
    def test_case_1_first_run_initializes_db_without_alert(self, mock_obter_extrator):
        """First run saves initial price, initializes week/month/year minimums, and DOES NOT alert."""
        url = "https://pt.aliexpress.com/item/1005001.html"
        self.repo.inserir_produto(url, preco_inicial=None)

        # Mock extractor to return 199.99
        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 199.99
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        # Asserts
        self.mock_telegram.enviar_alerta.assert_not_called()

        produto = self.repo.obter_produto(url)
        self.assertIsNotNone(produto)
        self.assertEqual(produto["ultimo_preco"], 199.99)
        self.assertEqual(produto["menor_preco_semana"], 199.99)
        self.assertEqual(produto["menor_preco_mes"], 199.99)
        self.assertEqual(produto["menor_preco_ano"], 199.99)
        self.assertIsNotNone(produto["data_atualizacao"])

        historico = self.repo.listar_historico(url)
        self.assertEqual(len(historico), 1)
        self.assertEqual(historico[0]["preco"], 199.99)

        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["sucesso"], 1)
        self.assertEqual(stats["primeiras_leituras"], 1)
        self.assertEqual(stats["alertas_enviados"], 0)

    # -------------------------------------------------------------------------
    # Test Case 2: Price Drop (novo_preco < ultimo_preco)
    # -------------------------------------------------------------------------
    @patch("main.obter_extrator")
    def test_case_2_price_drop_triggers_alert_and_updates_db(self, mock_obter_extrator):
        """Price drop dispatches Telegram alert with old and new prices and updates DB."""
        url = "https://pt.aliexpress.com/item/1005002.html"
        self.repo.inserir_produto(url, preco_inicial=250.00)

        # Mock extractor returning a lower price
        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 189.90
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        # Asserts: Telegram alert was dispatched with exact old and new price
        self.mock_telegram.enviar_alerta.assert_called_once_with(
            url=url, preco_antigo=250.00, preco_novo=189.90
        )

        produto = self.repo.obter_produto(url)
        self.assertIsNotNone(produto)
        self.assertEqual(produto["ultimo_preco"], 189.90)
        self.assertEqual(produto["menor_preco_semana"], 189.90)
        self.assertEqual(produto["menor_preco_mes"], 189.90)
        self.assertEqual(produto["menor_preco_ano"], 189.90)

        historico = self.repo.listar_historico(url)
        self.assertEqual(len(historico), 2)
        self.assertEqual(historico[-1]["preco"], 189.90)

        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["sucesso"], 1)
        self.assertEqual(stats["quedas_detectadas"], 1)
        self.assertEqual(stats["alertas_enviados"], 1)

    # -------------------------------------------------------------------------
    # Test Case 3: Price Increase or Equal (novo_preco >= ultimo_preco)
    # -------------------------------------------------------------------------
    @patch("main.obter_extrator")
    def test_case_3a_price_equal_updates_db_without_alert(self, mock_obter_extrator):
        """Equal price updates database timestamp and DOES NOT trigger Telegram alert."""
        url = "https://pt.aliexpress.com/item/1005003a.html"
        self.repo.inserir_produto(url, preco_inicial=100.00)

        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 100.00
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        self.mock_telegram.enviar_alerta.assert_not_called()

        produto = self.repo.obter_produto(url)
        self.assertEqual(produto["ultimo_preco"], 100.00)
        self.assertEqual(produto["menor_preco_semana"], 100.00)

        self.assertEqual(stats["precos_inalterados_ou_maiores"], 1)
        self.assertEqual(stats["alertas_enviados"], 0)

    @patch("main.obter_extrator")
    def test_case_3b_price_increase_preserves_minimums_without_alert(
        self, mock_obter_extrator
    ):
        """Price increase updates ultimo_preco, preserves lowest metrics, and DOES NOT alert."""
        url = "https://pt.aliexpress.com/item/1005003b.html"
        self.repo.inserir_produto(url, preco_inicial=100.00)

        # Price increases to 140.00
        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 140.00
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        self.mock_telegram.enviar_alerta.assert_not_called()

        produto = self.repo.obter_produto(url)
        self.assertEqual(produto["ultimo_preco"], 140.00)
        # Lowest price in period must remain 100.00
        self.assertEqual(produto["menor_preco_semana"], 100.00)
        self.assertEqual(produto["menor_preco_mes"], 100.00)
        self.assertEqual(produto["menor_preco_ano"], 100.00)

        self.assertEqual(stats["precos_inalterados_ou_maiores"], 1)
        self.assertEqual(stats["alertas_enviados"], 0)

    # -------------------------------------------------------------------------
    # Test Case 4: Multiple Products Processed Sequentially in a Single Pass
    # -------------------------------------------------------------------------
    @patch("main.obter_extrator")
    def test_case_4_multiple_products_batch_execution(self, mock_obter_extrator):
        """Processes multiple registered products sequentially in a single pass."""
        url_first = "https://pt.aliexpress.com/item/p1.html"
        url_drop = "https://pt.aliexpress.com/item/p2.html"
        url_rise = "https://pt.aliexpress.com/item/p3.html"
        url_equal = "https://pt.aliexpress.com/item/p4.html"

        self.repo.inserir_produto(url_first, preco_inicial=None)
        self.repo.inserir_produto(url_drop, preco_inicial=300.00)
        self.repo.inserir_produto(url_rise, preco_inicial=80.00)
        self.repo.inserir_produto(url_equal, preco_inicial=50.00)

        price_map = {
            url_first: 75.00,  # First run -> 75.00
            url_drop: 220.00,  # Drop 300.00 -> 220.00 (ALERT)
            url_rise: 95.00,   # Rise 80.00 -> 95.00 (NO ALERT)
            url_equal: 50.00,  # Equal 50.00 -> 50.00 (NO ALERT)
        }

        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.side_effect = lambda u: price_map[u]
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        # Verify summary stats
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["sucesso"], 4)
        self.assertEqual(stats["erros"], 0)
        self.assertEqual(stats["primeiras_leituras"], 1)
        self.assertEqual(stats["quedas_detectadas"], 1)
        self.assertEqual(stats["precos_inalterados_ou_maiores"], 2)
        self.assertEqual(stats["alertas_enviados"], 1)

        # Telegram alert sent EXACTLY ONCE for url_drop
        self.mock_telegram.enviar_alerta.assert_called_once_with(
            url=url_drop, preco_antigo=300.00, preco_novo=220.00
        )

        # Verify all products updated in DB
        self.assertEqual(self.repo.obter_produto(url_first)["ultimo_preco"], 75.00)
        self.assertEqual(self.repo.obter_produto(url_drop)["ultimo_preco"], 220.00)
        self.assertEqual(self.repo.obter_produto(url_rise)["ultimo_preco"], 95.00)
        self.assertEqual(self.repo.obter_produto(url_equal)["ultimo_preco"], 50.00)

    # -------------------------------------------------------------------------
    # Test Case 5: Single Extractor Error Does Not Abort Entire Batch Run
    # -------------------------------------------------------------------------
    @patch("main.obter_extrator")
    def test_case_5_extractor_errors_do_not_abort_batch(self, mock_obter_extrator):
        """Scraper errors on individual URLs are isolated and do not prevent other URLs from processing."""
        url_err1 = "https://pt.aliexpress.com/item/timeout.html"
        url_success = "https://pt.aliexpress.com/item/valid_drop.html"
        url_err2 = "https://pt.aliexpress.com/item/noprice.html"
        url_success2 = "https://pt.aliexpress.com/item/valid_rise.html"

        self.repo.inserir_produto(url_err1, preco_inicial=100.00)
        self.repo.inserir_produto(url_success, preco_inicial=200.00)
        self.repo.inserir_produto(url_err2, preco_inicial=50.00)
        self.repo.inserir_produto(url_success2, preco_inicial=40.00)

        def mock_extract(u):
            if u == url_err1:
                raise FalhaAcessoPaginaError("Page load timed out")
            if u == url_err2:
                raise PrecoNaoEncontradoError("Script price pattern missing")
            if u == url_success:
                return 150.00  # Price drop
            if u == url_success2:
                return 60.00   # Price rise
            return 10.0

        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.side_effect = mock_extract
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        # Batch completes with 2 successes and 2 errors
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["sucesso"], 2)
        self.assertEqual(stats["erros"], 2)
        self.assertEqual(stats["alertas_enviados"], 1)

        # url_success was processed and alert dispatched
        self.mock_telegram.enviar_alerta.assert_called_once_with(
            url=url_success, preco_antigo=200.00, preco_novo=150.00
        )
        self.assertEqual(self.repo.obter_produto(url_success)["ultimo_preco"], 150.00)
        self.assertEqual(self.repo.obter_produto(url_success2)["ultimo_preco"], 60.00)

        # Erroneous URLs preserve their prior state
        self.assertEqual(self.repo.obter_produto(url_err1)["ultimo_preco"], 100.00)
        self.assertEqual(self.repo.obter_produto(url_err2)["ultimo_preco"], 50.00)

    # -------------------------------------------------------------------------
    # Test Case 6: Clean One-Off Termination (No Looping)
    # -------------------------------------------------------------------------
    @patch("main.obter_extrator")
    def test_case_6_terminates_cleanly_without_looping(self, mock_obter_extrator):
        """Verifies one-off execution completes single pass and returns summary dictionary."""
        url = "https://pt.aliexpress.com/item/single_pass.html"
        self.repo.inserir_produto(url, preco_inicial=10.00)

        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 10.00
        mock_obter_extrator.return_value = mock_extractor

        # Invocation must return immediately (not hang or block in loop)
        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        self.assertIsInstance(stats, dict)
        self.assertEqual(mock_extractor.extrair_preco.call_count, 1)

    # -------------------------------------------------------------------------
    # Edge Cases & Robustness
    # -------------------------------------------------------------------------
    def test_edge_case_empty_database_completes_cleanly(self):
        """Empty database terminates gracefully without errors or alerts."""
        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["sucesso"], 0)
        self.assertEqual(stats["erros"], 0)
        self.assertEqual(stats["alertas_enviados"], 0)
        self.mock_telegram.enviar_alerta.assert_not_called()

    @patch("main.obter_extrator")
    def test_edge_case_empty_database_with_seed_url(self, mock_obter_extrator):
        """Empty database with SEED_URL in environment seeds the URL and processes it."""
        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 85.00
        mock_obter_extrator.return_value = mock_extractor

        with patch.dict(os.environ, {"SEED_URL": "https://pt.aliexpress.com/item/seed1.html"}):
            stats = executar_orquestrador(
                repository=self.repo, telegram_service=self.mock_telegram
            )

        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["sucesso"], 1)
        self.assertEqual(stats["primeiras_leituras"], 1)
        self.assertEqual(self.repo.obter_produto("https://pt.aliexpress.com/item/seed1.html")["ultimo_preco"], 85.00)

    @patch("main.obter_extrator")
    def test_edge_case_unsupported_domain_in_database(self, mock_obter_extrator):
        """URL with unsupported domain in DB is caught and counted as an error without crashing."""
        url_bad = "https://unsupported-store.com/item/1"
        url_good = "https://pt.aliexpress.com/item/2"

        self.repo.inserir_produto(url_bad, preco_inicial=None)
        self.repo.inserir_produto(url_good, preco_inicial=50.00)

        def mock_obter(u):
            if "unsupported" in u:
                raise DominioNaoSuportadoError("Domínio não suportado")
            mock_ext = MagicMock(spec=ExtratorBase)
            mock_ext.extrair_preco.return_value = 40.00  # drop
            return mock_ext

        mock_obter_extrator.side_effect = mock_obter

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["sucesso"], 1)
        self.assertEqual(stats["erros"], 1)
        self.assertEqual(stats["alertas_enviados"], 1)

    @patch("main.obter_extrator")
    def test_edge_case_telegram_failure_does_not_abort_db_update(
        self, mock_obter_extrator
    ):
        """If Telegram alerting fails, DB is still updated with new price and batch continues."""
        url = "https://pt.aliexpress.com/item/tg_fail.html"
        self.repo.inserir_produto(url, preco_inicial=200.00)

        # Telegram fails
        self.mock_telegram.enviar_alerta.return_value = False

        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 150.00
        mock_obter_extrator.return_value = mock_extractor

        stats = executar_orquestrador(
            repository=self.repo, telegram_service=self.mock_telegram
        )

        # Alert was attempted
        self.mock_telegram.enviar_alerta.assert_called_once()
        # Database was still updated
        self.assertEqual(self.repo.obter_produto(url)["ultimo_preco"], 150.00)
        self.assertEqual(stats["sucesso"], 1)

    @patch("main.obter_extrator")
    def test_custom_extractor_resolver_injection(self, mock_obter_extrator):
        """Custom extractor_resolver callable can be injected directly into executar_orquestrador."""
        url = "https://custom-resolver.com/item/1"
        self.repo.inserir_produto(url, preco_inicial=50.0)

        custom_mock = MagicMock(spec=ExtratorBase)
        custom_mock.extrair_preco.return_value = 30.0

        custom_resolver = MagicMock(return_value=custom_mock)

        stats = executar_orquestrador(
            repository=self.repo,
            telegram_service=self.mock_telegram,
            extractor_resolver=custom_resolver,
        )

        custom_resolver.assert_called_once_with(url)
        mock_obter_extrator.assert_not_called()
        self.assertEqual(stats["sucesso"], 1)
        self.assertEqual(stats["quedas_detectadas"], 1)

    @patch("main.executar_orquestrador")
    def test_main_cli_entrypoint_exit_code_0(self, mock_exec):
        """CLI main() entrypoint returns 0 on successful execution."""
        mock_exec.return_value = {"total": 1, "sucesso": 1, "erros": 0}
        exit_code = main()
        self.assertEqual(exit_code, 0)
        mock_exec.assert_called_once()

    @patch("main.executar_orquestrador")
    def test_main_cli_entrypoint_handles_fatal_exception(self, mock_exec):
        """CLI main() entrypoint returns 1 on unhandled fatal exception."""
        mock_exec.side_effect = RuntimeError("Fatal system error")
        exit_code = main()
        self.assertEqual(exit_code, 1)

    @patch("main.executar_orquestrador")
    def test_main_cli_with_add_url_and_db_arg(self, mock_exec):
        """CLI main() accepts --add-url and --db arguments."""
        mock_exec.return_value = {"total": 1, "sucesso": 1, "erros": 0}
        exit_code = main([
            "--db", ":memory:",
            "--add-url", "https://pt.aliexpress.com/item/new.html",
            "-v",
        ])
        self.assertEqual(exit_code, 0)
        mock_exec.assert_called_once_with(db_path=":memory:")


if __name__ == "__main__":
    unittest.main()
