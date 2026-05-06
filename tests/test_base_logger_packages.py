import builtins
import unittest
from unittest import mock

from ratio1.code_cheker.base import BaseCodeChecker
from ratio1.logging.base_logger import BaseLogger


class _FakeDistribution:
  def __init__(self, name, version):
    self.metadata = {'Name': name}
    self.version = version


class TestBaseLoggerGetPackages(unittest.TestCase):

  def test_get_packages_falls_back_to_importlib_metadata_when_pkg_resources_missing(self):
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
      if name == 'pkg_resources':
        raise ModuleNotFoundError("No module named 'pkg_resources'")
      return original_import(name, *args, **kwargs)

    fake_distributions = [
      _FakeDistribution('Torch', '2.9.1'),
      _FakeDistribution('Transformers', '4.57.1'),
      _FakeDistribution('My_Custom.Package', '1.2.3'),
    ]

    with mock.patch('builtins.__import__', side_effect=fake_import):
      with mock.patch('importlib.metadata.distributions', return_value=fake_distributions):
        result = BaseLogger.get_packages(
          as_dict=True,
          mandatory={'torch': '2.0', 'transformers': '4.43'},
        )

    self.assertEqual(result['torch'], '2.9.1')
    self.assertEqual(result['transformers'], '4.57.1')
    self.assertEqual(result['my-custom-package'], '1.2.3')


class TestCodeCheckerLoopInstrumentation(unittest.TestCase):

  def setUp(self):
    self.checker = BaseCodeChecker()
    self.checker.sleep = lambda _seconds: None

  def test_multiline_for_header_is_instrumented_without_crashing(self):
    code = "\n".join([
      "for item in (",
      "  items",
      "):",
      "  return item",
    ])

    result = self.checker._add_line_after_each_line(code)

    self.assertEqual(
      result,
      "\n".join([
        "for item in (",
        "  items",
        "):",
        "  plugin.sleep(0.001)",
        "  return item",
      ]),
    )

  def test_multiline_while_header_is_instrumented_without_crashing(self):
    code = "\n".join([
      "while (",
      "  should_continue",
      "):",
      "  return 'running'",
    ])

    result = self.checker._add_line_after_each_line(code)

    self.assertIn("  plugin.sleep(0.001)\n  return 'running'", result)

  def test_loop_like_line_without_colon_does_not_raise_index_error(self):
    code = "\n".join([
      "for item in items",
      "  return item",
    ])

    result = self.checker._add_line_after_each_line(code)

    self.assertEqual(result, code)

  def test_custom_method_creation_accepts_multiline_loop_header(self):
    code = "\n".join([
      "for item in (",
      "  [message]",
      "):",
      "  return item",
    ])
    b64code = self.checker.str_to_base64(code, compress=True)

    method, errors, warnings = self.checker._get_method_from_custom_code(
      str_b64code=b64code,
      self_var='plugin',
      method_arguments=['plugin', 'message'],
      debug=False,
    )

    self.assertIsNone(errors)
    self.assertEqual(warnings, [])
    self.assertEqual(method(plugin=self.checker, message='ok'), 'ok')


if __name__ == '__main__':
  unittest.main()
