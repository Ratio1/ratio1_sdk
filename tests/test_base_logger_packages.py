import builtins
import unittest
from unittest import mock

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


if __name__ == '__main__':
  unittest.main()
