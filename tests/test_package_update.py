import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ratio1.cli import package_update


class PackageUpdateCommandTests(unittest.TestCase):
  """Verify package-manager selection for the r1ctl update command."""

  def test_uses_uv_when_pip_is_unavailable(self):
    """
    Select ``uv pip`` for a pip-free environment that has uv installed.

    The active interpreter is passed to uv so the update cannot target a
    different environment merely because a different virtualenv is active.
    """
    with patch.object(package_update, "find_spec", return_value=None), \
         patch.object(package_update, "which", return_value="/usr/local/bin/uv"):
      command = package_update._update_command("ratio1")

    self.assertEqual(
      command,
      [
        "/usr/local/bin/uv", "pip", "install", "--python", sys.executable,
        "--upgrade", "ratio1",
      ],
    )

  def test_uses_pip_when_the_active_environment_has_pip(self):
    """Keep the existing pip command for environments that provide pip."""
    with patch.object(package_update, "find_spec", return_value=object()), \
         patch.object(package_update, "which") as which:
      command = package_update._update_command("ratio1")

    which.assert_not_called()
    self.assertEqual(
      command,
      [sys.executable, "-m", "pip", "install", "--upgrade", "ratio1"],
    )

  def test_uses_uv_beside_the_active_interpreter_when_not_on_path(self):
    """Find uv in the active virtualenv for absolute-path CLI invocations."""
    with patch.object(package_update, "find_spec", return_value=None), \
         patch.object(package_update, "which", return_value=None), \
         patch.object(package_update.sys, "prefix", "/venv"), \
         patch.object(package_update.Path, "is_file", return_value=True):
      command = package_update._update_command("ratio1")

    expected_uv = package_update.Path("/venv") / (
      "Scripts" if package_update.os.name == "nt" else "bin"
    ) / ("uv.exe" if package_update.os.name == "nt" else "uv")
    self.assertEqual(command[0], str(expected_uv))

  def test_falls_back_to_the_existing_pip_command_without_uv(self):
    """Preserve the existing failure behavior when neither installer exists."""
    with patch.object(package_update, "find_spec", return_value=None), \
         patch.object(package_update, "which", return_value=None):
      command = package_update._update_command("ratio1")

    self.assertEqual(
      command,
      [sys.executable, "-m", "pip", "install", "--upgrade", "ratio1"],
    )

  def test_windows_updater_uses_the_shared_command_selection(self):
    """Execute the deferred Windows updater through the shared installer path."""
    args = SimpleNamespace(quiet=True)
    with patch.object(package_update.platform, "system", return_value="Windows"), \
         patch.object(package_update, "_dist_name", return_value="ratio1"), \
         patch.object(package_update, "_local_version", return_value="1.0.0"), \
         patch.object(package_update, "log_with_color"), \
         patch.object(package_update.os, "execv", side_effect=RuntimeError("stop")) as execv:
      with self.assertRaisesRegex(RuntimeError, "stop"):
        package_update.update_package(args)

    wrapper_code = execv.call_args.args[1][2]
    self.assertIn("from ratio1.cli.package_update import _update_command", wrapper_code)
    self.assertIn("subprocess.call(_update_command(pkg)", wrapper_code)
    self.assertNotIn("'-m', 'pip'", wrapper_code)
    with patch.object(package_update, "_update_command", return_value=["uv", "pip"]), \
         patch("subprocess.call", return_value=0) as call, \
         patch("importlib.metadata.version", return_value="1.0.0"):
      exec(wrapper_code, {})

    call.assert_called_once_with(
      ["uv", "pip"],
      stdout=package_update.subprocess.DEVNULL,
      stderr=package_update.subprocess.DEVNULL,
    )
