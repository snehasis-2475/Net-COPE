# NetCoop AI — Multi-Agent Network Fault Diagnosis and Interoperability

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B.svg)](https://streamlit.io/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://docs.pydantic.dev/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF.svg)](https://vite.dev/)
[![Three.js](https://img.shields.io/badge/Three.js-r181-000000.svg)](https://threejs.org/)
[![Tests](https://img.shields.io/badge/Pytest-279%20Passed-brightgreen.svg)](https://docs.pytest.org/)

**NetCoop AI** is an enterprise-grade multi-agent network fault diagnosis system built for modern Network Operations Centers (NOC). It autonomously ingests multi-dimensional network telemetry, distributes analysis across specialized autonomous agents, correlates heterogeneous symptoms using an evidence-based causal graph, resolves conflicting observations, and delivers deterministic root cause analysis with actionable remediation runbooks.

The system ships with three ways to use it:

| Interface | Technology | Local URL |
| :--- | :--- | :--- |
| **Interactive web app** | React + Vite + Three.js | [http://localhost:5173](http://localhost:5173) |
| **REST API** | FastAPI + Uvicorn | [http://localhost:8000](http://localhost:8000) ([docs](http://localhost:8000/docs)) |
| **NOC console** | Streamlit + Plotly | [http://localhost:8501](http://localhost:8501) |

---

## Table of Contents

1. [Quickstart: Run the Website Locally](#quickstart-run-the-website-locally)
2. [System Architecture](#system-architecture)
3. [Technology Stack](#technology-stack)
4. [Project Directory Structure](#project-directory-structure)
5. [Interactive Web App](#interactive-web-app)
6. [Built-in Diagnostic Scenarios](#built-in-diagnostic-scenarios)
7. [Interoperability JSON Contract (AgentMessage)](#interoperability-json-contract-agentmessage)
8. [FastAPI Integration & API Reference (Milestone 11)](#fastapi-integration--api-reference-milestone-11)
9. [Streamlit NOC Dashboard (Milestone 12)](#streamlit-noc-dashboard-milestone-12)
10. [Evaluation vs. Traditional Baseline](#evaluation-vs-traditional-baseline)
11. [Verification & Automated Tests](#verification--automated-tests)
12. [Troubleshooting](#troubleshooting)
13. [Hackathon Acceptance Criteria Checklist](#hackathon-acceptance-criteria-checklist)

---

## Quickstart: Run the Website Locally

The website is the React app in `frontend/`. It talks to the FastAPI backend at `http://127.0.0.1:8000`. If the backend is not running, the website still works in **Local Autonomous Mode** using built-in sample data. The header status pill shows `ONLINE` when it is connected to the backend and `OFFLINE` when it is using sample data.

### 1. Prerequisites

| Tool | Version | Check with |
| :--- | :--- | :--- |
| Python | 3.14 (the project is developed and tested on 3.14) | `python --version` |
| Node.js | 20 or newer (includes npm) | `node --version` and `npm --version` |
| Git | Any recent version | `git --version` |

> On macOS and Linux, replace `python` with `python3` if `python` is not available. On Windows, `py` also works.

### Fastest way on Windows: one-click launchers

After installing Python and Node.js, double-click **`run_all.bat`** in the repository root. It opens the backend in one window, waits until the API responds, then opens the website in a second window and launches it in your browser at [http://localhost:5173](http://localhost:5173).

| Launcher | What it does | URL |
| :--- | :--- | :--- |
| `run_all.bat` | Starts the backend, waits for it, then starts the website | http://localhost:5173 |
| `run_backend.bat` | Starts the FastAPI backend | http://localhost:8000 |
| `run_frontend.bat` | Starts the website and opens your browser | http://localhost:5173 |
| `run_dashboard.bat` | Starts the Streamlit NOC console | http://localhost:8501 |
| `run_tests.bat` | Runs the Pytest suite | — |

The launchers:

- work when double-clicked or started from any folder, including paths with spaces;
- use the project virtual environment (`.venv`) if it exists, otherwise `python`, otherwise the `py` launcher;
- install missing Python packages from `requirements.txt` and missing website packages with `npm ci` on the first run, then skip installation afterwards;
- keep their window open with an error message if something fails.

Stop a service by pressing `Ctrl + C` in its window (answer `Y` to "Terminate batch job") or by closing the window. The first run can take a few minutes while dependencies install.

The manual steps below do the same thing on any operating system.

### 2. Get the code

```bash
git clone https://github.com/Banditapriyadarshini27/Agentic-AI.git
cd Agentic-AI
```

All commands below run from this repository root unless a step says `cd frontend`.

### 3. Install backend dependencies (one time)

Using a virtual environment is recommended, but you can also install directly into your default Python environment.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

> If you skip the virtual environment, run `python -m pip install -r requirements.txt` directly. If you use the virtual environment, activate it again in each new terminal before starting the backend, dashboard, or tests.

### 4. Install frontend dependencies (one time)

```bash
cd frontend
npm ci
cd ..
```

`npm ci` installs the exact versions pinned in `frontend/package-lock.json`, including Three.js for the 3D effects.

### 5. Start the backend API (terminal 1)

```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

On Windows you can also double-click `run_backend.bat`.

Confirm it is running by opening [http://localhost:8000/health](http://localhost:8000/health). Interactive API docs are at [http://localhost:8000/docs](http://localhost:8000/docs).

### 6. Start the website (terminal 2)

```bash
cd frontend
npm run dev
```

Vite prints a local address, normally:

```
  VITE v8.x  ready in 300 ms

  ➜  Local:   http://localhost:5173/
```

Open **[http://localhost:5173](http://localhost:5173)** in your browser. Edits under `frontend/src` reload instantly. Press `Ctrl + C` in the terminal to stop the server.

On Windows you can also double-click `run_frontend.bat`, which installs missing packages and opens the browser for you.

Useful variations:

```bash
npm run dev -- --port 3000   # use a different port
npm run dev -- --host        # expose on your local network (e.g. to test on a phone)
```

### 7. (Optional) Start the Streamlit NOC console (terminal 3)

```bash
python -m streamlit run dashboard/app.py
```

On Windows you can also run `run_dashboard.bat`. Open [http://localhost:8501](http://localhost:8501).

### 8. (Optional) Run a production build of the website

```bash
cd frontend
npm run build      # type-checks and writes the optimized site to frontend/dist
npm run preview    # serves frontend/dist at http://localhost:4173
```

### Launch summary

| What | Command | Directory | URL |
| :--- | :--- | :--- | :--- |
| Backend API | `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload` | repository root | http://localhost:8000 |
| Website (dev) | `npm run dev` | `frontend/` | http://localhost:5173 |
| Website (production preview) | `npm run build && npm run preview` | `frontend/` | http://localhost:4173 |
| Streamlit console | `python -m streamlit run dashboard/app.py` | repository root | http://localhost:8501 |
| Tests | `python -m pytest -v` | repository root | — |

### Optional: Copilot configuration

The report copilot (`POST /api/reports/{report_id}/ask`) answers operator questions using only facts in the diagnostic report. It can optionally use Anthropic Claude when these environment variables are set before starting the backend:

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `ANTHROPIC_API_KEY` | Enables LLM-backed answers | Not set; the copilot uses its built-in report-grounded explainer |
| `ANTHROPIC_MODEL` or `NETCOOP_COPILOT_MODEL` | Model name | `claude-3-5-sonnet-20241022` |

No environment variables are required to run the website, API, dashboard, or tests.

---

## System Architecture

```
                                  ┌────────────────────────┐
                                  │   Telemetry Ingestion  │
                                  │ (CSV, JSON, Scenarios) │
                                  └───────────┬────────────┘
                                              │
                                              ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                CENTRAL ORCHESTRATOR                                    │
│   • Input Validation & Schema Normalization  • Parallel Agent Dispatch (ThreadPool)    │
│   • Timeout & Crash Fault Tolerance          • Message Envelope Schema Enforcement     │
│   • Final Diagnostic Report Compilation                                                │
└───────────────┬─────────────────────────────┬─────────────────────────────┬────────────┘
                │                             │                             │
                ▼                             ▼                             ▼
    ┌───────────────────────┐     ┌───────────────────────┐     ┌───────────────────────┐
    │   Performance Agent   │     │ Infrastructure Agent  │     │  Connectivity Agent   │
    │ • Latency / RTT       │     │ • CPU / Memory Load   │     │ • DNS Status & Latency│
    │ • Jitter Variations   │     │ • Device Availability │     │ • DHCP Lease State    │
    │ • Packet Loss Rate    │     │ • Interface Flapping  │     │ • Wi-Fi RSSI / SNR    │
    │ • Bandwidth Saturation│     │ • CRC & Queue Drops   │     │ • Host Reachability   │
    └───────────┬───────────┘     └───────────┬───────────┘     └───────────┬───────────┘
                │                             │                             │
                └─────────────────────────────┼─────────────────────────────┘
                                              │
                                              ▼ (Standardized AgentMessage Bus)
                           ┌─────────────────────────────────────┐
                           │       Fault Correlation Agent       │
                           │ • Multi-Symptom Evidence Synthesis  │
                           │ • Causal Hypothesis Ranking         │
                           │ • Conflict Resolution Logic         │
                           │ • Uncertainty & Confidence Scoring  │
                           └──────────────────┬──────────────────┘
                                              │
                                              ▼
                           ┌─────────────────────────────────────┐
                           │        Recommendation Agent         │
                           │ • Prescriptive Mitigation Steps     │
                           │ • Verification Procedures           │
                           │ • Automated CLI Remediations        │
                           └──────────────────┬──────────────────┘
                                              │
                                              ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                UNIFIED DIAGNOSTIC REPORT                               │
│     Report ID • Probable Root Cause • Competing Causes • Evidence Matrix • Runbooks    │
└─────────────────────────────────────────────┬──────────────────────────────────────────┘
                                              │
                 ┌────────────────────────────┼────────────────────────────┐
                 ▼                            ▼                            ▼
     ┌───────────────────────┐    ┌───────────────────────┐    ┌───────────────────────┐
     │  FastAPI REST Server  │    │ React Web Application │    │ Streamlit NOC Console │
     │ http://localhost:8000 │    │ http://localhost:5173 │    │ http://localhost:8501 │
     └───────────────────────┘    └───────────────────────┘    └───────────────────────┘
```

---

## Technology Stack

- **Python**: 3.14+
- **Agent Interoperability**: Pydantic v2 (JSON-based schema envelope)
- **Data Engineering**: Pandas, NumPy
- **Backend API**: FastAPI, Uvicorn, Python-Multipart, Requests, HTTPX
- **Dashboard / NOC UI**: Streamlit, Plotly
- **Web App**: React 19, TypeScript, Vite 8, React Router 7
- **Web App Motion & 3D**: Three.js (WebGL scenes and shaders), Framer Motion, GSAP, Lenis smooth scrolling, D3
- **Copilot (optional)**: Anthropic Claude via SDK or HTTPX, with a deterministic report-grounded fallback
- **Testing**: Pytest

---

## Project Directory Structure

```
Agentic-AI/
├── communication/             # Interoperability protocol & models
│   ├── models.py              # AgentMessage, Finding, EvidenceItem, Telemetry schemas
│   ├── protocol.py            # Message validation, serialization, error builders
│   ├── telemetry_schema.py    # Canonical telemetry schema
│   ├── telemetry_validator.py # Record-level validation & partial batch isolation
│   ├── telemetry_ingestion.py # Normalization of incoming telemetry
│   └── telemetry_generator.py # Synthetic telemetry generation
├── agents/                    # Specialized autonomous diagnostic agents
│   ├── base_agent.py          # Abstract BaseAgent with fault-isolated execution
│   ├── performance_agent.py   # Latency, jitter, packet loss, bandwidth saturation
│   ├── infrastructure_agent.py# CPU, memory, interface status, CRC errors, queue drops
│   ├── connectivity_agent.py  # DNS, DHCP, Wi-Fi RSSI/SNR, reachability
│   ├── baseline_detector.py   # Explainable baseline anomaly detection
│   ├── correlation_agent.py
│   └── recommendation_agent.py
├── diagnosis/                 # Correlation, recommendation & reporting models
│   ├── models.py              # DiagnosticReport, RootCauseCandidate, CorrectiveAction
│   ├── correlation_agent.py   # Multi-hypothesis causal inference & conflict resolution
│   └── recommendation_agent.py# Priority runbooks with verification & CLI commands
├── orchestrator/
│   └── orchestrator.py        # Central Orchestrator: pipeline coordinator & fault-tolerant manager
├── copilot/
│   └── explainer.py           # Report-grounded operator copilot (optional Claude backend)
├── data/                      # Scenario datasets and CSV parsing
│   ├── scenarios.py           # 8 realistic reproducible network scenario generators
│   ├── csv_loader.py          # Robust CSV parser with fuzzy column mapping
│   └── samples/               # Pre-generated scenario CSV files for upload testing
│       ├── normal.csv
│       ├── congestion.csv
│       ├── weak_wifi.csv
│       ├── interface_failure.csv
│       ├── dns_failure.csv
│       ├── dhcp_failure.csv
│       ├── infrastructure_overload.csv
│       ├── invalid_telemetry.csv
│       ├── organizer_mock.csv
│       └── organizer_mock_telemetry.csv
├── api/
│   └── main.py                # FastAPI endpoints for health, scenarios, diagnosis, CSV, reports & copilot
├── dashboard/
│   ├── app.py                 # Interactive Streamlit NOC UI with KPI cards, Plotly charts, report export
│   └── components.py          # Reusable dashboard components
├── frontend/                  # React + Vite interactive web app
│   ├── index.html
│   ├── package.json           # Scripts: dev, build, preview, lint
│   └── src/
│       ├── App.tsx            # Router, smooth scrolling, page transitions
│       ├── index.css          # Design tokens, typography, hover & cursor styles
│       ├── components/        # Header, cursor, page transition, scroll progress, illustrations
│       │   └── three/         # Three.js scenes: SignalField, AgentRing, SignalRibbon, OrbitRings
│       ├── pages/             # Home, Ingest, Pipeline, Diagnosis, Runbook, Telemetry, Vault
│       ├── services/          # api.ts (backend client) & mockData.ts (offline fallback)
│       └── types/             # Telemetry and report TypeScript types
├── evaluation/                # Benchmark vs. traditional threshold-alarm baseline
│   ├── evaluate.py            # Evaluation framework (CLI)
│   ├── compare.py             # Baseline vs. NetCoop comparison
│   ├── baseline.py, metrics.py, generator.py, generator_hard.py
│   ├── comparison_results.json
│   └── results.md             # Latest evaluation report
├── scripts/
│   └── trace_and_verify_pipeline.py  # End-to-end frontend/backend trace & scenario checks
├── tests/                     # Comprehensive Pytest suite
├── documentation/             # Technical specifications
│   ├── ARCHITECTURE.md
│   ├── AGENT_COMMUNICATION.md
│   ├── API_REFERENCE.md
│   └── TESTING_GUIDE.md
├── reports/                   # Persisted diagnostic reports (JSON, created at runtime)
├── run_backend.bat            # Windows launcher: FastAPI backend
├── run_dashboard.bat          # Windows launcher: Streamlit console
├── run_tests.bat              # Windows launcher: Pytest suite
├── requirements.txt
└── README.md
```

---

## Interactive Web App

The React app in `frontend/` presents the investigation as a sequence of pages. All pages read live data from the FastAPI backend and fall back to bundled sample data when it is offline.

| Route | Page | What it does |
| :--- | :--- | :--- |
| `/` | **Incident** | Story of the alert cascade, the five specialist agents, and a live workbench to run a multi-agent diagnosis on any benchmark scenario |
| `/ingest` | **Ingest** | Telemetry ingest and scenario index: drag-and-drop or browse for CSV telemetry, inspect row/device/quarantine statistics, and load scenarios |
| `/pipeline` | **Pipeline** | The inter-agent bus: stage-by-stage pipeline, per-agent status, duration and findings, and raw message envelope inspection |
| `/diagnosis` | **Diagnosis** | Latest report: network health, certainty, heuristic confidence, affected devices, root cause narrative, evidence ledger, and alternative hypotheses |
| `/runbook` | **Runbook** | Priority-ordered remediation sequence with command, verification, and rollback tabs; disruptive actions require operator authorization |
| `/telemetry` | **Telemetry** | Time-series studio with per-metric charts and threshold breach highlighting |
| `/vault` | **Vault** | Report archive with direct fetch by Report ID or Diagnosis ID and side-by-side report comparison |

The latest diagnosis from the Incident page is cached in the browser (`localStorage`) so other pages immediately show its context.

### Visual design and interactions

- **Signal design system**: charcoal ink, paper gray, and signal yellow sections with wide uppercase grotesk headlines (Archivo) and monospace data labels (JetBrains Mono).
- **Three.js scenes**:
  - *Signal Field*: a point-cloud surface behind each page that bulges under the cursor and ripples iridescent colour splashes on movement and clicks.
  - *Agent Ring*: a rotating ring of the telemetry signals the agents watch; the cursor steers and tilts it, hovering highlights a signal, and clicking spins it.
  - *Signal Ribbon*: an iridescent twisting surface that bends under the cursor.
  - *Orbit Rings*: a wireframe meridian sphere on the diagnosis workbench whose core follows the cursor; it spins faster and pulses while a diagnosis runs.
- **Hover effects**: cursor-following colour spotlights on cards and rows, gliding row titles, rolling navigation labels, offset-shadow buttons, and outlined headline words that flood with colour.
- **Custom cursor** with a trailing ring and an iridescent burst on click.
- **Accessibility and performance**: WebGL scenes pause when offscreen, constant motion stops when the operating system's reduced-motion setting is on, the custom cursor is hidden on touch devices, and the 3D layers are skipped if WebGL is unavailable.

### Frontend scripts

Run these from `frontend/`:

| Command | Description |
| :--- | :--- |
| `npm run dev` | Start the development server with hot reload (default http://localhost:5173) |
| `npm run build` | Type-check with TypeScript and build to `frontend/dist` |
| `npm run preview` | Serve the production build (default http://localhost:4173) |
| `npm run lint` | Lint with Oxlint |

---

## Built-in Diagnostic Scenarios

NetCoop AI includes 8 reproducible synthetic scenarios modeling real-world network operational incidents:

| # | Scenario | Primary Symptoms | Diagnosed Root Cause |
| :-: | :--- | :--- | :--- |
| **1** | **Normal Operation** | Latency <15ms, 0% loss, CPU <35%, DNS nominal | `Nominal Network Operation` |
| **2** | **Network Congestion** | Core link bandwidth >95%, queue drops, latency spikes | `Network Bandwidth Congestion & Bufferbloat` |
| **3** | **Weak Wi-Fi** | Meeting room RSSI -86 dBm, low SNR, endpoint packet loss | `Wireless RF Attenuation / Weak Wi-Fi Coverage` |
| **4** | **Interface Failure** | Port status flapping/down, CRC framing errors | `Physical Interface / Cable Failure` |
| **5** | **DNS Failure** | Query timeouts, servfail errors, raw IP ping intact | `DNS Resolver Outage or Misconfiguration` |
| **6** | **DHCP Failure** | DHCP exhausted/timeout, client reachability degraded | `DHCP Service Failure / Scope Exhaustion` |
| **7** | **Infrastructure Overload** | Core router CPU 98%, RAM 94%, internal queue drops | `Device Hardware / Compute Resource Overload` |
| **8** | **Invalid Telemetry** | Missing IDs, negative latency, out-of-bounds metrics | `Invalid or Empty Telemetry (Safe Degradation)` |

Each scenario is available as a ready-to-upload CSV in `data/samples/` and can be downloaded from the API at `GET /api/scenarios/{scenario_id}/csv`.

---

## Interoperability JSON Contract (`AgentMessage`)

Every agent produces a standardized JSON message envelope ensuring seamless integration:

```json
{
  "message_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "task_id": "TASK-F3A19C02",
  "agent_id": "performance_agent",
  "timestamp": "2026-10-31T09:30:00.000Z",
  "status": "SUCCESS",
  "findings": [
    {
      "finding_id": "FND-A19F83E1",
      "category": "PERFORMANCE",
      "title": "Link Bandwidth Saturation",
      "description": "Bandwidth utilization reached 96.5% on core-router-01.",
      "severity": "CRITICAL",
      "affected_devices": ["core-router-01"],
      "metrics": {"max_bw_util_pct": 96.5}
    }
  ],
  "evidence": [
    {
      "metric_name": "bandwidth_util_pct",
      "observed_value": 96.5,
      "threshold": 80.0,
      "unit": "%",
      "details": "Bandwidth utilization peaked at 96.5%, exceeding 80.0% threshold."
    }
  ],
  "confidence": 0.92,
  "errors": [],
  "metadata": {"record_count": 15, "execution_time_ms": 12.4}
}
```

---

## FastAPI Integration & API Reference (Milestone 11)

NetCoop AI exposes an enterprise REST API powered by FastAPI, featuring pre-orchestration schema validation, Pydantic v2 serialization, structured error handling, and complete DiagnosticReport schema v2.0.0 compliance. CORS is enabled so the web app and other local tools can call it directly.

### Starting the API

```bash
# Option 1: Uvicorn directly (any OS)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Option 2: Uvicorn from an activated Windows virtual environment
.venv\Scripts\uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Option 3: Windows batch launcher
.\run_backend.bat
```

### Interactive Documentation (Swagger UI & OpenAPI)

Once the server is running, explore and test the endpoints interactively:

- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Technical Reference**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI 3.1 Specification (JSON)**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### Endpoint Overview

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/health` | API and Orchestrator health and readiness probe | `200` |
| `POST` | `/api/diagnose` | Run end-to-end multi-agent diagnosis on telemetry or scenario | `200`, `400`, `404`, `413`, `422`, `500` |
| `GET` | `/api/reports` | List recently generated diagnostic reports with pagination | `200`, `500` |
| `GET` | `/api/reports/{report_id}` | Fetch a complete DiagnosticReport by **Report ID** or **Diagnosis ID** | `200`, `404`, `500` |
| `POST` | `/api/reports/{report_id}/ask` | Ask the NetCoop Copilot a question about a diagnostic report | `200`, `404` |
| `GET` | `/api/scenarios` | List all available synthetic benchmark scenarios | `200` |
| `GET` | `/api/scenarios/{scenario_id}` | Get telemetry records and metadata for a specific scenario | `200`, `404` |
| `GET` | `/api/scenarios/{scenario_id}/csv` | Download scenario telemetry as CSV | `200`, `404` |
| `POST` | `/api/telemetry/submit` | Validate and ingest a raw telemetry batch | `200`, `400`, `413`, `422`, `500` |
| `POST` | `/api/telemetry/upload-csv` | Upload a telemetry CSV file with fuzzy column mapping | `200`, `400`, `500` |
| `POST` | `/api/upload` | Alias of `/api/telemetry/upload-csv` | `200`, `400`, `500` |
| `POST` | `/api/validate` | Alias of `/api/telemetry/submit` for batch validation | `200`, `400`, `413`, `422`, `500` |

See [`documentation/API_REFERENCE.md`](documentation/API_REFERENCE.md) for full details.

### Payload Specifications & Examples

#### 1. Diagnosis Request (`POST /api/diagnose`)

Clients can request diagnosis either by naming a built-in scenario or by providing a custom batch of telemetry records.

**Request by Scenario Name:**

```json
{
  "scenario_name": "congestion",
  "metadata": {"initiated_by": "noc_operator", "site": "datacenter-east"}
}
```

**Request with Direct Telemetry Batch:**

```json
{
  "telemetry": [
    {
      "timestamp": "2026-10-31T12:00:00Z",
      "device_id": "core-router-01",
      "interface": "GigabitEthernet0/0/1",
      "latency_ms": 145.2,
      "jitter_ms": 18.4,
      "packet_loss_pct": 8.5,
      "bandwidth_util_pct": 94.2,
      "cpu_util_pct": 72.0,
      "memory_util_pct": 68.5,
      "dns_latency_ms": 15.0,
      "dns_lookup_success": true,
      "dhcp_success": true
    }
  ]
}
```

Quick test from a terminal while the backend is running:

```bash
curl -X POST http://localhost:8000/api/diagnose \
  -H "Content-Type: application/json" \
  -d '{"scenario_name": "congestion"}'
```

#### 2. Diagnostic Report Response (`DiagnosticReport` Schema 2.0.0)

```json
{
  "report_id": "REP-20261031-120000-A1B2",
  "diagnosis_id": "7b04961d-dd50-48e0-bb12-d9f71cba8be6",
  "task_id": "TASK-A1B2C3D4",
  "schema_version": "2.0.0",
  "timestamp": "2026-10-31T12:00:01.234Z",
  "fault_detected": true,
  "overall_network_health": "DEGRADED",
  "health_classification": "DEGRADED",
  "diagnosis_certainty": "CONFIRMED",
  "primary_root_cause": "Network Congestion / Transit Bandwidth Saturation",
  "confidence_score": 0.92,
  "root_cause_confidence": 0.92,
  "confidence_explanation": "Bandwidth saturation (94.2%) strongly correlated with packet loss (8.5%) and queuing delay.",
  "contributing_factors": ["High buffer utilization", "Peak transit link utilization"],
  "alternative_hypotheses": [],
  "evidence": [
    {
      "evidence_id": "EVD-A19F83E1",
      "metric_name": "bandwidth_util_pct",
      "observed_value": 94.2,
      "threshold": 80.0,
      "unit": "%",
      "finding_type": "BANDWIDTH_SATURATION",
      "device_id": "core-router-01",
      "interface_name": "GigabitEthernet0/0/1"
    }
  ],
  "recommendations": [
    {
      "recommendation_id": "REC-9B1D-001",
      "priority": "HIGH",
      "action": "Enable ingress traffic shaping on GigabitEthernet0/0/1 and reroute non-critical traffic.",
      "category": "TRAFFIC_ENGINEERING"
    }
  ],
  "limitations": {
    "missing_agents": [],
    "invalid_records": 0,
    "stale_observations": []
  },
  "execution_metadata": {
    "execution_time_ms": 42.5,
    "agents_executed": ["performance_agent", "infrastructure_agent", "connectivity_agent", "correlation_agent", "recommendation_agent"],
    "records_analyzed": 1
  }
}
```

#### 3. Structured Error Response (`ErrorResponse`)

When validation fails, NetCoop AI returns structured field-level error messages without exposing sensitive internal stack traces:

```json
{
  "status_code": 422,
  "error_type": "ValidationError",
  "message": "Telemetry validation failed: 1 record(s) contain invalid fields.",
  "detail": [
    {
      "field": "telemetry[0].latency_ms",
      "message": "Input should be greater than or equal to 0",
      "error_type": "greater_than_equal",
      "value": -10.0
    }
  ],
  "timestamp": "2026-10-31T12:00:00.000Z"
}
```

### Request Validation & Operational Robustness

1. **Pre-Orchestration Validation**:
   - Requests are strictly validated before dispatching worker threads.
   - Missing required request fields yield HTTP 400.
   - Empty telemetry batches yield HTTP 400.
   - Batches exceeding 5,000 records yield HTTP 413 (Payload Too Large).
   - Unknown scenario names yield HTTP 404 with a list of available scenarios.
2. **Canonical Telemetry Validation**:
   - Out-of-bounds metrics (e.g. `latency_ms < 0`, `packet_loss_pct > 100`) are rejected with HTTP 422.
   - Missing optional fields remain distinguishable from measured zero (`0.0`) values.
   - **Partial Batch Isolation**: If a batch contains both valid and invalid records, the valid records are diagnosed while invalid records are logged under `limitations.invalid_records` rather than aborting analysis.
3. **Dual Identifier Resolution (`report_id` vs `diagnosis_id`)**:
   - Reports are indexed by both human-readable Report ID (e.g., `REP-20261031-143000-A1B2`) and UUID Diagnosis ID (e.g., `7b04961d-dd50-48e0-bb12-d9f71cba8be6`).
   - `GET /api/reports/{id}` automatically resolves either identifier format seamlessly.
4. **Resilience & Fault Isolation**:
   - Persistence failures (e.g., disk full or unwritable directory) are caught gracefully, logging a warning while still returning the complete diagnostic report to the client.
   - Orchestrator exceptions and unexpected server errors return a structured HTTP 500 response without leaking internal code execution paths.
5. **Grounded Copilot**:
   - Copilot answers use only facts in the referenced DiagnosticReport and cite evidence IDs (e.g. `[E1]`).
   - Without `ANTHROPIC_API_KEY`, or if the LLM call fails or exceeds its 8-second timeout, the built-in report explainer answers instead.

---

## Streamlit NOC Dashboard (Milestone 12)

NetCoop AI includes a dedicated, dark-themed Network Operations Center (NOC) dashboard built with Streamlit and Plotly. Designed for real-time observability, causal triage, and operational safety.

### Starting the Dashboard

```bash
# Option 1: Streamlit directly (any OS)
python -m streamlit run dashboard/app.py

# Option 2: Streamlit from an activated Windows virtual environment
.venv\Scripts\streamlit run dashboard/app.py

# Option 3: Windows batch launcher
.\run_dashboard.bat
```

Access the NOC interface in your browser at: [http://localhost:8501](http://localhost:8501)

### Dashboard Capabilities & Layout

1. **Network Overview & 4-Tier Health Status**:
   - Explicit 4-tier health indicators: `NOMINAL` (green), `DEGRADED` (amber), `CRITICAL` (red), `UNKNOWN` (slate).
   - High-visibility `FAULT DETECTED` vs `NO FAULT DETECTED` status banners.
   - Separate diagnostic certainty tiers (`CONFIRMED`, `PROVISIONAL`, `INDETERMINATE`, `NOT_APPLICABLE`), ensuring network operational health is never conflated with hypothesis certainty.
   - Non-fabricated confidence: Healthy networks explicitly display `N/A (Baseline Operational State)` rather than misleading root-cause confidence scores.
   - Multi-agent dispatch tally (`X Succeeded | Y Failed | Z Timed Out`).

2. **Diagnostic Summary & Causal Graph**:
   - Primary inferred root cause with technical descriptions, affected nodes, and certainty rating.
   - Corroborating telemetry symptoms vs contradicting / excluded factors.
   - Preserved alternative hypotheses with competing confidence levels and exclusion rationales.
   - Uncertainty notes detailing domain data gaps or sensor lag.

3. **Multi-Agent Execution Grid**:
   - Real-time execution cards for all 5 canonical agents:
     - Performance Agent
     - Infrastructure Health Agent
     - Connectivity Agent
     - Fault Correlation Agent
     - Recommendation Agent
   - Execution duration (ms), finding counts, evidence counts, and error/timeout traces.
   - **Failure Isolation**: A missing, failed, or timed-out agent is **never** presented as healthy.
   - Interactive JSON Message Bus inspector for auditing raw Pydantic envelopes.

4. **Multi-Dimensional Telemetry Visualizations**:
   - Automated detection of chronological time-series vs single-snapshot device comparisons.
   - Plotly charts across 10 core metrics: Latency (ms), Jitter (ms), Packet Loss (%), Throughput (Mbps), Bandwidth Utilization (%), CPU (%), RAM (%), Wi-Fi RSSI (dBm), Hardware Queue Drops, and Interface CRC Errors.
   - Missing optional metrics are safely handled without dashboard crashes.

5. **Findings & Evidence Explorer**:
   - Full 10-column interactive table: `Finding ID`, `Source Agent`, `Device`, `Interface`, `Metric`, `Observed Value`, `Threshold Baseline`, `Severity`, `Timestamp`, and `Finding Type`.
   - Real-time filtering by severity tier, publishing agent, and target device.
   - Consolidated evidence matrix linking telemetry breaches to root-cause hypotheses.

6. **Operational Recommendations & Advisory Runbooks**:
   - **Strict Advisory Mode**: Network remediation is advisory and explicitly requires human operator authorization before production execution.
   - Action categorization: `READ-ONLY DIAGNOSTIC`, `CONFIGURATION CHANGE`, `DISRUPTIVE REMEDIATION`.
   - Prerequisites, verification procedures, step-by-step rollback instructions, and copyable automation CLI snippets.

---

## Evaluation vs. Traditional Baseline

The `evaluation/` package benchmarks NetCoop AI against a naive threshold-alarm monitoring system on an Easy set and a Hard set (2x noise, 10–30% missing metrics, overlapping secondary faults, borderline thresholds, and 10% corrupted data). The full report is in [`evaluation/results.md`](evaluation/results.md).

| Metric | Easy Set: Baseline | Easy Set: NetCoop AI | Hard Set: Baseline | Hard Set: NetCoop AI |
| :--- | :---: | :---: | :---: | :---: |
| **Diagnostic Accuracy** | 85.7% | **85.7%** | 57.1% | **71.4%** |
| **Macro F1 Score** | 81.0% | **81.0%** | 48.6% | **66.7%** |
| **False Positive Rate (Healthy)** | 0.0% | **0.0%** | 100.0% | **0.0%** |
| **Alert / Root Cause Volume** | 57.43 alerts/ep | **0.86 cause/ep** | 36.29 alerts/ep | **0.86 cause/ep** |
| **Safety Gating Rate** | 0.0% (Ungated) | **54.5%** | 0.0% (Ungated) | **46.2%** |

Run the evaluation from the repository root:

```bash
python -m evaluation.evaluate --help   # evaluation framework options
python -m evaluation.compare           # baseline vs. NetCoop comparison
```

---

## Verification & Automated Tests

Execute the automated test suite with Pytest from the repository root:

```bash
python -m pytest -v

# or, from an activated Windows virtual environment
.venv\Scripts\pytest -v

# or, the Windows batch launcher
.\run_tests.bat
```

To trace a real telemetry record through all pipeline stages and check the frontend-backend integration, start the backend first and then run:

```bash
python scripts/trace_and_verify_pipeline.py
```

### Recorded Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\bandi\Agentic-AI
plugins: anyio-4.15.1
collected 207 items

tests/test_api.py::test_api_health PASSED                                [  1%]
tests/test_api_milestone11.py ....................                       [ 11%]
tests/test_audit_milestone10.py ..........                               [ 16%]
tests/test_connectivity_agent.py .................                       [ 24%]
tests/test_correlation_agent.py ..............                           [ 31%]
tests/test_csv_loader.py ...                                             [ 32%]
tests/test_dashboard_milestone12.py ..............                       [ 39%]
tests/test_evaluation.py ...........                                     [ 44%]
tests/test_infrastructure_agent.py .................                     [ 53%]
tests/test_milestone2_telemetry.py .........................             [ 65%]
tests/test_models.py ......                                              [ 68%]
tests/test_orchestrator.py .................                             [ 76%]
tests/test_performance_agent.py ...............                          [ 83%]
tests/test_recommendation_agent.py .............                         [ 90%]
tests/test_report_milestone10.py ..........                              [ 75%]
tests/test_robustness_milestone13.py ............................................................... [ 97%]
tests/test_scenarios.py ........                                         [100%]

====================== 279 passed, 4 warnings in 11.68s =======================
```

See [`documentation/TESTING_GUIDE.md`](documentation/TESTING_GUIDE.md) for the testing strategy.

---

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| Website header shows `OFFLINE` | The backend is not reachable at `http://127.0.0.1:8000`. Start it (Quickstart step 5) and wait up to 10 seconds for the status to refresh. The site keeps working with sample data meanwhile. |
| `npm: command not found` or `node` missing | Install Node.js 20+ from [nodejs.org](https://nodejs.org/) and open a new terminal. |
| `npm ci` fails with a lockfile error | Make sure you are in `frontend/`. If you changed dependencies yourself, run `npm install` instead. |
| `Cannot find package '@vitejs/plugin-react'` when starting the website | Website packages are not installed in `frontend/`. Run `npm ci` inside `frontend/`, or use `run_frontend.bat`, which installs them automatically. |
| A launcher window closes or reports `Python was not found` | Install Python with "Add python.exe to PATH" checked, then start the launcher again. |
| Port `5173` is already in use | Vite automatically picks the next free port and prints it, or choose one with `npm run dev -- --port 3000`. |
| Port `8000` is already in use | Stop the other process, or start Uvicorn with another port. Note that the website expects the API on port `8000` (set in `frontend/src/services/api.ts`). |
| `python` is not recognized (Windows) | Use `py` instead, or reinstall Python with "Add python.exe to PATH" checked. |
| PowerShell blocks `Activate.ps1` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip the virtual environment. |
| `ModuleNotFoundError` when starting the backend | Run commands from the repository root and install dependencies with `python -m pip install -r requirements.txt` in the same environment. |
| 3D effects do not appear | Enable hardware acceleration in your browser settings. The rest of the site works without WebGL. |
| Animations are static | Your operating system's reduced-motion setting is on; the site intentionally stops constant motion in that case. |

---

## Hackathon Acceptance Criteria Checklist

- [x] **5 Specialized Functional Agents**: Performance, Infrastructure Health, Connectivity, Fault Correlation, Recommendation.
- [x] **Central Orchestrator**: Ingestion, validation, parallel agent execution, fault/timeout recovery, and report synthesis.
- [x] **Pydantic v2 JSON Interoperability**: `message_id`, `task_id`, `agent_id`, `timestamp`, `status`, `findings`, `evidence`, `confidence`, `errors`.
- [x] **Evidence-Based Causal Inference**: Never claims certainty on ambiguous data; includes alternative hypotheses.
- [x] **Conflict Resolution**: Weighs contradicting indicators (e.g. Wi-Fi RF vs. transit link congestion).
- [x] **FastAPI Backend**: Complete REST endpoints for health, scenarios, CSV upload, diagnosis, reports, and copilot.
- [x] **Streamlit NOC Console**: Dark-theme operations center UI with KPI metric cards, Plotly charts, agent message inspector, and JSON report export.
- [x] **Interactive Web App**: React + Three.js investigation interface with live backend integration and offline fallback.
- [x] **8 Realistic Synthetic Scenarios**: Auto-generated and downloadable as sample CSVs.
- [x] **Comprehensive Pytest Suite**: 279/279 passing tests (including Milestone 11 API, Milestone 12 Dashboard, & Milestone 13 System Robustness suites).
- [x] **Complete Technical Documentation**: Architecture, agent communication, API reference, and testing guide.
