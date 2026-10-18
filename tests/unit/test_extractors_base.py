"""Unit tests for ExtratorBase abstract strategy interface and extractor exceptions.

Verifies:
1. ABC instantiation prevention (TypeError on direct instantiation of ExtratorBase).
2. Subclass enforcement (TypeError when concrete subclass fails to implement extrair_preco).
3. Valid concrete subclass instantiation and execution (polymorphism, LSP).
4. Method signature reflection (parameter names, kinds, and type annotations).
5. Return types, value handling, and super() call behavior.
6. URL validation helper (validar_url).
7. Domain exception hierarchy (ExtratorError, PrecoNaoEncontradoError, FalhaAcessoPaginaError, DominioNaoSuportadoError).
8. Downstream testability and mockability (create_autospec, MagicMock spec).
9. Package exports in src.extractors and src.extractors.base.
10. 100% offline execution guarantee with zero external network or I/O.
"""

import abc
import inspect
from typing import get_type_hints
import unittest
from unittest.mock import MagicMock, create_autospec

import src.extractors as extractors_pkg
import src.extractors.base as extractors_base_mod
from src.extractors import (
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


class TestExtratorBaseABCEnforcement(unittest.TestCase):
    """Verifies that ExtratorBase behaves strictly as an Abstract Base Class."""

    def test_cannot_instantiate_abc_directly(self):
        """Direct instantiation of ExtratorBase must raise TypeError."""
        with self.assertRaises(TypeError) as ctx:
            ExtratorBase()

        error_msg = str(ctx.exception).lower()
        self.assertIn("abstract", error_msg)
        self.assertIn("extrair_preco", str(ctx.exception))

    def test_cannot_instantiate_abc_with_positional_or_keyword_args(self):
        """Instantiating ExtratorBase with positional or keyword args must also raise TypeError."""
        with self.assertRaises(TypeError):
            ExtratorBase("https://example.com")

        with self.assertRaises(TypeError):
            ExtratorBase(timeout=30)

    def test_abc_metaclass_and_inheritance(self):
        """ExtratorBase must inherit from abc.ABC and use abc.ABCMeta metaclass."""
        self.assertTrue(issubclass(ExtratorBase, abc.ABC))
        self.assertIsInstance(ExtratorBase, abc.ABCMeta)

    def test_abstract_methods_registered(self):
        """ExtratorBase.__abstractmethods__ must be a frozenset containing exactly 'extrair_preco'."""
        self.assertEqual(
            ExtratorBase.__abstractmethods__,
            frozenset({"extrair_preco"}),
        )


class TestExtratorBaseSubclassEnforcement(unittest.TestCase):
    """Verifies that subclasses missing extrair_preco cannot be instantiated."""

    def test_empty_subclass_cannot_be_instantiated(self):
        """A subclass that implements no methods must raise TypeError on instantiation."""
        class IncompleteExtractor(ExtratorBase):
            pass

        self.assertEqual(
            IncompleteExtractor.__abstractmethods__,
            frozenset({"extrair_preco"}),
        )
        with self.assertRaises(TypeError) as ctx:
            IncompleteExtractor()

        self.assertIn("IncompleteExtractor", str(ctx.exception))
        self.assertIn("extrair_preco", str(ctx.exception))

    def test_subclass_with_other_methods_cannot_be_instantiated(self):
        """A subclass implementing other methods but omitting extrair_preco raises TypeError."""
        class PartialExtractor(ExtratorBase):
            def outro_metodo(self):
                return "outro"

        with self.assertRaises(TypeError) as ctx:
            PartialExtractor()

        self.assertIn("PartialExtractor", str(ctx.exception))
        self.assertIn("extrair_preco", str(ctx.exception))

    def test_subclass_with_wrong_method_name_raises_type_error(self):
        """A subclass implementing an alternative method name still raises TypeError."""
        class SubclassNomeErrado(ExtratorBase):
            def extrair(self, url: str) -> float:
                return 99.90

        with self.assertRaises(TypeError) as ctx:
            SubclassNomeErrado()
        self.assertIn("extrair_preco", str(ctx.exception))

    def test_subclass_retaining_abstractmethod_cannot_be_instantiated(self):
        """A subclass overriding extrair_preco decorated with @abstractmethod raises TypeError."""
        class StillAbstractExtractor(ExtratorBase):
            @abc.abstractmethod
            def extrair_preco(self, url: str) -> float:
                return 0.0

        with self.assertRaises(TypeError):
            StillAbstractExtractor()

    def test_multi_level_abstract_inheritance_chain(self):
        """Intermediate abstract classes cannot be instantiated; leaf concrete classes can."""
        class IntermediateExtractor(ExtratorBase):
            def helper(self):
                return True

        with self.assertRaises(TypeError):
            IntermediateExtractor()

        class ConcreteLeafExtractor(IntermediateExtractor):
            def extrair_preco(self, url: str) -> float:
                return 15.0

        leaf = ConcreteLeafExtractor()
        self.assertIsInstance(leaf, ExtratorBase)
        self.assertTrue(leaf.helper())
        self.assertEqual(leaf.extrair_preco("https://test.com"), 15.0)


class TestExtratorBaseValidSubclass(unittest.TestCase):
    """Verifies instantiation and execution of compliant concrete subclasses."""

    class ConcreteExtractor(ExtratorBase):
        """Valid test implementation of ExtratorBase."""
        def extrair_preco(self, url: str) -> float:
            clean_url = self.validar_url(url)
            if "not_found" in clean_url:
                raise PrecoNaoEncontradoError("Preço não localizado na página.")
            return 99.90

    def setUp(self):
        self.extractor = self.ConcreteExtractor()

    def test_valid_concrete_subclass_instantiation(self):
        """Compliant subclass instantiates without error and satisfies type checks."""
        self.assertIsInstance(self.extractor, ExtratorBase)
        self.assertTrue(issubclass(self.ConcreteExtractor, ExtratorBase))
        self.assertEqual(self.ConcreteExtractor.__abstractmethods__, frozenset())

    def test_extrair_preco_invocation_with_positional_arg(self):
        """Invoking extrair_preco with positional url string returns expected float."""
        result = self.extractor.extrair_preco("https://pt.aliexpress.com/item/1.html")
        self.assertIsInstance(result, float)
        self.assertEqual(result, 99.90)

    def test_extrair_preco_invocation_with_keyword_arg(self):
        """Invoking extrair_preco with keyword url=... returns expected float."""
        result = self.extractor.extrair_preco(url="https://pt.aliexpress.com/item/2.html")
        self.assertIsInstance(result, float)
        self.assertEqual(result, 99.90)

    def test_multiple_concrete_subclasses_polymorphism(self):
        """Multiple distinct extractor implementations operate polymorphically and independently."""
        class StoreAExtractor(ExtratorBase):
            def extrair_preco(self, url: str) -> float:
                return 10.50

        class StoreBExtractor(ExtratorBase):
            def extrair_preco(self, url: str) -> float:
                return 25.75

        extractor_a = StoreAExtractor()
        extractor_b = StoreBExtractor()

        self.assertTrue(issubclass(StoreAExtractor, ExtratorBase))
        self.assertTrue(issubclass(StoreBExtractor, ExtratorBase))

        strategies: list[ExtratorBase] = [extractor_a, extractor_b]
        results = [s.extrair_preco("https://store.com/item") for s in strategies]
        self.assertEqual(results, [10.50, 25.75])


class TestExtratorBaseSignatureAndAnnotations(unittest.TestCase):
    """Verifies interface reflection, method signature, parameter names, and annotations."""

    def test_extrair_preco_is_marked_abstract(self):
        """extrair_preco method attribute __isabstractmethod__ must be True on ExtratorBase."""
        self.assertTrue(hasattr(ExtratorBase, "extrair_preco"))
        self.assertTrue(
            getattr(ExtratorBase.extrair_preco, "__isabstractmethod__", False),
            "extrair_preco must be decorated with @abc.abstractmethod",
        )

    def test_signature_parameters_names_and_order(self):
        """Signature must have exactly ('self', 'url') parameters."""
        sig = inspect.signature(ExtratorBase.extrair_preco)
        param_names = list(sig.parameters.keys())
        self.assertEqual(param_names, ["self", "url"])

    def test_parameter_url_kind(self):
        """Parameter 'url' must be POSITIONAL_OR_KEYWORD."""
        sig = inspect.signature(ExtratorBase.extrair_preco)
        param_url = sig.parameters["url"]
        self.assertEqual(
            param_url.kind,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )

    def test_signature_type_annotations(self):
        """Signature annotations must specify url: str and return -> float."""
        sig = inspect.signature(ExtratorBase.extrair_preco)
        param_url = sig.parameters["url"]

        self.assertIn(param_url.annotation, (str, "str"))
        self.assertIn(sig.return_annotation, (float, "float"))

        hints = get_type_hints(ExtratorBase.extrair_preco)
        self.assertEqual(hints.get("url"), str)
        self.assertEqual(hints.get("return"), float)

    def test_docstrings_present(self):
        """ExtratorBase and extrair_preco must have informative docstrings."""
        self.assertIsNotNone(ExtratorBase.__doc__)
        self.assertGreater(len(ExtratorBase.__doc__.strip()), 10)
        self.assertIsNotNone(ExtratorBase.extrair_preco.__doc__)
        self.assertGreater(len(ExtratorBase.extrair_preco.__doc__.strip()), 10)


class TestExtratorBaseReturnTypesAndBehaviors(unittest.TestCase):
    """Verifies numerical return value handling and base class method behavior."""

    def test_various_valid_float_values(self):
        """Subclasses returning diverse valid float numbers succeed."""
        class DynamicExtractor(ExtratorBase):
            def __init__(self, val: float):
                self.val = val

            def extrair_preco(self, url: str) -> float:
                return self.val

        test_values = [0.0, 0.01, 49.90, 100.0, 129.999, 999999.99]
        for v in test_values:
            extractor = DynamicExtractor(v)
            res = extractor.extrair_preco("https://test.com")
            self.assertIsInstance(res, float)
            self.assertEqual(res, v)

    def test_super_extrair_preco_raises_not_implemented_error(self):
        """Calling super().extrair_preco from subclass raises NotImplementedError."""
        class DelegatingExtractor(ExtratorBase):
            def extrair_preco(self, url: str) -> float:
                return super().extrair_preco(url)

        extractor = DelegatingExtractor()
        with self.assertRaises(NotImplementedError) as ctx:
            extractor.extrair_preco("https://test.com")
        self.assertIn("Subclasses must implement extrair_preco", str(ctx.exception))


class TestExtratorBaseValidarUrl(unittest.TestCase):
    """Verifies the static validar_url helper on ExtratorBase."""

    def test_valid_url_returned_stripped(self):
        """Valid URL is stripped and returned as is."""
        url = "  https://pt.aliexpress.com/item/123.html  "
        self.assertEqual(
            ExtratorBase.validar_url(url),
            "https://pt.aliexpress.com/item/123.html",
        )

    def test_invalid_urls_raise_value_error(self):
        """None, empty, or whitespace strings raise ValueError."""
        for invalid in [None, "", "   ", "\t\n", 12345]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    ExtratorBase.validar_url(invalid)  # type: ignore[arg-type]


class TestExtratorBaseExceptionHierarchy(unittest.TestCase):
    """Verifies domain exception definitions and inheritance."""

    def test_exception_inheritance_structure(self):
        """Verifies inheritance tree for all extractor exceptions."""
        self.assertTrue(issubclass(ExtratorError, Exception))
        self.assertTrue(issubclass(PrecoNaoEncontradoError, ExtratorError))
        self.assertTrue(issubclass(PrecoNaoEncontradoError, ValueError))
        self.assertTrue(issubclass(FalhaAcessoPaginaError, ExtratorError))
        self.assertTrue(issubclass(DominioNaoSuportadoError, ExtratorError))
        self.assertTrue(issubclass(DominioNaoSuportadoError, ValueError))
        self.assertTrue(issubclass(InvalidURLError, ExtratorError))
        self.assertTrue(issubclass(InvalidURLError, ValueError))

    def test_aliases_compatibility(self):
        """English aliases reference their corresponding canonical Portuguese classes."""
        self.assertIs(ExtractorError, ExtratorError)
        self.assertIs(PriceNotFoundError, PrecoNaoEncontradoError)
        self.assertIs(ExtractorNetworkError, FalhaAcessoPaginaError)

    def test_raising_and_catching_domain_exceptions(self):
        """Derived extraction exceptions can be caught via ExtratorError."""
        exceptions_to_test = [
            PrecoNaoEncontradoError("Preço não localizado"),
            FalhaAcessoPaginaError("Timeout de conexão"),
            DominioNaoSuportadoError("Domínio não suportado"),
            InvalidURLError("URL malformada"),
        ]
        for exc in exceptions_to_test:
            with self.subTest(exc=exc.__class__.__name__):
                with self.assertRaises(ExtratorError):
                    raise exc

    def test_dual_inheritance_value_error_catching(self):
        """PrecoNaoEncontradoError and DominioNaoSuportadoError can be caught as ValueError."""
        with self.assertRaises(ValueError):
            raise PrecoNaoEncontradoError("Preço ausente")

        with self.assertRaises(ValueError):
            raise DominioNaoSuportadoError("Domínio desconhecido")


class TestExtratorBaseMockability(unittest.TestCase):
    """Verifies that ExtratorBase supports standard unit test doubles and autospecs."""

    def test_create_autospec_compatibility(self):
        """create_autospec(ExtratorBase) validates mock calls against the ABC contract."""
        mock_extractor = create_autospec(ExtratorBase)
        mock_extractor.extrair_preco.return_value = 149.50

        # Valid invocation succeeds
        price = mock_extractor.extrair_preco("https://aliexpress.com/item/1.html")
        self.assertEqual(price, 149.50)
        mock_extractor.extrair_preco.assert_called_once_with(
            "https://aliexpress.com/item/1.html"
        )

        # Invalid call with no arguments raises TypeError via autospec
        with self.assertRaises(TypeError):
            mock_extractor.extrair_preco()

    def test_magic_mock_spec_enforcement(self):
        """MagicMock with spec=ExtratorBase rejects non-existent attributes."""
        mock_extractor = MagicMock(spec=ExtratorBase)
        mock_extractor.extrair_preco.return_value = 50.0

        self.assertEqual(mock_extractor.extrair_preco("http://example.com"), 50.0)

        with self.assertRaises(AttributeError):
            _ = mock_extractor.non_existent_method()


class TestExtractorsPackageExports(unittest.TestCase):
    """Verifies package structure, imports, and __all__ declarations."""

    def test_package_exports_extrator_base(self):
        """src.extractors exports ExtratorBase in __all__."""
        self.assertTrue(hasattr(extractors_pkg, "ExtratorBase"))
        self.assertIn("ExtratorBase", extractors_pkg.__all__)

    def test_package_exports_exceptions(self):
        """src.extractors exports domain exceptions in __all__."""
        expected_exports = [
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
        for name in expected_exports:
            with self.subTest(symbol=name):
                self.assertTrue(hasattr(extractors_pkg, name), f"Missing {name} in package")
                self.assertIn(name, extractors_pkg.__all__, f"{name} not in __all__")

    def test_base_module_exports(self):
        """src.extractors.base defines __all__ with ExtratorBase and exceptions."""
        self.assertTrue(hasattr(extractors_base_mod, "__all__"))
        self.assertIn("ExtratorBase", extractors_base_mod.__all__)
        self.assertIn("ExtratorError", extractors_base_mod.__all__)

    def test_identity_between_package_and_base_module(self):
        """Symbols imported from package root are identical to those in base.py."""
        self.assertIs(extractors_pkg.ExtratorBase, extractors_base_mod.ExtratorBase)
        self.assertIs(extractors_pkg.ExtratorError, extractors_base_mod.ExtratorError)
        self.assertIs(
            extractors_pkg.PrecoNaoEncontradoError,
            extractors_base_mod.PrecoNaoEncontradoError,
        )


if __name__ == "__main__":
    unittest.main()
