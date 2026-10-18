"""Extractors package for EconoBot implementing the Strategy Pattern.

Exports the core strategy interface ExtratorBase and the extractor domain exceptions.
Concrete extractors and registry are exposed in downstream milestones.
"""

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
    "ExtratorError",
    "PrecoNaoEncontradoError",
    "FalhaAcessoPaginaError",
    "DominioNaoSuportadoError",
    "ExtractorError",
    "PriceNotFoundError",
    "ExtractorNetworkError",
    "InvalidURLError",
]
