r"""Unit tests for ExtratorAliExpress Playwright Stealth scraper and BeautifulSoup regex extraction.

Verifies:
1. 100% offline execution with unittest.mock.patch (zero real browser or network requests).
2. Exact Playwright Stealth launch flags:
   - chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
3. Exact context options:
   - new_context(user_agent=..., locale="pt-BR", viewport={"width": 1920, "height": 1080})
4. Exact webdriver evasion script:
   - page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
5. Exact navigation & timing parameters:
   - page.goto(url, wait_until="domcontentloaded", timeout=30000)
   - page.wait_for_timeout(3000)
6. BeautifulSoup script tag traversal and regex BRL extraction:
   - pattern: r'"priceCurrency"\s*:\s*"BRL"\s*,\s*"price"\s*:\s*"([\d\.]+)"'
7. Error handling:
   - PrecoNaoEncontradoError on missing price or non-BRL currency.
   - FalhaAcessoPaginaError on Playwright TimeoutError or network errors.
   - ValueError on invalid URLs.
8. Deterministic resource cleanup:
   - Context and browser closed in finally: blocks on both success and failure.
9. Interface compliance:
   - ExtratorAliExpress inherits from ExtratorBase and fulfills extrair_preco(url).
"""

import inspect
import re
import unittest
from unittest.mock import MagicMock, call, patch

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.extractors.aliexpress import (
    CHROMIUM_STEALTH_ARGS,
    DEFAULT_LOCALE,
    DEFAULT_NAVIGATION_TIMEOUT_MS,
    DEFAULT_POST_LOAD_WAIT_MS,
    DEFAULT_USER_AGENT,
    DEFAULT_VIEWPORT,
    NAVIGATION_WAIT_UNTIL,
    REGEX_PRECO_BRL,
    STEALTH_INIT_SCRIPT,
    ExtratorAliExpress,
)
from src.extractors.base import (
    ExtratorBase,
    ExtratorError,
    FalhaAcessoPaginaError,
    PrecoNaoEncontradoError,
)


class BaseAliExpressTest(unittest.TestCase):
    """Base test fixture providing mock setup and realistic HTML payloads."""

    EXPECTED_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    EXPECTED_LOCALE = "pt-BR"
    EXPECTED_VIEWPORT = {"width": 1920, "height": 1080}
    EXPECTED_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
    EXPECTED_INIT_SCRIPT = (
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    SAMPLE_URL = "https://pt.aliexpress.com/item/1005007460526309.html"

    SAMPLE_HTML_CLEAN = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Produto AliExpress</title>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Product","name":"Teclado Mecânico","offers":{"@type":"Offer","priceCurrency":"BRL","price":"116.29"}}
        </script>
      </head>
      <body><h1>Teclado Mecânico</h1></body>
    </html>
    """

    SAMPLE_HTML_SPACES = """
    <html>
      <head>
        <script>
          var meta = {
            "priceCurrency" : "BRL" ,
            "price" : "49.90"
          };
        </script>
      </head>
    </html>
    """

    SAMPLE_HTML_RUNPARAMS = """
    <html>
      <head>
        <script>
          window.runParams = {
            data: {
              priceComponent: {
                "priceCurrency": "BRL",
                "price": "141.64"
              }
            }
          };
        </script>
      </head>
    </html>
    """

    SAMPLE_HTML_MULTIPLE_SCRIPTS = """
    <html>
      <head>
        <script src="https://assets.aliexpress.com/ae-analytics.js"></script>
        <script>window.__INITIAL_DATA__ = {"user": "guest"};</script>
        <script type="application/ld+json">
          {"offers": {"priceCurrency": "BRL", "price": "299.99"}}
        </script>
        <script src="https://assets.aliexpress.com/ae-tracker.js"></script>
      </head>
    </html>
    """

    def setUp(self):
        """Create fresh extractor instance for each test."""
        self.extractor = ExtratorAliExpress()

    def _setup_playwright_mock(self, mock_sync, html_content=None):
        """Configure nested Playwright mock hierarchy supporting with and start() patterns."""
        if html_content is None:
            html_content = self.SAMPLE_HTML_CLEAN

        mock_playwright = MagicMock()
        mock_sync.return_value.__enter__.return_value = mock_playwright
        mock_sync.return_value.start.return_value = mock_playwright

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.content.return_value = html_content

        return mock_playwright, mock_browser, mock_context, mock_page


class TestExtratorAliExpressStealthConfiguration(BaseAliExpressTest):
    """Verifies that all Playwright stealth evasion flags match the exact specification."""

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_chromium_launch_arguments(self, mock_sync):
        """Assert chromium.launch is called with headless=True and AutomationControlled evasion."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)

        self.extractor.extrair_preco(self.SAMPLE_URL)

        p.chromium.launch.assert_called_once_with(
            headless=True,
            args=self.EXPECTED_LAUNCH_ARGS,
        )

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_browser_context_options(self, mock_sync):
        """Assert new_context is called with exact user_agent, locale pt-BR, and 1080p viewport."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)

        self.extractor.extrair_preco(self.SAMPLE_URL)

        browser.new_context.assert_called_once_with(
            user_agent=self.EXPECTED_USER_AGENT,
            locale=self.EXPECTED_LOCALE,
            viewport=self.EXPECTED_VIEWPORT,
        )

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_add_init_script_webdriver_cloaking(self, mock_sync):
        """Assert page.add_init_script cloaks navigator.webdriver via Object.defineProperty."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)

        self.extractor.extrair_preco(self.SAMPLE_URL)

        page.add_init_script.assert_called_once_with(self.EXPECTED_INIT_SCRIPT)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_goto_navigation_parameters(self, mock_sync):
        """Assert page.goto is called with wait_until='domcontentloaded' and timeout=30000."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)

        self.extractor.extrair_preco(self.SAMPLE_URL)

        page.goto.assert_called_once_with(
            self.SAMPLE_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_wait_for_timeout_delay(self, mock_sync):
        """Assert page.wait_for_timeout is called with exactly 3000 milliseconds."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)

        self.extractor.extrair_preco(self.SAMPLE_URL)

        page.wait_for_timeout.assert_called_once_with(3000)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_full_stealth_execution_sequence(self, mock_sync):
        """Assert lifecycle methods are executed in the required chronological order."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)
        manager = MagicMock()
        manager.attach_mock(p.chromium.launch, "launch")
        manager.attach_mock(browser.new_context, "new_context")
        manager.attach_mock(context.new_page, "new_page")
        manager.attach_mock(page.add_init_script, "add_init_script")
        manager.attach_mock(page.goto, "goto")
        manager.attach_mock(page.wait_for_timeout, "wait_for_timeout")
        manager.attach_mock(page.content, "content")
        manager.attach_mock(context.close, "context_close")
        manager.attach_mock(browser.close, "browser_close")

        self.extractor.extrair_preco(self.SAMPLE_URL)

        expected_calls = [
            call.launch(headless=True, args=self.EXPECTED_LAUNCH_ARGS),
            call.new_context(
                user_agent=self.EXPECTED_USER_AGENT,
                locale=self.EXPECTED_LOCALE,
                viewport=self.EXPECTED_VIEWPORT,
            ),
            call.new_page(),
            call.add_init_script(self.EXPECTED_INIT_SCRIPT),
            call.goto(self.SAMPLE_URL, wait_until="domcontentloaded", timeout=30000),
            call.wait_for_timeout(3000),
            call.content(),
            call.context_close(),
            call.browser_close(),
        ]
        manager.assert_has_calls(expected_calls, any_order=False)


class TestExtratorAliExpressExtractionLogic(BaseAliExpressTest):
    """Verifies BeautifulSoup script tag iteration and regex parsing for BRL prices."""

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_extract_clean_brl_price(self, mock_sync):
        """Assert clean BRL price is extracted correctly as float."""
        self._setup_playwright_mock(mock_sync, self.SAMPLE_HTML_CLEAN)

        price = self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(price, float)
        self.assertEqual(price, 116.29)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_extract_brl_price_with_whitespace(self, mock_sync):
        """Assert regex handles variable spacing and newlines around keys."""
        self._setup_playwright_mock(mock_sync, self.SAMPLE_HTML_SPACES)

        price = self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(price, float)
        self.assertEqual(price, 49.90)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_extract_brl_price_nested_in_window_runparams(self, mock_sync):
        """Assert price nested in window.runParams script block is extracted."""
        self._setup_playwright_mock(mock_sync, self.SAMPLE_HTML_RUNPARAMS)

        price = self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(price, float)
        self.assertEqual(price, 141.64)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_extract_brl_price_across_multiple_scripts(self, mock_sync):
        """Assert extractor iterates through script tags until target price is found."""
        self._setup_playwright_mock(mock_sync, self.SAMPLE_HTML_MULTIPLE_SCRIPTS)

        price = self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(price, float)
        self.assertEqual(price, 299.99)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_extract_integer_price_as_float(self, mock_sync):
        """Assert price without decimals is converted to float."""
        html = '<script>{"priceCurrency":"BRL","price":"100"}</script>'
        self._setup_playwright_mock(mock_sync, html)

        price = self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(price, float)
        self.assertEqual(price, 100.0)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_extract_cents_price_as_float(self, mock_sync):
        """Assert sub-one-real price is extracted as float."""
        html = '<script>{"priceCurrency":"BRL","price":"0.99"}</script>'
        self._setup_playwright_mock(mock_sync, html)

        price = self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(price, float)
        self.assertEqual(price, 0.99)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_usd_currency_raises_preco_nao_encontrado(self, mock_sync):
        """Assert non-BRL currency (USD) raises PrecoNaoEncontradoError."""
        html = '<script>{"priceCurrency":"USD","price":"25.00"}</script>'
        self._setup_playwright_mock(mock_sync, html)

        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_eur_currency_raises_preco_nao_encontrado(self, mock_sync):
        """Assert non-BRL currency (EUR) raises PrecoNaoEncontradoError."""
        html = '<script>{"priceCurrency":"EUR","price":"19.90"}</script>'
        self._setup_playwright_mock(mock_sync, html)

        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_missing_price_raises_preco_nao_encontrado(self, mock_sync):
        """Assert script with missing price field raises PrecoNaoEncontradoError."""
        html = '<script>{"item": "Laptop", "priceCurrency": "BRL"}</script>'
        self._setup_playwright_mock(mock_sync, html)

        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_no_scripts_raises_preco_nao_encontrado(self, mock_sync):
        """Assert HTML without any script tags raises PrecoNaoEncontradoError."""
        html = "<html><body><div>Sem scripts aqui</div></body></html>"
        self._setup_playwright_mock(mock_sync, html)

        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_empty_page_content_raises_preco_nao_encontrado(self, mock_sync):
        """Assert empty string content raises PrecoNaoEncontradoError."""
        self._setup_playwright_mock(mock_sync, "")

        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco(self.SAMPLE_URL)


class TestExtratorAliExpressDirectHtmlParsing(unittest.TestCase):
    """Direct offline unit tests for extrair_preco_do_html without Playwright."""

    def setUp(self):
        self.extractor = ExtratorAliExpress()

    def test_direct_clean_extraction(self):
        """Assert direct method extracts price correctly."""
        html = '<script>{"priceCurrency": "BRL", "price": "89.90"}</script>'
        price = self.extractor.extrair_preco_do_html(html)
        self.assertEqual(price, 89.90)

    def test_direct_classmethod_invocation(self):
        """Assert extrair_preco_do_html works as classmethod directly on class."""
        html = '<script>{"priceCurrency": "BRL", "price": "199.50"}</script>'
        price = ExtratorAliExpress.extrair_preco_do_html(html)
        self.assertEqual(price, 199.50)

    def test_direct_private_alias_invocation(self):
        """Assert _extrair_preco_do_html alias functions identically."""
        html = '<script>{"priceCurrency": "BRL", "price": "55.00"}</script>'
        price = self.extractor._extrair_preco_do_html(html)
        self.assertEqual(price, 55.00)

    def test_direct_invalid_html_raises(self):
        """Assert non-string or empty html raises PrecoNaoEncontradoError."""
        for invalid in ["", "   ", None]:
            with self.subTest(html=invalid):
                with self.assertRaises(PrecoNaoEncontradoError):
                    self.extractor.extrair_preco_do_html(invalid)  # type: ignore

    def test_direct_foreign_currency_raises(self):
        """Assert foreign currency raises PrecoNaoEncontradoError."""
        html = '<script>{"priceCurrency": "USD", "price": "50.00"}</script>'
        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco_do_html(html)


class TestExtratorAliExpressErrorHandling(BaseAliExpressTest):
    """Verifies that navigation timeouts and network errors raise FalhaAcessoPaginaError."""

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_playwright_timeout_raises_falha_acesso_pagina(self, mock_sync):
        """Assert Playwright TimeoutError during goto raises FalhaAcessoPaginaError."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)
        page.goto.side_effect = PlaywrightTimeoutError("Timeout 30000ms exceeded.")

        with self.assertRaises(FalhaAcessoPaginaError) as ctx:
            self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(ctx.exception, ExtratorError)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_playwright_network_error_raises_falha_acesso_pagina(self, mock_sync):
        """Assert Playwright Error during goto raises FalhaAcessoPaginaError."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)
        page.goto.side_effect = PlaywrightError("net::ERR_CONNECTION_REFUSED")

        with self.assertRaises(FalhaAcessoPaginaError) as ctx:
            self.extractor.extrair_preco(self.SAMPLE_URL)

        self.assertIsInstance(ctx.exception, ExtratorError)

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_generic_browser_exception_raises_falha_acesso_pagina(self, mock_sync):
        """Assert unexpected browser failure raises FalhaAcessoPaginaError or ExtratorError."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)
        page.goto.side_effect = RuntimeError("Browser process terminated unexpectedly")

        with self.assertRaises(ExtratorError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

    def test_invalid_urls_raise_value_error(self):
        """Assert empty, None, or whitespace-only URLs raise ValueError before Playwright launch."""
        for invalid_url in [None, "", "   ", "\t\n"]:
            with self.subTest(url=invalid_url):
                with self.assertRaises(ValueError):
                    self.extractor.extrair_preco(invalid_url)


class TestExtratorAliExpressResourceCleanup(BaseAliExpressTest):
    """Verifies that browser and context are closed in finally blocks across all paths."""

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_cleanup_on_success(self, mock_sync):
        """Assert context and browser are closed after successful extraction."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)

        self.extractor.extrair_preco(self.SAMPLE_URL)

        context.close.assert_called_once()
        browser.close.assert_called_once()

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_cleanup_on_navigation_timeout(self, mock_sync):
        """Assert context and browser are closed even when page.goto times out."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)
        page.goto.side_effect = PlaywrightTimeoutError("Navigation timeout")

        with self.assertRaises(FalhaAcessoPaginaError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

        context.close.assert_called_once()
        browser.close.assert_called_once()

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_cleanup_on_price_not_found(self, mock_sync):
        """Assert context and browser are closed even when price extraction fails."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync, "<html>Sem preco</html>")

        with self.assertRaises(PrecoNaoEncontradoError):
            self.extractor.extrair_preco(self.SAMPLE_URL)

        context.close.assert_called_once()
        browser.close.assert_called_once()

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_browser_closed_even_if_context_close_raises(self, mock_sync):
        """Assert browser.close() is still attempted if context.close() raises an exception."""
        p, browser, context, page = self._setup_playwright_mock(mock_sync)
        context.close.side_effect = RuntimeError("Context close error")

        # Extraction should succeed or fail without leaking the browser
        try:
            self.extractor.extrair_preco(self.SAMPLE_URL)
        except Exception:
            pass

        browser.close.assert_called_once()


class TestExtratorAliExpressInterfaceCompliance(BaseAliExpressTest):
    """Verifies that ExtratorAliExpress complies with ExtratorBase and the Strategy Pattern."""

    def test_subclass_of_extrator_base(self):
        """Assert ExtratorAliExpress is a subclass of ExtratorBase."""
        self.assertTrue(issubclass(ExtratorAliExpress, ExtratorBase))

    def test_instance_of_extrator_base(self):
        """Assert ExtratorAliExpress instance is an instance of ExtratorBase."""
        self.assertIsInstance(self.extractor, ExtratorBase)

    def test_extrair_preco_signature(self):
        """Assert extrair_preco method accepts (self, url: str) -> float."""
        sig = inspect.signature(self.extractor.extrair_preco)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["url"])

        url_param = sig.parameters["url"]
        self.assertIn(url_param.kind, (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ))

    @patch("src.extractors.aliexpress.sync_playwright")
    def test_polymorphic_strategy_call(self, mock_sync):
        """Assert extractor can be called via abstract base type reference."""
        self._setup_playwright_mock(mock_sync, self.SAMPLE_HTML_CLEAN)

        base_ref: ExtratorBase = self.extractor
        price = base_ref.extrair_preco(self.SAMPLE_URL)

        self.assertEqual(price, 116.29)

    def test_constants_and_attributes_exposed(self):
        """Assert required constants and class attributes are exposed."""
        self.assertEqual(
            self.extractor.CHROME_ARGS,
            ["--disable-blink-features=AutomationControlled"],
        )
        self.assertEqual(self.extractor.LOCALE, "pt-BR")
        self.assertEqual(self.extractor.VIEWPORT, {"width": 1920, "height": 1080})
        self.assertEqual(
            self.extractor.STEALTH_SCRIPT,
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
        )
        self.assertEqual(NAVIGATION_WAIT_UNTIL, "domcontentloaded")
        self.assertEqual(DEFAULT_NAVIGATION_TIMEOUT_MS, 30000)
        self.assertEqual(DEFAULT_POST_LOAD_WAIT_MS, 3000)


if __name__ == "__main__":
    unittest.main()
