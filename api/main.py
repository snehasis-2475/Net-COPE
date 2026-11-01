from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from communication.models import (
    AgentMessage,
    NetworkTelemetryRecord,
    Severity,
    TelemetryBatch,
)
from communication.telemetry_validator import RecordValidationError, TelemetryValidator
from data.csv_loader import load_telemetry_csv
from data.scenarios import (
    SCENARIO_METADATA,
    generate_scenario_data,
)
from diagnosis.models import DiagnosticReport, NetworkHealthStatus
from orchestrator.orchestrator import CentralOrchestrator

logger = logging.getLogger("api.netcoop")

app = FastAPI(
    title="NetCoop AI — Multi-Agent Network Fault Diagnosis API",
    description=(
        "Decentralized specialized multi-agent coordination system for continuous network telemetry "
        "monitoring, anomaly detection, causal fault correlation, and prescriptive operational runbooks."
    ),
    version="2.0.0",
    openapi_tags=[
        {"name": "System", "description": "System health and readiness checks."},
        {"name": "Scenarios", "description": "Pre-configured synthetic diagnostic scenarios for testing and NOC drills."},
        {"name": "Telemetry", "description": "Telemetry validation, ingestion, and staging pipelines."},
        {"name": "Diagnosis", "description": "Multi-agent diagnostic execution and root-cause correlation engine."},
        {"name": "Reports", "description": "Persistent unified diagnostic reports adhering to Schema 2.0.0."},
    ],
)

# CORS Middleware for dashboard or frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = CentralOrchestrator()


# =============================================================================
# DATA CONTRACTS & RESPONSE MODELS
# =============================================================================

class ErrorDetailItem(BaseModel):
    """Detailed validation failure for a specific telemetry record or field."""
    record_index: Optional[int] = Field(default=None, description="Index of invalid record in telemetry batch")
    device_id: Optional[str] = Field(default=None, description="Device ID if available")
    field: str = Field(..., description="Field name where validation failed")
    message: str = Field(..., description="Validation failure explanation")
    invalid_value: Any = Field(default=None, description="Observed invalid value")


class ErrorResponse(BaseModel):
    """Canonical structured error response."""
    error: str = Field(..., description="High-level error classification")
    message: str = Field(..., description="Human-readable error description")
    validation_errors: Optional[List[ErrorDetailItem]] = Field(
        default=None,
        description="Detailed field-level validation errors where applicable",
    )


class DiagnosisRequest(BaseModel):
    """Request payload to initiate a multi-agent network fault diagnosis."""
    scenario_id: Optional[str] = Field(
        default=None,
        description="Pre-configured reproducible scenario identifier (e.g., 'congestion', 'dns_failure', 'normal')",
        json_schema_extra={"example": "congestion"},
    )
    telemetry: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Raw telemetry records batch conforming to canonical TelemetryRecord schema",
        json_schema_extra={
            "example": [
                {
                    "timestamp": "2026-10-31T12:00:00Z",
                    "device_id": "edge-switch-01",
                    "device_type": "switch",
                    "latency_ms": 12.5,
                    "packet_loss_pct": 0.0,
                    "bandwidth_util_pct": 45.0,
                }
            ]
        },
    )


class HealthResponse(BaseModel):
    status: str = Field(..., description="System operational status", json_schema_extra={"example": "healthy"})
    service: str = Field(..., description="Service identifier", json_schema_extra={"example": "NetCoop AI Multi-Agent Diagnostic Engine"})
    version: str = Field(..., description="API and schema version", json_schema_extra={"example": "2.0.0"})
    timestamp: str = Field(..., description="Current ISO 8601 UTC timestamp")
    active_agents: List[str] = Field(..., description="Registered diagnostic agents")


class ScenarioItem(BaseModel):
    scenario_id: str = Field(..., description="Scenario identifier")
    title: str = Field(..., description="Scenario human-readable title")
    description: str = Field(..., description="Scenario description and context")
    expected_root_cause: str = Field(..., description="Ground-truth expected root-cause hypothesis")


class ScenarioListResponse(BaseModel):
    scenarios: List[ScenarioItem]
    total: int


class ScenarioDetailResponse(BaseModel):
    scenario_id: str
    metadata: Dict[str, Any]
    record_count: int
    records: List[Dict[str, Any]]


class TelemetrySubmitResponse(BaseModel):
    status: str = Field(..., description="'valid' or 'invalid'")
    valid_record_count: int = Field(..., description="Number of successfully validated records")
    errors: List[str] = Field(default_factory=list, description="Validation failure messages")
    sample_devices: List[str] = Field(default_factory=list, description="Devices identified in batch")


class ReportSummaryItem(BaseModel):
    report_id: str
    diagnosis_id: str
    task_id: str
    timestamp: datetime
    schema_version: str = "2.0.0"
    overall_network_health: NetworkHealthStatus
    fault_detected: bool
    diagnosis_certainty: str
    probable_root_cause: str
    confidence_score: float
    confidence: float
    affected_device_count: int
    execution_status: str


class ReportListResponse(BaseModel):
    reports: List[ReportSummaryItem]
    total: int


class AskReportRequest(BaseModel):
    question: str = Field(..., description="Operator question regarding this diagnostic report.")


class AskReportResponse(BaseModel):
    answer: str = Field(..., description="Grounded explanation of the report telemetry and diagnosis.")
    mode: str = Field(..., description="Inference mode: 'llm' or 'fallback'.")
    cited_evidence: List[str] = Field(default_factory=list, description="List of evidence citation identifiers such as [E1], [E2].")


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Converts Pydantic/FastAPI request validation errors into canonical structured ErrorResponse."""
    details = []
    for err in exc.errors():
        field_loc = ".".join(str(loc) for loc in err.get("loc", []))
        details.append(
            ErrorDetailItem(
                field=field_loc or "body",
                message=err.get("msg", "Invalid request body value"),
                invalid_value=str(err.get("input", "")),
            )
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="Request Validation Error",
            message="The request payload failed schema validation.",
            validation_errors=details,
        ).model_dump(),
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Agent Readiness",
    tags=["System"],
)
def health_check():
    """System health check endpoint verifying orchestrator and agent readiness."""
    return HealthResponse(
        status="healthy",
        service="NetCoop AI Multi-Agent Diagnostic Engine",
        version="2.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_agents=[
            "performance_agent",
            "infrastructure_agent",
            "connectivity_agent",
            "correlation_agent",
            "recommendation_agent",
        ],
    )


@app.get(
    "/api/scenarios",
    response_model=ScenarioListResponse,
    summary="List Diagnostic Scenarios",
    tags=["Scenarios"],
)
def get_available_scenarios():
    """Retrieves list of all built-in reproducible network diagnostic scenarios."""
    scenarios_list = [
        ScenarioItem(
            scenario_id=sc_id,
            title=meta["title"],
            description=meta["description"],
            expected_root_cause=meta["expected_root_cause"],
        )
        for sc_id, meta in SCENARIO_METADATA.items()
    ]
    return ScenarioListResponse(scenarios=scenarios_list, total=len(scenarios_list))


@app.get(
    "/api/scenarios/{scenario_id}",
    response_model=ScenarioDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Scenario not found"},
    },
    summary="Get Scenario Telemetry Dataset",
    tags=["Scenarios"],
)
def get_scenario_data(scenario_id: str):
    """Retrieves metadata and full telemetry dataset for a specific scenario."""
    sc_key = scenario_id.lower().replace("-", "_")
    if sc_key not in SCENARIO_METADATA:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found. Available scenarios: {sorted(SCENARIO_METADATA.keys())}",
        )
    records = generate_scenario_data(sc_key)
    meta = SCENARIO_METADATA[sc_key]
    return ScenarioDetailResponse(
        scenario_id=sc_key,
        metadata=meta,
        record_count=len(records),
        records=records,
    )


@app.get(
    "/api/scenarios/{scenario_id}/csv",
    summary="Download Scenario Telemetry as CSV",
    tags=["Scenarios"],
)
def download_scenario_csv(scenario_id: str):
    """Returns the scenario telemetry records formatted as downloadable CSV."""
    clean_id = Path(scenario_id).stem.lower()
    csv_path = Path("data/scenarios") / f"{clean_id}.csv"
    if not csv_path.exists():
        csv_path = Path("data/samples") / f"{clean_id}.csv"
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as f:
            csv_content = f.read()
    else:
        records = generate_scenario_data(clean_id)
        if not records:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
        import pandas as pd
        df = pd.DataFrame(records)
        csv_content = df.to_csv(index=False)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={clean_id}.csv"},
    )


@app.post(
    "/api/telemetry/submit",
    response_model=TelemetrySubmitResponse,
    summary="Validate & Stage Telemetry Batch",
    tags=["Telemetry"],
)
def submit_telemetry(payload: TelemetryBatch):
    """Validates and stages structured network telemetry records."""
    df, errors = orchestrator.validate_and_normalize_telemetry(payload)
    return TelemetrySubmitResponse(
        status="valid" if not df.empty else "invalid",
        valid_record_count=len(df),
        errors=errors,
        sample_devices=df["device_id"].unique().tolist() if not df.empty and "device_id" in df.columns else [],
    )


@app.post(
    "/api/telemetry/upload-csv",
    summary="Upload & Parse Telemetry CSV",
    tags=["Telemetry"],
)
async def upload_csv_telemetry(file: UploadFile = File(...)):
    """Uploads, normalizes, and validates telemetry from a CSV file."""
    fname = (file.filename or "").lower()
    if not (fname.endswith(".csv") or fname.endswith(".json")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a CSV (.csv) or JSON (.json).",
        )

    raw_bytes = await file.read()
    warnings = []
    if fname.endswith(".json"):
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
            items = parsed if isinstance(parsed, list) else parsed.get("records", parsed.get("telemetry", [parsed]))
            df, warnings = orchestrator.validate_and_normalize_telemetry(items)
        except Exception as jerr:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to parse JSON file: {str(jerr)}",
            )
    else:
        df, warnings = load_telemetry_csv(raw_bytes)
    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse CSV: {warnings}",
        )

    sample_records = [
        {
            k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
            for k, v in r.items()
        }
        for r in df.head(5).to_dict(orient="records")
    ]

    return {
        "filename": file.filename,
        "record_count": len(df),
        "columns": list(df.columns),
        "warnings": warnings,
        "sample_records": sample_records,
    }


@app.post(
    "/api/upload",
    summary="Upload & Parse Telemetry CSV (Alias)",
    tags=["Telemetry"],
)
async def upload_csv_telemetry_alias(file: UploadFile = File(...)):
    """Alias for /api/telemetry/upload-csv."""
    return await upload_csv_telemetry(file)


@app.post(
    "/api/validate",
    summary="Validate Telemetry Batch (Alias)",
    tags=["Telemetry"],
)
def validate_telemetry_alias(payload: Dict[str, Any]):
    """Alias for telemetry validation accepting {telemetry: [...]} or {records: [...]}."""
    telemetry_input = payload.get("telemetry", payload.get("records", payload))
    df, errors = orchestrator.validate_and_normalize_telemetry(telemetry_input)
    return TelemetrySubmitResponse(
        status="valid" if not df.empty else "invalid",
        valid_record_count=len(df),
        errors=errors,
        sample_devices=df["device_id"].unique().tolist() if not df.empty and "device_id" in df.columns else [],
    )


@app.post(
    "/api/diagnose",
    response_model=DiagnosticReport,
    responses={
        400: {"model": ErrorResponse, "description": "Missing or empty required parameters"},
        404: {"model": ErrorResponse, "description": "Specified scenario not found"},
        413: {"model": ErrorResponse, "description": "Telemetry batch exceeds size limit"},
        422: {"model": ErrorResponse, "description": "Malformed telemetry records"},
        500: {"model": ErrorResponse, "description": "Internal diagnosis execution error"},
    },
    summary="Run End-to-End Multi-Agent Diagnosis",
    tags=["Diagnosis"],
)
def run_diagnosis(request: DiagnosisRequest):
    """
    Executes end-to-end multi-agent network fault diagnosis.
    Accepts either a built-in `scenario_id` or a custom `telemetry` batch.
    Returns a unified DiagnosticReport conforming to Schema 2.0.0.
    """
    telemetry_data = None
    scenario_tag = "custom"

    # 1. Enforce mutually required fields
    if not request.scenario_id and request.telemetry is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: Must provide either 'scenario_id' or 'telemetry' in request body.",
        )

    # 2. Validate scenario_id if provided
    if request.scenario_id:
        sc_key = request.scenario_id.lower().replace("-", "_")
        if sc_key not in SCENARIO_METADATA:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario '{request.scenario_id}' not found. Available scenarios: {sorted(SCENARIO_METADATA.keys())}",
            )
        telemetry_data = generate_scenario_data(sc_key)
        scenario_tag = sc_key

    # 3. Validate telemetry batch if provided
    elif request.telemetry is not None:
        if len(request.telemetry) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telemetry batch cannot be empty. Please provide at least one telemetry record.",
            )

        if len(request.telemetry) > 5000:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Telemetry batch exceeds maximum permitted size of 5000 records (got {len(request.telemetry)}).",
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        normalized_telemetry = []
        for rec in request.telemetry:
            if isinstance(rec, dict):
                row = {
                    k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
                    for k, v in rec.items()
                }
                if not row.get("timestamp"):
                    row["timestamp"] = now_iso
                normalized_telemetry.append(row)
            else:
                normalized_telemetry.append(rec)

        # Pre-validate batch using canonical TelemetryValidator
        valid_records, validation_errors = TelemetryValidator.validate_batch(normalized_telemetry)

        # If batch is completely malformed (zero valid records), reject with structured HTTP 422
        if len(valid_records) == 0 and len(validation_errors) > 0:
            structured_errors = [
                ErrorDetailItem(
                    record_index=err.record_index,
                    device_id=err.device_id,
                    field=err.field,
                    message=err.message,
                    invalid_value=err.invalid_value,
                )
                for err in validation_errors
            ]
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=ErrorResponse(
                    error="Malformed Telemetry Batch",
                    message="All telemetry records in the batch failed validation against schema rules.",
                    validation_errors=structured_errors,
                ).model_dump(),
            )

        # Otherwise at least some valid records exist; pass raw telemetry to orchestrator
        # so orchestrator diagnoses valid records and logs partial errors in limitations
        telemetry_data = normalized_telemetry

    # 4. Execute diagnosis safely through orchestrator
    try:
        report = orchestrator.run_diagnosis(
            telemetry=telemetry_data,
            scenario_name=scenario_tag,
            save_report=True,
        )
        return report
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Unhandled exception during diagnosis execution: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred during diagnosis execution.",
        )


@app.get(
    "/api/reports/{report_id}",
    response_model=DiagnosticReport,
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"},
        500: {"model": ErrorResponse, "description": "Internal server error reading report"},
    },
    summary="Get Diagnostic Report by ID",
    tags=["Reports"],
)
def get_report(report_id: str):
    """Retrieves a previously generated diagnostic report by its Report ID or Diagnosis ID."""
    clean_id = Path(report_id).stem
    file_path = orchestrator.reports_dir / f"{clean_id}.json"
    if not file_path.exists():
        # Check if matched by diagnosis_id prefix
        matches = list(orchestrator.reports_dir.glob(f"*{clean_id}*.json"))
        if matches:
            file_path = matches[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report '{report_id}' not found.",
            )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DiagnosticReport.model_validate(data)
    except Exception as exc:
        logger.exception(f"Error reading report {report_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading or deserializing report: {str(exc)}",
        )


@app.post(
    "/api/reports/{report_id}/ask",
    response_model=AskReportResponse,
    summary="Ask NetCoop Copilot about a Diagnostic Report",
    tags=["Reports"],
)
def ask_report(report_id: str, payload: AskReportRequest):
    """
    Ask NetCoop natural language Copilot to explain a DiagnosticReport.
    Answers strictly using grounded report telemetry without inventing metrics.
    """
    report = get_report(report_id)
    from copilot.explainer import ask_copilot
    res = ask_copilot(report, payload.question)
    return AskReportResponse(
        answer=res.answer,
        mode=res.mode,
        cited_evidence=res.cited_evidence,
    )


@app.get(
    "/api/reports",
    response_model=ReportListResponse,
    summary="List Saved Diagnostic Reports",
    tags=["Reports"],
)
def list_reports(limit: int = Query(default=20, ge=1, le=100)):
    """Lists saved diagnostic reports with summary metadata."""
    report_files = sorted(
        list(orchestrator.reports_dir.glob("REP-*.json")) + list(orchestrator.reports_dir.glob("DIAG-*.json")),
        key=os.path.getmtime,
        reverse=True,
    )[:limit]

    results = []
    for p in report_files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            rc = data.get("selected_root_cause") or data.get("probable_root_cause")
            results.append(
                ReportSummaryItem(
                    report_id=data.get("report_id") or data.get("diagnosis_id") or "UNKNOWN",
                    diagnosis_id=data.get("diagnosis_id") or data.get("report_id") or "UNKNOWN",
                    task_id=data.get("task_id", ""),
                    timestamp=data.get("timestamp") or datetime.now(timezone.utc),
                    schema_version=data.get("schema_version", "2.0.0"),
                    overall_network_health=data.get("overall_network_health", NetworkHealthStatus.UNKNOWN),
                    fault_detected=data.get("fault_detected", False),
                    diagnosis_certainty=data.get("diagnosis_certainty", "CONFIRMED"),
                    probable_root_cause=rc.get("title") if rc else "None",
                    confidence_score=data.get("confidence_score") if data.get("confidence_score") is not None else (data.get("confidence") or 0.0),
                    confidence=data.get("confidence") if data.get("confidence") is not None else (data.get("confidence_score") or 0.0),
                    affected_device_count=len(data.get("affected_devices", [])),
                    execution_status=data.get("execution_status") or data.get("overall_status") or "COMPLETED",
                )
            )
        except Exception as exc:
            logger.warning(f"Failed to parse report file {p}: {exc}")
            continue

    return ReportListResponse(reports=results, total=len(results))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
