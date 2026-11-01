from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .telemetry_schema import TelemetryBatchSchema, TelemetryRecord
from .telemetry_validator import RecordValidationError, TelemetryValidator


class IngestionResult(BaseModel):
    """
    Standardized result emitted by TelemetryIngestionService for all data inputs.
    Maintains clean separation between successfully validated records and failed records.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    total_records: int = 0
    valid_count: int = 0
    error_count: int = 0
    valid_records: List[TelemetryRecord] = Field(default_factory=list)
    validation_errors: List[RecordValidationError] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_fully_valid(self) -> bool:
        """True if every record passed validation without errors."""
        return self.total_records > 0 and self.error_count == 0

    @property
    def has_partial_failures(self) -> bool:
        """True if some records succeeded while others failed."""
        return self.valid_count > 0 and self.error_count > 0

    def to_dataframe(self) -> pd.DataFrame:
        """Converts validated records into a pandas DataFrame ready for agents."""
        if not self.valid_records:
            return pd.DataFrame()
        return pd.DataFrame([r.model_dump() for r in self.valid_records])


class TelemetryIngestionService:
    """
    Unified telemetry ingestion engine supporting:
    1. Single JSON records (string or dict)
    2. Collections of JSON records
    3. CSV files (filepath, string, or bytes)
    4. Batch schema payloads
    Guarantees isolation: an error in record N never corrupts record N+1.
    """

    CSV_HEADER_MAP = {
        "timestamp": ["timestamp", "time", "datetime", "date_time", "ts"],
        "device_id": ["device_id", "device", "host", "hostname", "node", "node_id", "device_name"],
        "device_type": ["device_type", "type", "role", "node_type"],
        "location": ["location", "site", "datacenter", "dc", "rack"],
        "interface_name": ["interface_name", "interface", "port", "if_name", "interface_id"],
        "latency_ms": ["latency_ms", "latency", "rtt", "rtt_ms", "ping_ms"],
        "jitter_ms": ["jitter_ms", "jitter", "delay_variation"],
        "packet_loss_percent": ["packet_loss_percent", "packet_loss_pct", "packet_loss", "loss", "loss_pct"],
        "throughput_mbps": ["throughput_mbps", "throughput", "bandwidth", "tx_rate", "rx_rate"],
        "bandwidth_utilization_percent": [
            "bandwidth_utilization_percent", "bandwidth_util_pct", "bandwidth_util", "bw_util", "utilization_pct"
        ],
        "cpu_utilization_percent": ["cpu_utilization_percent", "cpu_util_pct", "cpu", "cpu_util", "processor_util"],
        "memory_utilization_percent": ["memory_utilization_percent", "memory_util_pct", "memory", "mem_util", "ram_util"],
        "device_status": ["device_status", "status", "health_state", "operational_status"],
        "interface_errors": ["interface_errors", "errors", "crc_errors", "frame_errors"],
        "queue_drops": ["queue_drops", "drops", "buffer_drops", "tail_drops"],
        "wifi_signal_dbm": ["wifi_signal_dbm", "wifi_rssi_dbm", "wifi_rssi", "rssi", "signal_dbm"],
        "dns_status": ["dns_status", "dns_resolution_status", "dns_result", "dns_state"],
        "dhcp_status": ["dhcp_status", "dhcp_state", "dhcp_result", "lease_status"],
        "connectivity_status": ["connectivity_status", "connectivity", "reachability", "reachability_status"],
    }

    def ingest_json_record(self, record_data: Union[str, Dict[str, Any]]) -> IngestionResult:
        """Ingests a single JSON telemetry record."""
        parsed_dict: Dict[str, Any] = {}
        if isinstance(record_data, str):
            try:
                parsed = json.loads(record_data)
                if not isinstance(parsed, dict):
                    err = RecordValidationError(
                        field="json",
                        message="JSON string must represent an object/dict",
                        invalid_value=record_data,
                    )
                    return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])
                parsed_dict = parsed
            except json.JSONDecodeError as exc:
                err = RecordValidationError(
                    field="json",
                    message=f"Malformed JSON syntax: {str(exc)}",
                    invalid_value=record_data,
                )
                return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])
        elif isinstance(record_data, dict):
            parsed_dict = record_data
        else:
            err = RecordValidationError(
                field="input",
                message=f"Expected JSON str or dict, got {type(record_data).__name__}",
                invalid_value=record_data,
            )
            return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])

        res = TelemetryValidator.validate_record(parsed_dict, index=0)
        return IngestionResult(
            total_records=1,
            valid_count=1 if res.is_valid else 0,
            error_count=0 if res.is_valid else len(res.errors),
            valid_records=[res.record] if res.is_valid and res.record else [],
            validation_errors=res.errors,
            metadata={"format": "json_single"},
        )

    def ingest_json_list(self, records_data: Union[str, List[Dict[str, Any]]]) -> IngestionResult:
        """Ingests an array/list of JSON telemetry records."""
        items: List[Any] = []
        if isinstance(records_data, str):
            try:
                parsed = json.loads(records_data)
                if not isinstance(parsed, list):
                    err = RecordValidationError(
                        field="json",
                        message="JSON string must represent a list/array of objects",
                        invalid_value=records_data,
                    )
                    return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])
                items = parsed
            except json.JSONDecodeError as exc:
                err = RecordValidationError(
                    field="json",
                    message=f"Malformed JSON syntax: {str(exc)}",
                    invalid_value=records_data,
                )
                return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])
        elif isinstance(records_data, list):
            items = records_data
        else:
            err = RecordValidationError(
                field="input",
                message=f"Expected JSON list or list of dicts, got {type(records_data).__name__}",
                invalid_value=records_data,
            )
            return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])

        valid_recs, errors = TelemetryValidator.validate_batch(items)
        return IngestionResult(
            total_records=len(items),
            valid_count=len(valid_recs),
            error_count=len(errors),
            valid_records=valid_recs,
            validation_errors=errors,
            metadata={"format": "json_list"},
        )

    def ingest_csv(
        self,
        csv_source: Union[str, bytes, Path, io.StringIO, io.BytesIO],
    ) -> IngestionResult:
        """
        Parses and validates a CSV telemetry file using Pandas.
        Supports fuzzy header matching and preserves valid rows when some rows are malformed.
        """
        try:
            if isinstance(csv_source, bytes):
                df = pd.read_csv(io.BytesIO(csv_source))
            elif isinstance(csv_source, Path):
                df = pd.read_csv(csv_source)
            elif isinstance(csv_source, str):
                if "\n" in csv_source or "," in csv_source:
                    df = pd.read_csv(io.StringIO(csv_source))
                else:
                    df = pd.read_csv(csv_source)
            else:
                df = pd.read_csv(csv_source)
        except Exception as exc:
            err = RecordValidationError(
                field="csv",
                message=f"Failed to read CSV structure: {str(exc)}",
                invalid_value=None,
            )
            return IngestionResult(total_records=0, valid_count=0, error_count=1, validation_errors=[err])

        if df.empty:
            err = RecordValidationError(
                field="csv",
                message="CSV dataset is empty",
                invalid_value=None,
            )
            return IngestionResult(total_records=0, valid_count=0, error_count=1, validation_errors=[err])

        # Normalize column names with fuzzy alias matching
        original_cols = list(df.columns)
        col_mapping = {}
        normalized_cols = {col.strip().lower().replace(" ", "_"): col for col in original_cols}

        for canonical_name, aliases in self.CSV_HEADER_MAP.items():
            for alias in aliases:
                if alias in normalized_cols:
                    col_mapping[normalized_cols[alias]] = canonical_name
                    break

        renamed_df = df.rename(columns=col_mapping)

        # Replace NaN with None across the DataFrame
        records = renamed_df.to_dict(orient="records")
        cleaned_records: List[Dict[str, Any]] = []
        for row in records:
            cleaned_row = {}
            for k, v in row.items():
                if pd.isna(v):
                    cleaned_row[k] = None
                else:
                    cleaned_row[k] = v
            cleaned_records.append(cleaned_row)

        valid_recs, errors = TelemetryValidator.validate_batch(cleaned_records)
        return IngestionResult(
            total_records=len(cleaned_records),
            valid_count=len(valid_recs),
            error_count=len(errors),
            valid_records=valid_recs,
            validation_errors=errors,
            metadata={"format": "csv", "columns_detected": list(renamed_df.columns)},
        )

    def ingest_batch(
        self,
        batch_input: Union[TelemetryBatchSchema, List[Any], Dict[str, Any]],
    ) -> IngestionResult:
        """Ingests a telemetry batch container."""
        if isinstance(batch_input, TelemetryBatchSchema):
            return IngestionResult(
                total_records=len(batch_input.records),
                valid_count=len(batch_input.records),
                error_count=0,
                valid_records=batch_input.records,
                validation_errors=[],
                metadata={"format": "telemetry_batch_schema", "source": batch_input.source},
            )
        elif isinstance(batch_input, dict) and "records" in batch_input:
            records = batch_input["records"]
            source = batch_input.get("source", "batch_dict")
            valid_recs, errors = TelemetryValidator.validate_batch(records)
            return IngestionResult(
                total_records=len(records),
                valid_count=len(valid_recs),
                error_count=len(errors),
                valid_records=valid_recs,
                validation_errors=errors,
                metadata={"format": "batch_dict", "source": source},
            )
        elif isinstance(batch_input, list):
            return self.ingest_json_list(batch_input)
        else:
            err = RecordValidationError(
                field="batch",
                message=f"Unsupported batch type {type(batch_input).__name__}",
                invalid_value=batch_input,
            )
            return IngestionResult(total_records=1, valid_count=0, error_count=1, validation_errors=[err])
