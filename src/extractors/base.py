"""Extraction Strategy Core Interface and Domain Exceptions for EconoBot.

Defines the ExtratorBase Abstract Base Class (Strategy Pattern) and
the domain exception hierarchy for web scrapers.
"""

import abc
import inspect
from typing import Any


# =====================================================================
# Domain Exceptions
# =====================================================================

class ExtratorError(Exception):
    """Base exception for all price extractor errors."""
    pass


class PrecoNaoEncontradoError(ExtratorError, ValueError):
    """Raised when the product price cannot be located or parsed in the page content."""
    pass


class FalhaAcessoPaginaError(ExtratorError):
    """Raised when the target page cannot be reached, loaded, or times out."""
    pass


class DominioNaoSuportadoError(ExtratorError, ValueError):
    """Raised when no extractor strategy is registered for the specified URL domain."""
    pass


# Backward-compatibility / alternative aliases
ExtractorError = ExtratorError
PriceNotFoundError = PrecoNaoEncontradoError
FalhaAcessoPaginaErrorAlias = FalhaAcessoPaginaError
ExtractorNetworkError = FalhaAcessoPaginaError


class InvalidURLError(ExtratorError, ValueError):
    """Raised when the provided URL is malformed, blank, or invalid."""
    pass


# =====================================================================
# Strategy Interface
# =====================================================================

class ExtratorBase(abc.ABC):
    """Abstract Base Class defining the strategy interface for product price extraction.

    All store-specific scrapers (e.g. ExtratorAliExpress) must inherit from ExtratorBase
    and implement the extrair_preco method according to the Strategy Pattern.
    """

    @staticmethod
    def validar_url(url: str) -> str:
        """Validate that the given URL is a non-empty string.

        Args:
            url (str): The product URL to validate.

        Returns:
            str: The stripped URL string.

        Raises:
            ValueError: If the URL is None, empty, or whitespace-only.
        """
        if not url or not isinstance(url, str):
            raise ValueError("URL do produto não pode ser nula ou vazia.")
        clean = url.strip()
        if not clean:
            raise ValueError("URL do produto não pode conter apenas espaços em branco.")
        return clean

    @abc.abstractmethod
    def extrair_preco(self, url: str) -> float:
        """Extract product price in BRL as a float from the given product URL.

        Args:
            url (str): The complete product page URL.

        Returns:
            float: The extracted price as a floating-point number in Brazilian Reais (BRL).

        Raises:
            ExtratorError: If extraction fails due to scraping, parsing, or network errors.
            PrecoNaoEncontradoError: If the price cannot be located on the page.
            FalhaAcessoPaginaError: If page loading fails or times out.
            DominioNaoSuportadoError: If the URL domain is not supported.
            ValueError: If the URL is invalid or empty.
            NotImplementedError: If invoked directly via super() without concrete logic.
        """
        raise NotImplementedError("Subclasses must implement extrair_preco(url)")


__all__ = [
    "ExtratorBase",
    "ExtratorError",
    "PrecoNaoEncontradoError",
    "FalhaAcessoPaginaError",
    "DominioNaoSuportadoError",
    "ExtractorError",
    "PriceNotFoundError",
    "ExtractorNetworkError",
    "InvalidURLError",
]
