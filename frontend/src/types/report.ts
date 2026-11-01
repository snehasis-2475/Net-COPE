export type NetworkHealthStatus = "NOMINAL" | "DEGRADED" | "CRITICAL" | "UNKNOWN";
export type DiagnosisCertainty = "CONFIRMED" | "PROVISIONAL" | "INDETERMINATE";
export type ActionCategory = "INVESTIGATION" | "MITIGATION" | "CONFIGURATION" | "RECOVERY" | "VERIFICATION";
export type AgentStatusType = "SUCCESS" | "PARTIAL_SUCCESS" | "ERROR" | "TIMEOUT" | "REJECTED";

export interface EvidenceItem {
  metric_name: string;
  observed_value: any;
  threshold?: number | string | null;
  unit?: string | null;
  device_id?: string | null;
  timestamp?: string | null;
  interpretation?: string | null;
}

export interface Finding {
  finding_id?: string;
  source_agent?: string;
  category: string;
  title: string;
  description: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  affected_devices: string[];
  metrics?: Record<string, any>;
  metric_name?: string;
  observed_value?: any;
  threshold?: any;
  unit?: string;
  finding_type?: string;
  timestamp?: string;
}

export interface RootCauseCandidate {
  title: string;
  description: string;
  confidence: number;
  supporting_symptoms: string[];
  contradicting_symptoms: string[];
  affected_devices: string[];
  evidence_references: string[];
  mitigation_category?: string;
}

export interface CorrectiveAction {
  priority: number;
  title: string;
  category: ActionCategory | string;
  description: string;
  target_device?: string | null;
  verification_step: string;
  automation_command?: string | null;
  rollback_procedure?: string | null;
  requires_human_approval: boolean;
}

export interface AgentExecutionSummary {
  status: AgentStatusType | string;
  duration_ms: number;
  finding_count: number;
  evidence_count: number;
  error_count: number;
  errors: string[];
}

export interface ReportLimitations {
  missing_telemetry: string[];
  invalid_records: string[];
  insufficient_evidence: boolean;
  notes: string[];
}

export interface AgentMessage {
  message_id: string;
  task_id: string;
  agent_id: string;
  timestamp: string;
  status: AgentStatusType | string;
  findings: Finding[];
  evidence: EvidenceItem[];
  confidence: number;
  errors: string[];
  metadata: Record<string, any>;
}

export interface DiagnosticReport {
  report_id: string;
  diagnosis_id: string;
  task_id: string;
  timestamp: string;
  execution_timestamp?: string;
  schema_version: string;
  report_version?: string;
  execution_duration_ms: number;
  overall_network_health: NetworkHealthStatus;
  fault_detected: boolean;
  diagnosis_certainty: DiagnosisCertainty;
  confidence_score: number;
  confidence_interpretation?: string;
  probable_root_cause: RootCauseCandidate;
  alternative_causes: RootCauseCandidate[];
  affected_devices: string[];
  supporting_evidence?: EvidenceItem[];
  individual_agent_findings: Record<string, Finding[]>;
  recommended_corrective_actions: CorrectiveAction[];
  successful_agents: string[];
  failed_agents: string[];
  timed_out_agents: string[];
  agent_execution_summary: Record<string, AgentExecutionSummary>;
  validated_findings: Finding[];
  rejected_messages: any[];
  conflicting_evidence: string[];
  uncertainty_notes: string[];
  warnings: string[];
  errors?: string[];
  limitations: ReportLimitations;
  summary?: string;
}
