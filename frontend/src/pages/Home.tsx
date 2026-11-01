import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageTransition } from "../components/PageTransition";
import {
  LighthouseIllustration,
  RouterIllustration,
  CableIllustration,
  AntennaIllustration,
  CompassIllustration,
  MagnifierIllustration,
} from "../components/Illustrations";
import { SignalField } from "../components/three/SignalField";
import { AgentRing } from "../components/three/AgentRing";
import { SignalRibbon } from "../components/three/SignalRibbon";
import { OrbitRings } from "../components/three/OrbitRings";
import { apiService } from "../services/api";
import type { ScenarioDefinition } from "../types/telemetry";
import type { DiagnosticReport } from "../types/report";

export const Home: React.FC = () => {
  const navigate = useNavigate();
  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("congestion");
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [diagnosisResult, setDiagnosisResult] = useState<DiagnosticReport | null>(null);

  useEffect(() => {
    apiService.getScenarios().then((res) => setScenarios(res.scenarios));
  }, []);

  const handleRunDiagnosis = async () => {
    setIsDiagnosing(true);
    try {
      const dataRes = await apiService.getScenarioData(selectedScenario);
      const diagRes = await apiService.runDiagnosis(dataRes.records, selectedScenario);
      setDiagnosisResult(diagRes.report);
      // Save to localStorage so other routes have immediate context
      localStorage.setItem("netcoop_latest_report", JSON.stringify(diagRes.report));
    } catch (err) {
      console.error("Diagnosis error:", err);
    } finally {
      setIsDiagnosing(false);
    }
  };

  const agents = [
    {
      name: "Performance Agent",
      domain: "Data-plane packet velocity & saturation",
      metrics: "Round-trip latency, jitter, packet loss %, link bandwidth utilization",
      illustration: <RouterIllustration size={160} color="var(--ivory)" />,
    },
    {
      name: "Infrastructure Agent",
      domain: "Physical hardware & interface stability",
      metrics: "CPU starvation %, memory pressure %, interface flapping, CRC errors, queue drops",
      illustration: <CableIllustration size={160} color="var(--ivory)" />,
    },
    {
      name: "Connectivity Agent",
      domain: "Access layer, RF propagation & discovery",
      metrics: "DNS resolution time, DHCP scope exhaustion, Wi-Fi RSSI, SNR, Layer 2 retries",
      illustration: <AntennaIllustration size={160} color="var(--ivory)" />,
    },
    {
      name: "Fault Correlation Agent",
      domain: "Causal synthesis & evidence weighting",
      metrics: "Contradiction resolution, evidence penalties, certainty tiers (Confirmed / Provisional)",
      illustration: <CompassIllustration size={160} color="var(--ivory)" />,
    },
    {
      name: "Recommendation Agent",
      domain: "Prescriptive remediation & safety gating",
      metrics: "Priority-ranked runbooks, disruptive human-approval gates, automated commands, rollback procedures",
      illustration: <MagnifierIllustration size={160} color="var(--ivory)" />,
    },
  ];

  return (
    <PageTransition theme="ivory" field={false}>
      {/* =========================================================================
          HERO COVER: VAST WARM IVORY SPACE & SCRIPTURE
          ========================================================================= */}
      <section
        className="theme-ink hero-section"
        style={{
          minHeight: "92vh",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "clamp(3rem, 7vw, 8rem) var(--margin-gutter) 3rem",
        }}
      >
        <SignalField tone="dark" className="hero-field" />
        <div style={{ maxWidth: "min(1320px, 100%)", position: "relative", zIndex: 1 }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "2rem",
            }}
          >
            CHAPTER ONE — AN INVESTIGATION OF INFRASTRUCTURE FAILURE
          </p>

          <h1
            className="serif-display"
            style={{
              fontSize: "clamp(2.4rem, 5vw, 6rem)",
              fontWeight: 700,
              lineHeight: 0.95,
              marginBottom: "2.5rem",
              letterSpacing: "-0.03em",
            }}
          >
            When everything alerts, <br />
            <span className="em-outline">nothing is clear.</span>
          </h1>

          <p
            style={{
              fontSize: "clamp(1.0625rem, 1.4vw, 1.3125rem)",
              lineHeight: 1.6,
              opacity: 0.75,
              maxWidth: "52ch",
              fontWeight: 300,
            }}
          >
            Modern enterprise networks do not break quietly. A single saturated transit link triggers a thousand alarms across DNS, Wi-Fi, application sockets, and switch ports. Five specialized agents disentangle the noise to uncover the solitary truth.
          </p>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            paddingTop: "4rem",
            borderTop: "var(--hairline-ivory)",
            position: "relative",
            zIndex: 1,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "2rem" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4 }}>
              01 / 03
            </span>
            <span style={{ fontSize: "0.875rem", opacity: 0.6 }}>
              Scroll to explore the causal investigation
            </span>
          </div>
          <div>
            <LighthouseIllustration size={110} color="var(--ivory)" />
          </div>
        </div>
      </section>

      {/* =========================================================================
          CHAPTER TWO: THE NOISE VS THE SIGNAL (CONVERGING ALERTS)
          ========================================================================= */}
      <section
        style={{
          minHeight: "90vh",
          backgroundColor: "var(--ivory)",
          padding: "clamp(4rem, 8vw, 8rem) var(--margin-gutter)",
          borderTop: "var(--hairline-ink)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
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
            THE CASCADE
          </p>
          <h2
            className="serif-headline"
            style={{
              fontSize: "clamp(2.2rem, 4vw, 3.8rem)",
              marginBottom: "1.5rem",
            }}
          >
            A dozen alarms, <span className="em-outline">one solitary break.</span>
          </h2>
          <p style={{ opacity: 0.7, maxWidth: "58ch", fontSize: "1rem" }}>
            Alert storms deceive human operators by mistaking downstream consequences for origins. Observe how disparate indicators scatter across the operations center floor:
          </p>
        </div>

        {/* Scattered typographic fragments */}
        <div
          style={{
            position: "relative",
            minHeight: "360px",
            border: "var(--hairline-ink)",
            padding: "3rem",
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "2.5rem",
          }}
        >
          <div className="signal-chip" data-spot style={{ borderLeft: "var(--hairline-ink)", paddingLeft: "1.5rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4 }}>PERFORMANCE BREACH</p>
            <p className="serif-subhead" style={{ fontSize: "1.5rem", marginTop: "0.5rem" }}>Transit RTT 184 ms</p>
            <p style={{ fontSize: "0.8125rem", opacity: 0.6 }}>Core uplink GigabitEthernet0/0/1 queue saturation</p>
          </div>

          <div className="signal-chip" data-spot style={{ borderLeft: "var(--hairline-ink)", paddingLeft: "1.5rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4 }}>APPARENT COLLATERAL</p>
            <p className="serif-subhead" style={{ fontSize: "1.5rem", marginTop: "0.5rem" }}>DNS Resolution Timeout</p>
            <p style={{ fontSize: "0.8125rem", opacity: 0.6 }}>Recursive lookup packets dropped in transit buffer</p>
          </div>

          <div className="signal-chip" data-spot style={{ borderLeft: "var(--hairline-ink)", paddingLeft: "1.5rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4 }}>FALSE SUSPECT</p>
            <p className="serif-subhead" style={{ fontSize: "1.5rem", marginTop: "0.5rem" }}>Wi-Fi Retries 32%</p>
            <p style={{ fontSize: "0.8125rem", opacity: 0.6 }}>Client TCP backoff mimicking RF signal degradation</p>
          </div>

          <div
            style={{
              gridColumn: "1 / -1",
              borderTop: "var(--hairline-ink)",
              paddingTop: "2rem",
              marginTop: "1rem",
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
            }}
          >
            <p
              className="serif-headline"
              style={{
                fontSize: "1.5rem",
                color: "var(--ink)",
              }}
            >
              The orchestrator resolves contradictions and isolates the single point of failure.
            </p>
            <Link to="/ingest" className="editorial-link" style={{ fontSize: "0.875rem", fontWeight: 500 }}>
              Inspect telemetry studio
            </Link>
          </div>
        </div>
      </section>

      {/* =========================================================================
          CHAPTER THREE: THE FIVE SPECIALIZED AGENTS (DEEP INK SECTION)
          ========================================================================= */}
      <section
        className="theme-ink"
        style={{
          padding: "clamp(5rem, 9vw, 9rem) var(--margin-gutter)",
          borderTop: "var(--hairline-ivory)",
        }}
      >
        <div className="minds-head">
        <div style={{ maxWidth: "900px" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "1.25rem",
            }}
          >
            THE FIVE MINDS
          </p>
          <h2
            className="serif-headline"
            style={{
              fontSize: "clamp(2.4rem, 4.5vw, 4.4rem)",
              marginBottom: "1.5rem",
              letterSpacing: "-0.02em",
            }}
          >
            Autonomous domain specialists, <br />
            <span className="em-outline">governed by evidence.</span>
          </h2>
          <p style={{ opacity: 0.7, maxWidth: "56ch", fontSize: "1.0625rem", lineHeight: 1.6 }}>
            Rather than a monolithic model speculating on raw numbers, five purpose-built agents scrutinize specific telemetry dimensions, communicate via strict Pydantic message envelopes, and submit verifiable findings to a causal deduction engine.
          </p>
        </div>
        <AgentRing className="agent-ring" />
        </div>

        {/* 5 Agent Panels */}
        <div style={{ display: "flex", flexDirection: "column", gap: "3.5rem" }}>
          {agents.map((agent, idx) => (
            <div
              key={agent.name}
              className="agent-row"
              data-spot
              style={{
                display: "grid",
                gridTemplateColumns: "80px 1fr 280px",
                gap: "3rem",
                alignItems: "center",
                paddingBottom: "3rem",
                borderBottom: "var(--hairline-ivory)",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "1rem",
                  opacity: 0.35,
                }}
              >
                0{idx + 1}
              </span>

              <div>
                <h3
                  className="serif-headline"
                  style={{
                    fontSize: "clamp(1.75rem, 2.5vw, 2.4rem)",
                    marginBottom: "0.75rem",
                  }}
                >
                  {agent.name}
                </h3>
                <p
                  style={{
                    fontSize: "1rem",
                    opacity: 0.85,
                    marginBottom: "0.75rem",
                    fontWeight: 300,
                  }}
                >
                  {agent.domain}
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.75rem",
                    opacity: 0.5,
                    lineHeight: 1.5,
                  }}
                >
                  Watched Metrics: {agent.metrics}
                </p>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                {agent.illustration}
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: "4rem", display: "flex", justifyContent: "flex-end" }}>
          <Link to="/pipeline" className="editorial-link" style={{ fontSize: "0.9375rem", color: "var(--ivory)" }}>
            Explore the real-time agent message bus
          </Link>
        </div>

        <div className="ribbon-band">
          <SignalRibbon className="ribbon-canvas" />
          <span className="ribbon-caption" style={{ left: "var(--margin-gutter)" }}>
            Fig. 03 — Correlated signal surface
          </span>
          <span className="ribbon-caption" style={{ right: "var(--margin-gutter)" }}>
            Move to bend the signal
          </span>
        </div>
      </section>

      {/* =========================================================================
          CHAPTER FOUR: THE LIVE DIAGNOSIS WORKBENCH
          ========================================================================= */}
      <section
        className="theme-signal"
        style={{
          padding: "clamp(5rem, 8vw, 8rem) var(--margin-gutter)",
          borderTop: "var(--hairline-ink)",
          backgroundColor: "var(--signal)",
        }}
      >
        <div className="workbench-head">
        <div style={{ maxWidth: "800px" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "1rem",
            }}
          >
            VERIFICATION
          </p>
          <h2
            className="serif-headline"
            style={{
              fontSize: "clamp(2.2rem, 3.8vw, 3.6rem)",
              marginBottom: "1rem",
            }}
          >
            Execute an operational diagnosis.
          </h2>
          <p style={{ opacity: 0.7, maxWidth: "56ch" }}>
            Select an incident scenario from the certified benchmark suite. The orchestrator dispatches telemetry to all five agents concurrently and compiles an evidence-grounded report.
          </p>
        </div>
        <OrbitRings active={isDiagnosing} className="orbit-canvas" />
        </div>

        {/* Diagnostic Control Console */}
        <div
          data-spot
          style={{
            border: "var(--hairline-ink)",
            padding: "2.5rem",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "3rem",
            alignItems: "center",
          }}
        >
          <div>
            <label
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.75rem",
                opacity: 0.5,
                display: "block",
                marginBottom: "0.75rem",
              }}
            >
              SELECT OPERATIONAL SCENARIO
            </label>
            <select
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              style={{
                width: "100%",
                padding: "0.875rem 1rem",
                border: "var(--hairline-ink)",
                backgroundColor: "transparent",
                color: "var(--ink)",
                fontFamily: "var(--font-sans)",
                fontSize: "1rem",
                outline: "none",
                cursor: "pointer",
              }}
            >
              {scenarios.map((sc) => (
                <option key={sc.id} value={sc.id}>
                  {sc.title} ({sc.category})
                </option>
              ))}
            </select>
            <p
              style={{
                fontSize: "0.8125rem",
                opacity: 0.6,
                marginTop: "1rem",
                lineHeight: 1.5,
              }}
            >
              {scenarios.find((s) => s.id === selectedScenario)?.description}
            </p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <button
              onClick={handleRunDiagnosis}
              disabled={isDiagnosing}
              style={{
                padding: "1rem 2rem",
                border: "var(--solid-ink)",
                backgroundColor: "var(--ink)",
                color: "var(--ivory)",
                fontFamily: "var(--font-sans)",
                fontSize: "0.9375rem",
                fontWeight: 500,
                cursor: isDiagnosing ? "wait" : "pointer",
                transition: "opacity 0.2s ease, transform 0.35s var(--ease-out), box-shadow 0.35s var(--ease-out)",
                opacity: isDiagnosing ? 0.6 : 1,
                textAlign: "center",
              }}
            >
              {isDiagnosing ? "Running Multi-Agent Diagnosis..." : "Run Multi-Agent Diagnosis"}
            </button>

            {diagnosisResult && (
              <div
                style={{
                  borderLeft: "2px solid var(--teal)",
                  paddingLeft: "1.25rem",
                  paddingTop: "0.5rem",
                  paddingBottom: "0.5rem",
                }}
              >
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
                  REPORT COMPILED: {diagnosisResult.report_id}
                </p>
                <p className="serif-subhead" style={{ fontSize: "1.125rem", marginTop: "0.25rem" }}>
                  {diagnosisResult.probable_root_cause.title}
                </p>
                <button
                  onClick={() => navigate("/diagnosis")}
                  className="editorial-link"
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 500,
                    marginTop: "0.5rem",
                    border: "none",
                    background: "none",
                    padding: 0,
                  }}
                >
                  View complete investigative report
                </button>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* =========================================================================
          CLOSING FOOTER
          ========================================================================= */}
      <footer
        className="theme-ink"
        style={{
          padding: "3rem var(--margin-gutter)",
          borderTop: "var(--hairline-ivory)",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.75rem",
          color: "var(--ivory-70)",
          fontFamily: "var(--font-mono)",
          overflow: "hidden",
        }}
      >
        <div>
          <span>NETCOOP AI — SCHEMA VERSION 2.0.0</span>
        </div>
        <div style={{ display: "flex", gap: "2rem" }}>
          <Link to="/vault" className="editorial-link">
            Report Archive
          </Link>
          <Link to="/telemetry" className="editorial-link">
            Time-Series Studio
          </Link>
        </div>
        <div className="footer-mark" aria-hidden="true">
          NetCoop AI
        </div>
      </footer>
    </PageTransition>
  );
};
