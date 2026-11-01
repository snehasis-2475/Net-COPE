import React, { useState, useEffect } from "react";
import { PageTransition } from "../components/PageTransition";
import type { DiagnosticReport } from "../types/report";
import { apiService } from "../services/api";
import { MOCK_REPORT_CONGESTION, MOCK_REPORT_NORMAL } from "../services/mockData";

export const Vault: React.FC = () => {
  const [reports, setReports] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [certaintyFilter, setCertaintyFilter] = useState<string>("ALL");
  const [directFetchId, setDirectFetchId] = useState("");
  const [fetchedReport, setFetchedReport] = useState<DiagnosticReport | null>(null);
  const [compareReportA] = useState<DiagnosticReport>(MOCK_REPORT_CONGESTION);
  const [compareReportB] = useState<DiagnosticReport>(MOCK_REPORT_NORMAL);
  const [showComparison, setShowComparison] = useState(false);

  useEffect(() => {
    apiService.getReports(50, 0).then((res) => {
      setReports(res.reports);
    });
  }, []);

  const handleDirectFetch = async () => {
    if (!directFetchId.trim()) return;
    const res = await apiService.getReportById(directFetchId.trim());
    if (res.report) {
      setFetchedReport(res.report);
    }
  };

  const handleExportJson = (rep: DiagnosticReport) => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(rep, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `${rep.report_id}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const filteredReports = reports.filter((r) => {
    const matchesSearch =
      !searchQuery ||
      r.report_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.diagnosis_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.overall_network_health.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesCertainty =
      certaintyFilter === "ALL" || r.diagnosis_certainty === certaintyFilter;

    return matchesSearch && matchesCertainty;
  });

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
            ARCHIVE & AUDIT TRAIL
          </p>
          <h1
            className="serif-headline"
            style={{
              fontSize: "clamp(2.4rem, 4.5vw, 4.2rem)",
              marginBottom: "1rem",
            }}
          >
            The Diagnostic Ledger
          </h1>
          <p style={{ opacity: 0.7, maxWidth: "56ch", fontSize: "1.0625rem" }}>
            Permanent audit record of generated investigative reports conforming to Schema 2.0.0. Inspect previous incident findings, fetch direct report hashes, or run comparative delta audits.
          </p>
        </div>

        {/* Filter and Search Bar */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 200px 320px",
            gap: "2rem",
            borderBottom: "var(--solid-ink)",
            paddingBottom: "1.5rem",
            marginBottom: "2rem",
            alignItems: "flex-end",
          }}
        >
          <div>
            <label style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5, display: "block", marginBottom: "0.5rem" }}>
              SEARCH BY IDENTIFIER OR HEALTH
            </label>
            <input
              type="text"
              placeholder="e.g. REP-B849A1C3 or DEGRADED"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem 0",
                border: "none",
                borderBottom: "var(--hairline-ink)",
                backgroundColor: "transparent",
                color: "var(--ink)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.875rem",
                outline: "none",
              }}
            />
          </div>

          <div>
            <label style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5, display: "block", marginBottom: "0.5rem" }}>
              CERTAINTY TIER
            </label>
            <select
              value={certaintyFilter}
              onChange={(e) => setCertaintyFilter(e.target.value)}
              style={{
                width: "100%",
                padding: "0.5rem 0",
                border: "none",
                borderBottom: "var(--hairline-ink)",
                backgroundColor: "transparent",
                color: "var(--ink)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.8125rem",
                outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="ALL">All Certainty Tiers</option>
              <option value="CONFIRMED">CONFIRMED</option>
              <option value="PROVISIONAL">PROVISIONAL</option>
              <option value="INDETERMINATE">INDETERMINATE</option>
            </select>
          </div>

          <div>
            <label style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5, display: "block", marginBottom: "0.5rem" }}>
              DIRECT IDENTIFIER LOOKUP
            </label>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input
                type="text"
                placeholder="REP-..."
                value={directFetchId}
                onChange={(e) => setDirectFetchId(e.target.value)}
                style={{
                  flex: 1,
                  padding: "0.4rem 0.6rem",
                  border: "var(--hairline-ink)",
                  backgroundColor: "transparent",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.75rem",
                  outline: "none",
                }}
              />
              <button
                onClick={handleDirectFetch}
                style={{
                  padding: "0.4rem 0.8rem",
                  backgroundColor: "var(--ink)",
                  color: "var(--ivory)",
                  border: "none",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6875rem",
                  cursor: "pointer",
                }}
              >
                Fetch
              </button>
            </div>
          </div>
        </div>

        {/* Direct Fetched Report Highlight */}
        {fetchedReport && (
          <div
            style={{
              padding: "2rem",
              border: "1.5px solid var(--teal)",
              marginBottom: "3rem",
              backgroundColor: "color-mix(in srgb, var(--teal) 4%, transparent)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: "var(--teal)" }}>
                DIRECT FETCH RESULT: {fetchedReport.report_id}
              </span>
              <button
                onClick={() => setFetchedReport(null)}
                style={{ background: "none", border: "none", cursor: "pointer", fontFamily: "var(--font-mono)" }}
              >
                [Dismiss]
              </button>
            </div>
            <h2 className="serif-subhead" style={{ fontSize: "1.5rem" }}>
              {fetchedReport.probable_root_cause.title}
            </h2>
            <p style={{ fontSize: "0.875rem", opacity: 0.75, marginTop: "0.5rem" }}>
              {fetchedReport.probable_root_cause.description}
            </p>
            <div style={{ marginTop: "1rem" }}>
              <button
                onClick={() => handleExportJson(fetchedReport)}
                className="editorial-link"
                style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)", border: "none", background: "none" }}
              >
                Export raw report JSON
              </button>
            </div>
          </div>
        )}

        {/* Ledger Table */}
        <div style={{ marginBottom: "5rem" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "160px 160px 180px 140px 140px 120px 1fr",
              paddingBottom: "1rem",
              borderBottom: "var(--solid-ink)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.6875rem",
              opacity: 0.5,
              letterSpacing: "0.08em",
            }}
          >
            <span>REPORT ID</span>
            <span>DIAGNOSIS ID</span>
            <span>TIMESTAMP (UTC)</span>
            <span>HEALTH</span>
            <span>CERTAINTY</span>
            <span>CONFIDENCE</span>
            <span style={{ textAlign: "right" }}>ACTIONS</span>
          </div>

          {filteredReports.map((r) => (
            <div
              key={r.report_id}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 160px 180px 140px 140px 120px 1fr",
                padding: "1.25rem 0",
                borderBottom: "var(--hairline-ink)",
                alignItems: "center",
                fontFamily: "var(--font-mono)",
                fontSize: "0.8125rem",
              }}
            >
              <span>{r.report_id}</span>
              <span style={{ opacity: 0.7 }}>{r.diagnosis_id}</span>
              <span style={{ opacity: 0.6 }}>{r.timestamp.substring(0, 19).replace("T", " ")}</span>
              <span style={{ fontWeight: 500 }}>{r.overall_network_health}</span>
              <span style={{ opacity: 0.8 }}>{r.diagnosis_certainty}</span>
              <span>
                {r.overall_network_health === "NOMINAL" ? "N/A" : `${Math.round(r.confidence_score * 100)}%`}
              </span>
              <div style={{ textAlign: "right" }}>
                <button
                  onClick={() => {
                    localStorage.setItem("netcoop_latest_report", JSON.stringify(MOCK_REPORT_CONGESTION));
                    window.location.href = "/diagnosis";
                  }}
                  className="editorial-link"
                  style={{
                    background: "none",
                    border: "none",
                    fontFamily: "var(--font-sans)",
                    fontSize: "0.8125rem",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  Inspect in story
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Side-by-Side Comparative Audit Tool */}
        <div style={{ borderTop: "var(--solid-ink)", paddingTop: "4rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "2rem" }}>
            <div>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.5 }}>
                DELTA RAIL AUDITOR
              </p>
              <h2 className="serif-headline" style={{ fontSize: "2rem" }}>
                Side-by-Side Incident Comparison
              </h2>
            </div>
            <button
              onClick={() => setShowComparison(!showComparison)}
              className="editorial-link"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.8125rem",
                background: "none",
                border: "none",
                cursor: "pointer",
              }}
            >
              {showComparison ? "Collapse comparison view [−]" : "Expand comparative audit view [+]"}
            </button>
          </div>

          {showComparison && (
            <div
              data-spot
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 140px 1fr",
                gap: "2.5rem",
                border: "var(--hairline-ink)",
                padding: "2.5rem",
              }}
            >
              {/* Column A */}
              <div>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
                  REPORT A (PRE-REMEDIATION)
                </p>
                <p className="serif-subhead" style={{ fontSize: "1.25rem", marginTop: "0.25rem" }}>
                  {compareReportA.report_id}
                </p>
                <p style={{ fontSize: "1rem", fontWeight: 500, marginTop: "0.75rem" }}>
                  {compareReportA.probable_root_cause.title}
                </p>
                <p style={{ fontSize: "0.875rem", opacity: 0.75, marginTop: "0.35rem", lineHeight: 1.5 }}>
                  {compareReportA.probable_root_cause.description}
                </p>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", marginTop: "1rem" }}>
                  Health: {compareReportA.overall_network_health} • Confidence: {Math.round(compareReportA.confidence_score * 100)}%
                </p>
                <button
                  onClick={() => handleExportJson(compareReportA)}
                  style={{
                    marginTop: "1.5rem",
                    padding: "0.4rem 0.8rem",
                    border: "var(--hairline-ink)",
                    background: "none",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6875rem",
                    cursor: "pointer",
                  }}
                >
                  Download JSON A
                </button>
              </div>

              {/* Central Delta Rail */}
              <div
                style={{
                  borderLeft: "var(--hairline-ink)",
                  borderRight: "var(--hairline-ink)",
                  padding: "0 1rem",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  alignItems: "center",
                  textAlign: "center",
                  gap: "1.5rem",
                }}
              >
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.625rem", opacity: 0.4 }}>HEALTH SHIFT</p>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", fontWeight: 500, color: "var(--teal)" }}>
                    RECOVERED
                  </p>
                </div>
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.625rem", opacity: 0.4 }}>CONFIDENCE DELTA</p>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>
                    -94% (Fault Cleared)
                  </p>
                </div>
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.625rem", opacity: 0.4 }}>RESOLVED NODES</p>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>
                    3 Devices OK
                  </p>
                </div>
              </div>

              {/* Column B */}
              <div>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
                  REPORT B (POST-REMEDIATION)
                </p>
                <p className="serif-subhead" style={{ fontSize: "1.25rem", marginTop: "0.25rem" }}>
                  {compareReportB.report_id}
                </p>
                <p style={{ fontSize: "1rem", fontWeight: 500, marginTop: "0.75rem" }}>
                  {compareReportB.probable_root_cause.title}
                </p>
                <p style={{ fontSize: "0.875rem", opacity: 0.75, marginTop: "0.35rem", lineHeight: 1.5 }}>
                  {compareReportB.probable_root_cause.description}
                </p>
                <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", marginTop: "1rem" }}>
                  Health: {compareReportB.overall_network_health} • Confidence: N/A (Zero-Fault Rule)
                </p>
                <button
                  onClick={() => handleExportJson(compareReportB)}
                  style={{
                    marginTop: "1.5rem",
                    padding: "0.4rem 0.8rem",
                    border: "var(--hairline-ink)",
                    background: "none",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6875rem",
                    cursor: "pointer",
                  }}
                >
                  Download JSON B
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  );
};
