"""Read configured resource sizes for SDK reporting without runtime defaults."""

import math
import re


def resource_size_gib(value, default_unit="b"):
  """Convert a non-negative configured size to GiB.

  Parameters
  ----------
  value : int, float, str or None
      Size in bytes, or a binary-unit string such as ``512m`` or ``2GiB``.
  default_unit : str, optional
      Unit for bare numbers: ``b`` for container limits, ``g`` for netmon
      hardware totals, which are already reported in GiB.

  Returns
  -------
  float or None
      Size in GiB, or None for missing, invalid, negative or non-finite data.
  """
  if isinstance(value, bool) or value is None:
    return None
  unit = default_unit
  if isinstance(value, str):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]*)?|\.[0-9]+)\s*([kmgt](?:i?b)?|b)?", value.strip().lower())
    if match is None:
      return None
    value, suffix = match.groups()
    unit = suffix[0] if suffix else default_unit
  try:
    amount = float(value)
    result = amount * 1024 ** {"b": -3, "k": -2, "m": -1, "g": 0, "t": 1}[unit]
  except (TypeError, ValueError, OverflowError):
    return None
  return result if math.isfinite(result) and result >= 0 else None


def resource_cpu_cores(value):
  """Read a non-negative CPU allocation or hardware core count.

  Parameters
  ----------
  value : int, float, str or None
      Core count, including numeric strings from container configuration.

  Returns
  -------
  float or None
      Cores, or None for missing, invalid, negative or non-finite data.
  """
  if isinstance(value, bool) or value is None:
    return None
  try:
    cores = float(value)
  except (TypeError, ValueError, OverflowError):
    return None
  return cores if math.isfinite(cores) and cores >= 0 else None


def pipeline_allocations(pipelines):
  """Sum CPU, memory and storage across Deeploy plugin instances.

  Parameters
  ----------
  pipelines : dict or None
      Cached SDK pipelines keyed by name. None means configs are unavailable;
      an empty dictionary represents a known node with no allocated jobs.

  Returns
  -------
  tuple[float or None, float or None, float or None]
      CPU cores, memory GiB and storage GiB. Missing allocation data makes
      only that dimension unknown. Admin and non-Deeploy pipelines are excluded.
  """
  if pipelines is None:
    return None, None, None
  totals = {"cpu": 0.0, "memory": 0.0, "storage": 0.0}
  for name, pipeline in pipelines.items():
    if str(name).lower() == "admin_pipeline" or not pipeline.config.get("IS_DEEPLOYED", False):
      continue
    for instance in pipeline.lst_plugin_instances:
      resources = instance.config.get("CONTAINER_RESOURCES")
      if not isinstance(resources, dict):
        resources = {}
      for key in totals:
        value = resources.get(key)
        size = resource_cpu_cores(value) if key == "cpu" else resource_size_gib(value)
        # Never turn a partial allocation sum into an apparently complete one.
        totals[key] = totals[key] + size if totals[key] is not None and size is not None else None
  return totals["cpu"], totals["memory"], totals["storage"]


def pipeline_allocations_gib(pipelines):
  """Return memory and storage totals using the existing two-value interface.

  Parameters
  ----------
  pipelines : dict or None
      Cached SDK pipelines keyed by name, or None for unavailable configs.

  Returns
  -------
  tuple[float or None, float or None]
      Memory and storage totals in GiB, excluding admin and non-Deeploy jobs.
  """
  return pipeline_allocations(pipelines)[1:]
