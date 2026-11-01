from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .telemetry_schema import (
    ConnectivityStatus,
    DHCPStatus,
    DNSStatus,
    DeviceStatus,
    DeviceType,
    TelemetryRecord,
)


class RecordValidationError(BaseModel):
    """Structured validation error detailing invalid fields in a telemetry record."""
    model_config = ConfigDict(populate_by_name=True)

    field: str = Field(..., description="Name of the invalid or missing field")
    message: str = Field(..., description="Human-readable explanation of why validation failed")
    invalid_value: Any = Field(default=None, description="The raw invalid value observed")
    record_index: Optional[int] = Field(default=None, description="Index of the record in a batch")
    device_id: Optional[str] = Field(default=None, description="Device identifier if available")

    def __str__(self) -> str:
        idx_info = f"[Record #{self.record_index}] " if self.record_index is not None else ""
        dev_info = f"(Device '{self.device_id}') " if self.device_id else ""
        return f"{idx_info}{dev_info}Field '{self.field}': {self.message} (Got: {self.invalid_value!r})"


class ValidationResult(BaseModel):
    """Result container for single record validation."""
    model_config = ConfigDict(populate_by_name=True)

    is_valid: bool
    record: Optional[TelemetryRecord] = None
    errors: List[RecordValidationError] = Field(default_factory=list)


class TelemetryValidator:
    """
    Robust telemetry validation engine ensuring all input records adhere strictly to
    identification, range, type, and domain rules before reaching diagnostic agents.
    Does NOT silently convert invalid values into valid ones.
    """

    NUMERIC_BOUNDS = {
        "latency_ms": (0.0, None, "Latency cannot be negative"),
        "jitter_ms": (0.0, None, "Jitter cannot be negative"),
        "throughput_mbps": (0.0, None, "Throughput cannot be negative"),
        "interface_errors": (0, None, "Interface errors cannot be negative"),
        "queue_drops": (0, None, "Queue drops cannot be negative"),
        "packet_loss_percent": (0.0, 100.0, "Packet loss percentage must be between 0.0 and 100.0%"),
        "bandwidth_utilization_percent": (0.0, 100.0, "Bandwidth utilization percentage must be between 0.0 and 100.0%"),
        "cpu_utilization_percent": (0.0, 100.0, "CPU utilization percentage must be between 0.0 and 100.0%"),
        "memory_utilization_percent": (0.0, 100.0, "Memory utilization percentage must be between 0.0 and 100.0%"),
        "wifi_signal_dbm": (-120.0, 0.0, "Wi-Fi signal RSSI must be between -120.0 and 0.0 dBm"),
    }

    # Aliases to check during raw inspection
    FIELD_ALIASES = {
        "packet_loss_pct": "packet_loss_percent",
        "bandwidth_util_pct": "bandwidth_utilization_percent",
        "cpu_util_pct": "cpu_utilization_percent",
        "memory_util_pct": "memory_utilization_percent",
        "wifi_rssi_dbm": "wifi_signal_dbm",
        "dns_resolution_status": "dns_status",
    }

    @classmethod
    def validate_record(cls, raw_data: Any, index: Optional[int] = None) -> ValidationResult:
        """
        Validates a single telemetry record with detailed rule checks and strict error reporting.
        """
        errors: List[RecordValidationError] = []

        if raw_data is None:
            err = RecordValidationError(
                field="record",
                message="Telemetry record payload cannot be None",
                invalid_value=None,
                record_index=index,
            )
            return ValidationResult(is_valid=False, record=None, errors=[err])

        if not isinstance(raw_data, (dict, TelemetryRecord)):
            err = RecordValidationError(
                field="record",
                message=f"Expected telemetry record dict or TelemetryRecord, got {type(raw_data).__name__}",
                invalid_value=raw_data,
                record_index=index,
            )
            return ValidationResult(is_valid=False, record=None, errors=[err])

        if isinstance(raw_data, TelemetryRecord):
            return ValidationResult(is_valid=True, record=raw_data, errors=[])

        # Normalize alias keys into standard schema keys
        data: Dict[str, Any] = {}
        for k, v in raw_data.items():
            canonical_key = cls.FIELD_ALIASES.get(k, k)
            # Only set canonical if not already explicitly present
            if canonical_key not in data:
                data[canonical_key] = v

        device_id_val = data.get("device_id")
        dev_id_str = str(device_id_val) if device_id_val is not None else None

        # 1. IDENTIFICATION RULES
        # Missing required device_id
        if "device_id" not in data or data["device_id"] is None or str(data["device_id"]).strip() == "":
            errors.append(
                RecordValidationError(
                    field="device_id",
                    message="Missing or empty required identification field 'device_id'",
                    invalid_value=data.get("device_id"),
                    record_index=index,
                    device_id=dev_id_str,
                )
            )

        # Missing required timestamp
        if "timestamp" not in data or data["timestamp"] is None or str(data["timestamp"]).strip() == "":
            errors.append(
                RecordValidationError(
                    field="timestamp",
                    message="Missing required identification field 'timestamp'",
                    invalid_value=data.get("timestamp"),
                    record_index=index,
                    device_id=dev_id_str,
                )
            )

        # 2. RANGE AND TYPE RULES FOR NUMERIC METRICS
        for field_name, (min_val, max_val, err_msg) in cls.NUMERIC_BOUNDS.items():
            if field_name in data and data[field_name] is not None:
                val = data[field_name]
                # Check data type
                if isinstance(val, bool):
                    errors.append(
                        RecordValidationError(
                            field=field_name,
                            message=f"Invalid data type for numeric field '{field_name}'. Booleans are not permitted.",
                            invalid_value=val,
                            record_index=index,
                            device_id=dev_id_str,
                        )
                    )
                    continue

                try:
                    num_val = float(val) if "int" not in str(type(val)) or field_name not in ["interface_errors", "queue_drops"] else int(val)
                except (ValueError, TypeError):
                    errors.append(
                        RecordValidationError(
                            field=field_name,
                            message=f"Invalid numeric data type for field '{field_name}'. Value cannot be parsed as number.",
                            invalid_value=val,
                            record_index=index,
                            device_id=dev_id_str,
                        )
                    )
                    continue

                import math
                if isinstance(num_val, float) and (math.isnan(num_val) or math.isinf(num_val)):
                    errors.append(
                        RecordValidationError(
                            field=field_name,
                            message=f"Field '{field_name}' must be a finite number (got {val})",
                            invalid_value=val,
                            record_index=index,
                            device_id=dev_id_str,
                        )
                    )
                    continue

                # Range check
                if min_val is not None and num_val < min_val:
                    errors.append(
                        RecordValidationError(
                            field=field_name,
                            message=f"{err_msg}. Observed: {num_val} < {min_val}",
                            invalid_value=val,
                            record_index=index,
                            device_id=dev_id_str,
                        )
                    )
                if max_val is not None and num_val > max_val:
                    errors.append(
                        RecordValidationError(
                            field=field_name,
                            message=f"{err_msg}. Observed: {num_val} > {max_val}",
                            invalid_value=val,
                            record_index=index,
                            device_id=dev_id_str,
                        )
                    )

        # 3. STATUS ENUM RULES
        status_checks = [
            ("device_status", DeviceStatus, "Allowed device_status values"),
            ("dns_status", DNSStatus, "Allowed dns_status values"),
            ("dhcp_status", DHCPStatus, "Allowed dhcp_status values"),
            ("connectivity_status", ConnectivityStatus, "Allowed connectivity_status values"),
        ]

        for status_field, enum_cls, desc in status_checks:
            if status_field in data and data[status_field] is not None:
                val = str(data[status_field]).strip().lower()
                allowed = {e.value for e in enum_cls}
                if val not in allowed:
                    errors.append(
                        RecordValidationError(
                            field=status_field,
                            message=f"Invalid status value for '{status_field}'. {desc}: {sorted(allowed)}",
                            invalid_value=data[status_field],
                            record_index=index,
                            device_id=dev_id_str,
                        )
                    )

        # If any preliminary rule failed, do not proceed to Pydantic instantiation
        if errors:
            return ValidationResult(is_valid=False, record=None, errors=errors)

        # 4. PYDANTIC MODEL INSTANTIATION
        try:
            record = TelemetryRecord.model_validate(data)
            return ValidationResult(is_valid=True, record=record, errors=[])
        except ValidationError as exc:
            for pydantic_err in exc.errors():
                loc = ".".join(str(l) for l in pydantic_err.get("loc", []))
                errors.append(
                    RecordValidationError(
                        field=loc or "schema",
                        message=pydantic_err.get("msg", "Schema validation error"),
                        invalid_value=pydantic_err.get("input"),
                        record_index=index,
                        device_id=dev_id_str,
                    )
                )
            return ValidationResult(is_valid=False, record=None, errors=errors)

    @classmethod
    def validate_batch(cls, records: List[Any]) -> Tuple[List[TelemetryRecord], List[RecordValidationError]]:
        """
        Validates a collection of telemetry records.
        Guarantees that one invalid record does NOT silently corrupt the remaining valid records.
        """
        valid_records: List[TelemetryRecord] = []
        all_errors: List[RecordValidationError] = []

        if not records:
            return valid_records, all_errors

        for idx, item in enumerate(records):
            res = cls.validate_record(item, index=idx)
            if res.is_valid and res.record is not None:
                valid_records.append(res.record)
            else:
                all_errors.extend(res.errors)

        return valid_records, all_errors
