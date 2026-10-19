"""AliExpress price extractor implementing Playwright Stealth and BeautifulSoup.

Extracts BRL product prices from AliExpress product pages using Playwright with
stealth evasion flags and BeautifulSoup + regex parsing on embedded JSON script tags.
Strictly adheres to Requirement R4 without CSS selectors.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from src.extractors.base import (
    ExtratorBase,
    ExtratorError,
    FalhaAcessoPaginaError,
    PrecoNaoEncontradoError,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Playwright Stealth Configuration Constants (per Requirement R4)
# =============================================================================

DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_LOCALE: str = "pt-BR"
DEFAULT_VIEWPORT: dict[str, int] = {"width": 1920, "height": 1080}
CHROMIUM_STEALTH_ARGS: list[str] = ["--disable-blink-features=AutomationControlled"]
STEALTH_INIT_SCRIPT: str = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"

DEFAULT_NAVIGATION_TIMEOUT_MS: int = 30000
DEFAULT_POST_LOAD_WAIT_MS: int = 3000
NAVIGATION_WAIT_UNTIL: str = "domcontentloaded"

# Regex for extracting BRL price from embedded JSON inside <script> tags
REGEX_PRECO_BRL: re.Pattern[str] = re.compile(
    r'"priceCurrency"\s*:\s*"BRL"\s*,\s*"price"\s*:\s*"([\d\.]+)"'
)


# =============================================================================
# Concrete Strategy Implementation
# =============================================================================

class ExtratorAliExpress(ExtratorBase):
    """Concrete strategy extractor for AliExpress product URLs.

    Uses Playwright with stealth evasions to render pages and bypass bot detection,
    then locates the product price within embedded JSON script tags using
    BeautifulSoup and regular expressions.
    """

    # Class-level attribute references for backward-compatibility and introspection
    PADRAO_PRECO: re.Pattern[str] = REGEX_PRECO_BRL
    CHROME_ARGS: list[str] = CHROMIUM_STEALTH_ARGS
    USER_AGENT: str = DEFAULT_USER_AGENT
    LOCALE: str = DEFAULT_LOCALE
    VIEWPORT: dict[str, int] = DEFAULT_VIEWPORT
    STEALTH_SCRIPT: str = STEALTH_INIT_SCRIPT

    def __init__(
        self,
        headless: bool = True,
        timeout: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        wait_time: int = DEFAULT_POST_LOAD_WAIT_MS,
    ) -> None:
        """Initialize ExtratorAliExpress with browser execution parameters.

        Args:
            headless: Whether to run Chromium in headless mode (default: True).
            timeout: Page navigation timeout in milliseconds (default: 30000).
            wait_time: Post-load wait timeout in milliseconds (default: 3000).
        """
        self.headless: bool = headless
        self.timeout: int = timeout
        self.wait_time: int = wait_time

    def _obter_html(self, url: str) -> str:
        """Retrieve raw page HTML using Playwright with stealth evasions.

        Args:
            url: Validated target product URL.

        Returns:
            str: Raw HTML content of the page.

        Raises:
            FalhaAcessoPaginaError: If navigation fails or times out.
            ExtratorError: On unexpected browser runtime failures.
        """
        browser = None
        context = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=CHROMIUM_STEALTH_ARGS,
                )
                try:
                    context = browser.new_context(
                        user_agent=DEFAULT_USER_AGENT,
                        locale=DEFAULT_LOCALE,
                        viewport=DEFAULT_VIEWPORT,
                    )
                    try:
                        page = context.new_page()
                        page.add_init_script(STEALTH_INIT_SCRIPT)
                        page.goto(
                            url,
                            wait_until=NAVIGATION_WAIT_UNTIL,
                            timeout=self.timeout,
                        )
                        page.wait_for_timeout(self.wait_time)
                        return page.content()
                    finally:
                        if context is not None:
                            context.close()
                finally:
                    if browser is not None:
                        browser.close()
        except (PrecoNaoEncontradoError, ValueError):
            raise
        except (PlaywrightTimeoutError, TimeoutError, PlaywrightError) as exc:
            raise FalhaAcessoPaginaError(
                f"Falha ao carregar a página {url}: {exc}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, ExtratorError):
                raise
            raise FalhaAcessoPaginaError(
                f"Falha ao carregar a página {url}: {exc}"
            ) from exc

    @classmethod
    def extrair_preco_do_html(cls, html: str, url: str = "") -> float:
        """Parse HTML and extract price in BRL using BeautifulSoup without CSS selectors.

        Iterates over all <script> tags and extracts the BRL price float from JSON
        matching REGEX_PRECO_BRL.

        Args:
            html: Raw page HTML string.
            url: Target URL for error contextualization (optional).

        Returns:
            float: Extracted product price in BRL.

        Raises:
            PrecoNaoEncontradoError: If no script tag contains the BRL price pattern.
        """
        if not html or not isinstance(html, str) or not html.strip():
            raise PrecoNaoEncontradoError(f"Preço não encontrado para a URL: {url}")

        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script")

        for script in scripts:
            conteudo = script.string or script.get_text() or ""
            if not conteudo:
                continue

            match = REGEX_PRECO_BRL.search(conteudo)
            if match:
                price_str = match.group(1)
                try:
                    return float(price_str)
                except (ValueError, TypeError) as exc:
                    raise PrecoNaoEncontradoError(
                        f"Preço não encontrado para a URL: {url}"
                    ) from exc

        raise PrecoNaoEncontradoError(f"Preço não encontrado para a URL: {url}")

    # Alias for decoupling and naming flexibility
    _extrair_preco_do_html = extrair_preco_do_html

    def extrair_preco(self, url: str) -> float:
        """Extract product price in BRL as a float from the given AliExpress URL.

        Args:
            url: Product page URL on AliExpress.

        Returns:
            float: Product price in BRL.

        Raises:
            ValueError: If url is None, empty, or whitespace-only.
            FalhaAcessoPaginaError: If page loading fails or times out.
            PrecoNaoEncontradoError: If BRL price pattern is not found in HTML scripts.
            ExtratorError: On general extraction errors.
        """
        clean_url = self.validar_url(url)
        html = self._obter_html(clean_url)
        return self.extrair_preco_do_html(html, clean_url)


__all__ = [
    "ExtratorAliExpress",
    "CHROMIUM_STEALTH_ARGS",
    "DEFAULT_USER_AGENT",
    "DEFAULT_LOCALE",
    "DEFAULT_VIEWPORT",
    "STEALTH_INIT_SCRIPT",
    "NAVIGATION_WAIT_UNTIL",
    "DEFAULT_NAVIGATION_TIMEOUT_MS",
    "DEFAULT_POST_LOAD_WAIT_MS",
    "REGEX_PRECO_BRL",
]
