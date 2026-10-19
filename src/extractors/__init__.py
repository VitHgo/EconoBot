"""Extractors package for EconoBot implementing the Strategy Pattern.

Exports the core strategy interface ExtratorBase, concrete extractors like
ExtratorAliExpress, and the extractor domain exceptions.
"""

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
    DominioNaoSuportadoError,
    ExtractorError,
    ExtractorNetworkError,
    ExtratorBase,
    ExtratorError,
    FalhaAcessoPaginaError,
    InvalidURLError,
    PrecoNaoEncontradoError,
    PriceNotFoundError,
)

__all__ = [
    "ExtratorBase",
    "ExtratorAliExpress",
    "ExtratorError",
    "PrecoNaoEncontradoError",
    "FalhaAcessoPaginaError",
    "DominioNaoSuportadoError",
    "ExtractorError",
    "PriceNotFoundError",
    "ExtractorNetworkError",
    "InvalidURLError",
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
