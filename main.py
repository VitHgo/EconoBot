#!/usr/bin/env python3
"""Main Entrypoint and Orchestrator for EconoBot.

Executes a one-off batch scan of registered products, extracts prices using
appropriate domain strategies (Strategy Pattern), tracks historical minimums
(week, month, year), and dispatches Telegram price drop alerts.

Strictly designed for one-off Cron execution:
- No while True loops
- No infinite loops
- No scheduling libraries (schedule, apscheduler, etc.)
- Exits cleanly with status code 0 upon completing one pass
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional

from src import config
from src.db.repository import ProdutoRepository
from src.extractors.base import DominioNaoSuportadoError, ExtratorBase, ExtratorError
from src.extractors.registry import obter_extrator
from src.services.telegram import TelegramService

logger = logging.getLogger("econobot")


# =============================================================================
# Core Business Logic Orchestration
# =============================================================================

def executar_orquestrador(
    db_path: Optional[str] = None,
    repository: Optional[ProdutoRepository] = None,
    telegram_service: Optional[TelegramService] = None,
    extractor_resolver: Optional[Callable[[str], ExtratorBase]] = None,
    extractor_factory: Optional[Callable[[str], ExtratorBase]] = None,
) -> Dict[str, Any]:
    """Execute a single-pass one-off price monitoring scan across all registered products.

    Args:
        db_path: Optional path to SQLite database. Used if repository is not injected.
        repository: Optional injected ProdutoRepository instance (e.g. in-memory for testing).
        telegram_service: Optional injected TelegramService instance.
        extractor_resolver: Optional callable resolving ExtratorBase instances from URLs.
        extractor_factory: Optional callable resolving ExtratorBase instances from URLs (alias).

    Returns:
        Dict[str, Any]: Comprehensive summary metrics and per-product execution details.
    """
    owns_repo = False
    if repository is None:
        target_db = db_path or getattr(config, "DATABASE_PATH", getattr(config, "DB_PATH", "econobot.db"))
        repository = ProdutoRepository(db_path=target_db)
        repository.init_db()
        owns_repo = True
    else:
        repository.init_db()

    if telegram_service is None:
        telegram_service = TelegramService()

    resolver = extractor_resolver or extractor_factory or obter_extrator

    try:
        # Fetch registered products
        produtos = repository.listar_produtos()

        # Handle empty database / optional environment seed
        if not produtos:
            seed_url = os.getenv("SEED_URL") or os.getenv("INITIAL_PRODUCT_URL")
            if seed_url:
                logger.info("Banco de dados vazio. Semeando URL inicial: %s", seed_url)
                repository.inserir_produto(seed_url)
                produtos = repository.listar_produtos()
            else:
                logger.info("Nenhum produto cadastrado no banco de dados para monitoramento.")
                return {
                    "total": 0,
                    "total_produtos": 0,
                    "sucesso": 0,
                    "sucessos": 0,
                    "erros": 0,
                    "primeiras_leituras": 0,
                    "primeira_leitura": 0,
                    "quedas_detectadas": 0,
                    "precos_inalterados_ou_maiores": 0,
                    "alertas_enviados": 0,
                    "alertas_falhados": 0,
                    "detalhes": [],
                }

        # Initialize counters
        total = len(produtos)
        sucesso = 0
        erros = 0
        primeiras_leituras = 0
        quedas_detectadas = 0
        precos_inalterados_ou_maiores = 0
        alertas_enviados = 0
        alertas_falhados = 0
        detalhes: List[Dict[str, Any]] = []

        logger.info("Iniciando monitoramento de preços para %d produtos cadastrados.", total)

        # Sequential single-pass iteration
        for produto in produtos:
            url = produto["url"]
            ultimo_preco = produto["ultimo_preco"]

            try:
                # 1. Resolve strategy extractor
                extrator = resolver(url)

                # 2. Extract current price
                novo_preco = extrator.extrair_preco(url)
                novo_preco = float(novo_preco)

                # 3. Decision Matrix (Requirement R5)
                if ultimo_preco is None:
                    # Case A: First reading (ultimo_preco is None)
                    # Updates database, DO NOT send alert!
                    logger.info(
                        "Primeira leitura para %s: R$ %.2f. Gravando no banco de dados sem envio de alerta.",
                        url,
                        novo_preco,
                    )
                    repository.atualizar_preco(url, novo_preco)
                    primeiras_leituras += 1
                    sucesso += 1
                    detalhes.append({
                        "url": url,
                        "status": "primeira_leitura",
                        "preco_anterior": None,
                        "novo_preco": novo_preco,
                        "alerta_enviado": False,
                        "erro": None,
                    })

                elif novo_preco < ultimo_preco:
                    # Case B: Price drop (novo_preco < ultimo_preco)
                    # Sends alert and updates database
                    logger.info(
                        "Queda de preço detectada para %s: R$ %.2f -> R$ %.2f (Economia: R$ %.2f)",
                        url,
                        ultimo_preco,
                        novo_preco,
                        ultimo_preco - novo_preco,
                    )
                    quedas_detectadas += 1

                    alerta_ok = False
                    try:
                        alerta_ok = bool(
                            telegram_service.enviar_alerta(
                                url=url,
                                preco_antigo=ultimo_preco,
                                preco_novo=novo_preco,
                            )
                        )
                        if alerta_ok:
                            alertas_enviados += 1
                            logger.info("Alerta de queda enviado via Telegram com sucesso para %s.", url)
                        else:
                            alertas_falhados += 1
                            logger.warning("Falha ou pulo no envio de alerta Telegram para %s.", url)
                    except Exception as alert_exc:
                        alertas_falhados += 1
                        logger.error(
                            "Erro inesperado ao enviar alerta Telegram para %s: %s",
                            url,
                            alert_exc,
                        )

                    # Update database with new lower price
                    repository.atualizar_preco(url, novo_preco)
                    sucesso += 1
                    detalhes.append({
                        "url": url,
                        "status": "queda",
                        "preco_anterior": ultimo_preco,
                        "novo_preco": novo_preco,
                        "alerta_enviado": alerta_ok,
                        "erro": None,
                    })

                else:
                    # Case C: Price rise or unchanged (novo_preco >= ultimo_preco)
                    # Updates database, DO NOT send alert!
                    logger.info(
                        "Preço estável ou em alta para %s: R$ %.2f -> R$ %.2f. Atualizando banco sem envio de alerta.",
                        url,
                        ultimo_preco,
                        novo_preco,
                    )
                    repository.atualizar_preco(url, novo_preco)
                    precos_inalterados_ou_maiores += 1
                    sucesso += 1
                    detalhes.append({
                        "url": url,
                        "status": "estavel",
                        "preco_anterior": ultimo_preco,
                        "novo_preco": novo_preco,
                        "alerta_enviado": False,
                        "erro": None,
                    })

            except (ExtratorError, Exception) as exc:
                # Scraper, network, or domain failure on individual product
                erros += 1
                logger.error("Falha ao processar URL '%s': %s", url, exc)
                detalhes.append({
                    "url": url,
                    "status": "erro",
                    "preco_anterior": ultimo_preco,
                    "novo_preco": None,
                    "alerta_enviado": False,
                    "erro": str(exc),
                })
                continue

        logger.info(
            "Orquestrador finalizado: %d produtos avaliados (%d sucessos, %d erros, %d alertas enviados).",
            total,
            sucesso,
            erros,
            alertas_enviados,
        )

        return {
            "total": total,
            "total_produtos": total,
            "sucesso": sucesso,
            "sucessos": sucesso,
            "erros": erros,
            "primeiras_leituras": primeiras_leituras,
            "primeira_leitura": primeiras_leituras,
            "quedas_detectadas": quedas_detectadas,
            "precos_inalterados_ou_maiores": precos_inalterados_ou_maiores,
            "alertas_enviados": alertas_enviados,
            "alertas_falhados": alertas_falhados,
            "detalhes": detalhes,
        }

    finally:
        if owns_repo and repository is not None:
            repository.close()


# =============================================================================
# CLI Entrypoint
# =============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for executing EconoBot in one-off mode.

    Args:
        argv: Optional list of command-line arguments. If None, defaults to empty
              list when invoked programmatically to prevent test-runner argument collision.

    Returns:
        int: Process exit code (0 for success, 1 for fatal error).
    """
    if argv is None:
        argv = []

    parser = argparse.ArgumentParser(
        prog="econobot",
        description="EconoBot: One-off Cron price monitor and Telegram alerter.",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=None,
        help="Path to SQLite database file (defaults to DB_PATH in .env or econobot.db)",
    )
    parser.add_argument(
        "--add-url",
        dest="add_url",
        action="append",
        default=[],
        help="Add one or more product URLs to the database before executing scan",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed DEBUG logging output",
    )
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ensure environment configuration is loaded
    config.load_config()

    target_db = args.db_path or getattr(config, "DATABASE_PATH", getattr(config, "DB_PATH", "econobot.db"))

    # Add URLs if specified via command line
    if args.add_url:
        repo = ProdutoRepository(db_path=target_db)
        repo.init_db()
        for url_to_add in args.add_url:
            clean = url_to_add.strip()
            if clean:
                repo.inserir_produto(clean)
                logger.info("URL inserida no banco de dados via CLI: %s", clean)
        repo.close()

    # Execute one-off orchestration
    try:
        resultado = executar_orquestrador(db_path=target_db)
        print("\n" + "=" * 60)
        print("          RELATÓRIO DE EXECUÇÃO - ECONOBOT")
        print("=" * 60)
        print(f"Total de produtos avaliados  : {resultado.get('total', 0)}")
        print(f"Sucessos                      : {resultado.get('sucesso', 0)}")
        print(f"Erros                         : {resultado.get('erros', 0)}")
        print(f"Primeiras leituras            : {resultado.get('primeiras_leituras', 0)}")
        print(f"Quedas de preço detectadas    : {resultado.get('quedas_detectadas', 0)}")
        print(f"Alertas enviados via Telegram : {resultado.get('alertas_enviados', 0)}")
        print(f"Preços estáveis ou em alta    : {resultado.get('precos_inalterados_ou_maiores', 0)}")
        print("=" * 60 + "\n")
        return 0
    except Exception as exc:
        logger.critical("Falha fatal na execução do orquestrador: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
