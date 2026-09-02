from base64 import b64encode
from importlib import metadata
import subprocess
import os
import sys
import platform
from importlib.util import find_spec
from pathlib import Path
from shutil import which
from ratio1.utils.config import log_with_color


def _dist_name() -> str:
  """Return the canonical wheel name (e.g. 'mycli') for the running code."""
  if __package__ is None or len(__package__) == 0:
    return 'ratio1'
  pkg = __package__.split(".", 1)[0]
  return metadata.distribution(pkg).metadata["Name"]


def _local_version(dist: str) -> str:
  try:
    return metadata.version(dist)
  except metadata.PackageNotFoundError:
    return "unknown"


def _fresh_version(dist: str) -> str:
  """Ask a brand-new interpreter for the package version just installed."""
  try:
    out = subprocess.check_output(
      [sys.executable, "-c",
       f"import importlib.metadata, sys; "
       f"print(importlib.metadata.version('{dist}'))"],
      text=True, stderr=subprocess.DEVNULL
    )
    return out.strip()
  except Exception as exc:
    return "unknown"


def _update_command(pkg_name: str) -> list[str]:
  """
  Build the package-manager command for the active Python environment.

  Parameters
  ----------
  pkg_name : str
      Distribution name to upgrade.

  Returns
  -------
  list[str]
      A command that upgrades ``pkg_name`` in ``sys.executable``'s environment.

  Notes
  -----
  ``uv venv --no-pip`` environments intentionally omit the ``pip`` module.
  When ``uv`` is available in such an environment, target the running
  interpreter explicitly instead of invoking ``python -m pip``.
  """
  if find_spec("pip") is None:
    uv = which("uv")
    if uv is None:
      uv_name = "uv.exe" if os.name == "nt" else "uv"
      local_uv = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin") / uv_name
      if local_uv.is_file():
        uv = str(local_uv)
    if uv is not None:
      return [uv, "pip", "install", "--python", sys.executable, "--upgrade", pkg_name]

  return [sys.executable, "-m", "pip", "install", "--upgrade", pkg_name]


def update_package(args) -> None:
  """
  Update the package in-place using the available environment package manager.

  Parameters
  ----------
  args : argparse.Namespace
      Parsed CLI arguments. ``quiet`` controls installer output forwarding.

  Notes
  -----
  This is invoked by ``r1ctl update``. The Windows branch starts a replacement
  interpreter because the installed executable is locked until this process
  exits. Its ``-c`` argument is encoded into a whitespace-free launcher because
  Windows ``os.execv`` otherwise splits inline source at the first space.
  """
  pkg_name = _dist_name()
  initial_version = _local_version(pkg_name)
  log_with_color(f"Attempting to update package: {pkg_name}(local version: {initial_version})")
  quiet = args.quiet

  # Windows needs the updater to run *after* we exit, otherwise r1ctl.exe is locked
  if platform.system() == "Windows":
    cwd = os.getcwd()
    wrapper_code_lines = [
      "import subprocess",
      "import sys",
      "import importlib.metadata as m",
      "from ratio1.cli.package_update import _update_command",
      f"pkg = '{pkg_name}'",
      f"quiet = {quiet}",
      f"initial_version = '{initial_version}'",
      f"print('Windows detected, running update in a new process...')",
      # The following line is a single line of code, no leading spaces
      # it is split into multiple lines for readability.
      "code = subprocess.call("
      "_update_command(pkg),"
      "stdout=subprocess.DEVNULL if quiet else None,"
      "stderr=subprocess.DEVNULL if quiet else None"
      ")",
      "msg_ok_new = f'Package {pkg} updated successfully from {initial_version} to {m.version(pkg)}.'",
      "msg_ok_same = f'Package {pkg} is already up-to-date at version {initial_version}.'",
      "msg_ok = msg_ok_new if m.version(pkg) != initial_version else msg_ok_same",
      "msg_bad = f'Package {pkg} update failed with exit code {code}.'",
      "print(msg_ok if code == 0 else msg_bad, file=sys.stderr if code else sys.stdout)",
      "print('Exiting the updater process with code:', code)",
      # Since this script is run in a new process, this is printed for the user
      # to know the process finished. This is done to mimic the behavior of
      # a standard command line command.
      f"print(r'{cwd}>', end='')",
    ]

    wrapper_code = '; '.join(wrapper_code_lines)
    wrapper_payload = b64encode(wrapper_code.encode("utf-8")).decode("ascii")
    launcher_code = f"exec(__import__('base64').b64decode('{wrapper_payload}'))"
    os.execv(sys.executable, [sys.executable, "-c", launcher_code])  # never returns
  # endif Windows

  cmd = _update_command(pkg_name)

  # Inherit or suppress output based on `quiet`
  stdout = subprocess.DEVNULL if quiet else None
  stderr = subprocess.STDOUT if quiet else None

  exit_code = subprocess.call(cmd, stdout=stdout, stderr=stderr)

  if exit_code != 0:
    log_with_color(f"Package {pkg_name} update failed with exit code {exit_code}.", color='r')
  else:
    updated_version = _fresh_version(pkg_name)
    if updated_version != initial_version:
      log_with_color(f"Package {pkg_name} updated successfully from {initial_version} to {updated_version}.", color='g')
    else:
      log_with_color(f"Package {pkg_name} is already up-to-date at version {initial_version}.", color='g')
  # endif exit_code
  return


if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(description="Update the package in-place.")
  parser.add_argument('--quiet', default=False)
  args = parser.parse_args()

  update_package(args)
