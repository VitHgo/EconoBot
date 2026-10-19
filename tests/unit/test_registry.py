"""Unit tests for Extrator Strategy Registry and Domain Routing.

Verifies:
1. URL domain resolution for AliExpress (apex domain, www, subdomains pt, es, m, etc.).
2. Case-insensitivity, ports, basic auth, query params, and anchors.
3. Scheme-less URL handling (e.g., 'aliexpress.com/item/1.html').
4. Instantiation and keyword argument propagation (headless, timeout, wait_time).
5. Unsupported domain rejection with DominioNaoSuportadoError and exact message format.
6. Lookalike and phishing domain rejection (e.g., 'fakealiexpress.com', 'aliexpress.com.attacker.com').
7. Dynamic registration of custom ExtratorBase strategies via registrar_extrator.
8. Domain normalization, error checking (ValueError on empty domain, TypeError on invalid class).
9. Registry isolation helpers: resetar_registro(), redefinir_registro(), remover_extrator(), listar_dominios_suportados().
10. Package exports in src.extractors and src.extractors.registry.
"""

import inspect
import unittest
from typing import get_type_hints

import src.extractors as extractors_pkg
import src.extractors.registry as registry_mod
from src.extractors import (
    DominioNaoSuportadoError,
    ExtratorAliExpress,
    ExtratorBase,
    ExtratorError,
    InvalidURLError,
    obter_extrator,
    registrar_extrator,
)
from src.extractors.registry import (
    _REGISTRY,
    extrair_dominio,
    listar_dominios_suportados,
    obter_classe_extrator,
    redefinir_registro,
    remover_extrator,
    resetar_registro,
)


class BaseRegistryTest(unittest.TestCase):
    """Base fixture guaranteeing registry isolation across tests."""

    def setUp(self):
        resetar_registro()

    def tearDown(self):
        resetar_registro()


class TestDomainExtraction(BaseRegistryTest):
    """Tests for extrair_dominio helper function."""

    def test_extrair_dominio_standard_https(self):
        url = "https://pt.aliexpress.com/item/100500123.html"
        self.assertEqual(extrair_dominio(url), "pt.aliexpress.com")

    def test_extrair_dominio_standard_http(self):
        url = "http://www.aliexpress.com/item/100500123.html"
        self.assertEqual(extrair_dominio(url), "www.aliexpress.com")

    def test_extrair_dominio_case_insensitive(self):
        url = "HTTPS://PT.ALIEXPRESS.COM/item/100500123.html"
        self.assertEqual(extrair_dominio(url), "pt.aliexpress.com")

    def test_extrair_dominio_with_port(self):
        url = "https://aliexpress.com:8080/item/100500123.html"
        self.assertEqual(extrair_dominio(url), "aliexpress.com")

    def test_extrair_dominio_without_scheme(self):
        url = "aliexpress.com/item/100500123.html"
        self.assertEqual(extrair_dominio(url), "aliexpress.com")

    def test_extrair_dominio_with_query_and_fragment(self):
        url = "https://aliexpress.com/item/123.html?spm=abc&aff=1#specs"
        self.assertEqual(extrair_dominio(url), "aliexpress.com")

    def test_extrair_dominio_empty_or_none(self):
        with self.assertRaises((ValueError, InvalidURLError)):
            extrair_dominio("")
        with self.assertRaises((ValueError, InvalidURLError)):
            extrair_dominio("   ")
        with self.assertRaises((ValueError, InvalidURLError, TypeError)):
            extrair_dominio(None)  # type: ignore[arg-type]


class TestObterExtratorAliExpress(BaseRegistryTest):
    """Tests resolution of default AliExpress extractor across various URL structures."""

    def test_apex_domain_https(self):
        """Standard apex domain returns ExtratorAliExpress instance."""
        ext = obter_extrator("https://aliexpress.com/item/100500123.html")
        self.assertIsInstance(ext, ExtratorAliExpress)
        self.assertIsInstance(ext, ExtratorBase)

    def test_apex_domain_http(self):
        """HTTP scheme returns ExtratorAliExpress instance."""
        ext = obter_extrator("http://aliexpress.com/item/100500123.html")
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_www_subdomain(self):
        """www.aliexpress.com returns ExtratorAliExpress instance."""
        ext = obter_extrator("https://www.aliexpress.com/item/100500123.html")
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_regional_subdomains(self):
        """Subdomains (pt, es, fr, ru, de, best, glo) return ExtratorAliExpress instance."""
        subdomains = ["pt", "es", "fr", "ru", "de", "best", "glo"]
        for sub in subdomains:
            url = f"https://{sub}.aliexpress.com/item/100500123.html"
            with self.subTest(subdomain=sub):
                ext = obter_extrator(url)
                self.assertIsInstance(ext, ExtratorAliExpress)

    def test_mobile_subdomain(self):
        """m.aliexpress.com returns ExtratorAliExpress instance."""
        ext = obter_extrator("https://m.aliexpress.com/item/100500123.html")
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_nested_subdomain(self):
        """Multi-level subdomain (e.g. pt.m.aliexpress.com) returns ExtratorAliExpress."""
        ext = obter_extrator("https://pt.m.aliexpress.com/item/100500123.html")
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_case_insensitivity(self):
        """Upper and mixed-case URLs resolve cleanly to ExtratorAliExpress."""
        urls = [
            "HTTPS://WWW.ALIEXPRESS.COM/ITEM/100500.HTML",
            "http://Pt.AliExpress.Com/item/100500",
            "HTTPS://ALIEXPRESS.COM/ITEM/100500",
        ]
        for u in urls:
            with self.subTest(url=u):
                ext = obter_extrator(u)
                self.assertIsInstance(ext, ExtratorAliExpress)

    def test_url_with_port(self):
        """URLs containing explicit ports are resolved correctly."""
        ext = obter_extrator("https://pt.aliexpress.com:8443/item/100500.html")
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_url_with_auth_credentials(self):
        """URLs containing basic authentication credentials resolve correctly."""
        ext = obter_extrator("https://user:password@aliexpress.com/item/100500.html")
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_url_with_query_and_fragment(self):
        """URLs with query strings and fragment identifiers resolve correctly."""
        url = "https://pt.aliexpress.com/item/1.html?spm=a2g0o&scm=1007#nav-review"
        ext = obter_extrator(url)
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_url_without_scheme(self):
        """URLs without scheme (e.g. 'aliexpress.com/item/1') resolve correctly."""
        urls = [
            "aliexpress.com/item/100500123.html",
            "pt.aliexpress.com/item/100500123.html",
            "www.aliexpress.com/item/100500123.html",
        ]
        for u in urls:
            with self.subTest(url=u):
                ext = obter_extrator(u)
                self.assertIsInstance(ext, ExtratorAliExpress)

    def test_url_with_whitespace(self):
        """Surrounding whitespace is stripped and resolved correctly."""
        url = "   https://pt.aliexpress.com/item/100500123.html \t\n"
        ext = obter_extrator(url)
        self.assertIsInstance(ext, ExtratorAliExpress)

    def test_kwargs_propagation_to_extractor(self):
        """Keyword arguments (headless, timeout, wait_time) are passed to constructor."""
        ext = obter_extrator(
            "https://aliexpress.com/item/1",
            headless=False,
            timeout=15000,
            wait_time=2000,
        )
        self.assertIsInstance(ext, ExtratorAliExpress)
        self.assertFalse(ext.headless)
        self.assertEqual(ext.timeout, 15000)
        self.assertEqual(ext.wait_time, 2000)


class TestDominioNaoSuportado(BaseRegistryTest):
    """Tests rejection of unsupported, malicious, or malformed URLs."""

    def test_unregistered_store_domain(self):
        """Unmapped third-party domains raise DominioNaoSuportadoError with exact message."""
        unregistered = [
            "https://www.amazon.com.br/dp/B08N5WRWNW",
            "https://shopee.com.br/product/123/456",
            "https://mercadolivre.com.br/MLB-12345",
            "https://magazineluiza.com.br/produto/123",
        ]
        for url in unregistered:
            with self.subTest(url=url):
                with self.assertRaises(DominioNaoSuportadoError) as ctx:
                    obter_extrator(url)
                self.assertEqual(
                    str(ctx.exception),
                    f"Domínio não suportado para extração: {url}",
                )

    def test_lookalike_and_phishing_domains_rejected(self):
        """Lookalike domains do not match registered aliexpress.com."""
        lookalikes = [
            "https://fakealiexpress.com/item/1",
            "https://not-aliexpress.com/item/1",
            "https://myaliexpress.com/item/1",
            "https://aliexpress.com.br/item/1",
        ]
        for url in lookalikes:
            with self.subTest(url=url):
                with self.assertRaises(DominioNaoSuportadoError):
                    obter_extrator(url)

    def test_attacker_suffix_domain_rejected(self):
        """Domain placed as subdomain of an attacker host is rejected."""
        attacker_url = "https://aliexpress.com.attacker.com/item/1"
        with self.assertRaises(DominioNaoSuportadoError):
            obter_extrator(attacker_url)

    def test_invalid_and_empty_urls_raise_error(self):
        """Empty, None, or unparseable URLs raise DominioNaoSuportadoError (or ValueError)."""
        invalid_urls = [None, "", "   ", "http://", "https:///", "://invalid"]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises((DominioNaoSuportadoError, ValueError)):
                    obter_extrator(url)  # type: ignore[arg-type]

    def test_exception_dual_inheritance(self):
        """DominioNaoSuportadoError is catchable as ValueError and ExtratorError."""
        with self.assertRaises(ValueError):
            obter_extrator("https://unsupported-store.com")

        with self.assertRaises(ExtratorError):
            obter_extrator("https://unsupported-store.com")


class TestRegistrarExtrator(BaseRegistryTest):
    """Tests dynamic registration and overriding of extraction strategies."""

    class MockCustomExtractor(ExtratorBase):
        """Dummy concrete extractor for registration tests."""
        def extrair_preco(self, url: str) -> float:
            return 88.50

    def test_register_new_domain(self):
        """Registering a new domain allows obter_extrator to resolve it."""
        registrar_extrator("shopee.com.br", self.MockCustomExtractor)
        ext = obter_extrator("https://shopee.com.br/item/123")
        self.assertIsInstance(ext, self.MockCustomExtractor)
        self.assertEqual(ext.extrair_preco("https://shopee.com.br/item/123"), 88.50)

    def test_register_new_domain_subdomain_routing(self):
        """Registered custom domain matches subdomains."""
        registrar_extrator("shopee.com.br", self.MockCustomExtractor)
        ext = obter_extrator("https://loja.oficial.shopee.com.br/item/123")
        self.assertIsInstance(ext, self.MockCustomExtractor)

    def test_register_domain_normalization(self):
        """Domain keys with uppercase, leading dots, or schemes are normalized."""
        registrar_extrator("  .AMAZON.COM.BR  ", self.MockCustomExtractor)
        ext = obter_extrator("https://www.amazon.com.br/dp/B08")
        self.assertIsInstance(ext, self.MockCustomExtractor)

    def test_override_default_registration(self):
        """Registering over an existing domain overrides the previous strategy."""
        registrar_extrator("aliexpress.com", self.MockCustomExtractor)
        ext = obter_extrator("https://aliexpress.com/item/1")
        self.assertIsInstance(ext, self.MockCustomExtractor)
        self.assertNotIsInstance(ext, ExtratorAliExpress)

    def test_invalid_domain_raises_value_error(self):
        """Empty or non-string domain raises ValueError."""
        for invalid in ["", "   ", None]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    registrar_extrator(invalid, self.MockCustomExtractor)  # type: ignore[arg-type]

    def test_invalid_extractor_class_raises_type_error(self):
        """Passing non-class or non-ExtratorBase class raises TypeError."""
        class NotAnExtractor:
            pass

        with self.assertRaises(TypeError):
            registrar_extrator("test.com", NotAnExtractor)  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            registrar_extrator("test.com", "not_a_type")  # type: ignore[arg-type]


class TestRegistryLifecycleAndHelpers(BaseRegistryTest):
    """Tests lifecycle management, removal, resetting, and introspection helpers."""

    def test_remover_extrator_success_and_missing(self):
        """remover_extrator removes registered strategy or returns None if missing."""
        removed = remover_extrator("aliexpress.com")
        self.assertIs(removed, ExtratorAliExpress)
        with self.assertRaises(DominioNaoSuportadoError):
            obter_extrator("https://aliexpress.com/item/1")

        # Removing non-existent domain returns None
        self.assertIsNone(remover_extrator("nonexistent.com"))

    def test_resetar_registro(self):
        """resetar_registro restores original defaults."""
        class MockOther(ExtratorBase):
            def extrair_preco(self, url: str) -> float:
                return 1.0

        registrar_extrator("other.com", MockOther)
        self.assertIn("other.com", _REGISTRY)

        resetar_registro()
        self.assertNotIn("other.com", _REGISTRY)
        self.assertIn("aliexpress.com", _REGISTRY)

    def test_redefinir_registro_alias(self):
        """redefinir_registro acts as an exact alias for resetar_registro."""
        class MockOther(ExtratorBase):
            def extrair_preco(self, url: str) -> float:
                return 1.0

        registrar_extrator("tempstore.com", MockOther)
        self.assertIn("tempstore.com", _REGISTRY)

        redefinir_registro()
        self.assertNotIn("tempstore.com", _REGISTRY)
        self.assertIn("aliexpress.com", _REGISTRY)

    def test_listar_dominios_suportados(self):
        """listar_dominios_suportados returns sorted list of registered keys."""
        domains = listar_dominios_suportados()
        self.assertIn("aliexpress.com", domains)
        self.assertEqual(domains, sorted(domains))

    def test_obter_classe_extrator(self):
        """obter_classe_extrator returns the class without instantiating it."""
        cls = obter_classe_extrator("https://pt.aliexpress.com/item/1")
        self.assertIs(cls, ExtratorAliExpress)


class TestRegistryContractsAndExports(BaseRegistryTest):
    """Verifies function signatures, annotations, and package exports."""

    def test_obter_extrator_signature(self):
        """obter_extrator specifies url: str -> ExtratorBase."""
        sig = inspect.signature(obter_extrator)
        self.assertIn("url", sig.parameters)
        hints = get_type_hints(obter_extrator)
        self.assertEqual(hints.get("url"), str)
        self.assertEqual(hints.get("return"), ExtratorBase)

    def test_registrar_extrator_signature(self):
        """registrar_extrator specifies (dominio: str, extrator_cls: type[ExtratorBase]) -> None."""
        sig = inspect.signature(registrar_extrator)
        self.assertIn("dominio", sig.parameters)
        self.assertIn("extrator_cls", sig.parameters)
        hints = get_type_hints(registrar_extrator)
        self.assertEqual(hints.get("dominio"), str)
        self.assertEqual(hints.get("return"), type(None))

    def test_registry_package_exports(self):
        """src.extractors exports obter_extrator and registrar_extrator."""
        self.assertTrue(hasattr(extractors_pkg, "obter_extrator"))
        self.assertTrue(hasattr(extractors_pkg, "registrar_extrator"))
        self.assertIn("obter_extrator", extractors_pkg.__all__)
        self.assertIn("registrar_extrator", extractors_pkg.__all__)


if __name__ == "__main__":
    unittest.main()
