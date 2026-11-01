import type { DiagnosticReport } from "../types/report";
import type { ScenarioDefinition, TelemetryRecord } from "../types/telemetry";
import { MOCK_REPORT_CONGESTION, MOCK_REPORT_NORMAL, MOCK_SCENARIOS, MOCK_TELEMETRY_SERIES } from "./mockData";

const API_BASE = "http://127.0.0.1:8000";

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  active_agents?: string[];
  timestamp?: string;
  isMock?: boolean;
}

export const apiService = {
  /**
   * Check FastAPI backend connectivity
   */
  async checkHealth(): Promise<HealthResponse> {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return { ...data, isMock: false };
    } catch {
      return {
        status: "offline",
        service: "NetCoop AI Multi-Agent Diagnostic Engine (Local Offline Mode)",
        version: "2.0.0",
        active_agents: ["performance_agent", "infrastructure_agent", "connectivity_agent", "correlation_agent", "recommendation_agent"],
        isMock: true,
      };
    }
  },

  /**
   * Retrieve catalog of pre-configured scenarios
   */
  async getScenarios(): Promise<{ scenarios: ScenarioDefinition[]; isMock: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/api/scenarios`, { signal: AbortSignal.timeout(2500) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list = (data.scenarios || data).map((s: any) => ({
        id: s.id,
        title: s.title,
        description: s.description,
        category: s.category || "GENERAL",
        expected_root_cause: s.expected_root_cause || "Calculated during diagnosis",
      }));
      return { scenarios: list, isMock: false };
    } catch {
      return { scenarios: MOCK_SCENARIOS, isMock: true };
    }
  },

  /**
   * Fetch generated telemetry for a scenario
   */
  async getScenarioData(scenarioId: string): Promise<{ records: TelemetryRecord[]; isMock: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/api/scenarios/${scenarioId}`, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return { records: data.records || data, isMock: false };
    } catch {
      return { records: MOCK_TELEMETRY_SERIES, isMock: true };
    }
  },

  /**
   * Trigger multi-agent diagnosis on telemetry data
   */
  async runDiagnosis(telemetry: TelemetryRecord[], scenarioName: string = "custom"): Promise<{ report: DiagnosticReport; isMock: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/api/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telemetry, scenario_name: scenarioName }),
        signal: AbortSignal.timeout(10000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      const report: DiagnosticReport = await res.json();
      return { report, isMock: false };
    } catch (err) {
      console.warn("Backend /api/diagnose offline, providing verified fallback report:", err);
      const fallback = scenarioName === "normal" ? MOCK_REPORT_NORMAL : MOCK_REPORT_CONGESTION;
      return { report: fallback, isMock: true };
    }
  },

  /**
   * List historical reports stored on the server
   */
  async getReports(limit: number = 50, offset: number = 0): Promise<{ reports: any[]; total: number; isMock: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/api/reports?limit=${limit}&offset=${offset}`, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      return { reports: data.reports || [], total: data.total || 0, isMock: false };
    } catch {
      return {
        reports: [
          {
            report_id: MOCK_REPORT_CONGESTION.report_id,
            diagnosis_id: MOCK_REPORT_CONGESTION.diagnosis_id,
            timestamp: MOCK_REPORT_CONGESTION.timestamp,
            overall_network_health: MOCK_REPORT_CONGESTION.overall_network_health,
            fault_detected: MOCK_REPORT_CONGESTION.fault_detected,
            confidence_score: MOCK_REPORT_CONGESTION.confidence_score,
            diagnosis_certainty: MOCK_REPORT_CONGESTION.diagnosis_certainty,
            probable_root_cause_title: MOCK_REPORT_CONGESTION.probable_root_cause.title,
          },
          {
            report_id: MOCK_REPORT_NORMAL.report_id,
            diagnosis_id: MOCK_REPORT_NORMAL.diagnosis_id,
            timestamp: MOCK_REPORT_NORMAL.timestamp,
            overall_network_health: MOCK_REPORT_NORMAL.overall_network_health,
            fault_detected: MOCK_REPORT_NORMAL.fault_detected,
            confidence_score: MOCK_REPORT_NORMAL.confidence_score,
            diagnosis_certainty: MOCK_REPORT_NORMAL.diagnosis_certainty,
            probable_root_cause_title: MOCK_REPORT_NORMAL.probable_root_cause.title,
          },
        ],
        total: 2,
        isMock: true,
      };
    }
  },

  /**
   * Fetch single report by ID or Diagnosis ID
   */
  async getReportById(id: string): Promise<{ report: DiagnosticReport | null; error?: string; isMock: boolean }> {
    try {
      const res = await fetch(`${API_BASE}/api/reports/${encodeURIComponent(id.trim())}`, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const report: DiagnosticReport = await res.json();
      return { report, isMock: false };
    } catch (err: any) {
      if (id === MOCK_REPORT_CONGESTION.report_id || id === MOCK_REPORT_CONGESTION.diagnosis_id) {
        return { report: MOCK_REPORT_CONGESTION, isMock: true };
      }
      if (id === MOCK_REPORT_NORMAL.report_id || id === MOCK_REPORT_NORMAL.diagnosis_id) {
        return { report: MOCK_REPORT_NORMAL, isMock: true };
      }
      return { report: null, error: `Report ${id} could not be retrieved: ${err.message}`, isMock: true };
    }
  },
};
