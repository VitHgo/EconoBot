"""Extractor Registry and Domain Strategy Routing for EconoBot.

Maps product URL domains (e.g., 'aliexpress.com') to concrete ExtratorBase
strategy implementations using urllib.parse.urlparse. Supports case-insensitive
matching, full subdomain resolution, dynamic extractor registration, and
custom instantiation parameters.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Type
from urllib.parse import urlparse

from src.extractors.aliexpress import ExtratorAliExpress
from src.extractors.base import DominioNaoSuportadoError, ExtratorBase, InvalidURLError

logger = logging.getLogger(__name__)

# =============================================================================
# Default Registry Configuration
# =============================================================================

_DEFAULT_REGISTRY: dict[str, type[ExtratorBase]] = {
    "aliexpress.com": ExtratorAliExpress,
}

_REGISTRY: dict[str, type[ExtratorBase]] = dict(_DEFAULT_REGISTRY)


# =============================================================================
# Domain Helpers
# =============================================================================

def extrair_dominio(url: str) -> str:
    """Extrai o hostname (domínio) em minúsculas a partir de uma URL.

    Suporta URLs completas com esquema (http, https), URLs sem esquema,
    URLs com portas e credenciais, e parâmetros de consulta.

    Args:
        url: URL do produto a ser analisada.

    Returns:
        str: Hostname normalizado em letras minúsculas sem portas ou caminhos.

    Raises:
        InvalidURLError: Se a URL for nula, vazia ou inválida.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL do produto não pode ser nula ou vazia.")
    clean = url.strip()
    if not clean:
        raise InvalidURLError("URL do produto não pode conter apenas espaços em branco.")

    # Se a URL não contiver esquema, prefixa com https:// para o urlparse interpretar o netloc
    prep = clean if "://" in clean else f"https://{clean}"
    try:
        parsed = urlparse(prep)
        hostname = (parsed.hostname or "").lower().strip()
        if not hostname:
            raise InvalidURLError(f"Não foi possível extrair domínio válido da URL: {url}")
        return hostname
    except (InvalidURLError, ValueError):
        raise
    except Exception as exc:
        raise InvalidURLError(f"URL inválida: {url}") from exc


def _normalizar_dominio(dominio: str) -> str:
    """Normaliza uma chave de domínio para o registro interno.

    Args:
        dominio: String representando o domínio (ex: 'aliexpress.com', '  .ALIEXPRESS.COM  ').

    Returns:
        str: Domínio limpo e normalizado em minúsculas sem pontos à esquerda.

    Raises:
        ValueError: Se o domínio for nulo, vazio ou inválido.
    """
    if not dominio or not isinstance(dominio, str):
        raise ValueError("Domínio não pode ser nulo ou vazio.")

    clean = dominio.strip().lower()
    if "://" in clean:
        try:
            parsed = urlparse(clean)
            clean = (parsed.hostname or clean).lower()
        except Exception:
            pass

    clean = clean.strip().lstrip(".")
    if "/" in clean:
        clean = clean.split("/", 1)[0]
    if ":" in clean:
        clean = clean.split(":", 1)[0]

    if not clean:
        raise ValueError("Domínio não pode ser vazio após normalização.")

    return clean


# =============================================================================
# Registry Management API
# =============================================================================

def registrar_extrator(dominio: str, extrator_cls: type[ExtratorBase]) -> None:
    """Registra uma nova estratégia de extração vinculada a um domínio.

    Permite estender dinamicamente o catálogo de estratégias de extração do EconoBot.

    Args:
        dominio: Domínio da loja (ex: 'shopee.com.br', 'amazon.com.br').
        extrator_cls: Classe concreta que herda de ExtratorBase.

    Raises:
        ValueError: Se o domínio for vazio ou inválido.
        TypeError: Se extrator_cls não for uma classe ou não herdar de ExtratorBase.
    """
    norm_dom = _normalizar_dominio(dominio)

    if not isinstance(extrator_cls, type) or not issubclass(extrator_cls, ExtratorBase):
        raise TypeError(
            f"extrator_cls deve ser uma classe derivada de ExtratorBase. Obtido: {extrator_cls!r}"
        )

    _REGISTRY[norm_dom] = extrator_cls
    logger.debug("Extrator %s registrado para o domínio '%s'", extrator_cls.__name__, norm_dom)


def remover_extrator(dominio: str) -> Optional[type[ExtratorBase]]:
    """Remove o registro de um domínio, retornando a classe removida se existir.

    Args:
        dominio: Domínio a ser removido.

    Returns:
        Optional[type[ExtratorBase]]: Classe desregistrada ou None se não encontrada.
    """
    try:
        norm_dom = _normalizar_dominio(dominio)
    except ValueError:
        return None
    return _REGISTRY.pop(norm_dom, None)


def resetar_registro() -> None:
    """Restaura o registro para as estratégias padrão do sistema (AliExpress).

    Útil para isolamento e limpeza entre execuções de testes unitários.
    """
    _REGISTRY.clear()
    _REGISTRY.update(_DEFAULT_REGISTRY)


redefinir_registro = resetar_registro


def listar_dominios_suportados() -> list[str]:
    """Retorna a lista de domínios atualmente suportados pelo registro.

    Returns:
        list[str]: Lista ordenada de domínios registrados.
    """
    return sorted(_REGISTRY.keys())


# =============================================================================
# Strategy Resolution & Resolution Logic
# =============================================================================

def obter_classe_extrator(url: str) -> type[ExtratorBase]:
    """Resolve a classe concreta de estratégia para a URL fornecida sem instanciá-la.

    Analisa o domínio da URL com urllib.parse.urlparse e busca correspondência
    no _REGISTRY, suportando subdomínios (ex: 'pt.aliexpress.com' mapeia para 'aliexpress.com').

    Args:
        url: URL completa do produto.

    Returns:
        type[ExtratorBase]: Classe do extrator correspondente ao domínio.

    Raises:
        DominioNaoSuportadoError: Se o domínio não estiver mapeado ou a URL for inválida.
    """
    try:
        hostname = extrair_dominio(url)
    except (InvalidURLError, ValueError, TypeError):
        raise DominioNaoSuportadoError(f"Domínio não suportado para extração: {url}")

    if not hostname:
        raise DominioNaoSuportadoError(f"Domínio não suportado para extração: {url}")

    # Ordena domínios registrados por tamanho decrescente para permitir casamento mais específico primeiro
    for reg_domain in sorted(_REGISTRY.keys(), key=len, reverse=True):
        reg = reg_domain.lower().lstrip(".")
        if hostname == reg or hostname.endswith("." + reg):
            return _REGISTRY[reg_domain]

    raise DominioNaoSuportadoError(f"Domínio não suportado para extração: {url}")


def obter_extrator(url: str, *args: Any, **kwargs: Any) -> ExtratorBase:
    """Instancia e retorna o extrator correspondente ao domínio da URL.

    Utiliza urllib.parse.urlparse para inspecionar o domínio e seleciona
    a estratégia concreta adequada (ex: 'aliexpress.com' -> ExtratorAliExpress).

    Args:
        url: URL completa do produto a ser consultado.
        *args: Argumentos posicionais encaminhados ao construtor do extrator.
        **kwargs: Argumentos nomeados encaminhados ao construtor do extrator (ex: headless, timeout).

    Returns:
        ExtratorBase: Instância configurada da estratégia concreta de extração.

    Raises:
        DominioNaoSuportadoError: Se o domínio da URL não estiver suportado ou a URL for inválida.
    """
    cls = obter_classe_extrator(url)
    return cls(*args, **kwargs)


__all__ = [
    "_DEFAULT_REGISTRY",
    "_REGISTRY",
    "extrair_dominio",
    "registrar_extrator",
    "remover_extrator",
    "resetar_registro",
    "redefinir_registro",
    "listar_dominios_suportados",
    "obter_classe_extrator",
    "obter_extrator",
]
