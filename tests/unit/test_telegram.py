"""Unit tests for Telegram notification service and message formatting.

Tests cover:
1. Service initialization with explicit credentials, config fallback, whitespace stripping, and custom options.
2. Credential validation, placeholder detection, and strict initialization mode.
3. Message formatting with URL, prices, currency precision, and division by zero protection.
4. Successful alert dispatch (HTTP 200, ok=True) with endpoint URL, headers, payload, and timeout verification.
5. Missing and placeholder credentials handling without making network calls.
6. HTTP client and server errors (400, 401, 403, 404, 429, 500, 502) returning False without crashing.
7. Telegram API rejection (HTTP 200, ok=False) handling.
8. Network exceptions (Timeout, ConnectionError, generic RequestException) handling.
9. Malformed JSON response body handling.
10. Security utilities (token masking and URL sanitization).
11. Package exports in src.services.
12. 100% offline socket isolation guarantee.
"""

import socket
import unittest
from unittest.mock import MagicMock, patch
import requests

from src import config
from src.services import (
    TelegramService,
    TelegramError,
    TelegramConfigError,
    TelegramNetworkError,
    TelegramAPIError,
    formatar_mensagem,
    mask_token,
    sanitize_url,
    is_valid_credential,
)


class TestTelegramServiceInitialization(unittest.TestCase):
    """Verifies constructor behavior, parameter binding, and config fallback."""

    def test_init_with_explicit_credentials(self):
        """Service stores explicitly provided token and chat_id."""
        service = TelegramService(token="123456:ABC-DEF", chat_id="987654321")
        self.assertEqual(service.token, "123456:ABC-DEF")
        self.assertEqual(service.chat_id, "987654321")
        self.assertEqual(
            service.endpoint,
            "https://api.telegram.org/bot123456:ABC-DEF/sendMessage",
        )
        self.assertEqual(service.timeout, 10.0)

    def test_init_defaults_to_config(self):
        """Service retrieves credentials from src.config when None is passed."""
        with patch.object(config, "TELEGRAM_TOKEN", "config_token_111"), \
             patch.object(config, "TELEGRAM_CHAT_ID", "config_chat_222"):
            service = TelegramService()
            self.assertEqual(service.token, "config_token_111")
            self.assertEqual(service.chat_id, "config_chat_222")
            self.assertEqual(
                service.endpoint,
                "https://api.telegram.org/botconfig_token_111/sendMessage",
            )

    def test_init_strips_whitespace(self):
        """Service strips leading and trailing whitespace from credentials."""
        service = TelegramService(token="  token_with_spaces  ", chat_id="  123456  ")
        self.assertEqual(service.token, "token_with_spaces")
        self.assertEqual(service.chat_id, "123456")

    def test_init_custom_timeout_and_base_url(self):
        """Service allows custom timeout and base URL configuration."""
        service = TelegramService(
            token="tok",
            chat_id="cid",
            timeout=5.5,
            base_url="https://custom-telegram.proxy.org",
        )
        self.assertEqual(service.timeout, 5.5)
        self.assertEqual(
            service.endpoint,
            "https://custom-telegram.proxy.org/bottok/sendMessage",
        )


class TestTelegramCredentialsValidation(unittest.TestCase):
    """Verifies credential validation, placeholder detection, and error behavior."""

    def test_is_configured_true_for_valid_credentials(self):
        """is_configured returns True for valid credentials."""
        service = TelegramService(token="12345:TOKEN", chat_id="98765")
        self.assertTrue(service.is_configured)
        self.assertTrue(service.validate_credentials(raise_exception=False))

    def test_placeholder_credentials_detected(self):
        """Placeholders from .env.example are detected as invalid."""
        service = TelegramService(
            token="your_bot_token_here",
            chat_id="your_chat_id_here",
        )
        self.assertFalse(service.is_configured)
        self.assertFalse(service.validate_credentials(raise_exception=False))
        self.assertIn("placeholder", service.last_error.lower())

    def test_strict_mode_raises_on_invalid_credentials(self):
        """Strict mode raises TelegramConfigError on initialization."""
        with self.assertRaises(TelegramConfigError):
            TelegramService(token="", chat_id="123", strict=True)

        with self.assertRaises(TelegramConfigError):
            TelegramService(token="your_bot_token_here", chat_id="123", strict=True)

    def test_config_error_inherits_from_value_error(self):
        """TelegramConfigError is a subclass of ValueError."""
        with self.assertRaises(ValueError):
            TelegramService(token="", chat_id="", strict=True)

    @patch("requests.post")
    def test_enviar_alerta_missing_token_returns_false_without_request(self, mock_post):
        """Empty token returns False and prevents outbound HTTP request."""
        service = TelegramService(token="", chat_id="12345")
        result = service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        mock_post.assert_not_called()
        self.assertIn("TELEGRAM_TOKEN", service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_missing_chat_id_returns_false_without_request(self, mock_post):
        """Empty chat_id returns False and prevents outbound HTTP request."""
        service = TelegramService(token="tok_123", chat_id="")
        result = service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        mock_post.assert_not_called()
        self.assertIn("TELEGRAM_CHAT_ID", service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_placeholder_returns_false_without_request(self, mock_post):
        """Placeholder credentials return False without HTTP call."""
        service = TelegramService(token="your_bot_token_here", chat_id="your_chat_id_here")
        result = service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        mock_post.assert_not_called()
        self.assertIn("placeholder", service.last_error.lower())

    @patch("requests.post")
    def test_enviar_alerta_whitespace_only_credentials_return_false(self, mock_post):
        """Whitespace-only credentials return False without HTTP call."""
        service = TelegramService(token="   ", chat_id="   ")
        result = service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_enviar_alerta_none_credentials_with_empty_config(self, mock_post):
        """None credentials with empty config return False without HTTP call."""
        with patch.object(config, "TELEGRAM_TOKEN", ""), \
             patch.object(config, "TELEGRAM_CHAT_ID", ""):
            service = TelegramService(token=None, chat_id=None)
            result = service.enviar_alerta("https://test.com", 100.0, 80.0)
            self.assertFalse(result)
            mock_post.assert_not_called()


class TestTelegramMessageFormatting(unittest.TestCase):
    """Verifies message construction, currency representation, and edge cases."""

    def test_formatar_mensagem_contains_all_required_elements(self):
        """Formatted alert text contains URL, old price, new price, and discount info."""
        url = "https://pt.aliexpress.com/item/1005006240404398.html"
        msg = TelegramService.formatar_mensagem(url=url, preco_antigo=150.00, preco_novo=120.00)

        self.assertIn(url, msg)
        self.assertIn("150.00", msg)
        self.assertIn("120.00", msg)
        self.assertIn("30.00", msg)
        self.assertIn("20.0%", msg)
        self.assertTrue(any(k in msg for k in ("Alerta", "Queda", "Preço")))

    def test_module_level_formatar_mensagem(self):
        """formatar_mensagem can also be invoked as a module-level function."""
        url = "https://example.com/product"
        msg = formatar_mensagem(url=url, preco_antigo=200.0, preco_novo=150.0)
        self.assertIn(url, msg)
        self.assertIn("200.00", msg)
        self.assertIn("150.00", msg)

    def test_formatar_mensagem_decimal_precision(self):
        """Single-decimal and multi-decimal floats are formatted to exactly 2 decimals."""
        msg = TelegramService.formatar_mensagem("https://test.com", preco_antigo=129.9, preco_novo=89.95)
        self.assertIn("129.90", msg)
        self.assertIn("89.95", msg)
        self.assertNotIn("129.9 ", msg)

    def test_formatar_mensagem_integer_floats(self):
        """Whole-number floats are formatted with two trailing zeros."""
        msg = TelegramService.formatar_mensagem("https://test.com", preco_antigo=100.0, preco_novo=80.0)
        self.assertIn("100.00", msg)
        self.assertIn("80.00", msg)

    def test_formatar_mensagem_division_by_zero_safety(self):
        """Zero initial price avoids ZeroDivisionError and formats safely."""
        msg = TelegramService.formatar_mensagem("https://test.com", preco_antigo=0.0, preco_novo=0.0)
        self.assertIn("0.00", msg)
        self.assertIn("0.0%", msg)

    def test_formatar_mensagem_complex_url_preservation(self):
        """Complex URL with parameters and fragment is fully retained in message."""
        url = "https://aliexpress.com/item/100.html?spm=a2g0o.cart.0.0.abc&pvid=xyz_123#nav-details"
        msg = TelegramService.formatar_mensagem(url=url, preco_antigo=50.0, preco_novo=40.0)
        self.assertIn(url, msg)


class TestTelegramAlertDispatch(unittest.TestCase):
    """Verifies enviar_alerta HTTP execution, payload structure, and response handling."""

    def setUp(self):
        self.service = TelegramService(token="123456:TEST_TOKEN", chat_id="999888")

    @patch("requests.post")
    def test_enviar_alerta_success_http_200(self, mock_post):
        """Successful alert sends HTTP POST to endpoint with valid JSON payload and returns True."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 12345}}
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta(
            url="https://aliexpress.com/item/100.html",
            preco_antigo=200.0,
            preco_novo=150.0,
        )

        self.assertTrue(result)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args

        # Verify endpoint URL
        self.assertEqual(args[0], "https://api.telegram.org/bot123456:TEST_TOKEN/sendMessage")

        # Verify JSON payload
        self.assertIn("json", kwargs)
        payload = kwargs["json"]
        self.assertEqual(payload["chat_id"], "999888")
        self.assertIn("https://aliexpress.com/item/100.html", payload["text"])
        self.assertIn("200.00", payload["text"])
        self.assertIn("150.00", payload["text"])

        # Verify timeout kwarg
        self.assertEqual(kwargs.get("timeout"), 10.0)

    @patch("requests.post")
    def test_enviar_alerta_api_rejected_with_200_ok_false(self, mock_post):
        """Returns False when Telegram API responds with HTTP 200 but ok=False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 404,
            "description": "Not Found: chat not found",
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        self.assertIn("chat not found", self.service.last_error)


class TestTelegramHttpFailures(unittest.TestCase):
    """Verifies that HTTP 4xx and 5xx error responses return False without unhandled exceptions."""

    def setUp(self):
        self.service = TelegramService(token="12345:TOKEN", chat_id="98765")

    @patch("requests.post")
    def test_enviar_alerta_http_400_bad_request(self, mock_post):
        """HTTP 400 Bad Request is caught and returns False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 400
        mock_resp.ok = False
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: chat not found",
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("chat not found", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_http_401_unauthorized(self, mock_post):
        """HTTP 401 Unauthorized is caught and returns False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 401
        mock_resp.ok = False
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 401,
            "description": "Unauthorized",
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("Unauthorized", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_http_403_forbidden(self, mock_post):
        """HTTP 403 Forbidden is caught and returns False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 403
        mock_resp.ok = False
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 403,
            "description": "Forbidden: bot was blocked by the user",
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("bot was blocked", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_http_404_not_found(self, mock_post):
        """HTTP 404 Not Found is caught and returns False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 404
        mock_resp.ok = False
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 404,
            "description": "Not Found",
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("404", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_http_429_rate_limited(self, mock_post):
        """HTTP 429 Too Many Requests is caught and logged."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 429
        mock_resp.ok = False
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests: retry after 5",
            "parameters": {"retry_after": 5},
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("429", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_http_500_internal_server_error(self, mock_post):
        """HTTP 500 Internal Server Error is caught and returns False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 500
        mock_resp.ok = False
        mock_resp.json.return_value = {
            "ok": False,
            "error_code": 500,
            "description": "Internal Server Error",
        }
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("500", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_http_502_bad_gateway(self, mock_post):
        """HTTP 502 Bad Gateway with non-JSON response returns False."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 502
        mock_resp.ok = False
        mock_resp.json.side_effect = ValueError("Non-JSON proxy error")
        mock_resp.text = "<html>502 Bad Gateway</html>"
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 75.0)
        self.assertFalse(result)
        self.assertIn("502", self.service.last_error)


class TestTelegramNetworkExceptions(unittest.TestCase):
    """Verifies that network exceptions (timeout, connection, request) return False without crashing."""

    def setUp(self):
        self.service = TelegramService(token="12345:TOKEN", chat_id="98765")

    @patch("requests.post")
    def test_enviar_alerta_timeout(self, mock_post):
        """requests.exceptions.Timeout returns False without raising."""
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
        result = self.service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        self.assertIn("Timeout", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_connection_error(self, mock_post):
        """requests.exceptions.ConnectionError returns False without raising."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to resolve host")
        result = self.service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)
        self.assertIn("Connection error", self.service.last_error)

    @patch("requests.post")
    def test_enviar_alerta_generic_request_exception(self, mock_post):
        """requests.exceptions.RequestException returns False without raising."""
        mock_post.side_effect = requests.exceptions.RequestException("Generic network failure")
        result = self.service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)

    @patch("requests.post")
    def test_enviar_alerta_malformed_json_response(self, mock_post):
        """Non-JSON response from proxy returns False without raising."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_resp

        result = self.service.enviar_alerta("https://test.com", 100.0, 80.0)
        self.assertFalse(result)

    @patch("requests.post")
    def test_enviar_alerta_raise_on_error_mode(self, mock_post):
        """raise_on_error=True raises TelegramNetworkError on network failure."""
        mock_post.side_effect = requests.exceptions.Timeout("Read timeout")

        with self.assertRaises(TelegramNetworkError):
            self.service.enviar_alerta(
                "https://test.com/item", 100.0, 75.0, raise_on_error=True
            )


class TestTelegramSecurityUtilities(unittest.TestCase):
    """Tests for token masking and URL sanitization."""

    def test_mask_token(self):
        """mask_token protects secrets in logs."""
        self.assertEqual(mask_token(""), "")
        self.assertEqual(mask_token("short"), "***")
        self.assertEqual(mask_token("123456789:abcdefghijk"), "1234...hijk")

    def test_sanitize_url(self):
        """sanitize_url replaces secret token with <REDACTED>."""
        raw_url = "https://api.telegram.org/bot123456:SECRET_TOKEN/sendMessage"
        sanitized = sanitize_url(raw_url)
        self.assertNotIn("SECRET_TOKEN", sanitized)
        self.assertEqual(sanitized, "https://api.telegram.org/bot<REDACTED>/sendMessage")

    def test_is_valid_credential(self):
        """is_valid_credential identifies valid and invalid credentials correctly."""
        self.assertTrue(is_valid_credential("12345:TOKEN"))
        self.assertTrue(is_valid_credential("987654321"))
        self.assertFalse(is_valid_credential(""))
        self.assertFalse(is_valid_credential("   "))
        self.assertFalse(is_valid_credential(None))
        self.assertFalse(is_valid_credential("your_bot_token_here"))
        self.assertFalse(is_valid_credential("your_chat_id_here"))
        self.assertFalse(is_valid_credential("<telegram_token>"))


class TestTelegramPackageAndOfflineGuarantees(unittest.TestCase):
    """Verifies package structure exports and 100% offline test isolation."""

    def test_services_package_exports_telegram_service(self):
        """src.services exports TelegramService in __all__."""
        import src.services
        self.assertTrue(hasattr(src.services, "TelegramService"))
        self.assertIn("TelegramService", src.services.__all__)

    @patch("requests.post")
    def test_100_percent_offline_socket_protection(self, mock_post):
        """Verifies that enviar_alerta does not touch physical sockets when mocked."""
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        def block_socket_connect(*args, **kwargs):
            raise RuntimeError("Real outbound network call attempted during test!")

        with patch.object(socket.socket, "connect", side_effect=block_socket_connect):
            service = TelegramService(token="tok", chat_id="cid")
            res = service.enviar_alerta("https://test.com", 100.0, 80.0)
            self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
