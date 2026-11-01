# NetCoop AI — System Architecture Specification

## 1. Executive Summary

**NetCoop AI** is a modular, multi-agent network fault diagnosis and interoperability platform designed for modern Network Operations Centers (NOC). The system ingests multi-dimensional network telemetry, distributes analysis across specialized autonomous agents, correlates heterogeneous symptoms using evidence-based causal graphs, and formulates prescriptive remediation runbooks.

---

## 2. High-Level Architecture Diagram

```
                              ┌──────────────────────────────────────────┐
                              │         Telemetry Ingest Layer           │
                              │ (CSV Upload, Real-Time JSON, Scenarios)  │
                              └────────────────────┬─────────────────────┘
                                                   │
                                                   ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               CENTRAL ORCHESTRATOR                                     │
│  - Telemetry Schema Normalization & Validation                                         │
│  - Parallel Task Dispatch & Lifecycle Execution                                        │
│  - Standardized JSON Message Envelope Validation                                       │
│  - Timeout Detection & Agent Crash Fallback                                            │
│  - Final Unified Diagnostic Report Assembly                                            │
└───────────────┬──────────────────────────┬──────────────────────────┬──────────────────┘
                │                          │                          │
                ▼                          ▼                          ▼
      ┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
      │   Performance    │       │  Infrastructure  │       │   Connectivity   │
      │      Agent       │       │   Health Agent   │       │      Agent       │
      │ - Latency (RTT)  │       │ - CPU/RAM Load   │       │ - DNS Resolution │
      │ - Jitter Var.    │       │ - Availability   │       │ - DHCP Leases    │
      │ - Packet Loss    │       │ - Link/Port State│       │ - Wi-Fi RSSI/SNR │
      │ - Bandwidth Sat. │       │ - Queue Drops    │       │ - Reachability   │
      └─────────┬────────┘       └─────────┬────────┘       └─────────┬────────┘
                │                          │                          │
                └──────────────────────────┼──────────────────────────┘
                                           │
                                           ▼ (Validated JSON Message Envelopes)
                        ┌─────────────────────────────────────┐
                        │      FAULT CORRELATION AGENT        │
                        │ - Multi-Symptom Evidence Synthesis  │
                        │ - Causal Hypothesis Matrix          │
                        │ - Conflict Resolution & Weighing    │
                        │ - Uncertainty / Confidence Scoring  │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼ (Primary Root Cause + Evidence)
                        ┌─────────────────────────────────────┐
                        │        RECOMMENDATION AGENT         │
                        │ - Prescriptive Remediation Steps    │
                        │ - Priority-Ranked Runbooks          │
                        │ - Verification Procedures           │
                        │ - Executable CLI Script Automation  │
                        └──────────────────┬──────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           UNIFIED DIAGNOSTIC REPORT                                    │
│       Report ID • Probable Root Cause • Alternative Causes • Evidence • Runbooks       │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                         ┌─────────────────┴─────────────────┐
                         ▼                                   ▼
              ┌─────────────────────┐             ┌─────────────────────┐
              │    FastAPI REST     │             │  Streamlit NOC UI   │
              │   API Endpoints     │             │ Interactive Console │
              └─────────────────────┘             └─────────────────────┘
```

---

## 3. Specialized Agent Specifications

### 3.1 Performance Agent (`agents/performance_agent.py`)
- **Domain Focus**: Transport layer performance and quality of service.
- **Key Metrics**:
  - `latency_ms`: Round-trip time (RTT). Thresholds: Warning >50ms, Critical >100ms.
  - `jitter_ms`: Delay variation. Thresholds: Warning >15ms, Critical >30ms.
  - `packet_loss_pct`: Transmission drops. Thresholds: Warning >2.0%, Critical >5.0%.
  - `bandwidth_util_pct` & `throughput_mbps`: Transit utilization. Thresholds: Warning >80%, Critical >92%.
- **Output**: Structured `Finding`s and `EvidenceItem`s with statistical summaries (mean, p95, max).

### 3.2 Infrastructure Health Agent (`agents/infrastructure_agent.py`)
- **Domain Focus**: Hardware compute resources and physical interface integrity.
- **Key Metrics**:
  - `cpu_util_pct`: Control plane CPU utilization (>80% warning, >90% critical).
  - `memory_util_pct`: System RAM saturation (>80% warning, >90% critical).
  - `device_availability`: Host uptime and reachability (<99% warning, <90% critical).
  - `interface_status`: Physical port states (`up`, `down`, `flapping`).
  - `interface_errors`: CRC framing errors, alignment drops, physical cable defects.
  - `queue_drops`: Switch/router buffer queue tail drops.
- **Output**: Hardware fault classifications and link health indicators.

### 3.3 Connectivity Agent (`agents/connectivity_agent.py`)
- **Domain Focus**: Core network naming, addressing, and physical wireless RF.
- **Key Metrics**:
  - `dns_resolution_status`: Query outcomes (`success`, `timeout`, `servfail`, `refused`).
  - `dns_latency_ms`: Query round-trip time (>100ms warning, >250ms critical).
  - `dhcp_status`: IP lease state (`bound`, `timeout`, `exhausted`, `failed`).
  - `wifi_rssi_dbm`: Wireless signal strength (<-72 dBm warning, <-82 dBm critical).
  - `wifi_snr_db`: Wireless signal-to-noise ratio (<18 dB warning).
  - `connectivity_status`: End-to-end reachability (`connected`, `degraded`, `disconnected`).
- **Output**: Layer 2/3 core service failure determinations.

### 3.4 Fault Correlation Agent (`diagnosis/correlation_agent.py`)
- **Domain Focus**: Cross-domain causal inference and hypothesis testing.
- **Functionality**:
  - Integrates findings and evidence across all specialized agents.
  - Evaluates competing causal hypotheses (Interface Failure vs. Congestion vs. Weak Wi-Fi vs. DNS vs. DHCP vs. Infrastructure Overload vs. Nominal).
  - **Conflict Resolution**: Weighs contradicting indicators (e.g., if Wi-Fi RSSI is -86 dBm and endpoint packet loss is 10%, but core switch bandwidth and CPU are healthy, the root cause is isolated to the wireless medium rather than core network congestion).
  - **Uncertainty Handling**: When evidence is sparse or ambiguous, calculates calibrated low confidence (<0.35) and marks the diagnosis as `INSUFFICIENT_EVIDENCE` with explicit missing data flags.

### 3.5 Recommendation Agent (`diagnosis/recommendation_agent.py`)
- **Domain Focus**: Operational remediation and incident runbooks.
- **Functionality**:
  - Maps correlated root causes and affected devices to prescriptive runbooks.
  - Prioritizes actions:
    - **Priority 1**: Immediate mitigation (e.g., bounce flapping port, traffic shaping, switch DNS forwarders).
    - **Priority 2**: Configuration / Root cause resolution (e.g., CoPP policy, expand DHCP scope, channel width adjustment).
    - **Priority 3**: Verification & hardening.
  - Produces executable CLI/PowerShell commands ready for automated or manual execution.

### 3.6 Central Orchestrator (`orchestrator/orchestrator.py`)
- **Domain Focus**: System coordination, fault isolation, and report generation.
- **Functionality**:
  - Ingests and normalizes raw telemetry (DataFrames, JSON, CSV).
  - Dispatches tasks concurrently to specialized domain agents using thread pools.
  - Manages timeouts and execution safety. If an agent crashes or times out, creates a fallback error message envelope and allows the remaining agents to complete.
  - Calls correlation and recommendation agents sequentially.
  - Assembles the final unified `DiagnosticReport` and persists it to disk.
