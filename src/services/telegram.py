"""Telegram notification service with resilience, security, and error handling for EconoBot."""

import logging
import re
from typing import Any, Dict, Optional, Set
import requests

from src import config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT: float = 10.0
TELEGRAM_API_BASE: str = "https://api.telegram.org"

KNOWN_PLACEHOLDERS: Set[str] = {
    "your_bot_token_here",
    "your_chat_id_here",
    "your_token_here",
    "your_token",
    "your_chat_id",
    "placeholder",
    "todo",
    "change_me",
    "insert_token_here",
    "<telegram_token>",
    "<telegram_chat_id>",
}


def mask_token(token: Optional[str]) -> str:
    """Mask sensitive bot token for safe logging."""
    if not token:
        return ""
    clean = token.strip()
    if len(clean) <= 8:
        return "***"
    return f"{clean[:4]}...{clean[-4:]}"


def sanitize_url(url: Optional[str]) -> str:
    """Sanitize Telegram endpoint URL by removing the raw bot token."""
    if not url:
        return ""
    return re.sub(r"/bot[^/]+/", "/bot<REDACTED>/", str(url))


def is_valid_credential(value: Optional[str]) -> bool:
    """Check if a credential string is valid (non-empty, non-whitespace, non-placeholder)."""
    if not value or not isinstance(value, str):
        return False
    clean = value.strip().lower()
    if not clean:
        return False
    if clean in KNOWN_PLACEHOLDERS:
        return False
    if clean.startswith("your_") or clean.startswith("<") or clean.endswith("_here"):
        return False
    return True


def formatar_mensagem(url: str, preco_antigo: float, preco_novo: float) -> str:
    """Format clear, informative price drop alert message.

    Args:
        url: The product URL.
        preco_antigo: Previous recorded price.
        preco_novo: Current lower price.

    Returns:
        str: Formatted alert message text.
    """
    diferenca = preco_antigo - preco_novo
    percentual = (diferenca / preco_antigo * 100.0) if preco_antigo > 0 else 0.0

    return (
        "🚨 Alerta de Queda de Preço!\n\n"
        f"Produto: {url}\n"
        f"Preço anterior: R$ {preco_antigo:.2f}\n"
        f"Novo preço: R$ {preco_novo:.2f}\n"
        f"Economia: R$ {diferenca:.2f} ({percentual:.1f}%)"
    )


# =====================================================================
# Domain Exceptions
# =====================================================================

class TelegramError(Exception):
    """Base exception for all Telegram notification service errors."""
    pass


class TelegramConfigError(TelegramError, ValueError):
    """Raised when Telegram credentials (token or chat_id) are missing or placeholders."""
    pass


class TelegramNetworkError(TelegramError):
    """Raised when a network timeout or connection failure occurs."""
    pass


class TelegramAPIError(TelegramError):
    """Raised when the Telegram Bot API returns an HTTP 4xx or 5xx error."""

    def __init__(
        self,
        status_code: int,
        description: str,
        response_data: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(f"Telegram API error {status_code}: {description}")
        self.status_code: int = status_code
        self.description: str = description
        self.response_data: Dict[str, Any] = response_data or {}


# =====================================================================
# Service Class
# =====================================================================

class TelegramService:
    """Service responsible for dispatching price drop alerts via Telegram Bot API."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        base_url: str = TELEGRAM_API_BASE,
        strict: bool = False,
    ):
        """Initialize TelegramService with bot token and chat_id.

        Args:
            token: Telegram Bot token. Defaults to config.TELEGRAM_TOKEN if None.
            chat_id: Telegram target chat ID. Defaults to config.TELEGRAM_CHAT_ID if None.
            timeout: HTTP request timeout in seconds (default 10.0s).
            base_url: Telegram API base URL (default 'https://api.telegram.org').
            strict: If True, validate credentials immediately during initialization
                    and raise TelegramConfigError if invalid.
        """
        if token is None:
            token = config.TELEGRAM_TOKEN
        if chat_id is None:
            chat_id = config.TELEGRAM_CHAT_ID

        self.token: str = str(token).strip() if token is not None else ""
        self.chat_id: str = str(chat_id).strip() if chat_id is not None else ""
        self.timeout: float = float(timeout)
        self.base_url: str = str(base_url).rstrip("/")
        self.last_error: Optional[str] = None

        if strict:
            self.validate_credentials(raise_exception=True)

    @property
    def endpoint(self) -> str:
        """Construct the Telegram API sendMessage URL."""
        return f"{self.base_url}/bot{self.token}/sendMessage"

    @property
    def is_configured(self) -> bool:
        """Check if both token and chat_id are valid non-placeholder strings."""
        return self.validate_credentials(raise_exception=False)

    def validate_credentials(self, raise_exception: bool = False) -> bool:
        """Validate configured token and chat_id.

        Args:
            raise_exception: If True, raise TelegramConfigError on invalid credentials.

        Returns:
            bool: True if both credentials are valid, False otherwise.
        """
        token_ok = is_valid_credential(self.token)
        chat_id_ok = is_valid_credential(self.chat_id)

        if not token_ok or not chat_id_ok:
            reasons = []
            if not token_ok:
                reasons.append(
                    f"TELEGRAM_TOKEN is missing or placeholder ('{mask_token(self.token)}')"
                )
            if not chat_id_ok:
                reasons.append(
                    f"TELEGRAM_CHAT_ID is missing or placeholder ('{self.chat_id}')"
                )
            msg = f"Invalid Telegram configuration: {'; '.join(reasons)}"
            self.last_error = msg

            if raise_exception:
                raise TelegramConfigError(msg)
            return False

        return True

    @staticmethod
    def formatar_mensagem(url: str, preco_antigo: float, preco_novo: float) -> str:
        """Format clear, informative price drop alert message."""
        return formatar_mensagem(url, preco_antigo, preco_novo)

    def enviar_alerta(
        self,
        url: str,
        preco_antigo: float,
        preco_novo: float,
        raise_on_error: bool = False,
    ) -> bool:
        """Send price drop alert to configured Telegram chat.

        Args:
            url: The product URL.
            preco_antigo: Previous recorded price.
            preco_novo: Current lower price.
            raise_on_error: If True, raises exceptions instead of returning False.

        Returns:
            bool: True if alert was dispatched and accepted by Telegram, False otherwise.
        """
        self.last_error = None

        if not self.validate_credentials(raise_exception=raise_on_error):
            logger.warning(
                "Telegram alert skipped for %s: %s", url, self.last_error
            )
            return False

        mensagem = self.formatar_mensagem(url, preco_antigo, preco_novo)
        payload = {
            "chat_id": self.chat_id,
            "text": mensagem,
        }

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
            )

            # Parse JSON body safely
            try:
                data = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError, AttributeError):
                data = None

            # Check HTTP status codes
            if response.status_code != 200:
                desc = (
                    data.get("description", response.text[:200] if hasattr(response, "text") and response.text else f"HTTP {response.status_code}")
                    if isinstance(data, dict)
                    else (response.text[:200] if hasattr(response, "text") and response.text else f"HTTP {response.status_code}")
                )
                err_msg = (
                    f"Telegram API HTTP {response.status_code} "
                    f"(chat_id: {self.chat_id}): {desc}"
                )
                self.last_error = err_msg

                if response.status_code == 429:
                    retry_after = data.get("parameters", {}).get("retry_after") if isinstance(data, dict) else None
                    logger.warning(
                        "Telegram rate limit reached (429). Retry after %s seconds.",
                        retry_after,
                    )
                elif 400 <= response.status_code < 500:
                    logger.error("Telegram client error: %s", sanitize_url(err_msg))
                else:
                    logger.error("Telegram server error: %s", sanitize_url(err_msg))

                if raise_on_error:
                    raise TelegramAPIError(response.status_code, desc, data if isinstance(data, dict) else {})
                return False

            # Non-JSON or malformed body
            if not isinstance(data, dict):
                err_msg = "Telegram API returned non-JSON response"
                self.last_error = err_msg
                logger.error(err_msg)
                if raise_on_error:
                    raise TelegramAPIError(response.status_code, err_msg)
                return False

            # Check Telegram response envelope {"ok": true}
            if not data.get("ok", False):
                desc = data.get("description", "Unknown Telegram rejection")
                err_msg = f"Telegram rejected message (ok=False): {desc}"
                self.last_error = err_msg
                logger.error(err_msg)

                if raise_on_error:
                    raise TelegramAPIError(response.status_code, desc, data)
                return False

            logger.info("Telegram alert sent successfully for %s", url)
            return True

        except requests.exceptions.Timeout as exc:
            err_msg = f"Timeout connecting to Telegram API after {self.timeout}s"
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise TelegramNetworkError(err_msg) from exc
            return False

        except requests.exceptions.ConnectionError as exc:
            err_msg = "Connection error while reaching Telegram API (offline or DNS error)"
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise TelegramNetworkError(err_msg) from exc
            return False

        except requests.exceptions.RequestException as exc:
            err_msg = f"General HTTP request failure: {sanitize_url(str(exc))}"
            self.last_error = err_msg
            logger.error("Telegram request failed: %s", sanitize_url(str(exc)))
            if raise_on_error:
                raise TelegramNetworkError(err_msg) from exc
            return False

        except Exception as exc:
            err_msg = f"Unexpected failure in Telegram service: {exc}"
            self.last_error = err_msg
            logger.error(err_msg)
            if raise_on_error:
                raise TelegramError(err_msg) from exc
            return False
