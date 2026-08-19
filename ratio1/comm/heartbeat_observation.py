"""Configuration, trust policy, and readiness for heartbeat observation modes."""

import json
import re
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..const import COMMS, HB, PAYLOAD_DATA


HEARTBEAT_MODE_FULL_NETWORK = "full_network"
HEARTBEAT_MODE_SELECTED_NODES = "selected_nodes"
HEARTBEAT_MODE_SUMMARY_DISCOVERY = "summary_discovery"
HEARTBEAT_OBSERVATION_MODES = (
  HEARTBEAT_MODE_FULL_NETWORK,
  HEARTBEAT_MODE_SELECTED_NODES,
  HEARTBEAT_MODE_SUMMARY_DISCOVERY,
)

DEFAULT_HEARTBEAT_MAX_AGE_SECONDS = 120.0
DEFAULT_HEARTBEAT_FUTURE_SKEW_SECONDS = 10.0
DEFAULT_HEARTBEAT_OBSERVATION_TIMEOUT_SECONDS = 30.0

_RATIO1_ADDRESS = re.compile(r"^0xai_[A-Za-z0-9_-]{20,}$")


def _ordered_addresses(values, field_name):
  """Validate and deduplicate Ratio1 addresses while preserving order.

  Parameters
  ----------
  values : iterable of str or str or None
    Address values supplied by a caller or config mapping.
  field_name : str
    Human-readable field label used in validation errors.

  Returns
  -------
  tuple of str
    Validated unique addresses.
  """
  if values is None:
    return ()
  if isinstance(values, str):
    values = [value.strip() for value in values.split(",") if value.strip()]
  result = []
  for value in values:
    if not isinstance(value, str) or not _RATIO1_ADDRESS.fullmatch(value):
      raise ValueError(
        "{} must contain full Ratio1 node addresses; got {!r}".format(
          field_name,
          value,
        )
      )
    if value not in result:
      result.append(value)
  return tuple(result)


def _positive_number(value, field_name, allow_zero=False):
  """Normalize one numeric observation setting.

  Parameters
  ----------
  value : object
    Value to convert to ``float``.
  field_name : str
    Setting name used in validation errors.
  allow_zero : bool, optional
    Whether zero is accepted.

  Returns
  -------
  float
    Validated numeric value.
  """
  try:
    result = float(value)
  except (TypeError, ValueError) as exc:
    raise ValueError("{} must be numeric".format(field_name)) from exc
  if not math.isfinite(result):
    raise ValueError("{} must be finite".format(field_name))
  if result < 0 or (result == 0 and not allow_zero):
    qualifier = "non-negative" if allow_zero else "positive"
    raise ValueError("{} must be {}".format(field_name, qualifier))
  return result


@dataclass(frozen=True)
class HeartbeatObservationConfig:
  """Hold the immutable heartbeat observation contract for one SDK session.

  Parameters
  ----------
  mode : str
    One of the three supported observation modes.
  nodes : tuple of str
    Selected signer addresses for ``selected_nodes``.
  summary_publishers : tuple of str
    Trusted signer addresses for ``summary_discovery``.
  max_age_seconds : float
    Maximum accepted signed-message age.
  future_skew_seconds : float
    Maximum accepted future clock skew.
  observation_timeout_seconds : float
    Time before missing reduced-mode evidence is reported as degraded.
  """

  mode: str = HEARTBEAT_MODE_FULL_NETWORK
  nodes: tuple = ()
  summary_publishers: tuple = ()
  max_age_seconds: float = DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
  future_skew_seconds: float = DEFAULT_HEARTBEAT_FUTURE_SKEW_SECONDS
  observation_timeout_seconds: float = DEFAULT_HEARTBEAT_OBSERVATION_TIMEOUT_SECONDS

  @classmethod
  def from_values(
      cls,
      mode=None,
      nodes=None,
      summary_publishers=None,
      max_age_seconds=None,
      future_skew_seconds=None,
      observation_timeout_seconds=None,
    ):
    """Build and validate a configuration from explicit values.

    Parameters
    ----------
    mode : str, optional
      Observation mode. Omission preserves ``full_network`` behavior.
    nodes : iterable of str, optional
      Exact node addresses for selected-node observation.
    summary_publishers : iterable of str, optional
      Trusted NetMon publisher addresses.
    max_age_seconds : float, optional
      Maximum signed-message age.
    future_skew_seconds : float, optional
      Maximum future timestamp allowance.
    observation_timeout_seconds : float, optional
      Reduced-mode readiness timeout.

    Returns
    -------
    HeartbeatObservationConfig
      Frozen validated configuration.
    """
    mode = mode or HEARTBEAT_MODE_FULL_NETWORK
    if mode not in HEARTBEAT_OBSERVATION_MODES:
      raise ValueError(
        "Invalid heartbeat observation mode {!r}; expected one of {}".format(
          mode,
          HEARTBEAT_OBSERVATION_MODES,
        )
      )

    normalized_nodes = _ordered_addresses(nodes, "selected nodes")
    normalized_publishers = _ordered_addresses(
      summary_publishers,
      "summary publishers",
    )
    if mode == HEARTBEAT_MODE_SELECTED_NODES and not normalized_nodes:
      raise ValueError("selected_nodes requires at least one selected node address")
    if mode == HEARTBEAT_MODE_SUMMARY_DISCOVERY and not normalized_publishers:
      raise ValueError(
        "summary_discovery requires at least one summary publisher address"
      )
    if mode == HEARTBEAT_MODE_FULL_NETWORK:
      normalized_nodes = ()
      normalized_publishers = ()

    max_age = (
      DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
      if max_age_seconds is None
      else _positive_number(max_age_seconds, "max_age_seconds")
    )
    future_skew = (
      DEFAULT_HEARTBEAT_FUTURE_SKEW_SECONDS
      if future_skew_seconds is None
      else _positive_number(
        future_skew_seconds,
        "future_skew_seconds",
        allow_zero=True,
      )
    )
    timeout = (
      DEFAULT_HEARTBEAT_OBSERVATION_TIMEOUT_SECONDS
      if observation_timeout_seconds is None
      else _positive_number(
        observation_timeout_seconds,
        "observation_timeout_seconds",
      )
    )
    return cls(
      mode=mode,
      nodes=normalized_nodes,
      summary_publishers=normalized_publishers,
      max_age_seconds=max_age,
      future_skew_seconds=future_skew,
      observation_timeout_seconds=timeout,
    )

  @classmethod
  def from_sources(
      cls,
      config=None,
      mode=None,
      nodes=None,
      summary_publishers=None,
      max_age_seconds=None,
      future_skew_seconds=None,
      observation_timeout_seconds=None,
    ):
    """Build configuration with explicit values taking precedence over a mapping.

    Parameters
    ----------
    config : dict, optional
      Session configuration containing observation keys.
    mode : str, optional
      Explicit observation mode override.
    nodes : iterable of str, optional
      Explicit selected-node override.
    summary_publishers : iterable of str, optional
      Explicit trusted-summary publisher override.
    max_age_seconds : float, optional
      Explicit age limit override.
    future_skew_seconds : float, optional
      Explicit future-skew override.
    observation_timeout_seconds : float, optional
      Explicit readiness timeout override.

    Returns
    -------
    HeartbeatObservationConfig
      Frozen merged configuration.
    """
    config = config or {}
    return cls.from_values(
      mode=(
        config.get("HEARTBEAT_OBSERVATION_MODE") if mode is None else mode
      ),
      nodes=(
        config.get("HEARTBEAT_OBSERVATION_NODES") if nodes is None else nodes
      ),
      summary_publishers=(
        config.get("HEARTBEAT_SUMMARY_PUBLISHERS")
        if summary_publishers is None
        else summary_publishers
      ),
      max_age_seconds=(
        config.get("HEARTBEAT_OBSERVATION_MAX_AGE")
        if max_age_seconds is None
        else max_age_seconds
      ),
      future_skew_seconds=(
        config.get("HEARTBEAT_OBSERVATION_FUTURE_SKEW")
        if future_skew_seconds is None
        else future_skew_seconds
      ),
      observation_timeout_seconds=(
        config.get("HEARTBEAT_OBSERVATION_TIMEOUT")
        if observation_timeout_seconds is None
        else observation_timeout_seconds
      ),
    )

  def heartbeat_topics(self, channel_config):
    """Resolve exact heartbeat subscriptions for this mode.

    Parameters
    ----------
    channel_config : dict
      Configured ``CTRL_CHANNEL`` mapping.

    Returns
    -------
    tuple of str
      Exact MQTT topics. Summary mode deliberately returns an empty tuple.
    """
    if self.mode == HEARTBEAT_MODE_SUMMARY_DISCOVERY:
      return ()
    if self.mode == HEARTBEAT_MODE_FULL_NETWORK:
      topic = channel_config.get(COMMS.TOPIC)
      if not isinstance(topic, str) or not topic:
        raise ValueError("CTRL_CHANNEL TOPIC is required")
      return (topic,)
    targeted_topic = channel_config.get(COMMS.TARGETED_TOPIC)
    if not isinstance(targeted_topic, str) or "{}" not in targeted_topic:
      raise ValueError(
        "selected_nodes requires CTRL_CHANNEL TARGETED_TOPIC capability"
      )
    return tuple(targeted_topic.format(node) for node in self.nodes)


@dataclass(frozen=True)
class ObservationDecision:
  """Represent one observation authorization or content decision.

  Parameters
  ----------
  accepted : bool
    Whether the message may cross the current boundary.
  reason : str
    Stable reason code suitable for telemetry.
  sender : str, optional
    Cryptographically verified sender when available.
  envelope : dict, optional
    Parsed raw envelope when available.
  """

  accepted: bool
  reason: str
  sender: str | None = None
  envelope: dict | None = None


class HeartbeatObservationPolicy:
  """Authorize reduced-mode messages before formatter-controlled mutation.

  Parameters
  ----------
  config : HeartbeatObservationConfig
    Immutable session observation settings.
  verifier : object
    Ratio1 blockchain engine exposing ``verify``.
  decompress_text : callable, optional
    Decoder for signed heartbeat-v2 ``ENCODED_DATA``.
  """

  def __init__(self, config, verifier, decompress_text=None):
    self.config = config
    self.verifier = verifier
    self.decompress_text = decompress_text
    self._lock = Lock()
    self._accepted = Counter()
    self._rejected = Counter()

  def _decision(self, accepted, reason, sender=None, envelope=None):
    """Create and account for a policy decision."""
    with self._lock:
      target = self._accepted if accepted else self._rejected
      target[reason] += 1
    return ObservationDecision(accepted, reason, sender, envelope)

  def _load_envelope(self, raw_message):
    """Decode one raw JSON object without invoking a formatter."""
    try:
      envelope = json.loads(raw_message) if isinstance(raw_message, str) else raw_message
    except (TypeError, ValueError, json.JSONDecodeError):
      return None
    return envelope if isinstance(envelope, dict) else None

  def _verify_envelope(self, envelope):
    """Verify signature and sender agreement on an unmodified envelope."""
    try:
      verification = self.verifier.verify(
        envelope,
        log_hash_sign_fails=False,
      )
    except Exception:
      return None, "verification_error"
    if not getattr(verification, "valid", False):
      return None, "invalid_signature"
    signed_sender = envelope.get(PAYLOAD_DATA.EE_SENDER)
    verified_sender = getattr(verification, "sender", None)
    if not signed_sender or verified_sender != signed_sender:
      return None, "verified_sender_mismatch"
    return verified_sender, None

  def _timestamp_reason(self, envelope, now, timestamp_key, stale_reason, future_reason):
    """Return a freshness rejection code or ``None`` for one timestamp."""
    timestamp_value = envelope.get(timestamp_key)
    if not timestamp_value:
      return "missing_timestamp"
    timestamp = _parse_wire_timestamp(timestamp_value, envelope)
    if timestamp is None:
      return "invalid_timestamp"
    now = _normalize_now(now)
    age = (now - timestamp).total_seconds()
    if age > self.config.max_age_seconds:
      return stale_reason
    if age < -self.config.future_skew_seconds:
      return future_reason
    return None

  def authorize_heartbeat(self, raw_message, now=None):
    """Authorize one raw heartbeat for the configured mode.

    Parameters
    ----------
    raw_message : str or dict
      Signed wire envelope before formatter decoding.
    now : datetime, optional
      Deterministic wall-clock value for freshness tests.

    Returns
    -------
    ObservationDecision
      Authorization result with a stable reason code.
    """
    envelope = self._load_envelope(raw_message)
    if envelope is None:
      return self._decision(False, "invalid_json")
    if self.config.mode == HEARTBEAT_MODE_FULL_NETWORK:
      return self._decision(True, "legacy_full_network", envelope=envelope)
    if self.config.mode != HEARTBEAT_MODE_SELECTED_NODES:
      return self._decision(False, "heartbeat_receive_disabled", envelope=envelope)

    sender, error = self._verify_envelope(envelope)
    if error:
      return self._decision(False, error, envelope=envelope)
    if sender not in self.config.nodes:
      return self._decision(False, "unselected_sender", sender, envelope)
    timestamp_error = self._timestamp_reason(
      envelope,
      now,
      PAYLOAD_DATA.EE_TIMESTAMP,
      "stale_timestamp",
      "future_timestamp",
    )
    if timestamp_error:
      return self._decision(False, timestamp_error, sender, envelope)

    body = envelope
    if envelope.get(HB.HEARTBEAT_VERSION) == HB.V2:
      encoded_data = envelope.get(HB.ENCODED_DATA)
      if not encoded_data or self.decompress_text is None:
        return self._decision(False, "invalid_encoded_heartbeat", sender, envelope)
      try:
        decoded_text = self.decompress_text(encoded_data)
        body = json.loads(decoded_text)
      except (TypeError, ValueError, json.JSONDecodeError):
        return self._decision(False, "invalid_encoded_heartbeat", sender, envelope)
      if not isinstance(body, dict):
        return self._decision(False, "invalid_encoded_heartbeat", sender, envelope)

    inner_sender = body.get(HB.EE_ADDR)
    if inner_sender is not None and inner_sender != sender:
      return self._decision(False, "inner_sender_mismatch", sender, envelope)
    if body.get(HB.CURRENT_TIME) is not None:
      inner_timestamp_error = self._timestamp_reason(
        body,
        now,
        HB.CURRENT_TIME,
        "stale_inner_timestamp",
        "future_inner_timestamp",
      )
      if inner_timestamp_error:
        return self._decision(False, inner_timestamp_error, sender, envelope)
    return self._decision(True, "accepted", sender, envelope)

  def authorize_summary(self, raw_message, now=None):
    """Authorize one raw trusted NetMon summary envelope.

    Parameters
    ----------
    raw_message : str or dict
      Signed payload envelope before formatter decoding.
    now : datetime, optional
      Deterministic wall-clock value for freshness tests.

    Returns
    -------
    ObservationDecision
      Authorization result. Decoded network content needs a separate check.
    """
    envelope = self._load_envelope(raw_message)
    if envelope is None:
      return self._decision(False, "invalid_json")
    path = envelope.get(PAYLOAD_DATA.EE_PAYLOAD_PATH)
    if (
      not isinstance(path, (list, tuple))
      or len(path) < 3
      or str(path[1]).lower() != "admin_pipeline"
      or str(path[2]).upper() != "NET_MON_01"
    ):
      return self._decision(False, "not_netmon_summary", envelope=envelope)
    sender, error = self._verify_envelope(envelope)
    if error:
      return self._decision(False, error, envelope=envelope)
    if sender not in self.config.summary_publishers:
      return self._decision(
        False,
        "untrusted_summary_publisher",
        sender,
        envelope,
      )
    timestamp_error = self._timestamp_reason(
      envelope,
      now,
      PAYLOAD_DATA.EE_TIMESTAMP,
      "stale_timestamp",
      "future_timestamp",
    )
    if timestamp_error:
      return self._decision(False, timestamp_error, sender, envelope)
    return self._decision(True, "accepted", sender, envelope)

  def validate_summary_content(self, decoded_message):
    """Require a non-empty decoded network map before state mutation.

    Parameters
    ----------
    decoded_message : dict
      Formatter-decoded NetMon payload.

    Returns
    -------
    ObservationDecision
      Content validation result.
    """
    if not isinstance(decoded_message, dict):
      return self._decision(False, "invalid_summary_content")
    current_network = decoded_message.get(PAYLOAD_DATA.NETMON_CURRENT_NETWORK)
    if not isinstance(current_network, dict) or not current_network:
      return self._decision(False, "empty_network_summary")
    return self._decision(True, "valid_summary_content")

  def snapshot(self):
    """Return policy acceptance and rejection counters.

    Returns
    -------
    dict
      Counter copies safe for status reporting.
    """
    with self._lock:
      return {
        "accepted": dict(self._accepted),
        "rejected": dict(self._rejected),
      }


def _normalize_now(now):
  """Normalize a wall-clock value to an aware UTC datetime."""
  if now is None:
    return datetime.now(timezone.utc)
  if now.tzinfo is None:
    return now.replace(tzinfo=timezone.utc)
  return now.astimezone(timezone.utc)


def _parse_wire_timestamp(value, envelope):
  """Parse a Ratio1 wire timestamp with its signed timezone metadata."""
  if not isinstance(value, str):
    return None
  parsed = None
  for timestamp_format in [HB.TIMESTAMP_FORMAT, HB.TIMESTAMP_FORMAT_SHORT]:
    try:
      parsed = datetime.strptime(value, timestamp_format)
      break
    except ValueError:
      continue
  if parsed is None:
    try:
      parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
      return None
  if parsed.tzinfo is None:
    tzinfo = _timezone_from_envelope(envelope)
    parsed = parsed.replace(tzinfo=tzinfo)
  return parsed.astimezone(timezone.utc)


def _timezone_from_envelope(envelope):
  """Resolve signed IANA or ``UTC+offset`` timezone metadata."""
  zone_name = envelope.get(PAYLOAD_DATA.EE_TZ)
  if isinstance(zone_name, str) and zone_name:
    try:
      return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
      pass
  timezone_name = envelope.get(PAYLOAD_DATA.EE_TIMEZONE, "UTC+0")
  match = re.fullmatch(r"UTC([+-])(\d{1,2})(?::?(\d{2}))?", str(timezone_name))
  if match:
    hours = int(match.group(2))
    minutes = int(match.group(3) or 0)
    offset = timedelta(hours=hours, minutes=minutes)
    if match.group(1) == "-":
      offset = -offset
    return timezone(offset)
  return timezone.utc


class HeartbeatObservationMonitor:
  """Track readiness and freshness for one immutable observation contract.

  Parameters
  ----------
  config : HeartbeatObservationConfig
    Session observation settings.
  clock : callable, optional
    Monotonic clock used for timeout and age calculation.
  """

  def __init__(self, config, clock=monotonic):
    self.config = config
    self._clock = clock
    self._lock = Lock()
    self._started_at = clock()
    self._last_valid_at = None
    self._last_valid_sender = None
    self._heartbeat_topics = []
    self._subscription_ready = config.mode != HEARTBEAT_MODE_SELECTED_NODES
    self._subscription_reason = None
    self._accepted_heartbeats = 0
    self._accepted_summaries = 0

  def set_subscription_status(self, ready, topics, reason=None):
    """Record the actual SUBACK state for selected topics.

    Parameters
    ----------
    ready : bool
      Whether every required exact topic received an acceptable SUBACK.
    topics : iterable of str
      Exact topics attempted or acknowledged.
    reason : str, optional
      Failure reason when not ready.

    Returns
    -------
    None
    """
    with self._lock:
      self._subscription_ready = bool(ready)
      self._heartbeat_topics = list(topics)
      self._subscription_reason = reason
    return

  def record_valid_observation(self, sender, source="heartbeat"):
    """Record one state-producing heartbeat or trusted summary.

    Parameters
    ----------
    sender : str
      Verified sender address.
    source : str, optional
      ``heartbeat`` or ``summary``.

    Returns
    -------
    None
    """
    with self._lock:
      self._last_valid_at = self._clock()
      self._last_valid_sender = sender
      if source == "summary":
        self._accepted_summaries += 1
      else:
        self._accepted_heartbeats += 1
    return

  def snapshot(self):
    """Return dynamic readiness and observation counters.

    Returns
    -------
    dict
      Current state, reason, topic provenance, sender, and freshness.
    """
    with self._lock:
      now = self._clock()
      last_age = (
        None
        if self._last_valid_at is None
        else max(0.0, now - self._last_valid_at)
      )
      elapsed = now - self._started_at
      mode = self.config.mode
      reason = None
      if mode == HEARTBEAT_MODE_FULL_NETWORK:
        state = "legacy_full_network"
      elif mode == HEARTBEAT_MODE_SELECTED_NODES:
        if not self._subscription_ready:
          if self._subscription_reason:
            state = "degraded"
            reason = self._subscription_reason
          else:
            state = "waiting_for_suback"
        elif self._last_valid_at is None:
          if elapsed > self.config.observation_timeout_seconds:
            state = "degraded"
            reason = "targeted_heartbeat_timeout"
          else:
            state = "waiting_for_targeted_heartbeat"
        elif last_age > self.config.observation_timeout_seconds:
          state = "degraded"
          reason = "targeted_heartbeat_timeout"
        else:
          state = "ready"
      else:
        if self._last_valid_at is None:
          if elapsed > self.config.observation_timeout_seconds:
            state = "degraded"
            reason = "trusted_summary_timeout"
          else:
            state = "waiting_for_trusted_summary"
        elif last_age > self.config.observation_timeout_seconds:
          state = "degraded"
          reason = "trusted_summary_timeout"
        else:
          state = "ready"
      return {
        "mode": mode,
        "state": state,
        "reason": reason,
        "heartbeat_topics": list(self._heartbeat_topics),
        "subscription_ready": self._subscription_ready,
        "last_valid_sender": self._last_valid_sender,
        "last_valid_age_seconds": last_age,
        "accepted_heartbeats": self._accepted_heartbeats,
        "accepted_summaries": self._accepted_summaries,
      }
