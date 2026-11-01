import React, { useState, useEffect } from "react";
import { PageTransition } from "../components/PageTransition";
import type { CorrectiveAction, DiagnosticReport } from "../types/report";
import { MOCK_REPORT_CONGESTION } from "../services/mockData";

export const Runbook: React.FC = () => {
  const [report, setReport] = useState<DiagnosticReport>(MOCK_REPORT_CONGESTION);
  const [authorizedActions, setAuthorizedActions] = useState<Record<number, boolean>>({});
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<Record<number, "command" | "verification" | "rollback">>({});

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

  const handleAuthorize = (priority: number) => {
    setAuthorizedActions((prev: Record<number, boolean>) => ({
      ...prev,
      [priority]: !prev[priority],
    }));
  };

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const actions: CorrectiveAction[] = report.recommended_corrective_actions || [];

  return (
    <PageTransition theme="ivory">
      <div style={{ padding: "clamp(3rem, 6vw, 6rem) var(--margin-gutter)" }}>
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
            PRESCRIPTIVE RUNBOOK
          </p>
          <h1
            className="serif-headline"
            style={{
              fontSize: "clamp(2.4rem, 4.5vw, 4.2rem)",
              marginBottom: "1rem",
            }}
          >
            Remediation Sequence & Safeguards
          </h1>
          <p style={{ opacity: 0.7, maxWidth: "56ch", fontSize: "1.0625rem" }}>
            Operational actions are priority-ordered. Disruptive commands modifying network routing or queue buffers require deliberate human operator authorization prior to reveal.
          </p>
        </div>

        {/* Sequential Runbook List */}
        <div style={{ display: "flex", flexDirection: "column", gap: "4rem" }}>
          {actions.map((act, idx) => {
            const isAuthorized = !!authorizedActions[act.priority];
            const currentTab = activeTab[idx] || "command";
            const isDisruptive = act.requires_human_approval;

            return (
              <div
                key={act.priority}
                data-spot
                style={{
                  borderTop: isDisruptive ? "var(--solid-ink)" : "var(--hairline-ink)",
                  paddingTop: "2.5rem",
                }}
              >
                {/* Meta Row */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    marginBottom: "1rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "baseline", gap: "1.5rem" }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.875rem", fontWeight: 500 }}>
                      P0{act.priority}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.5 }}>
                      [{act.category}]
                    </span>
                    {act.target_device && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.75 }}>
                        TARGET: {act.target_device}
                      </span>
                    )}
                  </div>

                  <div>
                    {isDisruptive ? (
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.75rem",
                          fontWeight: 500,
                          borderBottom: "1px solid var(--ink)",
                          paddingBottom: "1px",
                        }}
                      >
                        Human operator authorization required
                      </span>
                    ) : (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.5 }}>
                        Safe, read-only
                      </span>
                    )}
                  </div>
                </div>

                {/* Action Title and Description */}
                <h2 className="serif-subhead" style={{ fontSize: "1.75rem", marginBottom: "0.75rem" }}>
                  {act.title}
                </h2>
                <p style={{ fontSize: "1rem", opacity: 0.8, maxWidth: "68ch", lineHeight: 1.6, marginBottom: "2rem" }}>
                  {act.description}
                </p>

                {/* Disruptive Authorization Lock Control */}
                {isDisruptive && !isAuthorized && (
                  <div
                    style={{
                      border: "var(--hairline-ink)",
                      padding: "1.5rem",
                      marginBottom: "1.5rem",
                      backgroundColor: "var(--ink-08)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <div>
                      <p style={{ fontSize: "0.875rem", fontWeight: 500 }}>
                        Authorization Lock Active
                      </p>
                      <p style={{ fontSize: "0.75rem", opacity: 0.65 }}>
                        This command modifies device running state or egress QoS. Operator verification is mandatory.
                      </p>
                    </div>

                    <button
                      onClick={() => handleAuthorize(act.priority)}
                      style={{
                        padding: "0.5rem 1.25rem",
                        backgroundColor: "var(--ink)",
                        color: "var(--ivory)",
                        border: "none",
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.75rem",
                        cursor: "pointer",
                      }}
                    >
                      Authorize Execution
                    </button>
                  </div>
                )}

                {/* Command / Verification / Rollback Deck */}
                <div
                  style={{
                    backgroundColor: "var(--ink)",
                    color: "var(--ivory)",
                    padding: "1.75rem",
                    filter: isDisruptive && !isAuthorized ? "blur(4px)" : "none",
                    pointerEvents: isDisruptive && !isAuthorized ? "none" : "auto",
                    transition: "filter 0.3s ease",
                  }}
                >
                  {/* Tabs */}
                  <div
                    style={{
                      display: "flex",
                      gap: "2rem",
                      borderBottom: "var(--hairline-ivory)",
                      paddingBottom: "0.75rem",
                      marginBottom: "1.25rem",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.75rem",
                    }}
                  >
                    <span
                      onClick={() => setActiveTab({ ...activeTab, [idx]: "command" })}
                      style={{
                        cursor: "pointer",
                        opacity: currentTab === "command" ? 1 : 0.4,
                        borderBottom: currentTab === "command" ? "1px solid var(--teal)" : "none",
                        paddingBottom: "4px",
                      }}
                    >
                      Automation Command
                    </span>
                    <span
                      onClick={() => setActiveTab({ ...activeTab, [idx]: "verification" })}
                      style={{
                        cursor: "pointer",
                        opacity: currentTab === "verification" ? 1 : 0.4,
                        borderBottom: currentTab === "verification" ? "1px solid var(--teal)" : "none",
                        paddingBottom: "4px",
                      }}
                    >
                      Verification Step
                    </span>
                    <span
                      onClick={() => setActiveTab({ ...activeTab, [idx]: "rollback" })}
                      style={{
                        cursor: "pointer",
                        opacity: currentTab === "rollback" ? 1 : 0.4,
                        borderBottom: currentTab === "rollback" ? "1px solid var(--teal)" : "none",
                        paddingBottom: "4px",
                      }}
                    >
                      Rollback Procedure
                    </span>
                  </div>

                  {/* Content View */}
                  {currentTab === "command" && (
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <code style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", color: "var(--ivory-90)" }}>
                        {act.automation_command || "No automation CLI script provided for this item."}
                      </code>
                      {act.automation_command && (
                        <button
                          onClick={() => handleCopy(act.automation_command!, idx)}
                          style={{
                            background: "none",
                            border: "var(--hairline-ivory)",
                            color: "var(--ivory)",
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.6875rem",
                            padding: "0.35rem 0.75rem",
                            cursor: "pointer",
                            marginLeft: "1.5rem",
                          }}
                        >
                          {copiedIndex === idx ? "Copied" : "Copy"}
                        </button>
                      )}
                    </div>
                  )}

                  {currentTab === "verification" && (
                    <p style={{ fontFamily: "var(--font-sans)", fontSize: "0.875rem", opacity: 0.9, lineHeight: 1.5 }}>
                      {act.verification_step}
                    </p>
                  )}

                  {currentTab === "rollback" && (
                    <div>
                      <code style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", color: "var(--ivory-90)" }}>
                        {act.rollback_procedure || "Standard rollback: Re-enable previous device configuration state."}
                      </code>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </PageTransition>
  );
};
