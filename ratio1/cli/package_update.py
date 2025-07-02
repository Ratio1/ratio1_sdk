from importlib import metadata
import subprocess
import sys
from ratio1.utils.config import log_with_color


def _dist_name() -> str:
  """Return the canonical wheel name (e.g. 'mycli') for the running code."""
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


def update_package(args) -> None:
  """
  Update the package in-place using pip.
  This can be run through
  ```
  r1ctl update
  ```
  """
  pkg_name = _dist_name()
  initial_version = _local_version(pkg_name)
  log_with_color(f"Attempting to update package: {pkg_name}(local version: {initial_version})")
  quiet = args.quiet
  cmd = [sys.executable, "-m", "pip", "install", "--upgrade", pkg_name]

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
