import React, { useState } from "react";
import { PageTransition } from "../components/PageTransition";
import type { AgentMessage } from "../types/report";

export const Pipeline: React.FC = () => {
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState<number>(3);

  const pipelineStages = [
    { id: 1, name: "Telemetry Ingestion", description: "Validation, schema normalization, outlier quarantine" },
    { id: 2, name: "Parallel Domain Agents", description: "Performance, infrastructure & connectivity concurrent dispatch" },
    { id: 3, name: "Conflict Resolution", description: "Contradiction detection, penalty subtraction, evidence isolation" },
    { id: 4, name: "Causal Correlation", description: "Causal graph hypothesis mapping, certainty tiering" },
    { id: 5, name: "Runbook Synthesis", description: "Remediation formulation, human approval gating & rollback generation" },
  ];

  const agentEntries = [
    {
      id: "performance_agent",
      name: "Performance Agent",
      status: "SUCCESS",
      duration_ms: 18.4,
      findings_count: 2,
      confidence: 0.95,
      evidence_count: 4,
    },
    {
      id: "infrastructure_agent",
      name: "Infrastructure Agent",
      status: "SUCCESS",
      duration_ms: 22.1,
      findings_count: 1,
      confidence: 0.92,
      evidence_count: 3,
    },
    {
      id: "connectivity_agent",
      name: "Connectivity Agent",
      status: "SUCCESS",
      duration_ms: 16.9,
      findings_count: 1,
      confidence: 0.88,
      evidence_count: 2,
    },
    {
      id: "correlation_agent",
      name: "Fault Correlation Agent",
      status: "SUCCESS",
      duration_ms: 38.6,
      findings_count: 3,
      confidence: 0.94,
      evidence_count: 9,
    },
    {
      id: "recommendation_agent",
      name: "Recommendation Agent",
      status: "SUCCESS",
      duration_ms: 24.2,
      findings_count: 0,
      confidence: 1.0,
      evidence_count: 3,
    },
  ];

  const getMockAgentEnvelope = (agentId: string): AgentMessage => ({
    message_id: `MSG-${Math.random().toString(36).substring(2, 10).toUpperCase()}`,
    task_id: "TASK-7E82C941",
    agent_id: agentId,
    timestamp: new Date().toISOString(),
    status: "SUCCESS",
    findings: [
      {
        finding_id: `FND-${agentId.substring(0, 3).toUpperCase()}-01`,
        source_agent: agentId,
        category: agentId.includes("perf") ? "PERFORMANCE" : "INFRASTRUCTURE",
        title: agentId.includes("perf") ? "WAN Transit Latency Breach" : "Queue Buffer Overflow",
        description: "Verified telemetry threshold violation across consecutive evaluation windows.",
        severity: "HIGH",
        affected_devices: ["core-router-01"],
        metric_name: agentId.includes("perf") ? "latency_ms" : "queue_drops",
        observed_value: agentId.includes("perf") ? 184.2 : 312,
        threshold: agentId.includes("perf") ? 100.0 : 0,
        unit: agentId.includes("perf") ? "ms" : "packets",
      },
    ],
    evidence: [
      {
        metric_name: "bandwidth_util_pct",
        observed_value: 96.4,
        threshold: 80.0,
        unit: "%",
        device_id: "core-router-01",
        timestamp: new Date().toISOString(),
        interpretation: "Sustained WAN link saturation breaching operational threshold.",
      },
    ],
    confidence: 0.94,
    errors: [],
    metadata: {
      interoperability_protocol: "NetCoop.Envelope.v2",
      dispatch_method: "concurrent.futures.ThreadPoolExecutor",
      timeout_seconds: 8.0,
    },
  });

  return (
    <PageTransition theme="ink">
      <div style={{ padding: "clamp(3rem, 6vw, 6rem) var(--margin-gutter)", minHeight: "100vh" }}>
        {/* Header */}
        <div style={{ maxWidth: "800px", marginBottom: "4rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "1rem",
            }}
          >
            INTER-AGENT BUS
          </p>
          <h1
            className="serif-headline"
            style={{
              fontSize: "clamp(2.4rem, 4.5vw, 4.2rem)",
              marginBottom: "1rem",
            }}
          >
            The Autonomous Agent Bus
          </h1>
          <p style={{ opacity: 0.7, maxWidth: "56ch", fontSize: "1.0625rem" }}>
            A single continuous flow from raw telemetry ingest through concurrent domain agent analysis, conflict resolution, causal deduction, and safety runbook synthesis.
          </p>
        </div>

        {/* Continuous Thin SVG Pipeline with Electric Teal Traveling Pulse */}
        <div style={{ margin: "4rem 0 5rem" }}>
          <div style={{ position: "relative", width: "100%", height: "80px" }}>
            <svg
              width="100%"
              height="100%"
              viewBox="0 0 1000 80"
              preserveAspectRatio="none"
              style={{ overflow: "visible" }}
            >
              {/* Background Hairline */}
              <line x1="0" y1="40" x2="1000" y2="40" stroke="var(--ivory-15)" strokeWidth="1" />
              {/* Active Traveling Pulse Line */}
              <line
                x1="0"
                y1="40"
                x2={activeStep * 200}
                y2="40"
                stroke="var(--teal)"
                strokeWidth="1.5"
                style={{ transition: "x2 0.8s cubic-bezier(0.16, 1, 0.3, 1)" }}
              />

              {/* Milestone Nodes */}
              {pipelineStages.map((stage, idx) => {
                const cx = (idx / 4) * 1000;
                const isPassed = activeStep >= idx + 1;
                return (
                  <g key={stage.id} onClick={() => setActiveStep(idx + 1)} style={{ cursor: "pointer" }}>
                    <circle
                      cx={cx}
                      cy="40"
                      r={isPassed ? "5" : "3"}
                      fill="var(--ink)"
                      stroke={isPassed ? "var(--teal)" : "var(--ivory-40)"}
                      strokeWidth="1.5"
                    />
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Pipeline Stage Titles */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "1.5rem" }}>
            {pipelineStages.map((stage, idx) => (
              <div
                key={stage.id}
                onClick={() => setActiveStep(idx + 1)}
                style={{
                  borderTop: activeStep >= idx + 1 ? "1.5px solid var(--teal)" : "var(--hairline-ivory)",
                  paddingTop: "1rem",
                  cursor: "pointer",
                }}
              >
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4 }}>
                  STAGE 0{idx + 1}
                </p>
                <p className="serif-subhead" style={{ fontSize: "1.125rem", marginTop: "0.25rem" }}>
                  {stage.name}
                </p>
                <p style={{ fontSize: "0.75rem", opacity: 0.6, marginTop: "0.35rem", lineHeight: 1.4 }}>
                  {stage.description}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Agent Node Ledger */}
        <div style={{ marginTop: "5rem" }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.5, marginBottom: "1.5rem" }}>
            AGENT PARTICIPATION MATRIX & PROVENANCE
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 140px 140px 140px 180px",
              paddingBottom: "1rem",
              borderBottom: "var(--solid-ivory)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.6875rem",
              opacity: 0.5,
              letterSpacing: "0.08em",
            }}
          >
            <span>AGENT IDENTIFIER</span>
            <span>STATUS</span>
            <span>DURATION</span>
            <span>FINDINGS</span>
            <span style={{ textAlign: "right" }}>INSPECT ENVELOPE</span>
          </div>

          {agentEntries.map((ag) => (
            <div
              key={ag.id}
              className="hover-row"
              data-spot
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 140px 140px 140px 180px",
                padding: "1.5rem 0",
                borderBottom: "var(--hairline-ivory)",
                alignItems: "center",
              }}
            >
              <div>
                <p className="serif-subhead" style={{ fontSize: "1.25rem" }}>{ag.name}</p>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4 }}>{ag.id}</p>
              </div>

              <div>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.75rem",
                    borderBottom: "1px solid var(--ivory)",
                    paddingBottom: "1px",
                  }}
                >
                  {ag.status}
                </span>
              </div>

              <div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", opacity: 0.8 }}>
                  {ag.duration_ms} ms
                </span>
              </div>

              <div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", opacity: 0.8 }}>
                  {ag.findings_count} findings ({ag.evidence_count} evd)
                </span>
              </div>

              <div style={{ textAlign: "right" }}>
                <button
                  onClick={() => setSelectedAgent(ag.id)}
                  className="editorial-link"
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--ivory)",
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.8125rem",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  Open JSON envelope
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Slide-out Side Drawer for Raw AgentMessage JSON Envelope */}
        {selectedAgent && (
          <div
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              width: "clamp(340px, 45vw, 650px)",
              height: "100vh",
              backgroundColor: "var(--ink)",
              borderLeft: "var(--hairline-ivory)",
              zIndex: 1000,
              padding: "3rem",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              boxShadow: "-10px 0 40px rgba(0,0,0,0.6)",
            }}
          >
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  borderBottom: "var(--hairline-ivory)",
                  paddingBottom: "1.5rem",
                  marginBottom: "2rem",
                }}
              >
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
                    STANDARDIZED ENVELOPE INSPECTOR
                  </p>
                  <h3 className="serif-subhead" style={{ fontSize: "1.5rem", marginTop: "0.25rem" }}>
                    {selectedAgent}
                  </h3>
                </div>
                <button
                  onClick={() => setSelectedAgent(null)}
                  className="editorial-link"
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--ivory)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.8125rem",
                    cursor: "pointer",
                  }}
                >
                  Close [×]
                </button>
              </div>

              <pre
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.75rem",
                  lineHeight: 1.6,
                  color: "var(--ivory-90)",
                  backgroundColor: "rgba(255,255,255,0.03)",
                  padding: "1.5rem",
                  border: "var(--hairline-ivory)",
                  maxHeight: "calc(100vh - 220px)",
                  overflowY: "auto",
                }}
              >
                {JSON.stringify(getMockAgentEnvelope(selectedAgent), null, 2)}
              </pre>
            </div>

            <div style={{ paddingTop: "1rem", borderTop: "var(--hairline-ivory)" }}>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4 }}>
                Schema: Pydantic v2 • Validation: Strict Domain Bounds [0.0, 1.0]
              </p>
            </div>
          </div>
        )}
      </div>
    </PageTransition>
  );
};
