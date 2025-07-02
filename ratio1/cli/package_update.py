from importlib import metadata
import subprocess
import sys
from ratio1.utils.config import log_with_color


def _dist_name() -> str:
  """Return the canonical wheel name (e.g. 'mycli') for the running code."""
  pkg = __package__.split(".", 1)[0]
  return metadata.distribution(pkg).metadata["Name"]


def update_package(args) -> None:
  """
  Update the package in-place using pip.
  This can be run through
  ```
  r1ctl update
  ```
  """
  log_with_color(f"Updating package: {_dist_name()}")
  quiet = args.quiet
  cmd = [sys.executable, "-m", "pip", "install", "--upgrade", _dist_name()]

  # Inherit or suppress output based on `quiet`
  stdout = subprocess.DEVNULL if quiet else None
  stderr = subprocess.STDOUT if quiet else None

  exit_code = subprocess.call(cmd, stdout=stdout, stderr=stderr)

  if exit_code != 0:
    log_with_color(f"Package update failed with exit code {exit_code}.", color='r')
  else:
    log_with_color("Package updated successfully.", color='g')
  # endif exit_code
  return


if __name__ == "__main__":
  import argparse

  parser = argparse.ArgumentParser(description="Update the package in-place.")
  parser.add_argument('--quiet', action='store_false', help="Suppress pip's output.")
  args = parser.parse_args()

  update_package(args)
