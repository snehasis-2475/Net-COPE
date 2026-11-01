export type DeviceType = "router" | "switch" | "ap" | "gateway" | "endpoint" | "server" | "generic";

export interface TelemetryRecord {
  device_id: string;
  timestamp?: string;
  device_type?: DeviceType;
  latency_ms?: number | null;
  jitter_ms?: number | null;
  packet_loss_pct?: number | null;
  throughput_mbps?: number | null;
  bandwidth_util_pct?: number | null;
  cpu_util_pct?: number | null;
  memory_util_pct?: number | null;
  device_availability?: number | null;
  device_status?: "active" | "degraded" | "down" | "rebooting" | string;
  interface_name?: string | null;
  interface_flapping_count?: number | null;
  crc_errors?: number | null;
  queue_drops?: number | null;
  dns_status?: "ok" | "slow" | "timeout" | "nxdomain" | "servfail" | string;
  dns_latency_ms?: number | null;
  dhcp_status?: "ok" | "slow" | "timeout" | "exhausted" | string;
  dhcp_lease_time_sec?: number | null;
  wifi_rssi_dbm?: number | null;
  wifi_snr_db?: number | null;
  wifi_retry_rate_pct?: number | null;
  connectivity_status?: "connected" | "degraded" | "disconnected" | string;
  [key: string]: any;
}

export interface ScenarioDefinition {
  id: string;
  title: string;
  description: string;
  category: string;
  expected_root_cause: string;
  records_count?: number;
}
