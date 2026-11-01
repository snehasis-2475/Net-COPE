from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Union


class BaselineAnomaly(dict):
    """Explainable anomaly emitted by BaselineDetector supporting dict and attribute access."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        for k, v in kwargs.items():
            dict.__setitem__(self, k, v)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'BaselineAnomaly' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        dict.__setitem__(self, name, value)


class MetricBaselineState:
    """Per-device, per-metric EWMA state with robust spread and sustained anomaly counter."""

    def __init__(
        self,
        alpha: float = 0.05,
        min_std: float = 0.5,
        clip_sigma: float = 3.0,
        z_threshold: float = 3.5,
        sustained_required: int = 3,
        warmup_period: int = 10,
    ) -> None:
        self.alpha = alpha
        self.min_std = min_std
        self.clip_sigma = clip_sigma
        self.z_threshold = z_threshold
        self.sustained_required = sustained_required
        self.warmup_period = warmup_period

        self.count: int = 0
        self.mean: Optional[float] = None
        self.var: Optional[float] = None
        self.sustained_points: int = 0
        self.last_val: Optional[float] = None
        self.last_std: float = min_std
        self.last_z: float = 0.0

    def update(self, val: Optional[float]) -> None:
        if val is None:
            return
        try:
            val_f = float(val)
        except (ValueError, TypeError):
            return

        if math.isnan(val_f) or math.isinf(val_f):
            return

        self.count += 1
        self.last_val = val_f

        if self.mean is None:
            self.mean = val_f
            self.var = self.min_std**2
            self.last_std = self.min_std
            self.last_z = 0.0
            self.sustained_points = 0
            return

        current_std = math.sqrt(max(self.var if self.var is not None else 0.0, self.min_std**2))
        self.last_std = current_std
        deviation = val_f - self.mean
        z_score = deviation / current_std
        self.last_z = z_score

        # Warmup period check
        if self.count <= self.warmup_period:
            self.mean = (1 - self.alpha) * self.mean + self.alpha * val_f
            self.var = (1 - self.alpha) * (self.var if self.var is not None else 0.0) + self.alpha * (deviation**2)
            self.sustained_points = 0
            return

        # Check anomaly condition
        if abs(z_score) > self.z_threshold:
            self.sustained_points += 1
            effective_alpha = 0.0  # Freeze baseline update during sustained anomaly to prevent poisoning
        else:
            self.sustained_points = 0
            effective_alpha = self.alpha

        # Outlier clipping for baseline update (M-estimation clipping)
        clipped_dev = max(-self.clip_sigma * current_std, min(self.clip_sigma * current_std, deviation))
        self.mean = (1 - effective_alpha) * self.mean + effective_alpha * (self.mean + clipped_dev)
        self.var = (1 - effective_alpha) * (self.var if self.var is not None else 0.0) + effective_alpha * (clipped_dev**2)

    def get_anomaly(self, device_id: str, metric: str) -> Optional[BaselineAnomaly]:
        if self.count <= self.warmup_period:
            return None
        if self.sustained_points >= self.sustained_required and abs(self.last_z) > self.z_threshold and self.last_val is not None and self.mean is not None:
            direction = "above" if self.last_z > 0 else "below"
            metric_label = "RTT" if metric in ("rtt_ms", "latency_ms") else metric
            unit = (
                "ms"
                if metric in ("rtt_ms", "latency_ms", "jitter_ms", "dns_latency_ms", "dhcp_response_time_ms")
                else ("%" if "pct" in metric or "percent" in metric else ("dBm" if "dbm" in metric else ""))
            )
            desc = (
                f"{metric_label} is {abs(self.last_z):.1f} sigma {direction} this device's rolling baseline "
                f"({self.last_val:.0f}{unit} vs usual {self.mean:.0f}{unit}) for {self.sustained_points} consecutive samples"
            )
            return BaselineAnomaly(
                device_id=device_id,
                metric=metric,
                value=round(self.last_val, 2),
                current_value=round(self.last_val, 2),
                baseline=round(self.mean, 2),
                baseline_mean=round(self.mean, 2),
                baseline_std=round(self.last_std, 2),
                z_score=round(self.last_z, 2),
                direction=direction,
                sustained_points=self.sustained_points,
                sustained_count=self.sustained_points,
                description=desc,
                unit=unit,
            )
        return None


class BaselineDetector:
    """
    Per-device rolling baseline anomaly detector that catches 'silent degradation'
    (metrics drifting without crossing static thresholds).

    Features:
    - Per (device_id, metric) EWMA mean and robust spread
    - update(record) and score(record) -> list of anomalies
    - Flag only when |z| > 3.5 sustained for >= 3 consecutive points
    - Warm-up period (need >= 10 points before scoring)
    - Missing metrics handled cleanly without resetting state
    - Robust outlier clipping (M-estimation)
    - Pure Python / NumPy, deterministic, zero I/O
    - Human-readable explainable output
    """

    NUMERIC_METRICS = [
        "latency_ms",
        "rtt_ms",
        "packet_loss_pct",
        "jitter_ms",
        "bandwidth_util_pct",
        "cpu_utilization_pct",
        "memory_utilization_pct",
        "queue_drops",
        "error_count",
        "wifi_signal_strength_dbm",
        "wifi_retransmit_pct",
        "dns_latency_ms",
        "dns_failure_rate_pct",
        "dhcp_response_time_ms",
        "dhcp_failure_rate_pct",
    ]

    def __init__(
        self,
        alpha: float = 0.05,
        min_std: float = 0.5,
        z_threshold: float = 3.5,
        sustained_required: int = 3,
        warmup_period: int = 10,
        clip_sigma: float = 3.0,
    ) -> None:
        self.alpha = alpha
        self.min_std = min_std
        self.z_threshold = z_threshold
        self.sustained_required = sustained_required
        self.warmup_period = warmup_period
        self.clip_sigma = clip_sigma
        self._states: Dict[Tuple[str, str], MetricBaselineState] = {}
        self._latest_anomalies: List[BaselineAnomaly] = []

    def _get_or_create_state(self, device_id: str, metric_name: str) -> MetricBaselineState:
        key = (device_id, metric_name)
        if key not in self._states:
            self._states[key] = MetricBaselineState(
                alpha=self.alpha,
                min_std=self.min_std,
                clip_sigma=self.clip_sigma,
                z_threshold=self.z_threshold,
                sustained_required=self.sustained_required,
                warmup_period=self.warmup_period,
            )
        return self._states[key]

    def _extract_device_and_metrics(
        self,
        record_or_device_id: Any,
        metric_name: Optional[str] = None,
        value: Optional[float] = None,
    ) -> Tuple[str, List[Tuple[str, Optional[float]]]]:
        # Single-metric direct invocation: update(device_id, metric, value)
        if isinstance(record_or_device_id, str) and metric_name is not None:
            return record_or_device_id, [(metric_name, value)]

        # Record dict or object invocation: update(record)
        record = record_or_device_id
        if isinstance(record, dict):
            dev_id = str(record.get("device_id", "unknown"))
            items: List[Tuple[str, Optional[float]]] = []
            for k in self.NUMERIC_METRICS:
                if k in record:
                    items.append((k, record.get(k)))
            for k, v in record.items():
                if k not in self.NUMERIC_METRICS and isinstance(v, (int, float)) and not isinstance(v, bool):
                    if k not in ("port", "id", "episode_id"):
                        items.append((k, v))
            return dev_id, items

        # Object (Pydantic / dataclass / class)
        dev_id = str(getattr(record, "device_id", "unknown"))
        items = []
        for k in self.NUMERIC_METRICS:
            if hasattr(record, k):
                items.append((k, getattr(record, k)))
        return dev_id, items

    def update(
        self,
        record_or_device_id: Any,
        metric_name: Optional[str] = None,
        value: Optional[float] = None,
    ) -> Optional[Any]:
        dev_id, metrics = self._extract_device_and_metrics(record_or_device_id, metric_name, value)
        anomalies: List[BaselineAnomaly] = []

        for m_name, m_val in metrics:
            state = self._get_or_create_state(dev_id, m_name)
            state.update(m_val)
            anom = state.get_anomaly(dev_id, m_name)
            if anom:
                anomalies.append(anom)

        self._latest_anomalies = anomalies

        # Single metric call compatibility: if called with 3 args, return single anomaly or None
        if isinstance(record_or_device_id, str) and metric_name is not None:
            return anomalies[0] if anomalies else None
        return None

    def score(
        self,
        record_or_device_id: Any,
        metric_name: Optional[str] = None,
        value: Optional[float] = None,
    ) -> List[BaselineAnomaly]:
        dev_id, metrics = self._extract_device_and_metrics(record_or_device_id, metric_name, value)
        anomalies: List[BaselineAnomaly] = []

        for m_name, _ in metrics:
            key = (dev_id, m_name)
            if key in self._states:
                state = self._states[key]
                anom = state.get_anomaly(dev_id, m_name)
                if anom:
                    anomalies.append(anom)

        return anomalies

    def update_and_score(
        self,
        record_or_device_id: Any,
        metric_name: Optional[str] = None,
        value: Optional[float] = None,
    ) -> List[BaselineAnomaly]:
        self.update(record_or_device_id, metric_name, value)
        return self.score(record_or_device_id, metric_name, value)

    def get_state(self, device_id: str, metric_name: str) -> Optional[Dict[str, Any]]:
        key = (device_id, metric_name)
        state = self._states.get(key)
        if not state or state.mean is None:
            return None
        return {
            "device_id": device_id,
            "metric": metric_name,
            "count": state.count,
            "mean": state.mean,
            "std": state.last_std,
            "sustained_points": state.sustained_points,
            "sustained_count": state.sustained_points,
        }
