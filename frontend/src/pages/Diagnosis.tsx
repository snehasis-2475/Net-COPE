import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { PageTransition } from "../components/PageTransition";
import type { DiagnosticReport } from "../types/report";
import { MOCK_REPORT_CONGESTION } from "../services/mockData";

export const Diagnosis: React.FC = () => {
  const [report, setReport] = useState<DiagnosticReport>(MOCK_REPORT_CONGESTION);

  useEffect(() => {
    const cached = localStorage.getItem("netcoop_latest_report");
    if (cached) {
      try {
        setReport(JSON.parse(cached));
      } catch (e) {
        console.error(e);
      }
    }
  }, []);

  const isNominal = report.overall_network_health === "NOMINAL" || !report.fault_detected;

  return (
    <PageTransition theme="ivory">
      {/* =========================================================================
          MASTHEAD STRIP
          ========================================================================= */}
      <section
        style={{
          borderBottom: "var(--solid-ink)",
          padding: "1.75rem var(--margin-gutter)",
          display: "grid",
          gridTemplateColumns: "repeat(5, 1fr)",
          gap: "2rem",
          alignItems: "baseline",
        }}
      >
        <div>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
            NETWORK HEALTH
          </p>
          <p
            className="serif-subhead"
            style={{
              fontSize: "1.25rem",
              fontWeight: 500,
              marginTop: "0.25rem",
              textDecoration: report.overall_network_health === "CRITICAL" ? "underline" : "none",
            }}
          >
            {report.overall_network_health}
          </p>
        </div>

        <div>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
            DIAGNOSIS CERTAINTY
          </p>
          <p className="serif-subhead" style={{ fontSize: "1.25rem", marginTop: "0.25rem" }}>
            {report.diagnosis_certainty}
          </p>
        </div>

        <div>
          <p
            title="Calibrated heuristic score based on evidence weight minus contradiction penalties, not a statistical probability."
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.6875rem",
              opacity: 0.5,
              cursor: "help",
              textDecoration: "underline dotted",
            }}
          >
            HEURISTIC CONFIDENCE ⓘ
          </p>
          <p className="serif-subhead" style={{ fontSize: "1.25rem", marginTop: "0.25rem" }}>
            {isNominal ? (
              <span style={{ opacity: 0.45 }}>N/A (Zero-Fault Rule)</span>
            ) : (
              <span style={{ color: "var(--ink)", fontWeight: 500 }}>
                {Math.round(report.confidence_score * 100)}%
              </span>
            )}
          </p>
        </div>

        <div>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
            AFFECTED DEVICES
          </p>
          <p className="serif-subhead" style={{ fontSize: "1.25rem", marginTop: "0.25rem" }}>
            {report.affected_devices.length > 0 ? (
              `${report.affected_devices.length} Nodes Identified`
            ) : (
              <span style={{ opacity: 0.45 }}>None detected</span>
            )}
          </p>
        </div>

        <div style={{ textAlign: "right" }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
            REPORT IDENTIFIER
          </p>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.875rem", marginTop: "0.25rem" }}>
            {report.report_id}
          </p>
        </div>
      </section>

      {/* =========================================================================
          FEATURE COVER STORY: THE PROBABLE ROOT CAUSE
          ========================================================================= */}
      <section
        style={{
          padding: "clamp(4rem, 8vw, 7rem) var(--margin-gutter)",
          maxWidth: "1200px",
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.75rem",
            letterSpacing: "0.08em",
            opacity: 0.5,
            marginBottom: "1.5rem",
          }}
        >
          PRIMARY CAUSAL CONCLUSION
        </p>

        <h1
          className="serif-display"
          style={{
            fontSize: "clamp(2.4rem, 4.6vw, 4.8rem)",
            fontWeight: 600,
            lineHeight: 1.05,
            letterSpacing: "-0.025em",
            marginBottom: "2rem",
          }}
        >
          {report.probable_root_cause.title}
        </h1>

        {/* Affected Devices Tags */}
        {report.affected_devices.length > 0 && (
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "2.5rem" }}>
            {report.affected_devices.map((dev) => (
              <span
                key={dev}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.8125rem",
                  borderBottom: "1px solid var(--ink)",
                  paddingBottom: "2px",
                }}
              >
                {dev}
              </span>
            ))}
          </div>
        )}

        {/* Causal Chain Narrative Prose */}
        <p
          style={{
            fontSize: "clamp(1.125rem, 1.5vw, 1.375rem)",
            lineHeight: 1.65,
            opacity: 0.85,
            maxWidth: "60ch",
            fontWeight: 300,
          }}
        >
          {report.probable_root_cause.description}
        </p>
      </section>

      {/* =========================================================================
          EVIDENCE LEDGER: TWO COLUMNS DIVIDED BY 1PX HAIRLINE
          ========================================================================= */}
      <section
        style={{
          borderTop: "var(--solid-ink)",
          padding: "clamp(4rem, 6vw, 6rem) var(--margin-gutter)",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "clamp(3rem, 6vw, 6rem)",
        }}
      >
        {/* Column 1: Supporting Symptoms */}
        <div style={{ paddingRight: "clamp(1rem, 3vw, 3rem)" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "1.75rem",
            }}
          >
            SUPPORTING SYMPTOMS & VERIFIED EVIDENCE
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
            {report.probable_root_cause.supporting_symptoms.map((symptom, idx) => (
              <div
                key={idx}
                style={{
                  borderTop: "var(--hairline-ink)",
                  paddingTop: "1rem",
                }}
              >
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4 }}>
                  INDICATOR 0{idx + 1}
                </p>
                <p
                  className="serif-subhead"
                  style={{
                    fontSize: "1.1875rem",
                    marginTop: "0.25rem",
                    lineHeight: 1.45,
                  }}
                >
                  {symptom}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Column 2: What Argues Against It / Contradictions */}
        <div
          style={{
            borderLeft: "var(--hairline-ink)",
            paddingLeft: "clamp(1.5rem, 4vw, 4rem)",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "1.75rem",
            }}
          >
            WHAT ARGUES AGAINST IT & PENALTIES
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
            {report.conflicting_evidence.length > 0 ? (
              report.conflicting_evidence.map((conf, idx) => (
                <div
                  key={idx}
                  style={{
                    borderTop: "var(--hairline-ink)",
                    paddingTop: "1rem",
                  }}
                >
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4 }}>
                    CONTRADICTION ANALYSIS
                  </p>
                  <p
                    style={{
                      fontSize: "1rem",
                      marginTop: "0.25rem",
                      lineHeight: 1.5,
                      opacity: 0.8,
                    }}
                  >
                    {conf}
                  </p>
                </div>
              ))
            ) : (
              <p style={{ fontSize: "0.9375rem", opacity: 0.5, fontStyle: "italic" }}>
                No conflicting observations identified across domain agents.
              </p>
            )}

            {report.uncertainty_notes.map((note, idx) => (
              <div
                key={idx}
                style={{
                  borderTop: "var(--hairline-ink)",
                  paddingTop: "1rem",
                }}
              >
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4 }}>
                  CALIBRATION NOTE
                </p>
                <p
                  style={{
                    fontSize: "0.875rem",
                    marginTop: "0.25rem",
                    lineHeight: 1.5,
                    opacity: 0.75,
                  }}
                >
                  {note}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* =========================================================================
          ALTERNATIVE HYPOTHESES LIST
          ========================================================================= */}
      {report.alternative_causes.length > 0 && (
        <section
          style={{
            borderTop: "var(--hairline-ink)",
            padding: "clamp(4rem, 6vw, 6rem) var(--margin-gutter)",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.75rem",
              letterSpacing: "0.08em",
              opacity: 0.5,
              marginBottom: "2rem",
            }}
          >
            ALTERNATIVE HYPOTHESES EVALUATED & DEPRIORITIZED
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "2.5rem" }}>
            {report.alternative_causes.map((alt, idx) => (
              <div
                key={idx}
                className="hover-row"
                data-spot
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 200px",
                  gap: "3rem",
                  paddingBottom: "2rem",
                  borderBottom: "var(--hairline-ink)",
                  alignItems: "baseline",
                }}
              >
                <div>
                  <h3 className="serif-subhead" style={{ fontSize: "1.375rem" }}>
                    {alt.title}
                  </h3>
                  <p style={{ fontSize: "0.9375rem", opacity: 0.75, marginTop: "0.4rem", maxWidth: "60ch" }}>
                    {alt.description}
                  </p>
                  <p
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.75rem",
                      opacity: 0.5,
                      marginTop: "0.5rem",
                    }}
                  >
                    Reason Deprioritized: {alt.contradicting_symptoms.join("; ") || "Insufficient evidence support."}
                  </p>
                </div>

                <div>
                  <div
                    style={{
                      height: "1px",
                      backgroundColor: "var(--ink-15)",
                      width: "100%",
                      marginBottom: "0.5rem",
                      position: "relative",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 0,
                        height: "1px",
                        backgroundColor: "var(--ink)",
                        width: `${alt.confidence * 100}%`,
                      }}
                    />
                  </div>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.6 }}>
                    Weight: {Math.round(alt.confidence * 100)}%
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: "4rem", display: "flex", justifyContent: "flex-end" }}>
            <Link to="/runbook" className="editorial-link" style={{ fontSize: "0.9375rem", fontWeight: 500 }}>
              Proceed to safety-gated runbook actions
            </Link>
          </div>
        </section>
      )}
    </PageTransition>
  );
};
