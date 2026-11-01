import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { PageTransition } from "../components/PageTransition";
import {
  RouterIllustration,
  CableIllustration,
  AntennaIllustration,
  CompassIllustration,
  LighthouseIllustration,
  MagnifierIllustration,
} from "../components/Illustrations";
import { apiService } from "../services/api";
import type { ScenarioDefinition, TelemetryRecord } from "../types/telemetry";

export const Ingest: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [scenarios, setScenarios] = useState<ScenarioDefinition[]>([]);
  const [hoveredScenario, setHoveredScenario] = useState<string | null>("congestion");
  const [dragActive, setDragActive] = useState(false);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [uploadedRecords, setUploadedRecords] = useState<TelemetryRecord[] | null>(null);
  const [csvStats, setCsvStats] = useState<{
    total: number;
    devices: string[];
    warnings: string[];
    quarantined: number;
    fileType: string;
  } | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    apiService.getScenarios().then((res) => setScenarios(res.scenarios));
  }, []);

  const handleSelectScenario = async (scenarioId: string) => {
    setIsProcessing(true);
    try {
      const dataRes = await apiService.getScenarioData(scenarioId);
      const diagRes = await apiService.runDiagnosis(dataRes.records, scenarioId);
      localStorage.setItem("netcoop_latest_report", JSON.stringify(diagRes.report));
      navigate("/diagnosis");
    } catch (err) {
      console.error(err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDownloadCsv = (scenarioId: string) => {
    window.open(`http://127.0.0.1:8000/api/scenarios/${scenarioId}/csv`, "_blank");
  };

  // Header alias normalization table
  const HEADER_ALIASES: Record<string, string> = {
    cpu_utilization_pct: "cpu_util_pct",
    cpu_utilization: "cpu_util_pct",
    cpu_percent: "cpu_util_pct",
    link_utilization_pct: "bandwidth_util_pct",
    link_utilization: "bandwidth_util_pct",
    link_util_pct: "bandwidth_util_pct",
    bw_util: "bandwidth_util_pct",
    latency: "latency_ms",
    jitter: "jitter_ms",
    loss: "packet_loss_pct",
    packet_loss: "packet_loss_pct",
    device: "device_id",
    host: "device_id",
    hostname: "device_id",
    node: "device_id",
  };

  const processFile = (file: File) => {
    setSelectedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (file.name.toLowerCase().endsWith(".json")) {
        parseJson(text);
      } else {
        parseCsv(text);
      }
    };
    reader.readAsText(file);
  };

  const parseJson = (jsonText: string) => {
    try {
      const parsed = JSON.parse(jsonText);
      const items: any[] = Array.isArray(parsed)
        ? parsed
        : Array.isArray(parsed.records)
        ? parsed.records
        : Array.isArray(parsed.telemetry)
        ? parsed.telemetry
        : [parsed];

      const records: TelemetryRecord[] = [];
      const devices = new Set<string>();
      const warnings: string[] = [];
      let quarantined = 0;

      items.forEach((item, idx) => {
        if (!item || typeof item !== "object") {
          quarantined++;
          return;
        }
        if (!item.device_id && !item.device && !item.host) {
          quarantined++;
          warnings.push(`Record ${idx + 1}: Missing mandatory device_id; record quarantined.`);
          return;
        }
        const devId = String(item.device_id || item.device || item.host);
        devices.add(devId);
        records.push(item);
      });

      setUploadedRecords(records);
      setCsvStats({
        total: records.length,
        devices: Array.from(devices),
        warnings: warnings.slice(0, 4),
        quarantined,
        fileType: "JSON Batch",
      });
    } catch (err: any) {
      setCsvStats({
        total: 0,
        devices: [],
        warnings: [`Invalid JSON formatting: ${err.message}`],
        quarantined: 0,
        fileType: "Corrupt JSON",
      });
    }
  };

  const parseCsv = (csvText: string) => {
    const lines = csvText.trim().split("\n");
    if (lines.length < 2) {
      setCsvStats({
        total: 0,
        devices: [],
        warnings: ["Uploaded CSV contains no record rows."],
        quarantined: 0,
        fileType: "Empty CSV",
      });
      return;
    }

    const rawHeaders = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
    const normalizedHeaders = rawHeaders.map((h) => {
      const lower = h.toLowerCase().replace(/\s+/g, "_");
      return HEADER_ALIASES[lower] || lower;
    });

    const records: TelemetryRecord[] = [];
    const devices = new Set<string>();
    const warnings: string[] = [];
    let quarantined = 0;

    for (let i = 1; i < lines.length; i++) {
      const lineStr = lines[i].trim();
      if (!lineStr) continue;

      const values = lineStr.split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
      if (values.length !== normalizedHeaders.length) continue;

      const record: any = {};
      normalizedHeaders.forEach((h, idx) => {
        const val = values[idx];
        if (val === "" || val === "nan" || val === "null" || val === "None") {
          record[h] = null;
        } else {
          const num = parseFloat(val);
          record[h] = isNaN(num) ? val : num;
        }
      });

      if (!record.device_id) {
        quarantined++;
        warnings.push(`Row ${i}: Missing device_id, record quarantined.`);
        continue;
      }

      // Check bounds
      if (typeof record.packet_loss_pct === "number" && (record.packet_loss_pct < 0 || record.packet_loss_pct > 100)) {
        quarantined++;
        warnings.push(`Row ${i}: packet_loss_pct out of bounds [0, 100], quarantined.`);
        continue;
      }

      devices.add(String(record.device_id));
      records.push(record);
    }

    setUploadedRecords(records);
    setCsvStats({
      total: records.length,
      devices: Array.from(devices),
      warnings: warnings.slice(0, 4),
      quarantined,
      fileType: "CSV Telemetry",
    });
  };

  // Drag and drop handlers
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleDiagnoseUploaded = async () => {
    if (!uploadedRecords || uploadedRecords.length === 0) return;
    setIsProcessing(true);
    try {
      const diagRes = await apiService.runDiagnosis(uploadedRecords, selectedFileName || "uploaded_custom_telemetry");
      localStorage.setItem("netcoop_latest_report", JSON.stringify(diagRes.report));
      navigate("/diagnosis");
    } catch (err: any) {
      console.error("Diagnosis error:", err);
      alert(`Diagnosis failed: ${err.message || err}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const renderIllustration = (id: string | null) => {
    switch (id) {
      case "congestion":
      case "organizer_mock":
        return <RouterIllustration size={160} color="var(--ink)" />;
      case "weak_wifi":
        return <AntennaIllustration size={160} color="var(--ink)" />;
      case "interface_failure":
        return <CableIllustration size={160} color="var(--ink)" />;
      case "dns_failure":
      case "dhcp_failure":
        return <CompassIllustration size={160} color="var(--ink)" />;
      case "infrastructure_overload":
        return <MagnifierIllustration size={160} color="var(--ink)" />;
      default:
        return <LighthouseIllustration size={160} color="var(--ink)" />;
    }
  };

  return (
    <PageTransition theme="ivory">
      <div style={{ padding: "clamp(3rem, 6vw, 6rem) var(--margin-gutter)" }}>
        {/* Hidden Native File Input */}
        <input
          type="file"
          ref={fileInputRef}
          accept=".csv,.json,text/csv,application/json"
          onChange={handleFileInputChange}
          style={{ display: "none" }}
        />

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
            INGESTION STUDIO
          </p>
          <h1
            className="serif-headline"
            style={{
              fontSize: "clamp(2.4rem, 4.5vw, 4.2rem)",
              marginBottom: "1rem",
            }}
          >
            Telemetry Ingest & Scenario Index
          </h1>
          <p style={{ opacity: 0.7, maxWidth: "56ch", fontSize: "1.0625rem" }}>
            Upload any operational network telemetry dataset (CSV or JSON) or select a pre-configured benchmark scenario for automated multi-agent causal inference.
          </p>
        </div>

        {/* Section 1: CSV / JSON Ruled Drop Zone with Click-to-Browse */}
        <div style={{ marginBottom: "5rem" }}>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            data-spot
            style={{
              minHeight: "240px",
              border: dragActive ? "1.5px solid var(--teal)" : "var(--hairline-ink)",
              padding: "3rem",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "flex-start",
              transition: "all 0.3s ease",
              position: "relative",
              cursor: "pointer",
              backgroundColor: dragActive ? "color-mix(in srgb, var(--teal) 6%, transparent)" : "transparent",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.5 }}>
                TELEMETRY INGESTION PORT &middot; CSV / JSON
              </p>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.75rem",
                  padding: "0.45rem 1rem",
                  backgroundColor: "var(--ink)",
                  color: "var(--ivory)",
                  border: "none",
                  cursor: "pointer",
                  letterSpacing: "0.04em",
                }}
              >
                Browse Files
              </button>
            </div>

            <p className="serif-subhead" style={{ fontSize: "1.6rem", marginTop: "1rem" }}>
              {selectedFileName ? (
                <span>
                  Active File: <strong style={{ color: "var(--teal)" }}>{selectedFileName}</strong>
                </span>
              ) : (
                "Click to browse or drop an operational CSV or JSON telemetry file here"
              )}
            </p>

            <p style={{ fontSize: "0.875rem", opacity: 0.6, marginTop: "0.35rem", maxWidth: "68ch" }}>
              Accepts RFC-4180 CSV exports or JSON arrays containing device telemetry metrics (e.g. latency, jitter, loss, CPU, link utilization, queue drops). Auto-maps custom header aliases.
            </p>

            {csvStats && (
              <div
                onClick={(e) => e.stopPropagation()}
                style={{
                  marginTop: "2.5rem",
                  paddingTop: "1.75rem",
                  borderTop: "var(--hairline-ink)",
                  width: "100%",
                  display: "grid",
                  gridTemplateColumns: "repeat(5, 1fr)",
                  gap: "1.5rem",
                  alignItems: "center",
                }}
              >
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>FORMAT</p>
                  <p className="serif-subhead" style={{ fontSize: "1.2rem" }}>{csvStats.fileType}</p>
                </div>
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>PARSED RECORDS</p>
                  <p className="serif-subhead" style={{ fontSize: "1.2rem" }}>{csvStats.total} Rows</p>
                </div>
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>DEVICE DOMAIN</p>
                  <p className="serif-subhead" style={{ fontSize: "1.2rem" }}>{csvStats.devices.length} Devices</p>
                </div>
                <div>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>QUARANTINED</p>
                  <p className="serif-subhead" style={{ fontSize: "1.2rem" }}>{csvStats.quarantined} Records</p>
                </div>
                <div>
                  <button
                    onClick={handleDiagnoseUploaded}
                    disabled={isProcessing || csvStats.total === 0}
                    style={{
                      padding: "0.75rem 1.25rem",
                      backgroundColor: "var(--ink)",
                      color: "var(--ivory)",
                      border: "none",
                      fontFamily: "var(--font-sans)",
                      fontSize: "0.8125rem",
                      cursor: csvStats.total > 0 ? "pointer" : "not-allowed",
                      width: "100%",
                      textAlign: "center",
                      opacity: csvStats.total > 0 ? 1 : 0.5,
                    }}
                  >
                    {isProcessing ? "Diagnosing..." : "Run Multi-Agent Diagnosis"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Section 2: Scenario Catalog as Typographic Table of Contents */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 220px", gap: "4rem" }}>
          <div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "60px 1fr 240px",
                paddingBottom: "1rem",
                borderBottom: "var(--solid-ink)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6875rem",
                letterSpacing: "0.08em",
                opacity: 0.5,
              }}
            >
              <span>INDEX</span>
              <span>SCENARIO & DIAGNOSTIC OBJECTIVE</span>
              <span style={{ textAlign: "right" }}>ACTIONS</span>
            </div>

            {scenarios.map((sc, idx) => (
              <div
                key={sc.id}
                onMouseEnter={() => setHoveredScenario(sc.id)}
                className="hover-row"
                data-spot
                style={{
                  display: "grid",
                  gridTemplateColumns: "60px 1fr 240px",
                  padding: "1.75rem 0",
                  borderBottom: "var(--hairline-ink)",
                  alignItems: "baseline",
                }}
              >
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", opacity: 0.4 }}>
                  {idx < 9 ? `0${idx + 1}` : idx + 1}
                </span>

                <div style={{ paddingRight: "2rem" }}>
                  <h3 className="serif-subhead" style={{ fontSize: "1.375rem", fontWeight: 400 }}>
                    {sc.title}
                  </h3>
                  <p style={{ fontSize: "0.875rem", opacity: 0.65, marginTop: "0.35rem", lineHeight: 1.5 }}>
                    {sc.description}
                  </p>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.45, marginTop: "0.25rem" }}>
                    Expected: {sc.expected_root_cause}
                  </p>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "1.5rem" }}>
                  <button
                    onClick={() => handleSelectScenario(sc.id)}
                    className="editorial-link"
                    style={{
                      background: "none",
                      border: "none",
                      padding: 0,
                      fontFamily: "var(--font-sans)",
                      fontSize: "0.8125rem",
                      fontWeight: 500,
                      color: "var(--ink)",
                      cursor: "pointer",
                    }}
                  >
                    Load & analyse
                  </button>
                  <button
                    onClick={() => handleDownloadCsv(sc.id)}
                    className="editorial-link"
                    style={{
                      background: "none",
                      border: "none",
                      padding: 0,
                      fontFamily: "var(--font-sans)",
                      fontSize: "0.8125rem",
                      color: "var(--ink)",
                      opacity: 0.7,
                      cursor: "pointer",
                    }}
                  >
                    Download CSV
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Marginal Illustration that updates on row hover */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: "3rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.4, marginBottom: "1.5rem" }}>
              ARCHITECTURAL ENGRAVING
            </p>
            {renderIllustration(hoveredScenario)}
          </div>
        </div>
      </div>
    </PageTransition>
  );
};
